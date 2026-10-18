import json

import httpx
import pytest

from skylark.datasets import load_dataset
from skylark.provider import BASE_URL, Completion, NebiusProvider, ProviderError, billed_cost, parse_completion


def provider_with_transport(monkeypatch, handler):
    monkeypatch.setenv("NEBIUS_API_KEY", "fake-test-only-key")
    return NebiusProvider(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def completion_json(*, content='{"objects": []}', reason="stop", refusal=None):
    return {"id": "fake", "object": "chat.completion", "created": 1, "model": "fixture/model",
            "choices": [{"index": 0, "finish_reason": reason,
                         "message": {"role": "assistant", "content": content, "refusal": refusal}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}}


def test_catalog_uses_public_endpoint_and_whitelists_metadata(monkeypatch):
    def handler(request):
        assert str(request.url) == BASE_URL + "models?verbose=true"
        return httpx.Response(200, json={"object": "list", "data": [
            {"id": "nvidia/example", "object": "model", "created": 0, "owned_by": "nvidia",
             "pricing": {"prompt": "0.000001"}, "private_extra": "must not be displayed"}]})
    provider = provider_with_transport(monkeypatch, handler)
    try:
        models = provider.discover()
        assert models[0]["pricing"]["prompt"] == "0.000001"
        assert "private_extra" not in models[0]
    finally:
        provider.client.close()


@pytest.mark.parametrize("response_format", ["json_object", "json_schema", "prompt_only"])
def test_image_contract_and_reported_usage(monkeypatch, manifest, config, response_format):
    _, images = load_dataset(manifest)
    image = images["fixture-0"]
    settings = config.models[0].model_copy(update={"response_format": response_format})
    def handler(request):
        assert str(request.url) == BASE_URL + "chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == settings.model
        assert payload["max_tokens"] == settings.max_output_tokens
        assert "640 by 400" in payload["messages"][0]["content"]
        assert "PIXEL" in payload["messages"][0]["content"]
        assert payload["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        # Only the task/classes/image are transmitted: no reference annotations.
        assert "ground_truth" not in request.content.decode()
        if response_format == "prompt_only":
            assert "response_format" not in payload
        else:
            assert payload["response_format"]["type"] == response_format
        return httpx.Response(200, json=completion_json())
    provider = provider_with_transport(monkeypatch, handler)
    try:
        response = provider.label(image, ["apple"], "Label visible apples", settings)
        assert parse_completion(response, image, ["apple"]) == []
        assert billed_cost(response, settings) == pytest.approx(
            (120 * settings.input_usd_per_million + 40 * settings.output_usd_per_million) / 1_000_000)
    finally:
        provider.client.close()


@pytest.mark.parametrize("status,retryable", [(401, False), (402, False), (429, True), (503, True)])
def test_http_errors_sanitized_and_sdk_does_not_retry(monkeypatch, manifest, config, status, retryable):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "private-response-content"}})
    _, images = load_dataset(manifest)
    provider = provider_with_transport(monkeypatch, handler)
    try:
        with pytest.raises(ProviderError) as error:
            provider.label(images["fixture-0"], ["apple"], "test", config.models[0])
        assert error.value.retryable is retryable
        assert "private-response-content" not in str(error.value)
        assert "fake-test-only-key" not in str(error.value)
        assert len(calls) == 1
    finally:
        provider.client.close()


def test_timeout_is_uncertain_and_key_is_required(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("secret details", request=request)
    provider = provider_with_transport(monkeypatch, handler)
    try:
        with pytest.raises(ProviderError, match="billing is unconfirmed"):
            provider.discover()
    finally:
        provider.client.close()
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_TOKEN_FACTORY_KEY", raising=False)
    with pytest.raises(ValueError, match="Set NEBIUS_API_KEY"):
        NebiusProvider()


@pytest.mark.parametrize("content,reason", [
    ('```json\n{"objects": []}\n```', "stop"),
    ('{"objects": []}', "length"),
    ('{"objects": [{"label":"apple","bbox":[0,0,900,10]}]}', "stop"),
    ('{"objects": [{"label":"banana","bbox":[0,0,10,10]}]}', "stop"),
])
def test_malformed_truncated_or_invented_predictions_rejected(manifest, content, reason):
    _, images = load_dataset(manifest)
    with pytest.raises(ValueError):
        parse_completion(Completion(content, 100, 10, .1, reason), images["fixture-0"], ["apple"])


def test_missing_usage_never_assumed_free(config):
    assert billed_cost(Completion('{"objects": []}', None, None, .1), config.models[0]) is None
