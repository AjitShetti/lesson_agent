"""One function for every model call: complete(...).

Providers (all use the same OpenAI-style "chat/completions" request, so there is one code path):
  groq    key: GROQ_API_KEY
  gemini  key: GEMINI_API_KEY
  openai  key: OPENAI_API_KEY
  mock    offline fake models for tests

No SDK is needed. We call the HTTP API with `requests`.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

from .config import Settings


class LLMError(RuntimeError):
    pass


# provider -> (key variable, base URL)
PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    "gemini": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
}
RETRY_DELAYS = [2, 5, 15, 30, 60]  # seconds to wait before each retry of a 429 / 5xx / network error
# A 429 with one of these texts means the quota is used up. Waiting will not help, so we stop at once.
OUT_OF_QUOTA = ("per day", "insufficient_quota", "billing account is not active")
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
    if provider not in PROVIDERS:
        raise LLMError(f"Unknown provider: {provider}. Use groq, gemini, openai or mock.")
    key_var, base_url = PROVIDERS[provider]
    key = os.getenv(key_var)
    if not key:
        raise LLMError(f"{key_var} is not set.")
    if not model:
        raise LLMError(f"{role.upper()}_MODEL is not set. Put the model ID in your .env file.")

    body = {
        "model": model,
        "temperature": temp,
        "max_tokens": 4096 if role == "writer" else 16384,  # the judge budget includes the model's own thinking
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    _pace(provider, settings.call_interval)
    data = _post(f"{base_url}/chat/completions", {"Authorization": f"Bearer {key}"}, body, settings.timeout_seconds)

    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise LLMError("Model response contained no choices.")
    content = (choices[0].get("message") or {}).get("content", "")
    return content if isinstance(content, str) else ""


def _pace(provider: str, interval: float) -> None:
    """Wait so that calls to one provider are at least `interval` seconds apart (free-tier rate limits)."""
    if interval > 0:
        wait = _last_call.get(provider, 0) + interval - time.time()
        if wait > 0:
            time.sleep(wait)
    _last_call[provider] = time.time()


def _post(url: str, headers: dict, body: dict, timeout: int) -> dict:
    """POST with retries. Retries 429, 5xx and connection errors (timeouts only once); any other error stops at once."""
    last = ""
    timeouts = 0
    wait = 0.0  # the server's own "retry after" wins over our fixed delays
    for fallback in [0] + RETRY_DELAYS:
        if wait or fallback:
            time.sleep(wait or fallback)
        wait = 0.0
        try:
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.Timeout as e:  # a model that does not answer will not answer on the 5th try either
            timeouts += 1
            last = f"timed out after {timeout}s ({e.__class__.__name__})"
            if timeouts >= 2:
                break
            continue
        except requests.RequestException as e:  # connection problem: worth the normal retries
            last = str(e)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code == 429 and any(m in r.text.lower() for m in OUT_OF_QUOTA):
                raise LLMError(f"Out of quota. {last}")
            try:
                wait = min(float(r.headers.get("Retry-After", 0)), 90)
            except ValueError:
                wait = 0.0
            continue
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()
    raise LLMError(f"Model call failed after retries: {last}")


def parse_json(text: str):
    """Parse JSON from a model reply. Accepts ```json fences and extra words around the JSON."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    i, j = t.find("{"), t.rfind("}")
    if 0 <= i < j:
        try:
            return json.loads(t[i : j + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("No valid JSON found in model reply.")
