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


class FakeStream:
    def __init__(self, lines):
        self._lines = [(line + "\n").encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._lines)


def _sse_opener(rounds):
    """rounds: list of line-lists, one per HTTP call."""
    it = iter(rounds)

    def opener(req, timeout):
        return FakeStream(next(it))

    return opener


def test_anthropic_stream_text():
    lines = [
        'data: {"type":"content_block_start","content_block":{"type":"text"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello "}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"world"}}',
        'data: {"type":"content_block_stop"}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
    ]
    deltas = []
    out = ai.chat("anthropic", "K", "m", "sys", _msgs(),
                  opener=_sse_opener([lines]), on_delta=deltas.append)
    assert "".join(deltas) == "Hello world" and out == "Hello world"


def test_anthropic_stream_with_tool():
    r1 = [
        'data: {"type":"content_block_start","content_block":{"type":"tool_use","id":"t1","name":"list_logs"}}',
        'data: {"type":"content_block_delta","delta":{"type":"input_json_delta","partial_json":"{}"}}',
        'data: {"type":"content_block_stop"}',
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}',
    ]
    r2 = [
        'data: {"type":"content_block_start","content_block":{"type":"text"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Done."}}',
        'data: {"type":"content_block_stop"}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
    ]
    seen = {}
    out = ai.chat("anthropic", "K", "m", "sys", _msgs(), opener=_sse_opener([r1, r2]),
                  tools=_TOOLS, tool_executor=lambda n, a: seen.setdefault("n", n) or {"ok": 1},
                  on_delta=lambda c: None)
    assert seen["n"] == "list_logs" and out == "Done."


def test_openai_stream_text_and_tool():
    text = [
        'data: {"choices":[{"delta":{"content":"Hi "}}]}',
        'data: {"choices":[{"delta":{"content":"there"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    out = ai.chat("openai", "K", "m", "sys", _msgs(), opener=_sse_opener([text]),
                  on_delta=lambda c: None)
    assert out == "Hi there"

    r1 = [
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"list_logs","arguments":""}}]}}]}',
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]},"finish_reason":"tool_calls"}]}',
    ]
    r2 = ['data: {"choices":[{"delta":{"content":"Done."},"finish_reason":"stop"}]}']
    seen = {}
    out = ai.chat("openai", "K", "m", "sys", _msgs(), opener=_sse_opener([r1, r2]),
                  tools=_TOOLS, tool_executor=lambda n, a: seen.setdefault("n", n) or {"ok": 1},
                  on_delta=lambda c: None)
    assert seen["n"] == "list_logs" and out == "Done."


def test_gemini_stream_text_and_tool():
    text = [
        'data: {"candidates":[{"content":{"parts":[{"text":"Hi "}]}}]}',
        'data: {"candidates":[{"content":{"parts":[{"text":"there"}]}}]}',
    ]
    out = ai.chat("gemini", "K", "m", "sys", _msgs(), opener=_sse_opener([text]),
                  on_delta=lambda c: None)
    assert out == "Hi there"

    r1 = ['data: {"candidates":[{"content":{"parts":[{"functionCall":{"name":"list_logs","args":{}}}]}}]}']
    r2 = ['data: {"candidates":[{"content":{"parts":[{"text":"Done."}]}}]}']
    seen = {}
    out = ai.chat("gemini", "K", "m", "sys", _msgs(), opener=_sse_opener([r1, r2]),
                  tools=_TOOLS, tool_executor=lambda n, a: seen.setdefault("n", n) or {"ok": 1},
                  on_delta=lambda c: None)
    assert seen["n"] == "list_logs" and out == "Done."


def test_providers_have_defaults():
    for prov in ai.PROVIDERS.values():
        assert prov.default_model in prov.models
        assert prov.key_url.startswith("https://")
