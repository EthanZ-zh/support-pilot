from __future__ import annotations

from uuid import uuid4

import pytest

from support_pilot.channels.base import ChannelDeliveryError, TicketEvent
from support_pilot.channels.factory import get_outbound_channel
from support_pilot.channels.log import LoggingChannel
from support_pilot.channels.smtp import SmtpChannel
from support_pilot.channels.webhook import WebhookChannel
from support_pilot.config import Settings


def _event(*, assignee_email: str | None = None) -> TicketEvent:
    return TicketEvent(
        event_type="ticket_created",
        ticket_id=uuid4(),
        public_code="TKT-ABC123",
        tenant_id=uuid4(),
        status="OPEN",
        summary="bulk_export 不可用，需要人工排查",
        assignee_email=assignee_email,
    )


def test_event_payload_contains_structured_fields() -> None:
    payload = _event().to_payload()
    assert payload["public_code"] == "TKT-ABC123"
    assert payload["event"] == "ticket_created"
    assert payload["assignee"] == ""


def test_logging_channel_delivers_without_error(caplog: pytest.LogCaptureFixture) -> None:
    channel = LoggingChannel()
    with caplog.at_level("INFO", logger="support_pilot.channels"):
        channel.deliver(_event())
    assert "TKT-ABC123" in caplog.text


def test_factory_returns_logging_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPPORT_PILOT_NOTIFICATION_CHANNEL", "log")
    assert isinstance(get_outbound_channel(), LoggingChannel)


def test_smtp_channel_requires_configuration() -> None:
    with pytest.raises(ValueError, match="SMTP"):
        SmtpChannel(Settings(notification_channel="smtp"))


def test_smtp_build_message_content() -> None:
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
        smtp_to_email="ops@example.com",
    )
    message = SmtpChannel(settings)._build_message(_event(assignee_email="agent@example.com"))
    assert message["Subject"] == "[SupportPilot] ticket_created TKT-ABC123"
    assert message["To"] == "ops@example.com, agent@example.com"
    assert "bulk_export 不可用" in message.get_content()


def test_smtp_deliver_uses_mocked_client(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[object] = []

    class FakeSmtp:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        def __enter__(self) -> FakeSmtp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def starttls(self) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            return None

        def send_message(self, message: object) -> None:
            sent.append(message)

    monkeypatch.setattr("support_pilot.channels.smtp.smtplib.SMTP", FakeSmtp)
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
        smtp_to_email="ops@example.com",
    )
    SmtpChannel(settings).deliver(_event())
    assert len(sent) == 1


def test_smtp_requires_at_least_one_recipient() -> None:
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
    )
    channel = SmtpChannel(settings)
    with pytest.raises(ValueError, match="SMTP_TO_EMAIL"):
        channel._recipients(_event())


def test_webhook_channel_requires_url() -> None:
    with pytest.raises(ValueError, match="WEBHOOK_URL"):
        WebhookChannel(Settings(notification_channel="webhook"))


def test_webhook_payload_shape() -> None:
    settings = Settings(notification_channel="webhook", webhook_url="https://hook.example/x")
    payload = WebhookChannel(settings)._build_payload(_event())
    assert payload["msgtype"] == "text"
    assert "TKT-ABC123" in payload["text"]["content"]  # type: ignore[index]


def test_webhook_deliver_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, *, json: dict[str, object], timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("support_pilot.channels.webhook.httpx.post", fake_post)
    settings = Settings(notification_channel="webhook", webhook_url="https://hook.example/x")
    WebhookChannel(settings).deliver(_event())
    assert captured["url"] == "https://hook.example/x"
    assert captured["json"]["support_pilot_event"]["public_code"] == "TKT-ABC123"  # type: ignore[index]


def test_webhook_deliver_wraps_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def failing_post(url: str, *, json: dict[str, object], timeout: float) -> None:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("support_pilot.channels.webhook.httpx.post", failing_post)
    settings = Settings(notification_channel="webhook", webhook_url="https://hook.example/x")
    with pytest.raises(ChannelDeliveryError, match="Webhook"):
        WebhookChannel(settings).deliver(_event())


def test_factory_rejects_unknown_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPPORT_PILOT_NOTIFICATION_CHANNEL", "sms")
    with pytest.raises(ValueError, match="notification_channel"):
        Settings()


def test_settings_validates_channel_values() -> None:
    with pytest.raises(ValueError, match="notification_channel"):
        Settings(notification_channel="sms")
