from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def sample_excel_path() -> Path:
    return BASE_DIR / "samples" / "sample_schedule.xlsx"


@pytest.fixture
def sample_web_text() -> str:
    return (BASE_DIR / "samples" / "sample_web_schedule.txt").read_text(encoding="utf-8")


@pytest.fixture
def tmp_db_path(tmp_path) -> Path:
    return tmp_path / "test_schedule_sync.db"
