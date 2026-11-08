import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lesson_agent.config import Settings  # noqa: E402
from lesson_agent.rubric import load_context  # noqa: E402


@pytest.fixture
def mock_settings(tmp_path):
    return Settings.from_env(
        writer_provider="mock", judge_provider="mock",
        memory_db=tmp_path / "mem.db", output_dir=tmp_path / "out",
    )


@pytest.fixture
def ctx(mock_settings):
    return load_context(mock_settings)


def read(name: str) -> str:
    return (ROOT / "examples" / name).read_text(encoding="utf-8")
