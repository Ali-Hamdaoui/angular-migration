import http.client
import json
from contextlib import contextmanager

import pytest

from app.llm_gateway.azure_gateway import AzureGatewayError, UrllibAzureTransport, _extract_structured_output, _validate_response_state


class Response:
    def __init__(self, body: bytes, *, content_type="application/json", content_length=None):
        self.body = body
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        value, self.body = self.body[:size], self.body[size:]
        return value

    def close(self):
        return None


def transport(monkeypatch, response):
    monkeypatch.setattr("app.llm_gateway.azure_gateway.urllib.request.urlopen", lambda *args, **kwargs: response)
    return UrllibAzureTransport()


def test_http_200_valid_object_is_staged(monkeypatch):
    result = transport(monkeypatch, Response(b'{"status":"completed"}')).request(endpoint="https://resource.openai.azure.com", api_key="secret", api_version="v1", deployment="d", payload={}, timeout=1)
    assert result["status"] == "completed"


@pytest.mark.parametrize("body,stage", [(b"<html>gateway</html>", "response_json_decode"), (b"", "response_body_read"), (b"{bad", "response_json_decode"), (b"\xff", "response_decode")])
def test_http_200_bad_body_is_typed_and_never_contains_body(monkeypatch, body, stage):
    with pytest.raises(AzureGatewayError) as caught:
        transport(monkeypatch, Response(body, content_type="text/html" if body.startswith(b"<") else "application/json")).request(endpoint="https://resource.openai.azure.com", api_key="secret", api_version="v1", deployment="d", payload={}, timeout=1)
    error = caught.value
    assert error.failure_stage == stage
    decoded = body.decode("utf-8", errors="ignore")
    if decoded:
        assert decoded not in str(error)
    assert error.response_sha256 or not body


def test_truncated_body_is_not_a_fake_provider_error(monkeypatch):
    with pytest.raises(AzureGatewayError) as caught:
        transport(monkeypatch, Response(b'{"status":', content_length=100)).request(endpoint="https://resource.openai.azure.com", api_key="secret", api_version="v1", deployment="d", payload={}, timeout=1)
    assert caught.value.response_kind == "truncated"
    assert caught.value.failure_stage == "response_body_read"
    assert caught.value.provider_status is None


@pytest.mark.parametrize("status,expected", [(400, "invalid_request"), (401, "authentication"), (403, "authorization"), (404, "deployment"), (408, "timeout"), (429, "rate_limit"), (500, "server")])
def test_http_error_status_is_preserved_without_raw_body(monkeypatch, status, expected):
    error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError("https://resource.openai.azure.com", status, "x", {"Content-Type": "application/json", "x-ms-request-id": "rid"}, Response(b'{"error":{"code":"bad","message":"private"}}'))
    monkeypatch.setattr("app.llm_gateway.azure_gateway.urllib.request.urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(AzureGatewayError) as caught:
        UrllibAzureTransport().request(endpoint="https://resource.openai.azure.com", api_key="secret", api_version="v1", deployment="d", payload={}, timeout=1)
    assert caught.value.code.value == expected
    assert caught.value.provider_request_id == "rid"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("status,subtype", [("failed", "LLM_RESPONSE_FAILED"), ("incomplete", "LLM_RESPONSE_INCOMPLETE"), ("in_progress", "LLM_RESPONSE_INCOMPLETE")])
def test_responses_status_is_not_treated_as_completed(status, subtype):
    with pytest.raises(AzureGatewayError) as caught:
        _validate_response_state({"status": status, "incomplete_details": {"reason": "max_output_tokens"}})
    assert caught.value.failure_subtype == subtype


def test_output_search_does_not_assume_first_item_is_assistant():
    result = _extract_structured_output({"status": "completed", "output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": '{"answer":"ok"}'}]}]})
    assert result == {"answer": "ok"}


def test_missing_usage_is_typed():
    from app.llm_gateway.azure_gateway import _extract_usage
    with pytest.raises(AzureGatewayError) as caught:
        _extract_usage({"status": "completed"})
    assert caught.value.code.value == "protocol"
