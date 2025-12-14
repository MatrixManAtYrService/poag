# POAG Server

Business logic layer for the POAG API server, built on top of the generated FastAPI code from `poag-api`.

## Features

- **Session Management**: SQLite-based session storage with cwd/pid-based session IDs
- **XDG Directories**: Follows XDG base directory specification for data and state
- **Dependency Injection**: Testable design with sandboxed storage for tests
- **Integration**: Consumes generated FastAPI server from `poag-api` flake

## Architecture

```
┌─────────────────┐
│ Generated API   │  ← From poag-api#server (OpenAPI Generator)
│ (FastAPI routes)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Business Logic  │  ← This flake (session management)
│ (poag-server)   │
└─────────────────┘
```

## Session Management

Sessions are identified by `{cwd}.{pid}.{counter}` format:

- **cwd**: Current working directory where `poag` was invoked
- **pid**: Process ID of the poag invocation
- **counter**: Increments for each new session from the same cwd/pid pair

This session ID is used for OpenTelemetry trace correlation (see `agent-primers/langgraph/observability.md`).

### Storage Location

- **Sessions DB**: `$XDG_DATA_HOME/poag/sessions.db` (default: `~/.local/share/poag/sessions.db`)
- **Server State**: `$XDG_STATE_HOME/poag/` (port, pid files)

### Dependency Injection

The `Home` class (modeled after trifolium's config pattern) supports sandboxing for tests:

```python
from poag_server.config import Home
from poag_server.storage import SessionStorage

# Production use
home = Home()  # Uses XDG directories
storage = SessionStorage(home.sessions_db)

# Testing use
home = Home.sandbox("/tmp/test")  # Custom paths
storage = SessionStorage(home.sessions_db)
```

## Development

```bash
# Enter development environment
nix develop

# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_storage.py -v  # Session storage tests
pytest tests/test_api.py -v      # FastAPI endpoint tests
pytest tests/test_config.py -v   # Configuration tests

# Run checks
nix flake check
```

## API Endpoints

### POST /sessions

Create a new session with automatic counter increment.

**Request:**
```json
{
  "cwd": "/home/user/my-project",
  "pid": 12345
}
```

**Response:**
```json
{
  "session_id": "/home/user/my-project.12345.1",
  "counter": 1
}
```

### GET /hello

Health check endpoint.

**Response:**
```json
{
  "message": "world"
}
```

## Testing

Tests use dependency injection to create sandboxed environments:

```python
@pytest.fixture
def temp_home():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Home.sandbox(tmpdir)

def test_session_creation(temp_home):
    storage = SessionStorage(temp_home.sessions_db)
    session = storage.create_session(cwd="/test", pid=123)
    assert session.counter == 1
```

## Integration with poag-client

The `poag-client` flake consumes this server's API:

1. Client derives partial session ID from local cwd and pid
2. Client POSTs to `/sessions` endpoint
3. Server returns full session_id with counter
4. Client uses session_id for OTEL tracing in `poag ask` and `poag plan` commands

## Future Enhancements

- Session expiration and cleanup
- Session metadata (timestamps, user info)
- Session listing and search endpoints
- Metrics and observability integration
