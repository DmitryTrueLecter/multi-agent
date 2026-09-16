import pytest

from apps.members import service
from apps.members.schemas import Member


def test_invite_rejects_duplicate_email():
    existing = [Member("a@x.io", "viewer", "active")]
    with pytest.raises(service.DuplicateMember):
        service.invite(existing, "a@x.io", "editor")


def test_accept_expires_after_seven_days():
    with pytest.raises(service.InviteExpired):
        service.accept(Member("b@x.io", "viewer", "invited", invited_days_ago=8))


def test_accept_within_seven_days_activates():
    assert service.accept(Member("b@x.io", "viewer", "invited", invited_days_ago=7)).status == "active"


def test_remove_drops_only_that_email():
    members = [Member("a@x.io", "editor", "active"), Member("b@x.io", "viewer", "active")]
    assert [m.email for m in service.remove(members, "a@x.io")] == ["b@x.io"]
