{
  description = "POAG Client - Convenience wrapper with session management";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Consume the generated API client
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

        # Load workspace from source directory
        # Note: poag-api-client transitive deps must be manually listed in pyproject.toml
        # since path dependencies don't work with uv2nix's evaluation-time requirements
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

        # Virtual environment with all dependencies
        # Note: Generated API client added via PYTHONPATH, not in virtualenv
        clientEnv = pythonSet.mkVirtualEnv "poag-client-env" workspace.deps.default;

        # Dev virtualenv with test dependencies
        devClientEnv = pythonSet.mkVirtualEnv "poag-client-dev-env" workspace.deps.all;

      in
      {
        packages = {
          default = clientEnv;

          # Expose the built package derivation for parent flake consumption
          lib = pythonSet.poag-client;

          # Expose the generated API client (for parent flake source overrides)
          api-client-pkg = poag-api.packages.${system}.client-py-pkg;
          api-client-source = poag-api.packages.${system}.client-py-source;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            (editablePythonSet.mkVirtualEnv "poag-client-dev" workspace.deps.all)
            uv
          ];
          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
            # Add generated API client to PYTHONPATH for development
            PYTHONPATH = "${poag-api.packages.${system}.client-py-pkg}/${python.sitePackages}";
          };
          shellHook = ''
            export REPO_ROOT=$(pwd)

            echo "POAG Client development environment"
            echo ""
            echo "Client features:"
            echo "  - Session management (derives session IDs from cwd/pid)"
            echo "  - Convenience wrappers around generated API client"
            echo "  - OTEL trace correlation via session_id"
            echo ""
            echo "Testing:"
            echo "  pytest tests/ -v           # Run all tests"
            echo "  pytest tests/test_client.py -v  # Test client methods"
            echo ""
            echo "Generated API client available at:"
            echo "  ${poag-api.packages.${system}.client-py}"
          '';
        };

        checks = {
          pytest = pkgs.runCommand "poag-client-pytest" {
            buildInputs = [ devClientEnv pkgs.cacert ];
          } ''
            export HOME=$TMPDIR
            export PYTHONDONTWRITEBYTECODE=1
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
            # Add generated API client to PYTHONPATH
            export PYTHONPATH="${poag-api.packages.${system}.client-py-pkg}/${python.sitePackages}:$PYTHONPATH"

            # Copy source files to build directory
            cp -r ${./.} ./poag-client
            chmod -R +w ./poag-client
            cd ./poag-client

            # Run pytest
            ${devClientEnv}/bin/pytest tests/ -v --tb=short

            # Create output directory (required for checks)
            mkdir -p $out
            echo "All tests passed" > $out/result
          '';
        };
      }
    );
}
