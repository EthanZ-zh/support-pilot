from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

import httpx

from support_pilot.channels.base import ChannelDeliveryError, TicketEvent
from support_pilot.config import Settings


class WebhookChannel:
    name = "webhook"

    def __init__(self, settings: Settings) -> None:
        url = settings.webhook_url.get_secret_value()
        if not url:
            raise ValueError("Webhook notification channel requires WEBHOOK_URL")
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            _ = parsed.port
        except ValueError as error:
            raise ValueError("Webhook URL is invalid") from error
        if parsed.scheme.casefold() != "https":
            raise ValueError("Webhook URL must use HTTPS")
        if not hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError("Webhook URL must not include userinfo")
        normalized_host = hostname.rstrip(".").casefold()
        allowed_hosts = {
            host.strip().rstrip(".").casefold()
            for host in settings.webhook_allowed_hosts
            if host.strip()
        }
        if normalized_host not in allowed_hosts:
            raise ValueError("Webhook URL host is not allowed")
        try:
            address = ipaddress.ip_address(normalized_host)
        except ValueError:
            address = None
        if address is not None and (not address.is_global or address.is_multicast):
            raise ValueError("Webhook URL targets a disallowed IP address")
        self._settings = settings
        self._url = url

    def deliver(self, event: TicketEvent) -> None:
        try:
            response = httpx.post(
                self._url,
                json=self._build_payload(event),
                timeout=self._settings.channel_request_timeout_seconds,
                trust_env=False,
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
