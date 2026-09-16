from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

Status = Literal["created", "packed", "shipped", "delivered"]


@dataclass(frozen=True)
class Shipment:
    id: str
    order_id: str
    status: Status
    carrier: str | None = None
    tracking_number: str | None = None

    def with_status(self, status: Status) -> "Shipment":
        return replace(self, status=status)
