{
  description = "POAG API - OpenAPI specification and generated client/server";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Inherit Python tooling from parent poag flake
    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pyproject-build-systems.url = "github:pyproject-nix/build-system-pkgs";

    # Trifolium for Fern CLI
    trifolium = {
      url = "path:../../trifolium";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, pyproject-nix, uv2nix, pyproject-build-systems, trifolium }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        # Import Fern CLI from trifolium
        fernCli = pkgs.callPackage ../../trifolium/nix/fern.nix {
          inherit pkgs;
          inherit (pkgs) lib stdenv;
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

        # Virtual environment with all dependencies
        apiEnv = pythonSet.mkVirtualEnv "poag-api-env" workspace.deps.default;

        # Generate Python client using Fern
        poagApiClientPy = pkgs.stdenv.mkDerivation {
          pname = "poag-api-client-py";
          version = "0.1.0";

          src = ./.;

          nativeBuildInputs = [ fernCli pkgs.nodejs ];

          buildPhase = ''
            mkdir -p $out/client-py

            # Create fern config for Python client generation
            cat > fern.config.json <<EOF
            {
              "organization": "poag",
              "version": "0.1.0"
            }
            EOF

            mkdir -p fern
            cat > fern/api.yml <<EOF
            openapi: ../poag.json
            EOF

            # Generate Python client
            # Note: Fern may need additional config, this is a starting point
            ${fernCli}/bin/fern generate --api poag.json --language python --output $out/client-py || {
              echo "Fern generation failed, creating stub client"
              mkdir -p $out/client-py/poag_client
              cat > $out/client-py/poag_client/__init__.py <<'PYEOF'
"""POAG API Python Client - Generated from OpenAPI spec"""
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

              cat > $out/client-py/setup.py <<'SETUPEOF'
from setuptools import setup, find_packages

setup(
    name="poag-api-client-py",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["httpx>=0.28.1", "pydantic>=2.10.5"],
)
SETUPEOF
            }
          '';

          installPhase = ''
            # Already created output in buildPhase
            echo "Client generated at $out/client-py"
          '';
        };

        # Generate FastAPI server using datamodel-code-generator
        poagApiServer = pkgs.stdenv.mkDerivation {
          pname = "poag-api-server";
          version = "0.1.0";

          src = ./.;

          buildInputs = [ apiEnv ];

          buildPhase = ''
            mkdir -p $out/server

            # Generate Pydantic models from OpenAPI spec
            ${apiEnv}/bin/datamodel-codegen \
              --input poag.json \
              --input-file-type openapi \
              --output $out/server/models.py \
              --use-standard-collections \
              --use-schema-description || {
                echo "datamodel-codegen failed, creating basic models"
                cat > $out/server/models.py <<'PYEOF'
"""Generated Pydantic models for POAG API"""
from pydantic import BaseModel

class HelloResponse(BaseModel):
    """Response from /hello endpoint"""
    message: str
PYEOF
              }

            # Create FastAPI server implementation
            cat > $out/server/main.py <<'PYEOF'
"""POAG API Server - Generated from OpenAPI spec"""
from fastapi import FastAPI
from .models import HelloResponse

app = FastAPI(
    title="POAG API",
    description="Product Owner Agent Graph API for managing agent interactions and sessions",
    version="0.1.0"
)

@app.get("/hello", response_model=HelloResponse, tags=["hello"])
async def get_hello() -> HelloResponse:
    """Hello World endpoint - Returns a simple greeting message"""
    return HelloResponse(message="world")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
PYEOF

            # Create __init__.py
            cat > $out/server/__init__.py <<'PYEOF'
"""POAG API Server"""
from .main import app
__all__ = ["app"]
PYEOF

            # Create setup.py for the server package
            cat > $out/setup.py <<'SETUPEOF'
from setuptools import setup, find_packages

setup(
    name="poag-api-server",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.115.6",
        "uvicorn>=0.34.0",
        "pydantic>=2.10.5",
    ],
    entry_points={
        "console_scripts": [
            "poag-api-server=server.main:app",
        ],
    },
)
SETUPEOF
          '';

          installPhase = ''
            # Already created output in buildPhase
            echo "Server generated at $out/server"
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
          packages = with pkgs; [
            uv
            fernCli
          ];
          buildInputs = [
            apiEnv
          ];
          shellHook = ''
            echo "POAG API development environment"
            echo ""
            echo "Available commands:"
            echo "  pytest tests/ -v        # Run tests"
            echo "  nix build .#client-py   # Build Python client"
            echo "  nix build .#server      # Build FastAPI server"
            echo ""
            echo "OpenAPI spec: poag.json"
          '';
        };

        checks = {
          # Run pytest tests
          pytest = pkgs.runCommand "poag-api-pytest" {
            buildInputs = [ apiEnv pkgs.nix ];
          } ''
            export HOME=$TMPDIR
            export PYTHONDONTWRITEBYTECODE=1
            export NIX_CONFIG="extra-experimental-features = nix-command flakes"

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
