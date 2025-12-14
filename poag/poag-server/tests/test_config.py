"""Tests for configuration and Home class."""

import tempfile
from pathlib import Path

from poag_server.config import Home


def test_home_creates_directories():
    """Test that Home creates necessary directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Home.sandbox(tmpdir)

        assert home.data.exists()
        assert home.state.exists()


def test_sessions_db_path():
    """Test that sessions_db returns correct path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Home.sandbox(tmpdir)

        assert home.sessions_db == home.data / "sessions.db"


def test_port_storage():
    """Test storing and retrieving port number."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Home.sandbox(tmpdir)

        # Initially no port
        assert home.get_port() is None

        # Set port
        home.set_port(8000)
        assert home.get_port() == 8000

        # Update port
        home.set_port(9000)
        assert home.get_port() == 9000


def test_pid_storage():
    """Test storing and retrieving PID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Home.sandbox(tmpdir)

        # Initially no pid
        assert home.get_pid() is None

        # Set pid
        home.set_pid(12345)
        assert home.get_pid() == 12345

        # Update pid
        home.set_pid(67890)
        assert home.get_pid() == 67890
