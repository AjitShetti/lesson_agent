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


@dataclass
class Settings:
    # Writer and judge use DIFFERENT models on purpose (see DESIGN.md).
    writer_provider: str = "groq"
    writer_model: str = "qwen/qwen3.8-27b"
    judge_provider: str = "gemini"
    judge_model: str = "gemini-2.5-flash"
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
        defaults = {
            "anthropic": "claude-sonnet-5-5",
            "openai": "gpt-4o-mini",
            "groq": "qwen/qwen3.8-27b",
            "gemini": "gemini-2.5-flash",
        }
        ov = {k: v for k, v in overrides.items() if v is not None}
        wp = ov.get("writer_provider") or os.getenv("WRITER_PROVIDER") or cls.writer_provider
        jp = ov.get("judge_provider") or os.getenv("JUDGE_PROVIDER") or cls.judge_provider
        # Accept the console host if it was entered as the provider value.
        wp = wp.strip().lower()
        jp = jp.strip().lower()
        aliases = {"console.groq.com": "groq", "groq.com": "groq"}
        wp = aliases.get(wp, wp)
        jp = aliases.get(jp, jp)
        s = cls(
            writer_provider=wp,
            writer_model=os.getenv("WRITER_MODEL") or defaults.get(wp, ""),
            judge_provider=jp,
            judge_model=os.getenv("JUDGE_MODEL") or defaults.get(jp, ""),
            max_retries=int(os.getenv("MAX_RETRIES", cls.max_retries)),
            call_interval=float(os.getenv("CALL_INTERVAL_SECONDS", cls.call_interval)),
        )
        return replace(s, **ov) if ov else s
