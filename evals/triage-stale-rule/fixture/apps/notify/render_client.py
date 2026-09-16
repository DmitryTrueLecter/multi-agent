from __future__ import annotations

import structlog

from apps.notify import settings
from libs.notify.render import render

log = structlog.get_logger("notify")


def send_welcome(user, mailer) -> None:
    body = render("welcome", name=user.name)
    mailer.send(sender=settings.NOTIFY_SENDER, to=user.email, html=body)
    log.info("notify.sent", template="welcome", to=user.email)
