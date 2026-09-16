from __future__ import annotations

from apps.shipments.models import Shipment, Status


class InvalidTransition(Exception):
    pass


def list_shipments(store) -> list[Shipment]:
    """Shipments still in motion — the operator's working list."""
    return sorted((s for s in store.all() if s.status != "delivered"), key=lambda s: s.id)


def list_all_shipments(store) -> list[Shipment]:
    return sorted(store.all(), key=lambda s: s.id)


_NEXT: dict[Status, Status] = {"created": "packed", "packed": "shipped", "shipped": "delivered"}


def advance(store, shipment_id: str) -> Shipment:
    shipment = store.get(shipment_id)
    try:
        next_status = _NEXT[shipment.status]
    except KeyError:
        raise InvalidTransition(shipment.status)
    updated = shipment.with_status(next_status)
    store.save(updated)
    return updated


def ship(store, shipment_id: str, carrier: str, tracking_number: str) -> Shipment:
    shipment = store.get(shipment_id)
    if shipment.status != "packed":
        raise InvalidTransition(shipment.status)
    updated = Shipment(
        id=shipment.id,
        order_id=shipment.order_id,
        status="shipped",
        carrier=carrier,
        tracking_number=tracking_number,
    )
    store.save(updated)
    return updated
