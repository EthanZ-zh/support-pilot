from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate

from support_pilot.channels.base import ChannelDeliveryError, TicketEvent
from support_pilot.config import Settings


class SmtpChannel:
    name = "smtp"

    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise ValueError("SMTP notification channel requires SMTP_HOST and SMTP_FROM_EMAIL")
        self._settings = settings

    def deliver(self, event: TicketEvent) -> None:
        message = self._build_message(event)
        try:
            with smtplib.SMTP(
                self._settings.smtp_host,
                self._settings.smtp_port,
                timeout=self._settings.channel_request_timeout_seconds,
            ) as client:
                if self._settings.smtp_use_tls:
                    client.starttls()
                if self._settings.smtp_username:
                    client.login(self._settings.smtp_username, self._settings.smtp_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            raise ChannelDeliveryError("SMTP delivery failed") from error

    def _build_message(self, event: TicketEvent) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = f"[SupportPilot] {event.event_type} {event.public_code}"
        message["From"] = self._settings.smtp_from_email
        message["To"] = ", ".join(self._recipients(event))
        message["Date"] = formatdate(localtime=True)
        message.set_content(
            "\n".join(
                (
                    f"Ticket: {event.public_code}",
                    f"Event: {event.event_type}",
                    f"Status: {event.status}",
                    f"Summary: {event.summary}",
                    f"Tenant: {event.tenant_id}",
                    f"Time: {event.occurred_at.isoformat()}",
                )
            )
        )
        return message

    def _recipients(self, event: TicketEvent) -> list[str]:
        configured = self._settings.smtp_to_email.split(",")
        recipients = [email.strip() for email in configured if email.strip()]
        if event.assignee_email and event.assignee_email not in recipients:
            recipients.append(event.assignee_email)
        if not recipients:
            raise ValueError("SMTP notification channel requires SMTP_TO_EMAIL or assignee_email")
        return recipients
