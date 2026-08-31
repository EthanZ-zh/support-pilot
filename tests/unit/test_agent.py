import json

import httpx
import pytest
from pydantic import SecretStr

from support_pilot.agent.contracts import AgentRequest, ModelUsage
from support_pilot.agent.providers import (
    DeterministicDecisionProvider,
    ProviderConfigurationError,
    ProviderResponseError,
    QwenDecisionProvider,
    RetryingDecisionProvider,
    get_decision_provider,
)
from support_pilot.config import Settings


class AlwaysFailProvider:
    provider_name = "failing"
    model_name = "failing-v1"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def usage(self) -> ModelUsage:
        return ModelUsage()

    def decide(self, request: AgentRequest):  # type: ignore[no-untyped-def]
        self.calls += 1
        raise RuntimeError("provider unavailable")


def test_high_risk_rule_precedes_other_routes() -> None:
    decision = DeterministicDecisionProvider().decide(
        AgentRequest(message="请直接退款，并顺便创建工单")
    )

    assert decision.intent == "high_risk"
    assert decision.confidence == 1.0


def test_provider_retry_is_finite() -> None:
    provider = AlwaysFailProvider()

    with pytest.raises(RuntimeError, match="provider unavailable"):
        RetryingDecisionProvider(provider, max_attempts=2).decide(
            AgentRequest(message="为什么 webhook 验签失败？")
        )

    assert provider.calls == 2


def test_qwen_provider_sends_strict_schema_and_parses_usage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "intent": "quota",
                                    "confidence": 0.97,
                                    "reason": "user_asks_for_usage_limit",
                                }
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
        )

    provider = QwenDecisionProvider(
        api_key="unit-test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        transport=httpx.MockTransport(handler),
    )

    decision = provider.decide(
        AgentRequest(
            message="我想查看本月配额，Bearer abcdefghijk 不应外发",
            context={"metric_code": "api_requests_monthly"},
        )
    )

    assert decision.intent == "quota"
    assert provider.usage.model_calls == 1
    assert provider.usage.total_tokens == 120
    assert provider.usage.estimated_cost_cny == pytest.approx(0.00036)
    assert captured["authorization"] == "Bearer unit-test-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "qwen3.7-plus"
    assert payload["enable_thinking"] is False
    assert "max_tokens" not in payload
    response_format = payload["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["json_schema"]["strict"] is True
    user_message = json.loads(payload["messages"][1]["content"])
    assert user_message["context_fields_present"] == ["metric_code"]
    assert "tenant_id" not in user_message
    assert "abcdefghijk" not in user_message["message"]
    assert "[REDACTED]" in user_message["message"]


def test_qwen_provider_rejects_invalid_structured_response() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )
    )
    provider = QwenDecisionProvider(
        api_key="unit-test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        transport=transport,
    )

    with pytest.raises(ProviderResponseError, match="qwen_invalid_structured_response"):
        provider.decide(AgentRequest(message="查询一个问题"))


def test_qwen_factory_requires_key_and_keeps_secret_masked() -> None:
    missing_key = Settings(_env_file=None, agent_provider="qwen", qwen_api_key=None)
    with pytest.raises(ProviderConfigurationError, match="QWEN_API_KEY"):
        get_decision_provider(missing_key)

    settings = Settings(
        _env_file=None,
        agent_provider="qwen",
        qwen_api_key=SecretStr("unit-test-key"),
    )
    provider = get_decision_provider(settings)

    assert provider.provider_name == "qwen"
    assert "unit-test-key" not in repr(settings.qwen_api_key)

    standard_alias = Settings(
        _env_file=None,
        agent_provider="qwen",
        DASHSCOPE_API_KEY="standard-unit-test-key",
    )
    assert standard_alias.qwen_api_key is not None
    assert standard_alias.qwen_api_key.get_secret_value() == "standard-unit-test-key"


def test_qwen_provider_rejects_non_model_studio_base_url() -> None:
    with pytest.raises(ProviderConfigurationError, match="Beijing Model Studio"):
        QwenDecisionProvider(
            api_key="unit-test-key",
            base_url="https://example.com/compatible-mode/v1",
        )


def test_qwen_retry_accumulates_billed_usage() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        content = (
            "not-json"
            if call_count == 1
            else json.dumps(
                {
                    "intent": "knowledge",
                    "confidence": 0.91,
                    "reason": "documentation_question",
                }
            )
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 10,
                    "total_tokens": 60,
                },
            },
        )

    provider = RetryingDecisionProvider(
        QwenDecisionProvider(
            api_key="unit-test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            transport=httpx.MockTransport(handler),
        ),
        max_attempts=2,
    )

    decision = provider.decide(AgentRequest(message="Webhook 如何验签？"))

    assert decision.intent == "knowledge"
    assert provider.usage.model_calls == 2
    assert provider.usage.input_tokens == 100
    assert provider.usage.output_tokens == 20
    assert provider.usage.total_tokens == 120
