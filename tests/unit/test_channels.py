from __future__ import annotations

import ssl
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from support_pilot.application.contracts import TicketInput
from support_pilot.application.services import SupportService
from support_pilot.channels.base import ChannelDeliveryError, TicketEvent
from support_pilot.channels.factory import get_outbound_channel
from support_pilot.channels.log import LoggingChannel
from support_pilot.channels.smtp import SmtpChannel
from support_pilot.channels.webhook import WebhookChannel
from support_pilot.config import Settings
from support_pilot.domain.enums import IdempotencyStatus


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
    credentials: list[tuple[str, str]] = []
    tls_contexts: list[ssl.SSLContext | None] = []

    class FakeSmtp:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        def __enter__(self) -> FakeSmtp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def starttls(self, context: ssl.SSLContext | None = None) -> None:
            tls_contexts.append(context)

        def login(self, username: str, password: str) -> None:
            credentials.append((username, password))

        def send_message(self, message: object) -> None:
            sent.append(message)

    monkeypatch.setattr("support_pilot.channels.smtp.smtplib.SMTP", FakeSmtp)
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
        smtp_to_email="ops@example.com",
        smtp_username="mailer",
        smtp_password="smtp-secret",
    )
    SmtpChannel(settings).deliver(_event())
    assert len(sent) == 1
    assert credentials == [("mailer", "smtp-secret")]
    assert len(tls_contexts) == 1
    assert tls_contexts[0] is not None
    assert tls_contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert tls_contexts[0].check_hostname is True


@pytest.mark.parametrize("port", [0, 65_536])
def test_settings_rejects_invalid_smtp_ports(port: int) -> None:
    with pytest.raises(ValueError, match="smtp_port"):
        Settings(smtp_port=port)


def test_smtp_requires_to_email_at_construction() -> None:
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
    )
    with pytest.raises(ValueError, match="SMTP_TO_EMAIL"):
        SmtpChannel(settings)


def test_smtp_rejects_authenticated_connection_without_tls() -> None:
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
        smtp_to_email="ops@example.com",
        smtp_username="mailer",
        smtp_password="smtp-secret",
        smtp_use_tls=False,
    )
    with pytest.raises(ValueError, match="TLS"):
        SmtpChannel(settings)


def test_smtp_password_is_not_exposed() -> None:
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
        smtp_to_email="ops@example.com",
        smtp_password="smtp-secret",
    )
    assert isinstance(settings.smtp_password, SecretStr)
    assert "smtp-secret" not in repr(settings)
    assert "smtp-secret" not in repr(settings.model_dump())


def test_smtp_delivery_wraps_message_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        notification_channel="smtp",
        smtp_host="smtp.example.com",
        smtp_from_email="support@example.com",
        smtp_to_email="ops@example.com",
    )
    channel = SmtpChannel(settings)

    def fail_build(event: TicketEvent) -> object:
        raise ValueError("bad message configuration")

    monkeypatch.setattr(channel, "_build_message", fail_build)
    with pytest.raises(ChannelDeliveryError, match="SMTP delivery failed"):
        channel.deliver(_event())


def test_webhook_channel_requires_url() -> None:
    with pytest.raises(ValueError, match="WEBHOOK_URL"):
        WebhookChannel(Settings(notification_channel="webhook"))


def test_webhook_payload_shape() -> None:
    settings = Settings(
        notification_channel="webhook",
        webhook_url="https://hook.example/x",
        webhook_allowed_hosts=["hook.example"],
    )
    payload = WebhookChannel(settings)._build_payload(_event())
    assert payload["msgtype"] == "text"
    assert "TKT-ABC123" in payload["text"]["content"]  # type: ignore[index]


def test_webhook_deliver_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
        trust_env: bool,
    ) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["trust_env"] = trust_env
        return FakeResponse()

    monkeypatch.setattr("support_pilot.channels.webhook.httpx.post", fake_post)
    settings = Settings(
        notification_channel="webhook",
        webhook_url="https://hook.example/x",
        webhook_allowed_hosts=["hook.example"],
    )
    WebhookChannel(settings).deliver(_event())
    assert captured["url"] == "https://hook.example/x"
    assert captured["trust_env"] is False
    assert captured["json"]["support_pilot_event"]["public_code"] == "TKT-ABC123"  # type: ignore[index]


def test_webhook_deliver_wraps_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def failing_post(
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
        trust_env: bool,
    ) -> None:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("support_pilot.channels.webhook.httpx.post", failing_post)
    settings = Settings(
        notification_channel="webhook",
        webhook_url="https://hook.example/x",
        webhook_allowed_hosts=["hook.example"],
    )
    with pytest.raises(ChannelDeliveryError, match="Webhook"):
        WebhookChannel(settings).deliver(_event())


@pytest.mark.parametrize(
    ("url", "allowed_hosts"),
    [
        ("http://hook.example/x", ["hook.example"]),
        ("https://user:password@hook.example/x", ["hook.example"]),
        ("https://127.0.0.1/x", ["127.0.0.1"]),
        ("https://10.0.0.8/x", ["10.0.0.8"]),
        ("https://169.254.169.254/x", ["169.254.169.254"]),
        ("https://224.0.0.1/x", ["224.0.0.1"]),
        ("https://100.64.0.1/x", ["100.64.0.1"]),
        ("https://127.0.0.1./x", ["127.0.0.1"]),
        ("https://other.example/x", ["hook.example"]),
    ],
)
def test_webhook_rejects_unsafe_or_unapproved_urls(
    url: str, allowed_hosts: list[str]
) -> None:
    settings = Settings(
        notification_channel="webhook",
        webhook_url=url,
        webhook_allowed_hosts=allowed_hosts,
    )
    with pytest.raises(ValueError, match="Webhook"):
        WebhookChannel(settings)


def test_webhook_allows_an_explicit_global_literal_ip() -> None:
    settings = Settings(
        notification_channel="webhook",
        webhook_url="https://93.184.216.34/x",
        webhook_allowed_hosts=["93.184.216.34"],
    )
    WebhookChannel(settings)


def test_webhook_url_is_not_exposed() -> None:
    settings = Settings(
        notification_channel="webhook",
        webhook_url="https://hook.example/x?token=webhook-secret",
        webhook_allowed_hosts=["hook.example"],
    )
    assert isinstance(settings.webhook_url, SecretStr)
    assert "webhook-secret" not in repr(settings)
    assert "webhook-secret" not in repr(settings.model_dump())


def test_factory_rejects_unknown_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPPORT_PILOT_NOTIFICATION_CHANNEL", "sms")
    with pytest.raises(ValueError, match="notification_channel"):
        Settings()


def test_settings_validates_channel_values() -> None:
    with pytest.raises(ValueError, match="notification_channel"):
        Settings(notification_channel="sms")


class _FakeSession:
    def __init__(self) -> None:
        self.scalar_calls = 0
        self.commits = 0
        self.added: list[object] = []
        self.existing: object | None = None
        self.tickets: dict[object, object] = {}
        self.request_hash: str | None = None

    def add(self, value: object) -> None:
        self.added.append(value)
        if hasattr(value, "id") and value.id is None:  # type: ignore[attr-defined]
            value.id = uuid4()  # type: ignore[attr-defined]
        if hasattr(value, "public_code"):
            self.tickets[value.id] = value  # type: ignore[attr-defined]

    def flush(self) -> None:
        return None

    def scalar(self, _statement: object) -> object | None:
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            self.request_hash = _statement.compile().params["request_hash"]  # type: ignore[attr-defined]
            return "inserted"
        if self.scalar_calls == 2:
            return None
        return self.existing

    def execute(self, _statement: object) -> None:
        ticket = next((item for item in self.added if hasattr(item, "public_code")), None)
        if ticket is not None and self.existing is None:
            self.existing = SimpleNamespace(
                request_hash=self.request_hash,
                status=IdempotencyStatus.SUCCEEDED.value,
                resource_id=ticket.id,  # type: ignore[attr-defined]
            )
        return None

    def commit(self) -> None:
        self.commits += 1


class _FailingChannel:
    name = "failing"

    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.deliveries = 0
        self.commits_at_delivery: list[int] = []

    def deliver(self, event: TicketEvent) -> None:
        self.deliveries += 1
        self.commits_at_delivery.append(self.session.commits)
        assert self.session.commits >= 1
        raise ChannelDeliveryError("external failure")


def test_service_commits_before_delivery_failure_and_skips_replay(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession()
    channel = _FailingChannel(session)
    service = SupportService(session, channel=channel)  # type: ignore[arg-type]
    tenant_id = uuid4()
    actor = SimpleNamespace(id=uuid4(), tenant_id=tenant_id)
    tenant = SimpleNamespace(id=tenant_id)
    service._authorize_tenant = lambda **_kwargs: tenant  # type: ignore[method-assign]
    request = TicketInput(
        intent="ticket_request",
        message="please open a ticket",
        tenant_id=tenant_id,
        summary="API returns 403",
        description="Requests fail consistently.",
        category="authentication",
        severity="high",
        escalation_reason="user_requested",
    )

    with caplog.at_level("WARNING", logger="support_pilot.application.services"):
        first = service.process(request, actor=actor, idempotency_key="ticket-001")

    ticket = next(item for item in session.added if hasattr(item, "public_code"))
    service.repository.get_ticket = lambda ticket_id: session.tickets[ticket_id]  # type: ignore[method-assign]
    replayed = service.process(request, actor=actor, idempotency_key="ticket-001")

    assert first.data["replayed"] is False
    assert replayed.data["replayed"] is True
    assert session.commits >= 2
    assert channel.deliveries == 1
    assert channel.commits_at_delivery == [1]
    assert ticket.public_code in caplog.text
