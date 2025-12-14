"""Tests for the FastAPI endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from poag_server.config import Home
from poag_server.main import app, set_storage
from poag_server.storage import SessionStorage


@pytest.fixture
def temp_home():
    """Create a temporary home directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Home.sandbox(tmpdir)


@pytest.fixture
def client(temp_home):
    """Create a test client with sandboxed storage."""
    # Set up sandboxed storage
    storage = SessionStorage(temp_home.sessions_db)
    set_storage(storage)

    # Create test client
    with TestClient(app) as test_client:
        yield test_client


def test_hello_endpoint(client):
    """Test the hello endpoint."""
    response = client.get("/hello")

    assert response.status_code == 200
    assert response.json() == {"message": "world"}


def test_create_first_session(client):
    """Test creating the first session."""
    response = client.post(
        "/sessions",
        json={"cwd": "/home/user/project", "pid": 12345}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "/home/user/project.12345.1"
    assert data["counter"] == 1


def test_create_multiple_sessions(client):
    """Test creating multiple sessions for the same cwd/pid."""
    # First session
    response1 = client.post(
        "/sessions",
        json={"cwd": "/home/user/project", "pid": 12345}
    )
    assert response1.status_code == 200
    assert response1.json()["counter"] == 1

    # Second session
    response2 = client.post(
        "/sessions",
        json={"cwd": "/home/user/project", "pid": 12345}
    )
    assert response2.status_code == 200
    assert response2.json()["counter"] == 2

    # Third session
    response3 = client.post(
        "/sessions",
        json={"cwd": "/home/user/project", "pid": 12345}
    )
    assert response3.status_code == 200
    assert response3.json()["counter"] == 3


def test_sessions_independent_by_cwd(client):
    """Test that sessions with different cwds are independent."""
    response1 = client.post(
        "/sessions",
        json={"cwd": "/home/user/project1", "pid": 12345}
    )
    response2 = client.post(
        "/sessions",
        json={"cwd": "/home/user/project2", "pid": 12345}
    )

    # Both should start at counter 1
    assert response1.json()["counter"] == 1
    assert response2.json()["counter"] == 1


def test_sessions_independent_by_pid(client):
    """Test that sessions with different pids are independent."""
    response1 = client.post(
        "/sessions",
        json={"cwd": "/home/user/project", "pid": 12345}
    )
    response2 = client.post(
        "/sessions",
        json={"cwd": "/home/user/project", "pid": 67890}
    )

    # Both should start at counter 1
    assert response1.json()["counter"] == 1
    assert response2.json()["counter"] == 1
