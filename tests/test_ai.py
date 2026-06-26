"""Tests for the multi-provider AI chat client (mocked, no network)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

pytest.importorskip("PySide6")  # ai ships in the gui package
from vcds_gui import ai  # noqa: E402


class FakeResp:
    def __init__(self, data: dict):
        self._d = json.dumps(data).encode("utf-8")

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _msgs():
    return [{"role": "user", "content": "Why is my boost low?"}]


def test_anthropic_request_and_parse():
    seen = {}

    def opener(req, timeout):
        seen["url"] = req.full_url
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = json.loads(req.data)
        return FakeResp({"content": [{"type": "text", "text": "Likely a boost leak."}]})

    out = ai.chat("anthropic", "KEY", "claude-x", "sys-context", _msgs(), opener=opener)
    assert out == "Likely a boost leak."
    assert "api.anthropic.com" in seen["url"]
    assert seen["headers"]["x-api-key"] == "KEY"
    assert seen["body"]["system"] == "sys-context"


def test_openai_request_and_parse():
    def opener(req, timeout):
        body = json.loads(req.data)
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        assert "Bearer K" in dict((k.lower(), v) for k, v in req.header_items())["authorization"]
        return FakeResp({"choices": [{"message": {"content": "GPT reply"}}]})

    assert ai.chat("openai", "K", "gpt-4o", "sys", _msgs(), opener=opener) == "GPT reply"


def test_gemini_request_and_parse():
    def opener(req, timeout):
        assert "generativelanguage.googleapis.com" in req.full_url
        assert "key=K" in req.full_url
        body = json.loads(req.data)
        assert body["systemInstruction"]["parts"][0]["text"] == "sys"
        return FakeResp({"candidates": [{"content": {"parts": [{"text": "Gemini reply"}]}}]})

    assert ai.chat("gemini", "K", "gemini-2.0-flash", "sys", _msgs(), opener=opener) == "Gemini reply"


def test_missing_key_raises():
    with pytest.raises(RuntimeError, match="API key"):
        ai.chat("openai", "", "m", "", _msgs())


def test_http_error_is_surfaced():
    def opener(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":"invalid key"}')
        )

    with pytest.raises(RuntimeError, match="401"):
        ai.chat("anthropic", "K", "m", "", _msgs(), opener=opener)


_TOOLS = [{"name": "list_logs", "description": "list logs",
           "parameters": {"type": "object", "properties": {}, "required": []}}]


def _seq_opener(responses):
    it = iter(responses)

    def opener(req, timeout):
        return FakeResp(next(it))

    return opener


def test_anthropic_tool_loop():
    opener = _seq_opener([
        {"stop_reason": "tool_use",
         "content": [{"type": "tool_use", "id": "t1", "name": "list_logs", "input": {}}]},
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "You have 2 logs."}]},
    ])
    seen = {}

    def executor(name, args):
        seen["name"] = name
        return {"count": 2}

    out = ai.chat("anthropic", "K", "m", "sys", _msgs(), opener=opener,
                  tools=_TOOLS, tool_executor=executor)
    assert out == "You have 2 logs." and seen["name"] == "list_logs"


def test_openai_tool_loop():
    opener = _seq_opener([
        {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "list_logs", "arguments": "{}"}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "2 logs."}}]},
    ])
    out = ai.chat("openai", "K", "m", "sys", _msgs(), opener=opener,
                  tools=_TOOLS, tool_executor=lambda n, a: {"count": 2})
    assert out == "2 logs."


def test_gemini_tool_loop():
    opener = _seq_opener([
        {"candidates": [{"content": {"parts": [{"functionCall": {"name": "list_logs", "args": {}}}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "2 logs."}]}}]},
    ])
    out = ai.chat("gemini", "K", "m", "sys", _msgs(), opener=opener,
                  tools=_TOOLS, tool_executor=lambda n, a: {"count": 2})
    assert out == "2 logs."


def test_providers_have_defaults():
    for prov in ai.PROVIDERS.values():
        assert prov.default_model in prov.models
        assert prov.key_url.startswith("https://")
