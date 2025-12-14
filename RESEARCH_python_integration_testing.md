# Research: Integrating OpenAPI-Generated Python Packages in Nix Flakes

## Current Situation

We have a multi-flake Nix project using `pyproject-nix` and `uv2nix`. We're trying to integrate OpenAPI-generated Python client and server packages into our existing flake structure.

### Project Structure

```
poag/                                    # Parent flake
├── flake.nix                            # Integration tests (imports server + client)
├── tests/test_integration.py            # Needs: from poag_server import ..., from poag_client import ...
├── pyproject.toml                       # Lists poag-server, poag-client as dependencies
└── uv.lock

poag/poag-api/                           # OpenAPI spec + code generation
├── flake.nix                            # Generates client and server from OpenAPI spec
├── poag.json                            # OpenAPI 3.0 specification
└── outputs:
    ├── client-py (source)               # Generated: poag_api_client package (source)
    ├── client-py-pkg (package)          # Built: python3.12-poag-api-client-0.1.0
    ├── server (source)                  # Generated: poag_api_server package (source)
    └── server-pkg (package)             # Built: python3.12-poag-api-server-0.1.0

poag/poag-client/                        # Client wrapper (business logic)
├── flake.nix                            # Consumes poag-api as input
├── src/poag_client/client.py            # Imports: from poag_api_client import ApiClient, Configuration
├── pyproject.toml                       # Does NOT list poag-api-client (it's Nix-only)
└── uv.lock

poag/poag-server/                        # Server implementation (business logic)
├── flake.nix                            # Consumes poag-api as input
├── src/poag_server/main.py              # Imports: from poag_api_server.models import CreateSessionRequest
├── pyproject.toml                       # Does NOT list poag-api-server (it's Nix-only)
└── uv.lock
```

### What We're Trying to Achieve

1. **poag-api generates Python packages** from an OpenAPI spec using `openapi-generator-cli`
2. **poag-client wraps the generated client** with business logic (session management, etc.)
3. **poag-server implements the generated server models** with storage and actual endpoints
4. **Parent flake runs integration tests** that use both client and server together

### What Works

✅ **Code generation**: `poag-api` successfully generates Python source code and builds installable packages:
```nix
# poag-api/flake.nix
python-client-pkg = python.pkgs.buildPythonPackage {
  pname = "poag-api-client";
  version = "0.1.0";
  src = python-client;  # Generated source
  propagatedBuildInputs = [ pydantic python-dateutil urllib3 ... ];
};
```

✅ **Overlay injection**: Both child flakes inject the generated packages via overlays:
```nix
# poag-client/flake.nix
apiClientOverlay = final: prev: {
  poag-api-client = poag-api.packages.${system}.client-py-pkg;
};

pythonSet = pythonBase.overrideScope (
  pkgs.lib.composeManyExtensions [
    pyproject-build-systems.overlays.default
    workspace.mkPyprojectOverlay { sourcePreference = "wheel"; }
    apiClientOverlay
  ]
);
```

✅ **Packages build**: Both `poag-client` and `poag-server` build successfully:
```bash
$ nix build ./poag-client
$ nix build ./poag-server
# Both succeed!
```

### What Doesn't Work

❌ **Generated packages unavailable in dev shells**: The code imports `poag_api_client` but it's not available:
```bash
$ cd poag-client
$ nix develop
$ python -c "import poag_api_client"
ModuleNotFoundError: No module named 'poag_api_client'
```

❌ **Generated packages unavailable in integration tests**:
```bash
$ cd poag  # Parent flake
$ nix develop --command pytest tests/
ImportError: cannot import name 'CreateSessionRequest' from 'poag_api_server.models'
```

## The Core Problem

The generated API packages (`poag-api-client`, `poag-api-server`) are:
- ✅ Built as proper Python packages via `buildPythonPackage`
- ✅ Injected into the `pythonSet` via overlays
- ✅ Available when building packages with `nix build`
- ❌ **NOT available in virtual environments** created by `mkVirtualEnv`

### Why This Happens

When we create virtual environments, we use:
```nix
myEnv = pythonSet.mkVirtualEnv "my-env" workspace.deps.all;
```

The `workspace.deps.all` returns an attribute set of packages that come from `pyproject.toml`/`uv.lock`. The generated API packages are NOT in these files (they're Nix-only dependencies), so they're excluded from the venv.

### What We've Tried

**Attempt 1: Add to workspace.deps.all**
```nix
myEnv = pythonSet.mkVirtualEnv "my-env" (workspace.deps.all // {
  poag-api-client = pythonSet.poag-api-client;
});
```
**Result:** ❌ `error: expected a list but found a set: { type = "derivation"; ... }`

The issue: `pythonSet.poag-api-client` is a derivation, but `workspace.deps.all` expects a specific structure that `mkVirtualEnv` understands.

**Attempt 2: Add editable overlay in dev shell**
```nix
editablePythonSet = pythonSet.overrideScope (
  pkgs.lib.composeManyExtensions [
    editableOverlay
    apiClientOverlay  # Include generated package
  ]
);

devShells.default = pkgs.mkShell {
  buildInputs = [
    (editablePythonSet.mkVirtualEnv "dev" workspace.deps.all)
  ];
};
```
**Result:** ❌ Same error - the overlay adds the package to pythonSet, but `workspace.deps.all` doesn't include it

**Attempt 3: PYTHONPATH workaround**
```nix
shellHook = ''
  export PYTHONPATH="${pythonSet.poag-api-client}/lib/python3.12/site-packages:$PYTHONPATH"
'';
```
**Result:** 🤷 Not yet tested - would work but feels like a hack

**Attempt 4: Add to pyproject.toml**
```toml
[project]
dependencies = ["poag-api-client>=0.1.0"]

[tool.uv.sources]
poag-api-client = { path = "../poag-api/generated/client" }
```
**Result:** ❌ Can't work - the generated code isn't in a stable path, it's in `/nix/store/...`

## Key Questions for Further Research

### 1. How does `mkVirtualEnv` work internally?
- What structure does it expect from the deps attribute set?
- Can we manually construct the right structure for Nix-only packages?
- Is there a way to add packages to a venv after it's created?

### 2. What is the intended pattern for Nix-only Python dependencies?
- These packages don't exist in PyPI
- They're not in `pyproject.toml`/`uv.lock`
- They're only available through Nix
- How do pyproject-nix/uv2nix handle this case?

### 3. Is there an alternative to `mkVirtualEnv`?
- Can we use `buildEnv` or `python.withPackages` instead?
- Would that work with uv2nix's workspace model?
- What would we lose (editable installs, etc.)?

### 4. Should generated code be handled differently?
- Maybe generated packages should be in a separate derivation?
- Perhaps we need a "build-time only" vs "runtime" package distinction?
- Is there a way to make generated packages look like regular workspace dependencies?

### 5. How do propagatedBuildInputs work with mkVirtualEnv?
- When we include `poag-client` in the parent venv, should its `propagatedBuildInputs` (including `poag-api-client`) be automatically available?
- If so, why isn't it working?
- Do we need to explicitly declare the dependency relationship somewhere?

## What We Need

A way to make Nix-generated Python packages available in virtual environments created by `mkVirtualEnv`, such that:

- ✅ Works in `nix develop` (development shells)
- ✅ Works in `nix flake check` (CI/test environments)
- ✅ Works in `nix build` (production builds)
- ✅ Respects dependency relationships (if A depends on B, including A should pull in B)
- ✅ Integrates cleanly with pyproject-nix/uv2nix patterns
- ✅ Doesn't require manual `PYTHONPATH` manipulation
- ✅ Allows editable installs for workspace packages

## Reproduction Steps

```bash
cd /path/to/hello-subflakes/poag/poag-client
nix develop
python -c "import poag_api_client"  # Fails with ModuleNotFoundError
```

## Environment Details

- Nix version: 2.x (with flakes enabled)
- nixpkgs: nixos-unstable
- Python: 3.12
- pyproject-nix: latest (from GitHub)
- uv2nix: latest (from GitHub)
- uv: 0.9.x

---

**Current status**: We have working generated Python packages and overlays that inject them into pythonSet, but they're not accessible in virtual environments created by `mkVirtualEnv`. We need to understand how to either (a) make `mkVirtualEnv` include Nix-only dependencies, or (b) use a different environment construction approach that works with our use case.
