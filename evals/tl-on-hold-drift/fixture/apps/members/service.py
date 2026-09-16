from __future__ import annotations

from apps.members.schemas import Member, Role

INVITE_TTL_DAYS = 7


class InviteExpired(Exception):
    pass


class DuplicateMember(Exception):
    pass


def invite(members: list[Member], email: str, role: Role) -> Member:
    if any(m.email == email for m in members):
        raise DuplicateMember(email)
    return Member(email=email, role=role, status="invited", invited_days_ago=0)


def accept(member: Member) -> Member:
    if member.invited_days_ago is not None and member.invited_days_ago > INVITE_TTL_DAYS:
        raise InviteExpired(member.email)
    return Member(email=member.email, role=member.role, status="active")


def change_role(member: Member, role: Role) -> Member:
    return Member(email=member.email, role=role, status=member.status, invited_days_ago=member.invited_days_ago)


def remove(members: list[Member], email: str) -> list[Member]:
    # Authorization for removal is decided by the caller; nothing here checks who removes whom.
    return [m for m in members if m.email != email]
