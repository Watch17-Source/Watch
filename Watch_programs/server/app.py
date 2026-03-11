from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
)

import config
from db import init_db, close_db
from security import hash_password, verify_password, new_csrf_token
import store
from utils import require_hhmm, local_hhmm_now, unix_time


def create_app() -> Flask:
    init_db()

    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    # Cookie hardening
    app.config.update(
        SESSION_COOKIE_HTTPONLY=config.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=config.SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
    )

    # Close DB
    app.teardown_appcontext(close_db)

    # ---- Auth helpers ----

    # Compute admin hash once
    if config.ADMIN_PASSWORD_HASH:
        admin_hash = config.ADMIN_PASSWORD_HASH
    else:
        admin_hash = hash_password(config.ADMIN_PASSWORD).to_string()

    def is_logged_in() -> bool:
        return bool(session.get("logged_in"))

    def login_required(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not is_logged_in():
                return redirect(url_for("login", next=request.path))
            return fn(*args, **kwargs)
        return wrapper

    def csrf_token() -> str:
        tok = session.get("csrf_token")
        if not tok:
            tok = new_csrf_token()
            session["csrf_token"] = tok
        return tok

    @app.before_request
    def csrf_protect():
        # Only protect browser form posts (not device API)
        if request.method in ("POST", "PUT", "DELETE") and not request.path.startswith("/api/v1/device/"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not sent or sent != session.get("csrf_token"):
                abort(400, description="CSRF token missing/invalid")

    @app.context_processor
    def inject_globals():
        return dict(
            csrf_token=csrf_token,
            config=config,
            audio_prompt=bool(session.pop("audio_prompt", False)),
            palette={
                "orange": "#EE6C29",
                "jet": "#282B2B",
                "moonstone": "#7AA6B3",
            },
        )

    # ---- Device auth ----

    def require_device_auth(device_id: int) -> dict:
        token = request.headers.get("X-Device-Token", "").strip()
        if not token:
            abort(401, description="Missing device token")
        dev = store.get_device_by_token(device_id, token)
        if not dev:
            abort(403, description="Invalid device token or device id")
        if config.ENFORCE_DEVICE_IP_MATCH:
            ra = request.remote_addr or ""
            if ra != dev["ip"]:
                abort(403, description=f"IP mismatch ({ra} != {dev['ip']})")
        return dev

    # ---- Pages ----

    @app.get("/login")
    def login():
        if is_logged_in():
            return redirect(url_for("home"))
        return render_template("login.html", next=request.args.get("next") or "")

    @app.post("/login")
    def login_post():
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if username == config.ADMIN_USERNAME and verify_password(password, admin_hash):
            session["logged_in"] = True
            session["csrf_token"] = new_csrf_token()
            session["audio_prompt"] = True  # ask browser to enable sound after login
            flash("Logged in.", "ok")
            nxt = request.form.get("next") or url_for("home")
            return redirect(nxt)
        flash("Invalid username or password.", "err")
        return redirect(url_for("login"))

    @app.get("/logout")
    def logout():
        session.clear()
        flash("Logged out.", "ok")
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        if not is_logged_in():
            return redirect(url_for("login"))
        return redirect(url_for("home"))

    @app.get("/home")
    @login_required
    def home():
        return render_template("home.html")

    @app.get("/watch")
    @login_required
    def watch():
        # initial render uses server-side list; JS will poll for updates
        devices = store.list_devices()
        return render_template("watch.html", devices=decorate_devices_for_ui(devices))

    @app.get("/device/<int:device_id>")
    @login_required
    def device_detail(device_id: int):
        dev = store.get_device(device_id)
        if not dev:
            abort(404)
        cases = store.list_cases_for_device(device_id, limit=50)
        return render_template(
            "device_detail.html",
            dev=decorate_device_for_ui(dev),
            cases=cases,
        )

    @app.post("/device/<int:device_id>/update")
    @login_required
    def device_update(device_id: int):
        trigger = require_hhmm(request.form.get("trigger_time", ""))
        kill = require_hhmm(request.form.get("kill_time", ""))
        enabled = (request.form.get("enabled") == "1")
        store.update_device_schedule(device_id, trigger_time=trigger, kill_time=kill, enabled=enabled)
        flash("Device schedule updated.", "ok")
        return redirect(url_for("device_detail", device_id=device_id))


    def ack_device_alarm(device_id: int) -> dict:
        """Acknowledge an alarm for a device.

        - Marks the current case acked (if any)
        - Sets pause_until for UI clarity
        - Enqueues ACK_ALARM command for the device (so it stops alarming)
        - Sets ack_pending=True until the device confirms
        """
        dev = store.get_device(device_id)
        if not dev:
            abort(404)

        # Mark case acked at the time guard clicks OK
        case_id = dev.get("alarm_case_id")
        if case_id:
            store.mark_case_acked(case_id)

        # Set pause_until on server for UI clarity
        pause_until = datetime.now(timezone.utc) + timedelta(seconds=config.DEVICE_PAUSE_AFTER_ACK_S)
        store.set_pause_until(device_id, pause_until.isoformat(timespec="seconds"))

        # Enqueue ACK command for device; device will stop alarm and pause
        store.enqueue_command(device_id, "ACK_ALARM", {"pause_for_s": config.DEVICE_PAUSE_AFTER_ACK_S})
        store.set_ack_pending(device_id, ack_pending=True)

        return {"device_id": device_id, "case_id": case_id}


    @app.post("/device/<int:device_id>/ack")
    @login_required
    def device_ack(device_id: int):
        ack_device_alarm(device_id)

        flash("Acknowledgement sent to device. It should stop alarming and pause for 1 hour.", "ok")
        return redirect(url_for("device_detail", device_id=device_id))

    @app.post("/device/<int:device_id>/delete")
    @login_required
    def device_delete(device_id: int):
        store.delete_device(device_id)
        flash("Device deleted.", "ok")
        return redirect(url_for("watch"))

    @app.get("/cases")
    @login_required
    def cases():
        all_cases = store.list_cases(limit=300)
        return render_template("cases.html", cases=all_cases)

    @app.get("/add-device")
    @login_required
    def add_device():
        return render_template("add_device.html")

    @app.post("/add-device")
    @login_required
    def add_device_post():
        name = (request.form.get("name") or "").strip()
        ip = (request.form.get("ip") or "").strip()
        trigger = request.form.get("trigger_time") or config.DEFAULT_TRIGGER_TIME
        kill = request.form.get("kill_time") or config.DEFAULT_KILL_TIME

        if not name or not ip:
            flash("Name and IP are required.", "err")
            return redirect(url_for("add_device"))

        try:
            trigger = require_hhmm(trigger)
            kill = require_hhmm(kill)
        except Exception as e:
            flash(str(e), "err")
            return redirect(url_for("add_device"))

        try:
            dev = store.create_device(name=name, ip=ip, trigger_time=trigger, kill_time=kill)
        except Exception as e:
            flash(f"Failed to add device: {e}", "err")
            return redirect(url_for("add_device"))

        flash("Device added! Copy the token into the device config.py.", "ok")
        return render_template("add_device_done.html", dev=dev)

    @app.get("/credits")
    @login_required
    def credits():
        return render_template("credits.html")

    # ---- Admin JSON API (for live Watch page) ----

    @app.get("/api/v1/admin/devices")
    @login_required
    def api_admin_devices():
        devices = decorate_devices_for_ui(store.list_devices())
        return jsonify({"devices": devices, "server_hhmm": local_hhmm_now(), "server_epoch": unix_time()})


    @app.get("/api/v1/admin/alerts")
    @login_required
    def api_admin_alerts():
        """Return active alarms for the always-on alert overlay (browser UI)."""
        alarms = store.list_active_alarms()
        out = []
        for a in alarms:
            # Parse case details_json to a dict (if present)
            details = {}
            try:
                details = json.loads(a.get("case_details_json") or "{}")
            except Exception:
                details = {}

            out.append({
                "device_id": int(a["device_id"]),
                "device_name": a.get("device_name"),
                "ip": a.get("ip"),
                "status": "Broke",
                "case_id": int(a["case_id"]) if a.get("case_id") is not None else None,
                "case_started_at": a.get("case_started_at"),
                "ack_pending": bool(int(a.get("ack_pending") or 0)),
                "pause_until": a.get("pause_until"),
                "last_seen": a.get("last_seen"),
                "last_state": a.get("last_state"),
                "details": details,
            })

        return jsonify({"alarms": out, "server_hhmm": local_hhmm_now(), "server_epoch": unix_time()})


    @app.post("/api/v1/admin/device/<int:device_id>/ack")
    @login_required
    def api_admin_device_ack(device_id: int):
        """Acknowledge a device alarm from JS (used by the global alert prompt)."""
        ack_device_alarm(device_id)
        return jsonify({"ok": True, "device_id": device_id})


    # ---- Device JSON API ----

    @app.get("/api/v1/device/<int:device_id>/sync")
    def api_device_sync(device_id: int):
        dev = require_device_auth(device_id)

        # Update last_seen (and optionally last_state if device sends it as query)
        state = request.args.get("state")
        store.touch_device(device_id, last_state=state or dev.get("last_state") or "UNKNOWN")

        # Prepare pending commands
        cmds = store.fetch_pending_commands(device_id, max_n=5)
        cmd_out = []
        cmd_ids = []
        for c in cmds:
            cmd_ids.append(int(c["id"]))
            try:
                payload = json.loads(c.get("payload_json") or "{}")
            except Exception:
                payload = {}
            cmd_out.append({"id": int(c["id"]), "cmd": c["cmd"], "payload": payload})

        store.mark_commands_delivered(cmd_ids)

        # Basic config
        out = {
            "ok": True,
            "server_epoch": unix_time(),
            "server_hhmm": local_hhmm_now(),
            "config": {
                "enabled": bool(dev["enabled"]),
                "trigger_time": dev["trigger_time"],
                "kill_time": dev["kill_time"],
                "pause_after_ack_s": int(config.DEVICE_PAUSE_AFTER_ACK_S),
            },
            "commands": cmd_out,
        }
        return jsonify(out)

    @app.post("/api/v1/device/<int:device_id>/heartbeat")
    def api_device_heartbeat(device_id: int):
        dev = require_device_auth(device_id)
        data = request.get_json(silent=True) or {}
        state = str(data.get("state") or "UNKNOWN")
        store.touch_device(device_id, last_state=state)
        return jsonify({"ok": True})

    @app.post("/api/v1/device/<int:device_id>/event")
    def api_device_event(device_id: int):
        dev = require_device_auth(device_id)
        data = request.get_json(silent=True) or {}

        event_type = (data.get("type") or "").upper().strip()
        details = data.get("details") if isinstance(data.get("details"), dict) else {}

        # Always touch
        store.touch_device(device_id, last_state=str(data.get("state") or dev.get("last_state") or "UNKNOWN"))

        if event_type == "ALARM_START":
            # Create a case only if not already active
            current = store.get_device(device_id)
            if current and int(current.get("alarm_active") or 0) == 1:
                return jsonify({"ok": True, "note": "alarm already active"})

            case_id = store.create_case(device_id, dev["name"], status="BROKE", details=details)
            store.set_alarm_active(device_id, active=True, case_id=case_id)
            return jsonify({"ok": True, "case_id": case_id})

        if event_type == "ALARM_END":
            # Mark case ended
            current = store.get_device(device_id)
            case_id = current.get("alarm_case_id") if current else None
            if case_id:
                store.mark_case_ended(case_id)
            store.set_alarm_active(device_id, active=False, case_id=None)
            store.set_ack_pending(device_id, ack_pending=False)
            store.set_pause_until(device_id, None)
            return jsonify({"ok": True})

        if event_type == "ACK_RECEIVED":
            # Device confirms it received ACK_ALARM and stopped alarming (now in PAUSED).
            current = store.get_device(device_id)
            case_id = current.get("alarm_case_id") if current else None

            # Clear ack pending and clear alarm status on server so UI returns to Safe.
            store.set_ack_pending(device_id, ack_pending=False)
            if case_id:
                store.mark_case_ended(case_id)

            # Alarm is over once the device confirms it stopped.
            store.set_alarm_active(device_id, active=False, case_id=None)
            return jsonify({"ok": True})

        if event_type == "COMMAND_CLEARED":
            # Device tells server to clear a specific command id
            cmd_id = int(data.get("command_id") or 0)
            if cmd_id:
                store.clear_command(cmd_id)
            return jsonify({"ok": True})

        return jsonify({"ok": False, "error": "Unknown event type"}), 400

    return app


def decorate_devices_for_ui(devices: list[dict]) -> list[dict]:
    return [decorate_device_for_ui(d) for d in devices]


def decorate_device_for_ui(dev: dict) -> dict:
    from datetime import datetime

    d = dict(dev)
    # Compute status: Offline / Broke / Safe
    status = "Safe"
    now_utc = datetime.now(timezone.utc)

    last_seen = d.get("last_seen")
    if not last_seen:
        status = "Offline"
    else:
        try:
            # Parse ISO
            seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            age_s = (now_utc - seen_dt).total_seconds()
            if age_s > config.OFFLINE_AFTER_S:
                status = "Offline"
        except Exception:
            status = "Offline"

    if status != "Offline":
        if int(d.get("alarm_active") or 0) == 1:
            status = "Broke"

    d["ui_status"] = status
    d["ui_ack_pending"] = bool(int(d.get("ack_pending") or 0))
    return d


# Expose for wsgi
app = create_app()

if __name__ == "__main__":
    # Dev server (OK for quick testing on LAN). For production on the Pi, use waitress:
    #   python3 -m waitress --listen=0.0.0.0:80 wsgi:app
    app.run(host=config.BIND_HOST, port=config.PORT, debug=False)
