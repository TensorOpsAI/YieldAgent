"""Tests for the console campaign store."""

from __future__ import annotations

from yieldagent.store import campaigns


def _record(id_: str = "abc") -> dict:
    return {
        "id": id_,
        "created_at": "2026-06-04T10:00:00+00:00",
        "platform": "linkedin",
        "name": "Q3 Demand Gen",
        "objective": "leads",
        "status": "DRAFT",
        "group_urn": "urn:li:sponsoredCampaignGroup:1",
        "lcm_url": "https://www.linkedin.com/campaignmanager/accounts/1/campaigns",
        "targeting": {"geos": ["US"], "seniorities": ["Director"]},
        "unresolved": {},
        "payload": {"campaign": {"name": "Q3 Demand Gen"}, "result": {"ok": True}},
    }


def test_save_list_get_and_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("YIELDAGENT_DB", str(tmp_path / "test.db"))

    campaigns.save(_record())
    listed = campaigns.list_all()
    assert len(listed) == 1
    assert listed[0]["name"] == "Q3 Demand Gen"
    assert listed[0]["targeting"] == {"geos": ["US"], "seniorities": ["Director"]}

    full = campaigns.get("abc")
    assert full is not None
    assert full["payload"]["result"] == {"ok": True}
    assert campaigns.get("missing") is None

    assert campaigns.summary() == {"total": 1, "drafts": 1}


def test_list_is_newest_first(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("YIELDAGENT_DB", str(tmp_path / "test.db"))
    older = _record("old") | {"created_at": "2026-06-01T00:00:00+00:00", "name": "Old"}
    newer = _record("new") | {"created_at": "2026-06-04T00:00:00+00:00", "name": "New"}
    campaigns.save(older)
    campaigns.save(newer)
    assert [c["name"] for c in campaigns.list_all()] == ["New", "Old"]
