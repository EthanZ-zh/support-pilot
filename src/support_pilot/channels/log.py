from __future__ import annotations

import logging

from support_pilot.channels.base import TicketEvent

logger = logging.getLogger("support_pilot.channels")


class LoggingChannel:
    """Default channel: records delivery metadata without an external side effect."""

    name = "log"

    def deliver(self, event: TicketEvent) -> None:
        logger.info(
            "channel=log event=%s ticket=%s status=%s",
            event.event_type,
            event.public_code,
            event.status,
        )
