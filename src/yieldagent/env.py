"""Small `.env` loader for local CLI and MCP server entry points."""

from __future__ import annotations

import os
from pathlib import Path


def _find_dotenv(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def _parse_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
    return value


def load_dotenv(path: Path | None = None, *, override: bool = False) -> Path | None:
    """Load KEY=VALUE pairs from `.env` into `os.environ`.

    This intentionally handles the simple format used by this repo without
    adding a runtime dependency. Existing shell variables win unless
    ``override=True`` is passed.
    """
    dotenv_path = path or _find_dotenv()
    if dotenv_path is None:
        return None

    for line in dotenv_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").lstrip()
        if "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            continue
        if override or key not in os.environ:
            os.environ[key] = _parse_value(raw_value)

    return dotenv_path
