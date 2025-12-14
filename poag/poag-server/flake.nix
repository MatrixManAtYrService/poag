{
  description = "POAG Server - Business logic layer with session management";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Consume the generated API server
    poag-api.url = "path:../poag-api";

    # Python tooling
    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    pyproject-build-systems.url = "github:pyproject-nix/build-system-pkgs";
  };

  outputs = { self, nixpkgs, flake-utils, poag-api, pyproject-nix, uv2nix, pyproject-build-systems }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        # Load the workspace for dependency management
        workspace = uv2nix.lib.workspace.loadWorkspace {
          workspaceRoot = ./.;
        };

        overlay = workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
        };

        # Inject the generated API server package via overlay
        apiServerOverlay = final: prev: {
          poag-api-server = poag-api.packages.${system}.server-pkg;
        };

        pythonSet = (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope (
          pkgs.lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            overlay
            apiServerOverlay
          ]
        );

        # Editable overlay for development
        editableOverlay = workspace.mkEditablePyprojectOverlay {
          root = "$REPO_ROOT";
        };

        editablePythonSet = pythonSet.overrideScope (
          pkgs.lib.composeManyExtensions [
            editableOverlay
            apiServerOverlay
          ]
        );

        # Virtual environment with all dependencies
        serverEnv = pythonSet.mkVirtualEnv "poag-server-env" workspace.deps.default;

      in
      {
        packages = {
          default = serverEnv;

          # Expose the built package derivation for parent flake consumption
          lib = pythonSet.poag-server;

          # Expose the generated API server (for parent flake source overrides)
          api-server-pkg = poag-api.packages.${system}.server-pkg;
          api-server-source = poag-api.packages.${system}.server-source;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            (editablePythonSet.mkVirtualEnv "poag-server-dev" workspace.deps.all)
            uv
          ];
          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
          };
          shellHook = ''
            export REPO_ROOT=$(pwd)

            # Create symlink to generated API server for uv lock
            mkdir -p generated
            ln -sfn ${poag-api.packages.${system}.server-source} generated/poag-api-server

            echo "POAG Server development environment"
            echo ""
            echo "Business logic layer:"
            echo "  - Session management with SQLite"
            echo "  - XDG-based configuration (like trifolium)"
            echo "  - Dependency injection for testing"
            echo ""
            echo "Testing:"
            echo "  pytest tests/ -v           # Run all tests"
            echo "  pytest tests/test_storage.py -v  # Test session storage"
            echo "  pytest tests/test_api.py -v      # Test FastAPI endpoints"
            echo ""
            echo "Generated API server available at:"
            echo "  ${poag-api.packages.${system}.server}"
          '';
        };

        checks = {
          pytest = pkgs.runCommand "poag-server-pytest" {
            buildInputs = [ serverEnv pkgs.cacert ];
          } ''
            export HOME=$TMPDIR
            export PYTHONDONTWRITEBYTECODE=1
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt

            # Copy source files to build directory
            cp -r ${./.} ./poag-server
            chmod -R +w ./poag-server
            cd ./poag-server

            # Run pytest
            ${serverEnv}/bin/pytest tests/ -v --tb=short

            # Create output directory (required for checks)
            mkdir -p $out
            echo "All tests passed" > $out/result
          '';
        };
      }
    );
}
