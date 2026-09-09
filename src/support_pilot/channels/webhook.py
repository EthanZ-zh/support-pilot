from __future__ import annotations

import httpx

from support_pilot.channels.base import ChannelDeliveryError, TicketEvent
from support_pilot.config import Settings


class WebhookChannel:
    name = "webhook"

    def __init__(self, settings: Settings) -> None:
        if not settings.webhook_url:
            raise ValueError("Webhook notification channel requires WEBHOOK_URL")
        self._settings = settings

    def deliver(self, event: TicketEvent) -> None:
        try:
            response = httpx.post(
                self._settings.webhook_url,
                json=self._build_payload(event),
                timeout=self._settings.channel_request_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ChannelDeliveryError("Webhook delivery failed") from error

    def _build_payload(self, event: TicketEvent) -> dict[str, object]:
        return {
            "msgtype": "text",
            "text": {
                "content": (
                    f"Ticket {event.public_code} {event.event_type} "
                    f"({event.status}): {event.summary}"
                )
            },
            "support_pilot_event": event.to_payload(),
        }
