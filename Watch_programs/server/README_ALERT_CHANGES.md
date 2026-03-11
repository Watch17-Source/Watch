# WATCH Server — Alert & Audio Enhancements (Change Log)

This document describes the **new always-on intruder alert prompt + ringing sound** feature added to the WATCH Flask server UI,
without changing the existing GUI layout/pages.

> **Goal:** When an intruder alarm happens, guards should see an alert prompt on *any page* and hear a ringing sound.
> Clicking **Okay** should stop the ringing and send an **ACK** command to the device.

---

## What was added

### 1) Always-on alarm prompt (all pages)
- A global alarm prompt is injected into `templates/base.html`, so it exists on **every page after login**.
- The prompt displays:
  - **Room name**
  - **Status** (Broke)
  - **Started time** (from the active case)
  - **Device IP**
  - **Ack state** (sent / not sent)
- Each alarm row includes:
  - **Okay** (ACK) button
  - **Open room** link to the room/device detail page

**Files:**
- `templates/base.html` (new overlay markup + global script injection)
- `static/styles.css` (styling for the prompt)
- `static/alerts.js` (polling + UI rendering + ACK sending)

**Important UI fix:**
- The overlay/toast use the HTML `[hidden]` attribute to show/hide.
- A global CSS rule was added to enforce `[hidden]{display:none !important;}` so the overlay is never stuck visible.

**Cache-busting improvement (prevents "I updated the server but my browser still shows old UI")**
- Added `config.STATIC_VERSION` and appended it as a `?v=` query parameter on CSS/JS assets in `base.html`.
- If you ever change CSS/JS again, bump `STATIC_VERSION` and clients will automatically re-fetch.

---

### 2) Ringing sound (no external sound file required)
- The ringing sound is generated using the **Web Audio API** (oscillator “siren”).
- This means **no MP3/WAV file is required**.
- Volume is kept moderate by default.

**Important browser rule:** Browsers require a **user gesture** (tap/click) before audio can play.
So the app cannot “auto-play” sound immediately after login without at least one user click.

---

### 3) Audio permission prompt after successful login
- On successful login, the server sets a session flag and the UI shows a small **“Enable sound alerts”** toast.
- The guard taps **Enable sound** once, and audio will work for alarms afterward (for that browser session).

**Files:**
- `app.py` (sets `session["audio_prompt"] = True` after login)
- `templates/base.html` (toast UI)
- `static/alerts.js` (handles enabling audio)

---

### 4) New lightweight alert API endpoint
A new endpoint powers the always-on alert overlay:

- `GET /api/v1/admin/alerts`
  - Returns current **active alarms** (devices with `alarm_active=1`) with basic case metadata.

It relies on a new DB helper:

- `store.list_active_alarms()`

---

### 5) New admin ACK endpoint used by the alert prompt
The overlay’s **Okay** button uses:

- `POST /api/v1/admin/device/<device_id>/ack`

This reuses the same ACK logic as the existing form-based ACK button on the device detail page.

---

## Security / correctness changes

### CSRF protection tightened
Originally, CSRF protection was skipped for all `/api/*`.
That was safe for device endpoints, but not ideal for **admin POST APIs**.

**Change:**
- CSRF is now skipped only for device endpoints:
  - `/api/v1/device/...`

So **admin POST APIs** are protected (including the new ACK endpoint).

---

## Operational notes & limitations (important)

### “Always-on even if the page isn’t loaded”
A browser page cannot receive live alarms if:
- the tab is completely closed, or
- the browser/app is not running.

This update guarantees:
- alarms are available on **any page inside the WATCH UI** while logged in and the site is open (even in a background tab).

If you truly need alerts when the site is closed, you’d need a separate always-running client (mobile app/desktop app) or Web Push.
Web Push typically requires HTTPS and (often) internet access through the browser push service.

---

## How to test

### Quick manual test
1. Run the server and log in.
2. Click **Enable sound** in the toast.
3. Trigger a device alarm:
   - From hardware, or
   - Use `tools/sim_device.py` to send an `ALARM_START` event.
4. Confirm:
   - The alert prompt appears on any page.
   - The siren rings.
   - Clicking **Okay** stops ringing and sends ACK.

### Device simulation (existing tool)
The repo already includes:
- `tools/sim_device.py`

You can extend it to send `ALARM_END` or `ACK_RECEIVED` if needed.

---

## Customizing the ring sound
If you prefer an external sound file (MP3/WAV), you can replace the Web Audio siren in:
- `static/alerts.js`

With an `<audio>` element and `.play()`/`.pause()` calls.
However, the same browser gesture rule still applies.

---

## Summary of modified / added files

**Modified**
- `app.py`
- `config.py`
- `store.py`
- `templates/base.html`
- `static/styles.css`

**Added**
- `static/alerts.js`
- `README_ALERT_CHANGES.md`
