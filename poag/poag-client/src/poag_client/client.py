"""POAG Client with session management."""

import os
from dataclasses import dataclass

import httpx
from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""

    cwd: str
    pid: int


class SessionResponse(BaseModel):
    """Response containing session information."""

    session_id: str
    counter: int


class HelloResponse(BaseModel):
    """Simple hello world response."""

    message: str


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
        self.client = httpx.Client(base_url=base_url)

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

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
        response = self.client.get("/hello")
        response.raise_for_status()
        data = HelloResponse.model_validate(response.json())
        return data.message

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
        response = self.client.post("/sessions", json=request.model_dump())
        response.raise_for_status()

        data = SessionResponse.model_validate(response.json())
        return Session(session_id=data.session_id, counter=data.counter)
