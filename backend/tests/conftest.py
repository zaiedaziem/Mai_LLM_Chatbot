import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # makes `src` importable

from src.main import app  # noqa: E402
from src.dependencies import get_db, get_llm, get_system_prompt  # noqa: E402
from src.middleware import rate_limit as rate_limit_module  # noqa: E402
from fakes import FakeLLM, FakeSupabase  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    rate_limit_module.reset()  # in-memory state would otherwise leak between tests


@pytest.fixture
def db():
    return FakeSupabase()


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def client(db, llm):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_system_prompt] = lambda: "You are a test assistant."
    yield TestClient(app)
    app.dependency_overrides.clear()
