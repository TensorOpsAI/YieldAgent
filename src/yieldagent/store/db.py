"""SQLite connection + schema for the console's campaign store.

One table, demo-scale, stdlib only. Path comes from `YIELDAGENT_DB`
(default `yieldagent.db` in the working directory).
"""

from __future__ import annotations

import os
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    platform    TEXT NOT NULL,
    name        TEXT NOT NULL,
    objective   TEXT NOT NULL,
    status      TEXT NOT NULL,
    group_urn   TEXT,
    lcm_url     TEXT,
    targeting   TEXT NOT NULL,
    unresolved  TEXT NOT NULL,
    payload     TEXT NOT NULL
);
"""


def db_path() -> str:
    return os.environ.get("YIELDAGENT_DB", "yieldagent.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn
