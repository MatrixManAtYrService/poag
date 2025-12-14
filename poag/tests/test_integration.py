"""Integration tests for poag-client and poag-server.

These tests verify that the client can successfully communicate with the server,
and that session management works end-to-end.
"""

import os
import tempfile
import time
from pathlib import Path
from threading import Thread

import pytest
import httpx
from fastapi.testclient import TestClient

# Import server components
from poag_server.config import Home as ServerHome
from poag_server.main import app, set_storage
from poag_server.storage import SessionStorage

# Import client
from poag_client import PoagClient


@pytest.fixture
def temp_home():
    """Create a temporary home directory for the server."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ServerHome.sandbox(tmpdir)


@pytest.fixture
def server_storage(temp_home):
    """Create session storage for the server."""
    return SessionStorage(temp_home.sessions_db)


@pytest.fixture
def test_client(server_storage):
    """Create a FastAPI test client with sandboxed storage."""
    set_storage(server_storage)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def poag_client(test_client):
    """Create a POAG client that talks to the test server."""
    # TestClient uses a base URL that works with the client
    client = PoagClient(base_url="http://testserver")
    # Replace the httpx client with the test client
    client.client = test_client
    yield client


def test_client_server_hello(poag_client):
    """Test that client can call the hello endpoint."""
    message = poag_client.hello()
    assert message == "world"


def test_client_server_create_session(poag_client):
    """Test creating a session through the client."""
    session = poag_client.create_session(cwd="/test/project", pid=12345)

    assert session.session_id == "/test/project.12345.1"
    assert session.counter == 1


def test_client_server_session_counter_increments(poag_client):
    """Test that session counter increments for the same cwd/pid."""
    session1 = poag_client.create_session(cwd="/test/project", pid=12345)
    session2 = poag_client.create_session(cwd="/test/project", pid=12345)
    session3 = poag_client.create_session(cwd="/test/project", pid=12345)

    assert session1.counter == 1
    assert session2.counter == 2
    assert session3.counter == 3

    assert session1.session_id == "/test/project.12345.1"
    assert session2.session_id == "/test/project.12345.2"
    assert session3.session_id == "/test/project.12345.3"


def test_client_server_different_cwd(poag_client):
    """Test that different cwds have independent counters."""
    session1 = poag_client.create_session(cwd="/test/project1", pid=12345)
    session2 = poag_client.create_session(cwd="/test/project2", pid=12345)

    # Both should start at counter 1
    assert session1.counter == 1
    assert session2.counter == 1


def test_client_server_different_pid(poag_client):
    """Test that different pids have independent counters."""
    session1 = poag_client.create_session(cwd="/test/project", pid=12345)
    session2 = poag_client.create_session(cwd="/test/project", pid=67890)

    # Both should start at counter 1
    assert session1.counter == 1
    assert session2.counter == 1


def test_client_server_session_persistence(poag_client, server_storage):
    """Test that sessions are persisted in the database."""
    # Create sessions
    session1 = poag_client.create_session(cwd="/test/project", pid=12345)
    session2 = poag_client.create_session(cwd="/test/project", pid=12345)

    # Verify they're in the database
    all_sessions = server_storage.list_sessions()
    assert len(all_sessions) == 2

    # Verify by cwd/pid filter
    filtered_sessions = server_storage.list_sessions(cwd="/test/project", pid=12345)
    assert len(filtered_sessions) == 2
    assert filtered_sessions[0].counter in [1, 2]
    assert filtered_sessions[1].counter in [1, 2]


def test_client_uses_os_environment(test_client):
    """Test that client correctly uses os.getcwd() and os.getpid() by default."""
    # Create a client without mocking
    client = PoagClient(base_url="http://testserver")
    client.client = test_client

    # Get actual cwd and pid
    actual_cwd = os.getcwd()
    actual_pid = os.getpid()

    # Create session (should use actual cwd/pid)
    session = client.create_session()

    # Verify session ID contains the actual cwd and pid
    expected_prefix = f"{actual_cwd}.{actual_pid}."
    assert session.session_id.startswith(expected_prefix)
    assert session.counter >= 1  # Counter depends on test execution order
