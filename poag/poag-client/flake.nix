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

        # Create source tree with path dependencies in place
        # This must happen before loadWorkspace so the path dependency can be resolved
        srcWithGeneratedDeps = pkgs.runCommand "poag-client-src-with-deps" {
          src = ./.;
        } ''
          # Copy source to output
          cp -r $src $out
          chmod -R u+w $out

          # Create the generated directory with the dependency
          mkdir -p $out/generated
          cp -r ${poag-api.packages.${system}.client-py-source} $out/generated/poag-api-client
        '';

        # Load the workspace from the augmented source tree
        # Use outPath to convert the derivation to a path (triggers IFD)
        workspace = uv2nix.lib.workspace.loadWorkspace {
          workspaceRoot = srcWithGeneratedDeps.outPath;
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
        clientEnv = pythonSet.mkVirtualEnv "poag-client-env" workspace.deps.default;

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
          };
          shellHook = ''
            export REPO_ROOT=$(pwd)

            # Create symlink to generated API client for uv lock
            mkdir -p generated
            ln -sfn ${poag-api.packages.${system}.client-py-source} generated/poag-api-client

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
            buildInputs = [ clientEnv pkgs.cacert ];
          } ''
            export HOME=$TMPDIR
            export PYTHONDONTWRITEBYTECODE=1
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt

            # Copy source files to build directory
            cp -r ${./.} ./poag-client
            chmod -R +w ./poag-client
            cd ./poag-client

            # Run pytest
            ${clientEnv}/bin/pytest tests/ -v --tb=short

            # Create output directory (required for checks)
            mkdir -p $out
            echo "All tests passed" > $out/result
          '';
        };
      }
    );
}
