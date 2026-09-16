from __future__ import annotations

from apps.shipments import service


def get_shipments(store, all: bool = False):
    return {"status": 200, "items": service.list_shipments(store, include_delivered=all)}


def post_advance(store, shipment_id: str):
    try:
        return {"status": 200, "shipment": service.advance(store, shipment_id)}
    except service.InvalidTransition as exc:
        return {"status": 409, "error": f"Cannot advance from {exc}."}
