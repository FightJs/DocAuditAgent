"""Shared offline fixtures for backend integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Return an isolated app whose deterministic reviewer never calls an LLM."""
    with TestClient(create_app()) as test_client:
        yield test_client
