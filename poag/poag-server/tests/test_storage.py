"""Tests for session storage."""

import tempfile
from pathlib import Path

import pytest

from poag_server.storage import SessionStorage


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


def test_create_first_session(temp_db):
    """Test creating the first session for a cwd/pid pair."""
    storage = SessionStorage(temp_db)

    session = storage.create_session(cwd="/home/user/project", pid=12345)

    assert session.cwd == "/home/user/project"
    assert session.pid == 12345
    assert session.counter == 1
    assert session.session_id == "/home/user/project.12345.1"


def test_create_multiple_sessions_same_cwd_pid(temp_db):
    """Test that counter increments for the same cwd/pid."""
    storage = SessionStorage(temp_db)

    session1 = storage.create_session(cwd="/home/user/project", pid=12345)
    session2 = storage.create_session(cwd="/home/user/project", pid=12345)
    session3 = storage.create_session(cwd="/home/user/project", pid=12345)

    assert session1.counter == 1
    assert session2.counter == 2
    assert session3.counter == 3

    assert session1.session_id == "/home/user/project.12345.1"
    assert session2.session_id == "/home/user/project.12345.2"
    assert session3.session_id == "/home/user/project.12345.3"


def test_create_sessions_different_cwd(temp_db):
    """Test that different cwds have independent counters."""
    storage = SessionStorage(temp_db)

    session1 = storage.create_session(cwd="/home/user/project1", pid=12345)
    session2 = storage.create_session(cwd="/home/user/project2", pid=12345)

    # Same pid, different cwd - counters should both start at 1
    assert session1.counter == 1
    assert session2.counter == 1


def test_create_sessions_different_pid(temp_db):
    """Test that different pids have independent counters."""
    storage = SessionStorage(temp_db)

    session1 = storage.create_session(cwd="/home/user/project", pid=12345)
    session2 = storage.create_session(cwd="/home/user/project", pid=67890)

    # Same cwd, different pid - counters should both start at 1
    assert session1.counter == 1
    assert session2.counter == 1


def test_get_session(temp_db):
    """Test retrieving a session by ID."""
    storage = SessionStorage(temp_db)

    created_session = storage.create_session(cwd="/home/user/project", pid=12345)
    retrieved_session = storage.get_session(created_session.session_id)

    assert retrieved_session is not None
    assert retrieved_session.session_id == created_session.session_id
    assert retrieved_session.cwd == created_session.cwd
    assert retrieved_session.pid == created_session.pid
    assert retrieved_session.counter == created_session.counter


def test_get_nonexistent_session(temp_db):
    """Test retrieving a session that doesn't exist."""
    storage = SessionStorage(temp_db)

    session = storage.get_session("nonexistent.session.id")
    assert session is None


def test_list_all_sessions(temp_db):
    """Test listing all sessions."""
    storage = SessionStorage(temp_db)

    storage.create_session(cwd="/home/user/project1", pid=12345)
    storage.create_session(cwd="/home/user/project2", pid=67890)
    storage.create_session(cwd="/home/user/project1", pid=12345)

    sessions = storage.list_sessions()
    assert len(sessions) == 3


def test_list_sessions_by_cwd(temp_db):
    """Test filtering sessions by cwd."""
    storage = SessionStorage(temp_db)

    storage.create_session(cwd="/home/user/project1", pid=12345)
    storage.create_session(cwd="/home/user/project2", pid=67890)
    storage.create_session(cwd="/home/user/project1", pid=99999)

    sessions = storage.list_sessions(cwd="/home/user/project1")
    assert len(sessions) == 2
    assert all(s.cwd == "/home/user/project1" for s in sessions)


def test_list_sessions_by_pid(temp_db):
    """Test filtering sessions by pid."""
    storage = SessionStorage(temp_db)

    storage.create_session(cwd="/home/user/project1", pid=12345)
    storage.create_session(cwd="/home/user/project2", pid=12345)
    storage.create_session(cwd="/home/user/project1", pid=67890)

    sessions = storage.list_sessions(pid=12345)
    assert len(sessions) == 2
    assert all(s.pid == 12345 for s in sessions)


def test_list_sessions_by_cwd_and_pid(temp_db):
    """Test filtering sessions by both cwd and pid."""
    storage = SessionStorage(temp_db)

    storage.create_session(cwd="/home/user/project", pid=12345)
    storage.create_session(cwd="/home/user/project", pid=12345)
    storage.create_session(cwd="/home/user/project", pid=67890)
    storage.create_session(cwd="/home/other/project", pid=12345)

    sessions = storage.list_sessions(cwd="/home/user/project", pid=12345)
    assert len(sessions) == 2
    assert all(s.cwd == "/home/user/project" and s.pid == 12345 for s in sessions)
