"""Lightweight .env loading for local development.

Docker Compose reads .env by itself, but manual uvicorn runs do not. This keeps
local startup predictable without adding a runtime dependency.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_if_present() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
