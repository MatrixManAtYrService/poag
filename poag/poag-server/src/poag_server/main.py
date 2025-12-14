"""POAG Server FastAPI application with business logic."""

from fastapi import FastAPI
from pydantic import BaseModel

from poag_server.config import Home
from poag_server.storage import SessionStorage

# Models that match the OpenAPI spec
# (These will be replaced by imports from the generated code in the full integration)


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


# Initialize application
app = FastAPI(
    title="POAG API",
    description="Product Owner Agent Graph API for managing agent interactions and sessions",
    version="0.1.0"
)

# Global storage (will be dependency-injected in tests)
_storage: SessionStorage | None = None


def get_storage() -> SessionStorage:
    """Get or create the session storage instance."""
    global _storage
    if _storage is None:
        home = Home()
        _storage = SessionStorage(home.sessions_db)
    return _storage


def set_storage(storage: SessionStorage) -> None:
    """Set the session storage instance (for testing)."""
    global _storage
    _storage = storage


@app.get("/hello", response_model=HelloResponse)
async def get_hello() -> HelloResponse:
    """Simple hello endpoint for health checks."""
    return HelloResponse(message="world")


@app.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest) -> SessionResponse:
    """Create a new session.

    Sessions are tracked by cwd and pid, with an incrementing counter.
    The session_id format is: {cwd}.{pid}.{counter}

    This session_id can be used for OTEL tracing correlation.
    """
    storage = get_storage()
    session = storage.create_session(cwd=request.cwd, pid=request.pid)

    return SessionResponse(
        session_id=session.session_id,
        counter=session.counter
    )
