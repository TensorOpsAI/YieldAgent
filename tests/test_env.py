"""Tests for the `.env` loader, including the empty-shadow fix."""

from __future__ import annotations

import os

from yieldagent.env import load_dotenv


def test_empty_env_var_is_filled_from_dotenv(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("FOO_KEY=real-value\n")
    # Simulates an inherited-but-empty var (e.g. ANTHROPIC_API_KEY=) shadowing it.
    monkeypatch.setenv("FOO_KEY", "")
    load_dotenv(env)
    assert os.environ["FOO_KEY"] == "real-value"


def test_nonempty_env_var_wins(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("FOO_KEY=from-file\n")
    monkeypatch.setenv("FOO_KEY", "from-shell")
    load_dotenv(env)
    assert os.environ["FOO_KEY"] == "from-shell"


def test_override_replaces_nonempty(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("FOO_KEY=from-file\n")
    monkeypatch.setenv("FOO_KEY", "from-shell")
    load_dotenv(env, override=True)
    assert os.environ["FOO_KEY"] == "from-file"
