# POAG API

OpenAPI specification and code generation for the POAG (Product Owner Agent Graph) API.

## Overview

This subflake provides:
- **OpenAPI spec** (`poag.json`) defining the API contract
- **Python client SDK** generated from the spec
- **FastAPI server** generated from the spec
- **Type-safe** Pydantic v2 models shared between client and server

## Quick Start

```bash
# Enter the development shell
nix develop

# Generate client and server code with Fern (requires Docker)
./scripts/generate.sh

# Run tests
pytest tests/ -v

# Build packages
nix build .#client-py
nix build .#server
```

## Code Generation

### Fern-based Generation (Recommended)

For full type safety and Pydantic v2 support:

```bash
# Generate both client and server
./scripts/generate.sh

# Or use Fern directly
cd fern
fern generate --group all
```

This generates:
- `generated/client-py/` - Full Python SDK with async support
- `generated/server/` - FastAPI server stubs with abstract service classes

### Stub Generation (Fallback)

If you don't run Fern generation, Nix builds will use simple stub implementations that work for basic testing but lack the full type safety and features of Fern-generated code.

## Project Structure

```
poag-api/
├── poag.json                # OpenAPI 3.0 specification
├── fern/                    # Fern configuration
│   ├── fern.config.json
│   └── generators.yml       # Python client + FastAPI server config
├── generated/               # Fern output (gitignored, regenerate locally)
│   ├── client-py/
│   └── server/
├── scripts/
│   └── generate.sh          # Fern generation script
├── tests/
│   ├── test_openapi_spec.py        # Spec validation
│   └── test_client_server_integration.py  # Integration tests
├── pyproject.toml           # Dependencies
├── uv.lock                  # Locked dependencies
└── flake.nix                # Nix package definition
```

## Fern Configuration

The `fern/generators.yml` configures two generators:

1. **fernapi/fern-python-sdk** (v4.45.9)
   - Generates typed Python client with sync/async support
   - Pydantic v2 models
   - Auto-pagination, retries, OAuth support

2. **fernapi/fern-fastapi-server** (v0.0.33)
   - Generates abstract service classes
   - FastAPI app registration
   - Pydantic v2 request/response models

Both use `pydantic_config.version: v2` for native Pydantic v2 support.

## Development Workflow

### 1. Modify the API

Edit `poag.json` to add/change endpoints:

```json
{
  "paths": {
    "/hello": {
      "get": {
        "operationId": "getHello",
        "responses": { ... }
      }
    }
  }
}
```

### 2. Validate

```bash
fern check
```

### 3. Regenerate Code

```bash
./scripts/generate.sh
```

### 4. Implement Business Logic

For Fern-generated servers, implement the abstract service classes:

```python
# my_implementation.py (NOT in generated/)
from generated.server.resources.hello.service.service import AbstractHelloService
from generated.server.types import HelloResponse

class HelloService(AbstractHelloService):
    def get_hello(self) -> HelloResponse:
        return HelloResponse(message="world")
```

Then register with your FastAPI app:

```python
from fastapi import FastAPI
from generated.server.register import register
from my_implementation import HelloService

app = FastAPI()
register(app, hello=HelloService())
```

### 5. Test

```bash
pytest tests/ -v
```

## Using the Generated Client

```python
from generated.client_py import PoagClient

# Synchronous
client = PoagClient(base_url="http://localhost:8000")
response = client.hello.get_hello()
print(response.message)  # "world"

# Async
from generated.client_py import AsyncPoagClient

async def main():
    client = AsyncPoagClient(base_url="http://localhost:8000")
    response = await client.hello.get_hello()
    print(response.message)
```

## Nix Builds

The flake provides these outputs:

- `packages.default` - Python environment with all dependencies
- `packages.client-py` - Generated Python client SDK
- `packages.server` - Generated FastAPI server stubs
- `packages.test-env` - Combined environment for testing
- `checks.pytest` - Automated test suite

## Testing

The test suite includes:

1. **OpenAPI Spec Validation** - Ensures `poag.json` is valid
2. **Integration Tests** - Tests client + server together
   - Builds both packages with Nix
   - Starts FastAPI server
   - Calls endpoints with generated client
   - Validates responses match schema

## Next Steps

This is **Milestone 1** of the POAG project. Future milestones:

- **Milestone 2**: Business logic libraries (poag-server-logic, poag-client-logic)
- **Milestone 3**: TypeScript client + React UI (poag-ui)
- **Milestone 4**: Wire into main `poag` CLI

## References

- [Fern Documentation](https://docs.buildwithfern.com/)
- [OpenAPI 3.0 Spec](https://swagger.io/specification/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Pydantic v2](https://docs.pydantic.dev/latest/)
