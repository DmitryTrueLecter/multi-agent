from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["viewer", "editor"]


@dataclass(frozen=True)
class Member:
    email: str
    role: Role
    status: Literal["active", "invited"]
    invited_days_ago: int | None = None
