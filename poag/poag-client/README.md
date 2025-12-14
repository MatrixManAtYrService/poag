# POAG Client

Python client library for POAG with session management and convenience wrappers.

## Features

- **Session Management**: Automatically derives session IDs from cwd/pid
- **Convenience API**: Simple wrapper around the generated client from `poag-api`
- **OTEL Integration**: Session IDs used for trace correlation
- **Testable**: Mocking-friendly design for unit tests

## Usage

```python
from poag_client import PoagClient

# Initialize client
with PoagClient(base_url="http://localhost:8000") as client:
    # Test connection
    message = client.hello()  # Returns "world"

    # Create a session (automatically uses os.getcwd() and os.getpid())
    session = client.create_session()
    print(f"Session ID: {session.session_id}")  # e.g., "/home/user/project.12345.1"
    print(f"Counter: {session.counter}")        # 1

    # Create another session (counter increments)
    session2 = client.create_session()
    print(f"Counter: {session2.counter}")       # 2
```

## Session ID Format

Session IDs follow the pattern: `{cwd}.{pid}.{counter}`

- **cwd**: Current working directory where `poag` was invoked
- **pid**: Process ID of the poag invocation
- **counter**: Increments for each new session from the same cwd/pid pair

This session ID is used for OpenTelemetry trace correlation when using `poag ask` or `poag plan` commands (see `agent-primers/langgraph/observability.md`).

## Development

```bash
# Enter development environment
nix develop

# Run tests
pytest tests/ -v

# Run checks
nix flake check
```

## Testing

Tests use mocking to avoid requiring a running server:

```python
def test_create_session_with_explicit_values():
    with PoagClient() as client:
        # Mock the server response
        mock_response = Mock()
        mock_response.json.return_value = {
            "session_id": "/custom/path.99999.2",
            "counter": 2
        }

        with patch.object(client.client, 'post', return_value=mock_response):
            session = client.create_session(cwd="/custom/path", pid=99999)
            assert session.counter == 2
```

## Integration with poag-server

The client talks to `poag-server` which:
1. Receives the cwd and pid
2. Looks up existing sessions in SQLite
3. Increments the counter
4. Returns the full session_id

Integration tests (client + server together) are in the parent `poag` flake.

## Architecture

```
┌─────────────────┐
│ Generated Client│  ← From poag-api#client-py (OpenAPI Generator)
│ (API methods)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ POAG Client     │  ← This flake (session management wrappers)
│ (poag-client)   │
└─────────────────┘
```

The generated client provides low-level API access. This wrapper adds:
- Session ID derivation from environment
- Convenience methods
- Future: retry logic, error handling, etc.
