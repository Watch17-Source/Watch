"""WATCH Server Configuration (Raspberry Pi 4, Python 3.11.2)

Edit this file to change:
- admin username/password
- bind host/port
- database location
- security options

Default login:
  user: admin
  pass: admin

IMPORTANT:
- Change the default credentials before deployment.
- Make sure your Raspberry Pi system timezone is set to Asia/Manila (or your local TZ),
  because schedules use the Pi's local time.
"""

from __future__ import annotations

from pathlib import Path
import os
import secrets

# Network
BIND_HOST = os.getenv("WATCH_BIND_HOST", "0.0.0.0")
# Port 80 gives the nicest URL: http://192.168.68.58/
# If you prefer not to bind to 80, use 8080 and access http://192.168.68.58:8080/
PORT = int(os.getenv("WATCH_PORT", "80"))

# Static IP reservation (for your router reference)
SERVER_STATIC_IP = os.getenv("WATCH_SERVER_IP", "192.168.1.3")

# Database
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("WATCH_DB_PATH", str(BASE_DIR / "watchhub.db")))

# Session secret (used to sign login cookies)
# Generate once and keep stable.
SECRET_KEY = os.getenv("WATCH_SECRET_KEY") or secrets.token_hex(32)

# Admin login (no signup)
ADMIN_USERNAME = os.getenv("WATCH_ADMIN_USER", "admin")

# Option A (simple): store plaintext here (recommended to change immediately)
ADMIN_PASSWORD = os.getenv("WATCH_ADMIN_PASS", "admin")

# Option B (more secure): store a password hash and set ADMIN_PASSWORD=None
# Format: "pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>"
ADMIN_PASSWORD_HASH = os.getenv("WATCH_ADMIN_PASSHASH") or None

# Device authentication
# Devices must send their token in header: X-Device-Token
ENFORCE_DEVICE_IP_MATCH = False  # also require request.remote_addr == device.ip

# Offline threshold: if last heartbeat older than this, show OFFLINE in UI
OFFLINE_AFTER_S = 90

# How long to keep server-generated "ack" commands if the device doesn't fetch them (seconds)
COMMAND_TTL_S = 6 * 60 * 60  # 6 hours

# Default per-device schedule (guards can override per device)
DEFAULT_TRIGGER_TIME = "22:00"  # curfew start
DEFAULT_KILL_TIME = "05:00"     # curfew end

# Device pause time after guard clicks OK
DEVICE_PAUSE_AFTER_ACK_S = 60 * 60  # 1 hour

# UI refresh interval (milliseconds) on Watch page
WATCH_POLL_MS = 2000

# Static asset version (cache buster)
# Bump this value when you change CSS/JS and need clients to refresh cached files.
STATIC_VERSION = "2"

# Global alarm/alert poll interval (milliseconds) for the always-on alert overlay
# (Smaller = faster alerts; keep reasonable to avoid unnecessary load)
ALERT_POLL_MS = 1200

# If True, the UI will gently pulse/flash while an unacked alarm is active
ALERT_FLASH_ENABLED = True

# Basic hardening
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# If you later serve behind HTTPS, set this to True
SESSION_COOKIE_SECURE = False
