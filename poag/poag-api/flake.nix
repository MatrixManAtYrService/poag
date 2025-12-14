{
  description = "POAG API - OpenAPI specification and generated client/server";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Inherit Python tooling from parent poag flake
    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pyproject-build-systems.url = "github:pyproject-nix/build-system-pkgs";
  };

  outputs = { self, nixpkgs, flake-utils, pyproject-nix, uv2nix, pyproject-build-systems }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        # Build Fern CLI directly
        fernCli = pkgs.stdenv.mkDerivation rec {
          pname = "fern-api";
          version = "0.95.2";

          src = pkgs.fetchurl {
            url = "https://registry.npmjs.org/fern-api/-/fern-api-${version}.tgz";
            hash = "sha256-yC64q0zLzlKuY1Appsmw+iNBFTKCmE5TE1NQCpOj7ag=";
          };

          nativeBuildInputs = [ pkgs.nodejs pkgs.makeWrapper ];

          dontBuild = true;
          dontConfigure = true;

          installPhase = ''
            runHook preInstall

            mkdir -p $out/lib/node_modules/${pname}
            cp -r . $out/lib/node_modules/${pname}
            mkdir -p $out/bin

            # Find and link the executable
            if [ -f $out/lib/node_modules/${pname}/cli.cjs ]; then
              makeWrapper ${pkgs.nodejs}/bin/node $out/bin/fern \
                --add-flags "$out/lib/node_modules/${pname}/cli.cjs"
            elif [ -f $out/lib/node_modules/${pname}/dist/bundle.cjs ]; then
              makeWrapper ${pkgs.nodejs}/bin/node $out/bin/fern \
                --add-flags "$out/lib/node_modules/${pname}/dist/bundle.cjs"
            else
              echo "ERROR: Could not find fern entry point!"
              ls -la $out/lib/node_modules/${pname}
              exit 1
            fi

            runHook postInstall
          '';
        };

        # Load the workspace for dependency management
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

        # Editable overlay for development
        editableOverlay = workspace.mkEditablePyprojectOverlay {
          root = "$REPO_ROOT";
        };

        editablePythonSet = pythonSet.overrideScope editableOverlay;

        # Virtual environment with all dependencies (including dev)
        apiEnv = pythonSet.mkVirtualEnv "poag-api-env" workspace.deps.default;

        # Python client - use Fern-generated code if available, otherwise create stub
        poagApiClientPy = pkgs.stdenv.mkDerivation {
          pname = "poag-api-client-py";
          version = "0.1.0";

          src = ./.;

          buildPhase = ''
            # Check if Fern-generated client exists (user ran scripts/generate.sh)
            if [ -d generated/client-py ] && [ -f generated/client-py/pyproject.toml ]; then
              echo "Using Fern-generated Python client"
              cp -r generated/client-py ./client-build
            else
              echo "Fern-generated client not found, creating stub client"
              echo "Run 'scripts/generate.sh' in devShell to generate with Fern"
              mkdir -p ./client-build/poag_client

              cat > ./client-build/poag_client/__init__.py <<'PYEOF'
"""POAG API Python Client - Stub implementation
Run scripts/generate.sh in the devShell to generate the full client with Fern.
"""
import httpx
from typing import Dict, Any

class PoagClient:
    """Client for POAG API"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url)

    def get_hello(self) -> Dict[str, Any]:
        """Call the /hello endpoint"""
        response = self.client.get("/hello")
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close the HTTP client"""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
PYEOF

              cat > ./client-build/pyproject.toml <<'TOMLEOF'
[project]
name = "poag-api-client-py"
version = "0.1.0"
dependencies = ["httpx>=0.28.1", "pydantic>=2.10.5"]
TOMLEOF
            fi
          '';

          installPhase = ''
            mkdir -p $out
            cp -r ./client-build $out/client-py
          '';
        };

        # FastAPI server - use Fern-generated code if available, otherwise create stub
        poagApiServer = pkgs.stdenv.mkDerivation {
          pname = "poag-api-server";
          version = "0.1.0";

          src = ./.;

          buildPhase = ''
            # Check if Fern-generated server exists (user ran scripts/generate.sh)
            if [ -d generated/server ]; then
              echo "Using Fern-generated FastAPI server"
              cp -r generated/server ./server-build
            else
              echo "Fern-generated server not found, creating stub server"
              echo "Run 'scripts/generate.sh' in devShell to generate with Fern"
              mkdir -p ./server-build/server

              cat > ./server-build/server/models.py <<'PYEOF'
"""Generated Pydantic models for POAG API"""
from pydantic import BaseModel

class HelloResponse(BaseModel):
    """Response from /hello endpoint"""
    message: str
PYEOF

              cat > ./server-build/server/main.py <<'PYEOF'
"""POAG API Server - Stub implementation
Run scripts/generate.sh in the devShell to generate the full server with Fern.
"""
from fastapi import FastAPI
from .models import HelloResponse

app = FastAPI(
    title="POAG API",
    description="Product Owner Agent Graph API",
    version="0.1.0"
)

@app.get("/hello", response_model=HelloResponse, tags=["hello"])
async def get_hello() -> HelloResponse:
    """Hello World endpoint"""
    return HelloResponse(message="world")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
PYEOF

              cat > ./server-build/server/__init__.py <<'PYEOF'
"""POAG API Server"""
from .main import app
__all__ = ["app"]
PYEOF
            fi
          '';

          installPhase = ''
            mkdir -p $out
            cp -r ./server-build/server $out/
          '';
        };

        # Combined test environment with both client and server
        testEnv = pkgs.buildEnv {
          name = "poag-api-test-env";
          paths = [
            apiEnv
            poagApiClientPy
            poagApiServer
          ];
        };

      in
      {
        packages = {
          default = apiEnv;
          client-py = poagApiClientPy;
          server = poagApiServer;
          test-env = testEnv;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            (editablePythonSet.mkVirtualEnv "poag-api-dev" workspace.deps.all)
            uv
            fernCli
          ];
          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
          };
          shellHook = ''
            export REPO_ROOT=$(pwd)
            chmod +x scripts/generate.sh 2>/dev/null || true

            echo "POAG API development environment"
            echo ""
            echo "Code generation:"
            echo "  ./scripts/generate.sh   # Generate client & server with Fern (requires Docker)"
            echo "  fern check              # Validate OpenAPI spec and Fern config"
            echo ""
            echo "Testing & building:"
            echo "  pytest tests/ -v        # Run tests"
            echo "  nix build .#client-py   # Build Python client"
            echo "  nix build .#server      # Build FastAPI server"
            echo "  nix flake check         # Run all checks"
            echo ""
            echo "OpenAPI spec: poag.json"
            echo "Fern config: fern/generators.yml"
          '';
        };

        checks = {
          # Run pytest tests
          pytest = pkgs.runCommand "poag-api-pytest" {
            buildInputs = [ apiEnv pkgs.nix pkgs.cacert ];
          } ''
            export HOME=$TMPDIR
            export PYTHONDONTWRITEBYTECODE=1
            export NIX_CONFIG="extra-experimental-features = nix-command flakes"
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt

            # Copy source files to build directory
            cp -r ${./.} ./poag-api
            chmod -R +w ./poag-api
            cd ./poag-api

            # Run pytest
            ${apiEnv}/bin/pytest tests/ -v --tb=short

            # Create output directory (required for checks)
            mkdir -p $out
            echo "All tests passed" > $out/result
          '';
        };
      }
    );
}
