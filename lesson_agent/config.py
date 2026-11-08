"""Settings. Read from environment variables (or a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # optional: load .env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

# Model used when WRITER_MODEL / JUDGE_MODEL is not set.
DEFAULT_MODELS = {
    "groq": "qwen/qwen3.8-27b",
    "gemini": "gemini-flash-latest",  # "-latest" keeps working when Google retires a dated model name
    "openai": "gpt-4o-mini",
}


def _env(name: str, default: str = "") -> str:
    """Read a variable. Text after '#' is a comment, so `MODEL=   # fill me in` counts as empty."""
    return os.getenv(name, default).split("#")[0].strip()


@dataclass
class Settings:
    # Writer and judge use DIFFERENT vendors on purpose (see DESIGN.md).
    writer_provider: str = "groq"
    writer_model: str = DEFAULT_MODELS["groq"]
    judge_provider: str = "gemini"
    judge_model: str = DEFAULT_MODELS["gemini"]
    writer_temperature: float = 0.7
    judge_temperature: float = 0.0  # judge must be repeatable
    max_retries: int = 2  # 1 first try + 2 retries = 3 attempts at most
    call_interval: float = 0.0  # seconds to wait between calls to one provider (free tiers need ~4)
    timeout_seconds: int = 120
    # Only used by the offline "mock" provider (plumbing tests, not quality tests).
    mock_writer_mode: str = "flawed_then_good"  # flawed_then_good | good | always_bad
    data_dir: Path = field(default_factory=lambda: ROOT / "data")
    examples_dir: Path = field(default_factory=lambda: ROOT / "examples")
    output_dir: Path = field(default_factory=lambda: ROOT / "outputs")
    memory_db: Path = field(default_factory=lambda: ROOT / "memory" / "memory.db")

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        ov = {k: v for k, v in overrides.items() if v is not None}
        wp = (ov.get("writer_provider") or _env("WRITER_PROVIDER") or cls.writer_provider).lower()
        jp = (ov.get("judge_provider") or _env("JUDGE_PROVIDER") or cls.judge_provider).lower()
        s = cls(
            writer_provider=wp,
            writer_model=_env("WRITER_MODEL") or DEFAULT_MODELS.get(wp, ""),
            judge_provider=jp,
            judge_model=_env("JUDGE_MODEL") or DEFAULT_MODELS.get(jp, ""),
            max_retries=int(_env("MAX_RETRIES", str(cls.max_retries))),
            call_interval=float(_env("CALL_INTERVAL_SECONDS", str(cls.call_interval))),
        )
        return replace(s, **ov) if ov else s
