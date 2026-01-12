# Minimal Demo: Nix-Only Python Package Integration with uv2nix

This demo shows the challenge of integrating a Nix-built Python library into a uv2nix-based consumer project.

## The Problem

How can a uv2nix-based project consume a Nix-only Python package (not in PyPI) without:
1. Manually listing all transitive dependencies in the consumer's `pyproject.toml`
2. Using PYTHONPATH hacks

## Demo Structure

```
nix-python-integration-demo/
├── flake.nix              # Consumer: hello CLI
├── pyproject.toml         # Consumer dependencies
├── uv.lock
├── src/
│   └── hello_cli/
│       └── __init__.py    # CLI entrypoint
└── greeting-lib/
    ├── flake.nix          # Library: greeting function
    ├── pyproject.toml     # Library dependencies (pydantic)
    └── src/
        └── greeting/
            └── __init__.py
```

## Setup Instructions

### 1. Create the directory structure

```bash
mkdir -p nix-python-integration-demo/greeting-lib/src/greeting
mkdir -p nix-python-integration-demo/src/hello_cli
cd nix-python-integration-demo
```

### 2. Create the greeting library (inner flake)

**File: `greeting-lib/pyproject.toml`**
```toml
[project]
name = "greeting"
version = "0.1.0"
description = "A simple greeting library (Nix-only, not in PyPI)"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

**File: `greeting-lib/src/greeting/__init__.py`**
```python
"""A simple greeting library that returns a pydantic model."""
from pydantic import BaseModel


class Greeting(BaseModel):
    """A greeting message."""
    greeting: str


def get_greeting() -> Greeting:
    """Return a greeting."""
    return Greeting(greeting="world")
```

**File: `greeting-lib/flake.nix`**
```nix
{
  description = "Greeting library - Nix-only Python package";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pyproject-build-systems.url = "github:pyproject-nix/build-system-pkgs";
  };

  outputs = { self, nixpkgs, flake-utils, pyproject-nix, uv2nix, pyproject-build-systems }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

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

      in
      {
        packages = {
          default = pythonSet.greeting;
          lib = pythonSet.greeting;
        };
      }
    );
}
```

**File: `greeting-lib/uv.lock`** (generate with `cd greeting-lib && uv lock`)

### 3. Create the hello CLI (outer flake)

**File: `pyproject.toml`**
```toml
[project]
name = "hello-cli"
version = "0.1.0"
description = "A CLI that uses the greeting library"
requires-python = ">=3.12"
dependencies = [
    # greeting library is provided via Nix PYTHONPATH (not in PyPI)
    #
    # PROBLEM: We must manually list greeting's transitive deps here
    # because uv2nix can't access the Nix-built package at evaluation time
    "pydantic>=2.0.0",  # <-- Transitive dep from greeting library
]

[project.scripts]
hello = "hello_cli:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

**File: `src/hello_cli/__init__.py`**
```python
"""A simple CLI that uses the greeting library."""
from greeting import get_greeting


def main():
    """Print hello world using the greeting library."""
    greet = get_greeting()
    print(f"hello {greet.greeting}")


if __name__ == "__main__":
    main()
```

**File: `flake.nix`**
```nix
{
  description = "Hello CLI - consumes Nix-only greeting library";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Consume the greeting library
    greeting-lib.url = "path:./greeting-lib";

    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pyproject-build-systems.url = "github:pyproject-nix/build-system-pkgs";
  };

  outputs = { self, nixpkgs, flake-utils, greeting-lib, pyproject-nix, uv2nix, pyproject-build-systems }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

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

        # Virtual environment with dependencies from uv.lock
        helloEnv = pythonSet.mkVirtualEnv "hello-cli-env" workspace.deps.default;

      in
      {
        packages.default = helloEnv;

        devShells.default = pkgs.mkShell {
          buildInputs = [ helloEnv ];
          env = {
            # WORKAROUND: Add greeting library via PYTHONPATH
            # This works, but feels like a hack
            PYTHONPATH = "${greeting-lib.packages.${system}.lib}/${python.sitePackages}";
          };
          shellHook = ''
            echo "Hello CLI development environment"
            echo "Run: hello"
          '';
        };
      }
    );
}
```

**File: `uv.lock`** (generate with `uv lock`)

### 4. Initialize and test

```bash
# From greeting-lib directory
cd greeting-lib
uv lock
cd ..

# From root directory
uv lock

# Test the CLI
nix develop --command hello
# Should print: hello world

# Verify it works
nix build .#default
result/bin/hello
# Should print: hello world
```

## The Question for the Community

**Current Working Solution (PYTHONPATH injection):**
```nix
devShells.default = pkgs.mkShell {
  env = {
    PYTHONPATH = "${greeting-lib.packages.${system}.lib}/${python.sitePackages}";
  };
};
```

**Problems with this approach:**
1. Have to manually list `pydantic` in the consumer's `pyproject.toml` even though it's only a transitive dependency
2. Using `PYTHONPATH` feels like a hack
3. Can't use uv's path dependencies because `workspace.loadWorkspace` runs at Nix evaluation time (before derivations are built)

**Questions:**
- Is there a better way to integrate Nix-only Python packages with uv2nix?
- Can overlays work without causing `passthru.dependencies` structure errors?
- Should we contribute support for this pattern to uv2nix?

## What Doesn't Work

**Attempt 1: Overlay injection**
```nix
# This causes: "expected a list but found a set: { pydantic = [ ]; }"
greetingOverlay = final: prev: {
  greeting = greeting-lib.packages.${system}.lib;
};
```

**Attempt 2: Path dependencies**
```toml
# In pyproject.toml
[tool.uv.sources]
greeting = { path = "./greeting-lib" }

# This causes: "internal error: accessed dependencies from pyproject.nix project, not uv.lock"
# Because ./greeting-lib doesn't exist at evaluation time
```

**Attempt 3: Derived source tree**
```nix
# Doesn't work because loadWorkspace expects path type, not derivation
srcWithGreeting = pkgs.runCommand "src-with-greeting" {} ''
  cp -r ${./.} $out
  ln -s ${greeting-lib.packages.${system}.lib} $out/greeting-lib
'';
```

## Repository Files Summary

This creates a fully working demo showing:
- ✅ What works (PYTHONPATH injection)
- ❌ What the problems are (manual transitive deps, PYTHONPATH hack)
- ❓ What we'd like instead (clean overlay or path dependency support)
