from __future__ import annotations

from support_pilot.channels.base import OutboundChannel
from support_pilot.channels.log import LoggingChannel
from support_pilot.channels.smtp import SmtpChannel
from support_pilot.channels.webhook import WebhookChannel
from support_pilot.config import Settings, get_settings


def get_outbound_channel(settings: Settings | None = None) -> OutboundChannel:
    resolved = settings or get_settings()
    if resolved.notification_channel == "log":
        return LoggingChannel()
    if resolved.notification_channel == "smtp":
        return SmtpChannel(resolved)
    if resolved.notification_channel == "webhook":
        return WebhookChannel(resolved)
    raise AssertionError("validated notification channel is unsupported")
