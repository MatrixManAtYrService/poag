"""Tests for the POAG client."""

import pytest
from unittest.mock import Mock, patch
import httpx

from poag_client import PoagClient


def test_client_initialization():
    """Test that client initializes with correct base URL."""
    client = PoagClient(base_url="http://test:9000")
    assert client.base_url == "http://test:9000"
    client.close()


def test_client_context_manager():
    """Test that client works as a context manager."""
    with PoagClient() as client:
        assert client.client is not None


def test_hello_endpoint():
    """Test the hello method."""
    with PoagClient() as client:
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "world"}
        mock_response.raise_for_status = Mock()

        with patch.object(client.client, 'get', return_value=mock_response):
            message = client.hello()
            assert message == "world"


def test_create_session_with_defaults():
    """Test creating a session with default cwd and pid."""
    with PoagClient() as client:
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "/test/path.12345.1",
            "counter": 1
        }
        mock_response.raise_for_status = Mock()

        with patch.object(client.client, 'post', return_value=mock_response):
            with patch('os.getcwd', return_value="/test/path"):
                with patch('os.getpid', return_value=12345):
                    session = client.create_session()

                    assert session.session_id == "/test/path.12345.1"
                    assert session.counter == 1


def test_create_session_with_explicit_values():
    """Test creating a session with explicit cwd and pid."""
    with PoagClient() as client:
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "/custom/path.99999.2",
            "counter": 2
        }
        mock_response.raise_for_status = Mock()

        with patch.object(client.client, 'post', return_value=mock_response):
            session = client.create_session(cwd="/custom/path", pid=99999)

            assert session.session_id == "/custom/path.99999.2"
            assert session.counter == 2


def test_create_session_increments_counter():
    """Test that multiple sessions from same cwd/pid increment the counter."""
    with PoagClient() as client:
        # First session
        mock_response1 = Mock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = {
            "session_id": "/test/path.12345.1",
            "counter": 1
        }
        mock_response1.raise_for_status = Mock()

        # Second session
        mock_response2 = Mock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = {
            "session_id": "/test/path.12345.2",
            "counter": 2
        }
        mock_response2.raise_for_status = Mock()

        with patch.object(client.client, 'post', side_effect=[mock_response1, mock_response2]):
            with patch('os.getcwd', return_value="/test/path"):
                with patch('os.getpid', return_value=12345):
                    session1 = client.create_session()
                    session2 = client.create_session()

                    assert session1.counter == 1
                    assert session2.counter == 2
