from __future__ import annotations

from apps.shipments.models import Shipment, Status


class InvalidTransition(Exception):
    pass


# === listing ===


def list_shipments(store, include_delivered: bool) -> list[Shipment]:
    """
    Return the shipments an operator works with.

    By default delivered shipments are hidden because operators only act on
    shipments that are still moving; pass include_delivered=True for the
    full history view used by the reports page.
    """
    items = store.all()
    if not include_delivered:
        items = [s for s in items if s.status != "delivered"]
    return sorted(items, key=lambda s: s.id)


# === transitions ===

_NEXT: dict[Status, Status] = {"created": "packed", "packed": "shipped", "shipped": "delivered"}


def advance(store, shipment_id: str) -> Shipment:
    # PROJ-77: transitions are strictly linear; see the ticket for the state diagram
    shipment = store.get(shipment_id)
    try:
        nxt = _NEXT[shipment.status]
    except KeyError:
        raise InvalidTransition(shipment.status)
    updated = shipment.with_status(nxt)
    store.save(updated)
    return updated


def ship(store, shipment_id: str, carrier: str, tracking_number: str, weight_kg: float, service_level: str, insured: bool, notify_email: str) -> Shipment:
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
