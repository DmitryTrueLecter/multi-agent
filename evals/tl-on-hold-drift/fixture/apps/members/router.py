from __future__ import annotations

from apps.members import service
from apps.members.schemas import Role


def get_members(store):
    return sorted(store.all(), key=lambda m: (m.status != "active", m.email))


def post_invite(store, email: str, role: Role):
    try:
        member = service.invite(store.all(), email, role)
    except service.DuplicateMember:
        return {"status": 409, "error": "This person is already a member or has a pending invite."}
    store.save(member)
    return {"status": 201, "member": member}


def post_accept(store, email: str):
    member = store.get(email)
    try:
        store.save(service.accept(member))
    except service.InviteExpired:
        return {"status": 410, "error": "This invite has expired. Ask an editor to invite you again."}
    return {"status": 200}


def post_role(store, email: str, role: Role):
    store.save(service.change_role(store.get(email), role))
    return {"status": 200}


def delete_member(store, email: str):
    store.replace_all(service.remove(store.all(), email))
    return {"status": 204}
