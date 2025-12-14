# Research: Integration Testing with Multiple Python Subflakes in Nix

## Context

I have a multi-flake Nix project where each subflake is a Python package managed with `pyproject-nix` and `uv2nix`. I need to run integration tests in a parent flake that import packages from multiple child flakes.

## Current Setup

### Flake Structure
```
poag/                          # Parent flake
├── flake.nix                  # Consumes poag-server and poag-client
├── tests/test_integration.py  # Needs: import poag_server, import poag_client
├── pyproject.toml
└── uv.lock

poag/poag-server/              # Child flake 1
├── flake.nix                  # Consumes poag-api
├── src/poag_server/
├── pyproject.toml
└── uv.lock

poag/poag-client/              # Child flake 2
├── flake.nix                  # Consumes poag-api
├── src/poag_client/
├── pyproject.toml
└── uv.lock
```

### How Each Flake Creates Its Environment

Each child flake uses this pattern:
```nix
{
  inputs.pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
  inputs.uv2nix.url = "github:pyproject-nix/uv2nix";

  outputs = { pyproject-nix, uv2nix, ... }:
    let
      workspace = uv2nix.lib.workspace.loadWorkspace {
        workspaceRoot = ./.;
      };

      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      pythonSet = (pkgs.callPackage pyproject-nix.build.packages {
        inherit python;
      }).overrideScope (
        pkgs.lib.composeManyExtensions [
          pyproject-build-systems.overlays.default
          overlay
        ]
      );

      # Virtual environment with dependencies
      myEnv = pythonSet.mkVirtualEnv "my-env" workspace.deps.all;
    in {
      packages.default = myEnv;
    };
}
```

## The Problem

In the parent flake, I want to run integration tests that import both `poag_server` and `poag_client`:

```python
# tests/test_integration.py
from poag_server.main import app        # From child flake 1
from poag_client import PoagClient      # From child flake 2

def test_integration():
    # Test that client can talk to server
    ...
```

### What I Tried

**Attempt 1: `buildEnv` to merge environments**
```nix
integrationEnv = pkgs.buildEnv {
  name = "integration-env";
  paths = [
    poagEnv                          # Parent's venv
    poag-server.packages.${system}.default   # Child 1's venv
    poag-client.packages.${system}.default   # Child 2's venv
  ];
};
```

**Result:** ❌ Failed with:
```
pkgs.buildEnv error: two given paths contain a conflicting subpath:
  `/nix/store/.../poag-server-env/bin/python3' and
  `/nix/store/.../poag-env/bin/python3'
```

**Attempt 2: Manual `PYTHONPATH`**
```nix
shellHook = ''
  export PYTHONPATH="${poag-server.packages.${system}.default}/lib/python3.12/site-packages:${poag-client.packages.${system}.default}/lib/python3.12/site-packages:$PYTHONPATH"
'';
```

**Status:** 🤷 Untested - feels like a hack, may have issues with transitive dependencies

## Questions

1. **What is the idiomatic way to make packages from multiple `pyproject-nix` flakes available for integration testing?**

2. **Should I:**
   - Add `poag-server` and `poag-client` as dependencies in the parent's `pyproject.toml`?
   - Use `uv2nix` workspace features to create a multi-package workspace?
   - Use `pyproject-nix` overlays to compose the environments?
   - Manually manage `PYTHONPATH` (and is there a cleaner way)?
   - Something else entirely?

3. **How do I handle the fact that each child flake's packages are outputs of Nix builds, not editable installs?**
   - The test needs to import from `${child-flake}/lib/python3.12/site-packages/package_name`
   - Should I create a custom overlay that adds these paths?

4. **Is there a way to create a "test-only" Python environment that:**
   - Uses the parent flake's dependencies (pytest, etc.)
   - Can import from multiple child flakes
   - Works with both `nix develop` and `nix flake check`
   - Doesn't require manual `PYTHONPATH` manipulation

5. **Are there examples of multi-flake Python projects using `pyproject-nix`/`uv2nix` with integration tests?**

## Constraints

- Each subflake should remain independently testable (their own unit tests work)
- The parent flake should not duplicate the child flakes' dependencies
- Should work in both development (`nix develop`) and CI (`nix flake check`)
- Prefer idiomatic Nix patterns over shell hacks

## Desired Outcome

A clean, reusable pattern for:
```nix
# Parent flake
{
  inputs = {
    child-flake-1.url = "path:./child1";
    child-flake-2.url = "path:./child2";
  };

  outputs = { ... }:
    let
      # ??? How to create testEnv that can import from both child flakes ???
    in {
      devShells.default = pkgs.mkShell {
        # Tests can: import child1_package, import child2_package
      };

      checks.pytest = pkgs.runCommand "integration-tests" {
        # Same capability
      } ''
        pytest tests/
      '';
    };
}
```

## Additional Context

- Using `nixpkgs` from `nixos-unstable` channel
- Python 3.12
- `pyproject-nix` latest (follows approach in their examples)
- `uv2nix` latest (uses `workspace.loadWorkspace` pattern)
- Child flakes already export their packages via `packages.default`

---

## Solution: Pre-built Derivation Injection

After trying multiple approaches, the cleanest solution is **Option 1: Export pre-built derivations directly**.

### How It Works

1. **Child flakes** build their packages using pyproject-nix and export the built derivation:
   ```nix
   # poag-server/flake.nix
   {
     packages = {
       default = pythonSet.mkVirtualEnv "env" workspace.deps.default;
       lib = pythonSet.poag-server;  # Export the built package derivation
     };
   }
   ```

2. **Parent flake** declares dependencies in `pyproject.toml`:
   ```toml
   [project]
   dependencies = [
     "poag-server>=0.1.0",
     "poag-client>=0.1.0",
   ]

   [tool.uv.sources]
   poag-server = { path = "./poag-server", editable = true }
   poag-client = { path = "./poag-client", editable = true }
   ```

3. **Parent flake** injects pre-built derivations via overlay:
   ```nix
   # poag/flake.nix
   let
     overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

     # Inject pre-built derivations from child flakes
     childOverrides = final: prev: {
       poag-server = poag-server.packages.${system}.lib;
       poag-client = poag-client.packages.${system}.lib;
     };

     pythonSet = pythonBase.overrideScope (
       pkgs.lib.composeManyExtensions [
         pyproject-build-systems.overlays.default
         overlay
         childOverrides  # Replaces packages with pre-built versions
       ]
     );
   in
   {
     # Use pythonSet to create virtualenvs
     packages.default = pythonSet.mkVirtualEnv "poag-env" workspace.deps.all;
   }
   ```

### Why This Works

- **No wheel file handling**: pyproject-nix expects derivations, not wheel files
- **Independent builds**: Each child flake builds its package separately
- **No duplication**: Parent doesn't rebuild what children already built
- **Clean composition**: Uses standard Nix overlay mechanism
- **Works everywhere**: `nix develop`, `nix flake check`, and `nix build` all work

### Test Results

- ✅ All child flake tests pass independently (19 tests for server, 6 for client)
- ✅ All integration tests pass (7 tests)
- ✅ Works in `nix develop` for interactive testing
- ✅ Works in `nix flake check` for CI

### Why NOT Wheel Injection

The initial attempt to export wheel files failed because pyproject-nix's build infrastructure expects source trees or derivations, not pre-built `.whl` files. When you override `src` with a wheel path, the unpack phase doesn't know how to handle it.

---

**Research completed:** Pre-built derivation injection is the idiomatic pattern for multi-flake Python integration with pyproject-nix/uv2nix
