from __future__ import annotations

from apps.shipments import service


# Operators reach this from the shipments board.
# The `all` switch went away with the listing split;
# the board and the report page now call separate entrypoints.
def get_shipments(store):
    return {"status": 200, "items": service.list_shipments(store)}


def get_all_shipments(store):
    return {"status": 200, "items": service.list_all_shipments(store)}


def post_advance(store, shipment_id: str):
    try:
        return {"status": 200, "shipment": service.advance(store, shipment_id)}
    except service.InvalidTransition as exc:
        return {"status": 409, "error": f"Cannot advance from {exc}."}
