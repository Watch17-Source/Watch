"""High-level DB operations for WATCH server."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from db import execute, query_one, query_all, utc_now_iso, prune_expired_commands, command_expiry_iso


def row_to_dict(row):
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def list_devices():
    rows = query_all("SELECT * FROM devices ORDER BY name ASC")
    return [row_to_dict(r) for r in rows]


def list_active_alarms():
    """Return active alarms with case metadata (if available).

    This is used by the always-on alert overlay in the web UI.
    """
    rows = query_all(
        """
        SELECT
            d.id            AS device_id,
            d.name          AS device_name,
            d.ip            AS ip,
            d.last_seen     AS last_seen,
            d.last_state    AS last_state,
            d.alarm_case_id AS case_id,
            d.ack_pending   AS ack_pending,
            d.pause_until   AS pause_until,
            c.started_at    AS case_started_at,
            c.acked_at      AS case_acked_at,
            c.ended_at      AS case_ended_at,
            c.details_json  AS case_details_json
        FROM devices d
        LEFT JOIN cases c ON c.id = d.alarm_case_id
        WHERE d.alarm_active = 1
        ORDER BY c.started_at DESC, d.name ASC
        """
    )
    return [row_to_dict(r) for r in rows]


def get_device(device_id: int):
    return row_to_dict(query_one("SELECT * FROM devices WHERE id = ?", (device_id,)))


def get_device_by_ip(ip: str):
    return row_to_dict(query_one("SELECT * FROM devices WHERE ip = ?", (ip,)))


def get_device_by_token(device_id: int, token: str):
    return row_to_dict(query_one("SELECT * FROM devices WHERE id = ? AND token = ?", (device_id, token)))


def create_device(*, name: str, ip: str, trigger_time: str, kill_time: str) -> dict:
    token = secrets.token_urlsafe(24)
    now = utc_now_iso()
    device_id = execute(
        """
        INSERT INTO devices (name, ip, token, trigger_time, kill_time, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, ip, token, trigger_time, kill_time, now),
    )
    d = get_device(device_id)
    d["token"] = token
    return d


def update_device_schedule(device_id: int, *, trigger_time: str, kill_time: str, enabled: bool):
    execute(
        "UPDATE devices SET trigger_time=?, kill_time=?, enabled=? WHERE id=?",
        (trigger_time, kill_time, 1 if enabled else 0, device_id),
    )


def update_device_name_ip(device_id: int, *, name: str, ip: str):
    execute(
        "UPDATE devices SET name=?, ip=? WHERE id=?",
        (name, ip, device_id),
    )


def delete_device(device_id: int):
    execute("DELETE FROM devices WHERE id=?", (device_id,))


def touch_device(device_id: int, *, last_state: str | None = None):
    now = utc_now_iso()
    if last_state is None:
        execute("UPDATE devices SET last_seen=? WHERE id=?", (now, device_id))
    else:
        execute("UPDATE devices SET last_seen=?, last_state=? WHERE id=?", (now, last_state, device_id))


def set_alarm_active(device_id: int, *, active: bool, case_id: int | None = None):
    execute(
        "UPDATE devices SET alarm_active=?, alarm_case_id=?, ack_pending=? WHERE id=?",
        (1 if active else 0, case_id, 0, device_id),
    )


def set_ack_pending(device_id: int, *, ack_pending: bool):
    execute("UPDATE devices SET ack_pending=? WHERE id=?", (1 if ack_pending else 0, device_id))


def set_pause_until(device_id: int, pause_until_iso: str | None):
    execute("UPDATE devices SET pause_until=? WHERE id=?", (pause_until_iso, device_id))


def create_case(device_id: int, device_name: str, *, status: str, details: dict | None = None) -> int:
    now = utc_now_iso()
    details_json = json.dumps(details or {}, separators=(",", ":"))
    case_id = execute(
        """
        INSERT INTO cases (device_id, device_name, status, started_at, server_received_at, details_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (device_id, device_name, status, now, now, details_json),
    )
    return case_id


def mark_case_acked(case_id: int):
    now = utc_now_iso()
    execute("UPDATE cases SET acked_at=? WHERE id=? AND acked_at IS NULL", (now, case_id))


def mark_case_ended(case_id: int):
    now = utc_now_iso()
    execute("UPDATE cases SET ended_at=? WHERE id=? AND ended_at IS NULL", (now, case_id))


def list_cases(limit: int = 200):
    rows = query_all(
        "SELECT * FROM cases ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [row_to_dict(r) for r in rows]


def list_cases_for_device(device_id: int, limit: int = 100):
    rows = query_all(
        "SELECT * FROM cases WHERE device_id=? ORDER BY id DESC LIMIT ?",
        (device_id, limit),
    )
    return [row_to_dict(r) for r in rows]


def enqueue_command(device_id: int, cmd: str, payload: dict | None = None) -> int:
    prune_expired_commands()
    now = utc_now_iso()
    expires_at = command_expiry_iso()
    payload_json = json.dumps(payload or {}, separators=(",", ":"))
    return execute(
        """
        INSERT INTO commands (device_id, cmd, payload_json, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (device_id, cmd, payload_json, now, expires_at),
    )


def fetch_pending_commands(device_id: int, *, max_n: int = 5) -> list[dict]:
    prune_expired_commands()
    rows = query_all(
        """
        SELECT * FROM commands
        WHERE device_id=? AND cleared_at IS NULL
        ORDER BY id ASC
        LIMIT ?
        """,
        (device_id, max_n),
    )
    return [row_to_dict(r) for r in rows]


def mark_commands_delivered(command_ids: list[int]):
    if not command_ids:
        return
    now = utc_now_iso()
    qmarks = ",".join(["?"] * len(command_ids))
    execute(f"UPDATE commands SET delivered_at=? WHERE id IN ({qmarks})", (now, *command_ids))


def clear_command(command_id: int):
    now = utc_now_iso()
    execute("UPDATE commands SET cleared_at=? WHERE id=?", (now, command_id))
