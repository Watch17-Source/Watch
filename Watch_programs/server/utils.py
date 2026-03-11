"""Utility helpers (validation, time formatting)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Tuple

HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def is_valid_hhmm(s: str) -> bool:
    return bool(HHMM_RE.match(s.strip()))


def require_hhmm(s: str) -> str:
    s = (s or "").strip()
    if not is_valid_hhmm(s):
        raise ValueError("Time must be HH:MM (00:00 to 23:59)")
    return s


def local_hhmm_now() -> str:
    # Uses system local time
    return datetime.now().strftime("%H:%M")


def unix_time() -> int:
    # Unix epoch seconds
    return int(datetime.now(timezone.utc).timestamp())
