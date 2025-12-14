# POAG API

OpenAPI specification and generated client/server for the Product Owner Agent Graph API.

## Overview

This subflake manages the POAG API specification and automatically generates:
- **FastAPI Server** - Python server implementation
- **Python Client** - Python client library
- **TypeScript Client** - TypeScript/JavaScript client library
- **API Documentation** - HTML documentation

All code generation is:
- **Fully offline** - Uses OpenAPI Generator CLI (no cloud calls)
- **Reproducible** - Deterministic builds via Nix
- **Pure** - No network access during builds
- **Validated** - Automated tests verify generated packages

## Code Generation

Code is generated automatically during `nix build` using [OpenAPI Generator](https://openapi-generator.tech/):

```bash
# Generate all packages
nix build .#server      # FastAPI server
nix build .#client-py   # Python client
nix build .#client-ts   # TypeScript client
nix build .#docs        # HTML documentation

# Access the generated code
ls -la result/
```

### Why OpenAPI Generator?

We switched from Fern to OpenAPI Generator because:
- ✅ Fully offline (packaged in nixpkgs)
- ✅ Works with `nix build` (pure, reproducible)
- ✅ Supports all error codes and response types
- ✅ Mature and widely adopted
- ✅ No cloud dependencies or Docker required

## Development Workflow

```bash
# Enter development environment
nix develop

# Edit the OpenAPI specification
vim poag.json

# Generate and test
nix build .#server
pytest tests/ -v

# Run all checks
nix flake check
```

### Important Notes

- The devShell loads **independently** of code generation
- Even if your OpenAPI spec has errors, you can still enter the devShell to fix them
- Code generation only happens when you explicitly run `nix build`
- Tests validate the structure of generated packages

## Testing

Tests are organized into three categories:

### 1. Specification Tests
- `test_openapi_spec.py` - Validates poag.json is valid OpenAPI 3.0
- `test_sessions_spec.py` - Tests session endpoint definitions

### 2. Generated Package Tests
- `test_generated_packages.py` - Validates structure of all generated packages
  - Checks for required files (models, APIs, etc.)
  - Verifies Python and TypeScript packages are well-formed
  - Ensures consistency across all three packages

### 3. Integration Tests
- Full end-to-end tests are in a separate subflake
- This keeps the API spec/generation focused and lightweight

Run tests:
```bash
# In devShell
pytest tests/ -v

# Or via Nix check
nix flake check
```

## Package Structure

### FastAPI Server (`nix build .#server`)
```
src/poag_api_server/
├── apis/              # API route handlers
├── models/            # Pydantic models
├── main.py           # FastAPI app entry point
└── security_api.py   # Authentication/security
```

### Python Client (`nix build .#client-py`)
```
poag_api_client/
├── api/              # API client methods
├── models/           # Data models (Pydantic)
├── api_client.py     # HTTP client
└── configuration.py  # Client config
```

### TypeScript Client (`nix build .#client-ts`)
```
src/
├── apis/             # API client classes
├── models/           # TypeScript interfaces
└── runtime.ts        # HTTP runtime
```

## OpenAPI Specification

The API is defined in `poag.json` (OpenAPI 3.0 format).

Current endpoints:
- `GET /hello` - Simple health check
- `POST /sessions` - Create new session

To modify the API:
1. Edit `poag.json`
2. Run `nix build .#<package>` to regenerate
3. Run `pytest` to validate
4. Commit changes

## Nix Flake Outputs

```bash
# Packages
nix build .#server      # FastAPI server package
nix build .#client-py   # Python client package
nix build .#client-ts   # TypeScript client package
nix build .#docs        # API documentation

# DevShell
nix develop            # Development environment

# Checks
nix flake check        # Run all tests
```

## Advanced Usage

### Custom OpenAPI Generator Options

The flake.nix file contains the OpenAPI Generator configuration. You can customize:
- Package names
- Generator versions
- Additional properties
- Template customizations

See the `flake.nix` file for the current configuration.

### Using in Other Projects

```nix
{
  inputs.poag-api.url = "path:./poag/poag-api";

  outputs = { self, poag-api, ... }: {
    # Use the generated packages
    myPackage = pkgs.buildEnv {
      name = "my-app";
      paths = [
        poag-api.packages.${system}.client-py
      ];
    };
  };
}
```

## CI/CD Integration

All builds are pure and reproducible:

```bash
# In CI pipeline
nix flake check              # Validate everything
nix build .#server           # Build server
nix build .#client-py        # Build Python client
nix build .#client-ts        # Build TypeScript client

# All outputs are in the Nix store with deterministic paths
```

## Troubleshooting

### DevShell won't load

The devShell is designed to load **even if the OpenAPI spec has errors**. If it's not loading, check:
- Nix flake evaluation errors
- Python dependency issues in pyproject.toml

### Generated code looks wrong

1. Check your OpenAPI spec is valid: `pytest tests/test_openapi_spec.py`
2. Review OpenAPI Generator logs (available in nix log)
3. Check the generator version in flake.nix

### Tests failing

Run tests with verbose output:
```bash
pytest tests/ -vv --tb=long
```

Check that the generated packages have the expected structure by examining the nix store output.

## License

See root repository for license information.
