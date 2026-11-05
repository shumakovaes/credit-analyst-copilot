import json
import httpx
import pytest

from credit_copilot.providers import LiveProvider, ProviderError, plan
from credit_copilot.settings import Settings


def settings(**values):
    return Settings(_env_file=None, provider="live", llm_model="test-model", llm_api_key="unit-test-secret", **values)


@pytest.mark.parametrize("style", ["chat_completions", "responses"])
def test_live_adapter_schema_and_response_parsing(style):
    expected = plan("SELECT COUNT(*) AS n FROM copilot_data.loans")
    captured = []
    def respond(request):
        body = json.loads(request.content)
        captured.append(body)
        assert body["model"] == "test-model" and body["store"] is False
        if style == "responses":
            assert body["text"]["format"]["strict"] is True
            result = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": expected.model_dump_json()}]}]}
        else:
            assert body["response_format"]["json_schema"]["strict"] is True
            result = {"choices": [{"finish_reason": "stop", "message": {"content": expected.model_dump_json()}}]}
        return httpx.Response(200, json=result)
    actual = LiveProvider(settings(llm_api_style=style), httpx.MockTransport(respond)).generate("Сколько?", [])
    assert actual == expected and len(captured) == 1


def test_provider_errors_redact_vendor_body_and_credentials():
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text="unit-test-secret vendor-private-info"))
    with pytest.raises(ProviderError) as err:
        LiveProvider(settings(), transport).generate("test", [])
    assert "401" in str(err.value) and "unit-test-secret" not in str(err.value) and "private" not in str(err.value)


def test_invalid_json_fails_closed():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "DELETE FROM loans"}}]}))
    with pytest.raises(ProviderError):
        LiveProvider(settings(), transport).generate("test", [])


def test_network_timeout_is_bounded_error():
    def timeout(request):
        raise httpx.ReadTimeout("vendor-private", request=request)
    with pytest.raises(ProviderError, match="время ожидания"):
        LiveProvider(settings(), httpx.MockTransport(timeout)).generate("test", [])


def test_missing_key_does_not_fall_back_to_demo():
    with pytest.raises(ProviderError):
        LiveProvider(Settings(_env_file=None, provider="live"))
