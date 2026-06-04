"""CRUD for console-created campaigns.

JSON columns (`targeting`, `unresolved`, `payload`) are (de)serialized here so
callers work with plain dicts.
"""

from __future__ import annotations

import json
from typing import Any

from . import db

_JSON_COLUMNS = ("targeting", "unresolved", "payload")
_INSERT = """
INSERT OR REPLACE INTO campaigns
    (id, created_at, platform, name, objective, status, group_urn, lcm_url,
     targeting, unresolved, payload)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def save(record: dict[str, Any]) -> None:
    conn = db.connect()
    with conn:
        conn.execute(
            _INSERT,
            (
                record["id"],
                record["created_at"],
                record["platform"],
                record["name"],
                record["objective"],
                record["status"],
                record.get("group_urn"),
                record.get("lcm_url"),
                json.dumps(record.get("targeting", {})),
                json.dumps(record.get("unresolved", {})),
                json.dumps(record.get("payload", {})),
            ),
        )
    conn.close()


def list_all() -> list[dict[str, Any]]:
    conn = db.connect()
    rows = conn.execute(
        "SELECT id, created_at, platform, name, objective, status, lcm_url, targeting "
        "FROM campaigns ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [{**dict(r), "targeting": json.loads(r["targeting"])} for r in rows]


def get(campaign_id: str) -> dict[str, Any] | None:
    conn = db.connect()
    row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    record = dict(row)
    for column in _JSON_COLUMNS:
        record[column] = json.loads(record[column])
    return record


def delete(campaign_id: str) -> bool:
    """Remove a campaign record from the app store. Returns True if a row was
    deleted. Note: this only forgets it locally — it does not touch LinkedIn.
    """
    conn = db.connect()
    with conn:
        cur = conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def summary() -> dict[str, int]:
    conn = db.connect()
    total = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
    drafts = conn.execute(
        "SELECT COUNT(*) FROM campaigns WHERE status = 'DRAFT'"
    ).fetchone()[0]
    conn.close()
    return {"total": total, "drafts": drafts}
