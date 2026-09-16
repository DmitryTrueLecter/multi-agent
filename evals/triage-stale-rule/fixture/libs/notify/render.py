"""Template rendering with lazy per-template loading (NOTIFY-77 replaced the import-time warm)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"


@lru_cache(maxsize=None)
def _load(name: str) -> str:
    return (TEMPLATES / f"{name}.html").read_text()


def render(name: str, **ctx: object) -> str:
    return _load(name).format(**ctx)
