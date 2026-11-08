"""One function for every model call: complete(...).

Providers
  anthropic  Claude (own API format)
  openai     OpenAI            key: OPENAI_API_KEY   url: OPENAI_BASE_URL (optional)
  groq       Groq              key: GROQ_API_KEY     url: GROQ_BASE_URL (optional)
  xai        Grok (xAI)        key: XAI_API_KEY      url: XAI_BASE_URL (optional)
  gemini     Google Gemini     key: GEMINI_API_KEY   url: GEMINI_BASE_URL (optional)
  mock       offline fake models for tests

openai, groq, xai and gemini all use the OpenAI-style "chat/completions" request, so they share one code path.
No SDK is needed. We call the HTTP APIs with `requests`.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

from .config import Settings


class LLMError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# provider -> (key env var, default base URL, base-URL env var)
COMPAT = {
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1", "OPENAI_BASE_URL"),
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "GROQ_BASE_URL"),
    "xai": ("XAI_API_KEY", "https://api.x.ai/v1", "XAI_BASE_URL"),
    "gemini": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_BASE_URL"),
}
RETRY_DELAYS = [2, 5, 15, 30, 60]  # seconds; free tiers need long waits after a 429
_last_call: dict[str, float] = {}


def complete(settings: Settings, role: str, task: str, system: str, user: str, json_mode: bool = False) -> str:
    """role is "writer" or "judge". `task` names the step (the mock provider uses it)."""
    if role == "writer":
        provider, model, temp = settings.writer_provider, settings.writer_model, settings.writer_temperature
    else:
        provider, model, temp = settings.judge_provider, settings.judge_model, settings.judge_temperature

    if provider == "mock":
        from . import mock_llm

        return mock_llm.respond(settings, role, task, system, user)
    if not model:
        raise LLMError(f"{role.upper()}_MODEL is not set. Put the model ID in your .env file.")
    max_tokens = 4096 if role == "writer" else 1600
    _pace(provider, settings.call_interval)
    if provider == "anthropic":
        return _anthropic(model, temp, system, user, settings.timeout_seconds, max_tokens)
    if provider in COMPAT:
        return _chat_compat(provider, model, temp, system, user, json_mode, settings.timeout_seconds, max_tokens)
    raise LLMError(f"Unknown provider: {provider}. Use anthropic, openai, groq, xai, gemini or mock.")


def _pace(provider: str, interval: float) -> None:
    """Wait so that calls to one provider are at least `interval` seconds apart (free-tier rate limits)."""
    if interval > 0:
        wait = _last_call.get(provider, 0) + interval - time.time()
        if wait > 0:
            time.sleep(wait)
    _last_call[provider] = time.time()


def _post(url: str, headers: dict, body: dict, timeout: int) -> dict:
    last = None
    delays = [0] + RETRY_DELAYS
    next_delay = None
    for fallback_delay in delays:
        delay = next_delay if next_delay is not None else fallback_delay
        next_delay = None
        if delay:
            time.sleep(delay)
        try:
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:  # network problem: retry
            last = str(e)
            continue
        if r.status_code in (429, 500, 502, 503, 529):
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            body_lower = r.text.lower()
            if r.status_code == 429 and any(
                marker in body_lower
                for marker in ("exceeded your current quota", "insufficient_quota", "billing account is not active")
            ):
                raise LLMError(f"HTTP 429: {r.text[:300]}", status=429)
            retry_after = (getattr(r, "headers", None) or {}).get("Retry-After")
            if not retry_after:
                # Groq includes a precise wait in some 429 response bodies even when
                # Retry-After is absent. Honor it instead of retrying too early.
                match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)\s*(ms|s)", r.text, re.I)
                if match:
                    retry_after = float(match.group(1))
                    if match.group(2).lower() == "ms":
                        retry_after /= 1000
            if retry_after:
                try:
                    next_delay = min(float(retry_after), 90)
                except ValueError:
                    pass
            continue
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}", status=r.status_code)
        return r.json()
    raise LLMError(f"Model call failed after retries: {last}")


def _anthropic(model, temp, system, user, timeout, max_tokens=4096) -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not set.")
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        {"model": model, "max_tokens": max_tokens, "temperature": temp, "system": system,
         "messages": [{"role": "user", "content": user}]},
        timeout,
    )
    return "".join(b.get("text", "") for b in data.get("content", []))


def _chat_compat(provider, model, temp, system, user, json_mode, timeout, max_tokens=4096) -> str:
    key_env, default_url, url_env = COMPAT[provider]
    key = os.getenv(key_env)
    # Older project templates may store the Groq key under XAI_API_KEY.
    if provider == "groq" and not key:
        key = os.getenv("XAI_API_KEY")
    if not key:
        raise LLMError(f"{key_env} is not set.")
    base = os.getenv(url_env, default_url).rstrip("/")
    body = {"model": model, "temperature": temp, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}"}
    try:
        data = _post(f"{base}/chat/completions", headers, body, timeout)
    except LLMError as e:
        # Some models refuse optional settings (temperature, response_format). Retry once without them.
        if e.status == 400 and ("response_format" in body or "temperature" in body):
            body.pop("response_format", None)
            body.pop("temperature", None)
            data = _post(f"{base}/chat/completions", headers, body, timeout)
        else:
            raise
    choices = data.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        raise LLMError("Model response contained no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    return content if isinstance(content, str) else ""


def parse_json(text: str):
    """Parse JSON from a model reply. Accepts ```json fences and extra words around the JSON."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if starts:
        i = min(starts)
        j = max(t.rfind("}"), t.rfind("]"))
        if j > i:
            return json.loads(t[i : j + 1])
    raise ValueError("No valid JSON found in model reply.")
