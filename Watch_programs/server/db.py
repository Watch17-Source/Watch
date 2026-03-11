"""SQLite database helpers for WATCH server."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable
from datetime import datetime, timezone

from flask import g

from config import DB_PATH, COMMAND_TTL_S


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        # Improve concurrency a bit
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        g.db = conn
    return g.db


def close_db(e: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL;")
    db.execute("PRAGMA foreign_keys=ON;")
    cur = db.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            ip              TEXT NOT NULL UNIQUE,
            token           TEXT NOT NULL UNIQUE,
            enabled         INTEGER NOT NULL DEFAULT 1,
            trigger_time    TEXT NOT NULL,
            kill_time       TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            last_seen       TEXT,
            last_state      TEXT,
            alarm_active    INTEGER NOT NULL DEFAULT 0,
            alarm_case_id   INTEGER,
            ack_pending     INTEGER NOT NULL DEFAULT 0,
            pause_until     TEXT
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id           INTEGER NOT NULL,
            device_name         TEXT NOT NULL,
            status              TEXT NOT NULL,
            started_at          TEXT NOT NULL,
            acked_at            TEXT,
            ended_at            TEXT,
            details_json        TEXT,
            server_received_at  TEXT NOT NULL,
            FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS commands (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id       INTEGER NOT NULL,
            cmd             TEXT NOT NULL,
            payload_json    TEXT,
            created_at      TEXT NOT NULL,
            delivered_at    TEXT,
            cleared_at      TEXT,
            expires_at      TEXT NOT NULL,
            FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
        );
        """
    )

    db.commit()
    db.close()


def query_one(sql: str, args: Iterable[Any] = ()):
    db = get_db()
    cur = db.execute(sql, tuple(args))
    row = cur.fetchone()
    cur.close()
    return row


def query_all(sql: str, args: Iterable[Any] = ()):
    db = get_db()
    cur = db.execute(sql, tuple(args))
    rows = cur.fetchall()
    cur.close()
    return rows


def execute(sql: str, args: Iterable[Any] = ()) -> int:
    db = get_db()
    cur = db.execute(sql, tuple(args))
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id


def prune_expired_commands() -> None:
    """Delete commands that are expired and not yet cleared."""
    now = utc_now_iso()
    execute(
        "DELETE FROM commands WHERE cleared_at IS NULL AND expires_at < ?",
        (now,),
    )


def command_expiry_iso() -> str:
    # utc_now + ttl
    from datetime import timedelta
    dt = datetime.now(timezone.utc) + timedelta(seconds=COMMAND_TTL_S)
    return dt.isoformat(timespec="seconds")
