import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from fakes import FakeGroq, FakeSupabase  # noqa: E402


@pytest.fixture
def db():
    return FakeSupabase()


@pytest.fixture
def llm():
    return FakeGroq()


@pytest.fixture
def client(db, llm):
    main.app.dependency_overrides[main.get_db] = lambda: db
    main.app.dependency_overrides[main.get_llm] = lambda: llm
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
