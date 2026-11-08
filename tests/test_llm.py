"""Check how we talk to the real APIs, without using the network."""
import pytest

from lesson_agent import llm
from lesson_agent.config import Settings


class FakeResp:
    def __init__(self, status, data):
        self.status_code, self._d, self.text = status, data, str(data)

    def json(self):
        return self._d


def test_anthropic_request_and_parse(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        return FakeResp(200, {"content": [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]})

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(writer_provider="anthropic")
    assert llm.complete(s, "writer", "write", "SYS", "USER") == "Hello world"
    assert seen["url"].endswith("/v1/messages") and seen["headers"]["x-api-key"] == "k"
    assert seen["body"]["system"] == "SYS" and seen["body"]["messages"][0]["content"] == "USER"


def test_openai_request_uses_json_mode_and_zero_temperature_for_judge(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, body=json)
        return FakeResp(200, {"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(judge_provider="openai")
    llm.complete(s, "judge", "flow", "SYS", "USER", json_mode=True)
    assert seen["url"].endswith("/chat/completions")
    assert seen["body"]["temperature"] == 0.0 and seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["max_tokens"] == 1600


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.LLMError, match="ANTHROPIC_API_KEY"):
        llm.complete(Settings.from_env(writer_provider="anthropic"), "writer", "write", "s", "u")


def test_retry_on_rate_limit_then_succeed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    calls = iter([FakeResp(429, {}), FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})])
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: next(calls))
    assert llm.complete(Settings.from_env(judge_provider="openai"), "judge", "t", "s", "u") == "ok"


def test_xai_uses_its_own_key_and_url(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xk")
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        return FakeResp(200, {"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(writer_provider="xai", writer_model="grok-x")
    assert llm.complete(s, "writer", "write", "S", "U") == "hi"
    assert seen["url"] == "https://api.x.ai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer xk" and seen["body"]["model"] == "grok-x"


def test_groq_uses_its_own_key_and_openai_compatible_url(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        return FakeResp(200, {"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(writer_provider="groq", writer_model="qwen/qwen3.8-27b")
    assert llm.complete(s, "writer", "write", "S", "U") == "hi"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer gk"


def test_groq_accepts_legacy_xai_key_variable(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "legacy-groq-key")
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, auth=headers["Authorization"])
        return FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(writer_provider="groq", writer_model="m")
    assert llm.complete(s, "writer", "write", "S", "U") == "ok"
    assert seen["auth"] == "Bearer legacy-groq-key"


def test_quota_429_fails_without_rate_limit_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResp(429, {"error": "You exceeded your current quota; check billing."}))
    with pytest.raises(llm.LLMError, match="current quota"):
        llm._post("https://example.test", {}, {}, 5)
    assert sleeps == []


def test_gemini_uses_its_own_key_and_url_at_the_same_time_as_xai(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xk")
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    urls = []

    def post(url, headers, json, timeout):
        urls.append((url, headers["Authorization"]))
        return FakeResp(200, {"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(writer_provider="xai", writer_model="a", judge_provider="gemini", judge_model="b")
    llm.complete(s, "writer", "write", "S", "U")
    llm.complete(s, "judge", "flow", "S", "U", json_mode=True)
    assert urls[0] == ("https://api.x.ai/v1/chat/completions", "Bearer xk")
    assert urls[1] == ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "Bearer gk")


def test_400_error_retries_without_optional_settings(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    bodies = []

    def post(url, headers, json, timeout):
        bodies.append(dict(json))
        if "response_format" in json or "temperature" in json:
            return FakeResp(400, {"error": "response_format not supported"})
        return FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(judge_provider="gemini", judge_model="m")
    assert llm.complete(s, "judge", "flow", "S", "U", json_mode=True) == "ok"
    assert "response_format" in bodies[0] and "response_format" not in bodies[1] and "temperature" not in bodies[1]


def test_retry_after_header_is_respected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    llm._last_call.clear()
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", lambda x: sleeps.append(x))

    class R429(FakeResp):
        headers = {"Retry-After": "7"}

    calls = iter([R429(429, {}), FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})])
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: next(calls))
    s = Settings.from_env(judge_provider="gemini", judge_model="m")
    assert llm.complete(s, "judge", "t", "s", "u") == "ok"
    assert sleeps == [7]


def test_retry_after_in_groq_message_is_respected(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: sleeps.append(seconds))
    class R429(FakeResp):
        headers = {}
    calls = iter([
        R429(429, {"error": {"message": "Rate limit reached due to token quota. Please try again in 217.5ms."}}),
        FakeResp(200, {"choices": [{"message": {"content": "ok"}}]}),
    ])
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: next(calls))
    assert llm._post("https://example.test", {}, {}, 5)["choices"][0]["message"]["content"] == "ok"
    assert sleeps == [0.2175]


def test_call_interval_spaces_out_calls(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", lambda x: sleeps.append(x))
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": "ok"}}]}))
    llm._last_call.clear()
    s = Settings.from_env(judge_provider="gemini", judge_model="m", call_interval=4.0)
    llm.complete(s, "judge", "t", "s", "u")
    llm.complete(s, "judge", "t", "s", "u")
    assert sleeps and 0 < sleeps[0] <= 4.0


def test_missing_model_gives_clear_error(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "xk")
    monkeypatch.delenv("WRITER_MODEL", raising=False)
    s = Settings.from_env(writer_provider="xai")
    with pytest.raises(llm.LLMError, match="WRITER_MODEL"):
        llm.complete(s, "writer", "write", "s", "u")


def test_unknown_provider_is_rejected():
    with pytest.raises(llm.LLMError, match="Unknown provider"):
        llm.complete(Settings.from_env(writer_provider="nope", writer_model="m"), "writer", "write", "s", "u")


def test_writer_and_judge_default_to_different_models():
    s = Settings()
    assert (s.writer_provider, s.writer_model) != (s.judge_provider, s.judge_model)
