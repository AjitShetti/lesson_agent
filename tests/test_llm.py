"""Check how we talk to the real APIs, without using the network."""
import pytest

from lesson_agent import llm
from lesson_agent.config import Settings


class FakeResp:
    def __init__(self, status, data, headers=None):
        self.status_code, self._d, self.text, self.headers = status, data, str(data), headers or {}

    def json(self):
        return self._d


def ok(text="ok"):
    return FakeResp(200, {"choices": [{"message": {"content": text}}]})


def capture(monkeypatch, response=None):
    seen = {}

    def post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        return response or ok("hi")

    monkeypatch.setattr(llm.requests, "post", post)
    return seen


def test_judge_request_is_json_mode_zero_temperature(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    seen = capture(monkeypatch, ok("{}"))
    llm.complete(Settings.from_env(judge_provider="openai"), "judge", "review", "SYS", "USER", json_mode=True)
    assert seen["url"].endswith("/chat/completions")
    assert seen["body"]["temperature"] == 0.0 and seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]


def test_groq_uses_its_own_key_and_url(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    seen = capture(monkeypatch)
    s = Settings.from_env(writer_provider="groq", writer_model="some-model")
    assert llm.complete(s, "writer", "write", "S", "U") == "hi"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer gk" and seen["body"]["model"] == "some-model"
    assert "response_format" not in seen["body"]  # the writer asks for text, not JSON


def test_writer_and_judge_keys_do_not_mix(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    monkeypatch.setenv("GEMINI_API_KEY", "mk")
    urls = []

    def post(url, headers, json, timeout):
        urls.append((url, headers["Authorization"]))
        return ok()

    monkeypatch.setattr(llm.requests, "post", post)
    s = Settings.from_env(writer_provider="groq", writer_model="a", judge_provider="gemini", judge_model="b")
    llm.complete(s, "writer", "write", "S", "U")
    llm.complete(s, "judge", "review", "S", "U", json_mode=True)
    assert urls[0] == ("https://api.groq.com/openai/v1/chat/completions", "Bearer gk")
    assert urls[1] == ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "Bearer mk")


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(llm.LLMError, match="GROQ_API_KEY"):
        llm.complete(Settings.from_env(writer_provider="groq"), "writer", "write", "s", "u")


def test_missing_model_gives_clear_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    s = Settings.from_env(writer_provider="openai", writer_model="")
    with pytest.raises(llm.LLMError, match="WRITER_MODEL"):
        llm.complete(s, "writer", "write", "s", "u")


def test_unknown_provider_is_rejected():
    with pytest.raises(llm.LLMError, match="Unknown provider"):
        llm.complete(Settings.from_env(writer_provider="nope", writer_model="m"), "writer", "write", "s", "u")


def test_retry_on_rate_limit_then_succeed(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    calls = iter([FakeResp(429, "slow down"), ok()])
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: next(calls))
    assert llm.complete(Settings.from_env(judge_provider="openai"), "judge", "t", "s", "u") == "ok"
    assert sleeps == [2]  # first fixed delay


def test_retry_after_header_is_respected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    calls = iter([FakeResp(429, "slow down", {"Retry-After": "7"}), ok()])
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: next(calls))
    assert llm.complete(Settings.from_env(judge_provider="gemini", judge_model="m"), "judge", "t", "s", "u") == "ok"
    assert sleeps == [7]


def test_daily_quota_429_fails_at_once_without_waiting(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    body = "Generate content requests per day limit exceeded on Free Tier."
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResp(429, body))
    with pytest.raises(llm.LLMError, match="Out of quota"):
        llm._post("https://example.test", {}, {}, 5)
    assert sleeps == []


def test_other_4xx_errors_are_not_retried(monkeypatch):
    posts = []

    def post(*args, **kwargs):
        posts.append(1)
        return FakeResp(404, "no such model")

    monkeypatch.setattr(llm.requests, "post", post)
    with pytest.raises(llm.LLMError, match="HTTP 404"):
        llm._post("https://example.test", {}, {}, 5)
    assert len(posts) == 1


def test_call_interval_spaces_out_calls(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: ok())
    llm._last_call.clear()
    s = Settings.from_env(judge_provider="gemini", judge_model="m", call_interval=4.0)
    llm.complete(s, "judge", "t", "s", "u")
    llm.complete(s, "judge", "t", "s", "u")
    assert sleeps and 0 < sleeps[0] <= 4.0


def test_json_in_code_fence_is_parsed():
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json('Here you go: {"a": 1} Thanks') == {"a": 1}
    with pytest.raises(ValueError):
        llm.parse_json("no json here")


def test_writer_and_judge_default_to_different_vendors():
    s = Settings()
    assert s.writer_provider != s.judge_provider


def test_comment_in_env_value_counts_as_empty(monkeypatch):
    monkeypatch.setenv("WRITER_MODEL", "   # exact model ID from your console")
    assert Settings.from_env(writer_provider="groq").writer_model == "qwen/qwen3.8-27b"  # falls back to the default


def test_timeout_is_retried_once_then_gives_up(monkeypatch):
    posts = []

    def post(*args, **kwargs):
        posts.append(1)
        raise llm.requests.Timeout("slow")

    monkeypatch.setattr(llm.time, "sleep", lambda *_: None)
    monkeypatch.setattr(llm.requests, "post", post)
    with pytest.raises(llm.LLMError, match="timed out"):
        llm._post("https://example.test", {}, {}, 5)
    assert len(posts) == 2
