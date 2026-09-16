import pytest

from apps.shipments import service
from apps.shipments.models import Shipment


class MemoryStore:
    def __init__(self, items):
        self._items = {s.id: s for s in items}

    def all(self):
        return list(self._items.values())

    def get(self, shipment_id):
        return self._items[shipment_id]

    def save(self, shipment):
        self._items[shipment.id] = shipment


def test_list_hides_delivered_by_default():
    store = MemoryStore([Shipment("s1", "o1", "created"), Shipment("s2", "o2", "delivered")])
    assert [s.id for s in service.list_shipments(store)] == ["s1"]


def test_list_includes_delivered_when_asked():
    store = MemoryStore([Shipment("s1", "o1", "created"), Shipment("s2", "o2", "delivered")])
    assert len(service.list_all_shipments(store)) == 2


def test_advance_moves_one_step():
    store = MemoryStore([Shipment("s1", "o1", "created")])
    assert service.advance(store, "s1").status == "packed"


def test_advance_from_delivered_is_invalid():
    store = MemoryStore([Shipment("s1", "o1", "delivered")])
    with pytest.raises(service.InvalidTransition):
        service.advance(store, "s1")
