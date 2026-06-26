"""Multi-provider AI chat client (Anthropic / OpenAI / Google Gemini).

Thin REST clients over stdlib ``urllib`` — no provider SDKs — so it stays light
and bundles cleanly into the PyInstaller app. Qt-free and dependency-free, with
an injectable opener so it can be unit-tested without network access.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

_SSL_CTX: Optional[ssl.SSLContext] = None


def _ssl_context() -> Optional[ssl.SSLContext]:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        try:
            return ssl.create_default_context()
        except Exception:  # noqa: BLE001
            return None


def _default_opener(req, timeout):
    global _SSL_CTX
    if _SSL_CTX is None:
        _SSL_CTX = _ssl_context()
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)


@dataclass
class Provider:
    id: str
    label: str
    models: List[str]
    default_model: str
    key_url: str


PROVIDERS: Dict[str, Provider] = {
    "anthropic": Provider(
        "anthropic", "Anthropic (Claude)",
        ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "claude-sonnet-4-6", "https://console.anthropic.com/settings/keys",
    ),
    "openai": Provider(
        "openai", "OpenAI (GPT)",
        ["gpt-4o", "gpt-4o-mini", "o4-mini"],
        "gpt-4o", "https://platform.openai.com/api-keys",
    ),
    "gemini": Provider(
        "gemini", "Google (Gemini)",
        ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "gemini-2.0-flash", "https://aistudio.google.com/apikey",
    ),
}

Opener = Callable[..., object]
Message = Dict[str, str]  # {"role": "user"|"assistant", "content": str}


def _post_json(url: str, headers: dict, payload: dict, opener: Opener, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with opener(req, timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"{exc.code} {exc.reason}: {body[:400]}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from None


def _tool_result_str(result) -> str:
    s = json.dumps(result)
    return s if len(s) <= 8000 else s[:8000] + "…(truncated)"


def chat(
    provider_id: str,
    api_key: str,
    model: str,
    system: str,
    messages: List[Message],
    max_tokens: int = 1024,
    timeout: float = 90,
    opener: Optional[Opener] = None,
    tools: Optional[List[dict]] = None,
    tool_executor: Optional[Callable[[str, dict], object]] = None,
    max_tool_rounds: int = 6,
) -> str:
    """Send a chat conversation to a provider and return the assistant's reply.

    Args:
        provider_id: One of ``PROVIDERS``.
        api_key: The provider API key.
        model: Model id (see ``Provider.models``).
        system: System prompt (vehicle context).
        messages: Prior turns as ``{"role", "content"}`` dicts.
        tools: Optional neutral tool specs (``{name, description, parameters}``)
            the model may call; ``tool_executor(name, args)`` runs them locally.
    """
    if not api_key:
        raise RuntimeError("No API key set for this provider.")
    op = opener or _default_opener
    args = (api_key, model, system, messages, max_tokens, timeout, op, tools,
            tool_executor, max_tool_rounds)
    if provider_id == "anthropic":
        return _anthropic(*args)
    if provider_id == "openai":
        return _openai(*args)
    if provider_id == "gemini":
        return _gemini(*args)
    raise ValueError(f"Unknown provider: {provider_id}")


def _anthropic(api_key, model, system, messages, max_tokens, timeout, opener,
               tools, executor, rounds) -> str:
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    convo = list(messages)
    spec = [{"name": t["name"], "description": t["description"],
             "input_schema": t["parameters"]} for t in tools] if tools else None
    for _ in range(rounds if (tools and executor) else 1):
        payload = {"model": model, "max_tokens": max_tokens, "messages": convo}
        if system:
            payload["system"] = system
        if spec:
            payload["tools"] = spec
        data = _post_json("https://api.anthropic.com/v1/messages", headers, payload, opener, timeout)
        content = data.get("content", [])
        if data.get("stop_reason") == "tool_use" and executor:
            convo.append({"role": "assistant", "content": content})
            results = []
            for b in content:
                if b.get("type") == "tool_use":
                    out = executor(b.get("name"), b.get("input", {}))
                    results.append({"type": "tool_result", "tool_use_id": b.get("id"),
                                    "content": _tool_result_str(out)})
            convo.append({"role": "user", "content": results})
            continue
        return "".join(b.get("text", "") for b in content if b.get("type") == "text").strip() \
            or "(no response)"
    return "(stopped after tool rounds)"


def _openai(api_key, model, system, messages, max_tokens, timeout, opener,
            tools, executor, rounds) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    convo = ([{"role": "system", "content": system}] if system else []) + list(messages)
    spec = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
             "parameters": t["parameters"]}} for t in tools] if tools else None
    for _ in range(rounds if (tools and executor) else 1):
        payload = {"model": model, "messages": convo, "max_tokens": max_tokens}
        if spec:
            payload["tools"] = spec
        data = _post_json("https://api.openai.com/v1/chat/completions", headers, payload, opener, timeout)
        msg = data["choices"][0]["message"]
        calls = msg.get("tool_calls")
        if calls and executor:
            convo.append(msg)
            for tc in calls:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                out = executor(tc["function"]["name"], args)
                convo.append({"role": "tool", "tool_call_id": tc["id"],
                              "content": _tool_result_str(out)})
            continue
        return (msg.get("content") or "").strip()
    return "(stopped after tool rounds)"


def _gemini(api_key, model, system, messages, max_tokens, timeout, opener,
            tools, executor, rounds) -> str:
    contents = [{"role": "model" if m["role"] == "assistant" else "user",
                 "parts": [{"text": m["content"]}]} for m in messages]
    base = {"generationConfig": {"maxOutputTokens": max_tokens}}
    if system:
        base["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        base["tools"] = [{"functionDeclarations": [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in tools]}]
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
           f"?key={api_key}")
    for _ in range(rounds if (tools and executor) else 1):
        data = _post_json(url, {}, {**base, "contents": contents}, opener, timeout)
        cand = data["candidates"][0]["content"]
        parts = cand.get("parts", [])
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if calls and executor:
            contents.append(cand)
            resp = []
            for c in calls:
                out = executor(c.get("name"), c.get("args", {}))
                resp.append({"functionResponse": {"name": c.get("name"), "response": {"result": out}}})
            contents.append({"role": "user", "parts": resp})
            continue
        return "".join(p.get("text", "") for p in parts).strip()
    return "(stopped after tool rounds)"


SYSTEM_PREAMBLE = (
    "You are an expert VAG/Audi (Volkswagen Auto Group) diagnostic assistant "
    "embedded in the VCDS Toolkit app. Help the user diagnose their vehicle from "
    "the data below. Be specific and practical: name the most likely causes, the "
    "checks to confirm them, and typical fixes, ordered by likelihood. If the data "
    "is insufficient, say what to log next. Keep safety in mind."
)


def vehicle_system_prompt(context: str, persona: Optional[str] = None) -> str:
    """Wrap a diagnostic-context string in the assistant system prompt.

    Args:
        context: The current vehicle data block (may be empty).
        persona: Brand-specific system preamble (defaults to a generic one).
    """
    preamble = persona or SYSTEM_PREAMBLE
    if not context:
        return preamble + "\n\n(No vehicle data has been loaded yet.)"
    return preamble + "\n\n--- CURRENT VEHICLE DATA ---\n" + context
