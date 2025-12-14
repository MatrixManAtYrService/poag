"""POAG Client with session management."""

import os
from dataclasses import dataclass

# Import the generated API client
from poag_api_client import ApiClient, Configuration
from poag_api_client.api import HelloApi, SessionsApi
from poag_api_client.models import CreateSessionRequest


@dataclass
class Session:
    """Represents a POAG session."""

    session_id: str
    counter: int


class PoagClient:
    """POAG API client with convenience methods for session management.

    This client wraps the generated API client (from poag-api) with
    business logic for deriving session IDs and managing connections.

    Sessions are identified by {cwd}.{pid}.{counter} where:
    - cwd: Current working directory where poag was invoked
    - pid: Process ID of the poag invocation
    - counter: Increments for each session from the same cwd/pid

    The session_id is used for OpenTelemetry trace correlation.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize the POAG client.

        Args:
            base_url: Base URL of the POAG server
        """
        self.base_url = base_url

        # Configure and create the generated API client
        config = Configuration(host=base_url)
        self.api_client = ApiClient(configuration=config)

        # Create API instances
        self.hello_api = HelloApi(self.api_client)
        self.sessions_api = SessionsApi(self.api_client)

    def close(self) -> None:
        """Close the API client."""
        self.api_client.close()

    def __enter__(self) -> "PoagClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.close()

    def hello(self) -> str:
        """Test the connection with the hello endpoint.

        Returns:
            The message from the server (should be "world")
        """
        response = self.hello_api.get_hello()
        return response.message

    def create_session(self, cwd: str | None = None, pid: int | None = None) -> Session:
        """Create a new session on the server.

        The client derives the partial session ID from the current environment,
        then posts it to the server which adds the counter and returns the
        full session_id.

        Args:
            cwd: Current working directory (defaults to os.getcwd())
            pid: Process ID (defaults to os.getpid())

        Returns:
            Session object with session_id and counter
        """
        if cwd is None:
            cwd = os.getcwd()
        if pid is None:
            pid = os.getpid()

        request = CreateSessionRequest(cwd=cwd, pid=pid)
        response = self.sessions_api.create_session(request)

        return Session(session_id=response.session_id, counter=response.counter)
