{
  description = "POAG - Product Owner Agent Graph for Subflakes";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    # Beads - git-backed issue tracker for AI coding workflows
    beads = {
      url = "github:steveyegge/beads";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.flake-utils.follows = "flake-utils";
    };

    # POAG subflakes (poag-api is transitive through server and client)
    poag-server.url = "path:./poag-server";
    poag-client.url = "path:./poag-client";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs = {
        pyproject-nix.follows = "pyproject-nix";
        uv2nix.follows = "uv2nix";
        nixpkgs.follows = "nixpkgs";
      };
    };
  };

  outputs = { self, nixpkgs, flake-utils, beads, poag-server, poag-client, pyproject-nix, uv2nix, pyproject-build-systems }:
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

        # Inject pre-built derivations from child flakes
        # This replaces packages in the pythonSet with already-built versions
        childOverrides = final: prev: {
          poag-server = poag-server.packages.${system}.lib;
          poag-client = poag-client.packages.${system}.lib;
        };

        pythonSet = (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope (
          pkgs.lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            overlay
            childOverrides  # Replaces packages with pre-built versions
          ]
        );

        # Virtual environment with all dependencies (from uv.lock)
        # Note: poag-api-client and poag-api-server are added via PYTHONPATH
        poagEnv = pythonSet.mkVirtualEnv "poag-env" workspace.deps.all;

        # Override beads with correct Go modules hash
        beadsFixed = beads.packages.${system}.default.overrideAttrs (old: {
          vendorHash = "sha256-iTPi8+pbKr2Q352hzvIOGL2EneF9agrDmBwTLMUjDBE=";
        });

        # Combined package with both poag and bd commands
        poagWithBeads = pkgs.symlinkJoin {
          name = "poag-with-beads";
          paths = [ poagEnv beadsFixed ];
          meta = {
            description = "POAG agent orchestration with Beads issue tracker";
          };
        };

      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            poagWithBeads
            pkgs.uv
            pkgs.nix  # For running nix flake metadata
          ];

          shellHook = ''
            # Add generated API packages to PYTHONPATH
            export PYTHONPATH="${poag-client.packages.${system}.api-client-pkg}/${python.sitePackages}:${poag-server.packages.${system}.api-server-pkg}/${python.sitePackages}:$PYTHONPATH"

            export ANTHROPIC_API_KEY=$(cat ~/.anthropic-api-key 2>/dev/null || echo "")
            if [ -z "$ANTHROPIC_API_KEY" ]; then
              echo "Warning: ANTHROPIC_API_KEY not found in ~/.anthropic-api-key" >&2
            fi
            echo ""
            echo "POAG development environment"
            echo ""
            echo "Agent tools:"
            echo "  poag plan 'request'  # Generate development plan"
            echo "  poag ls              # List all subflakes"
            echo "  bd init              # Initialize issue tracker (first time)"
            echo "  bd list              # List all issues"
            echo "  bd ready             # Show ready-to-work issues"
            echo ""
            echo "Integration testing:"
            echo "  pytest tests/ -v     # Run integration tests (client + server)"
            echo ""
            echo "Subflake packages (pre-built derivations):"
            echo "  poag-server: ${poag-server.packages.${system}.lib}"
            echo "  poag-client: ${poag-client.packages.${system}.lib}"
          '';
        };

        packages = {
          default = poagWithBeads;
        };

        checks = {
          # Integration tests
          pytest = pkgs.runCommand "poag-integration-pytest" {
            buildInputs = [ poagEnv pkgs.cacert ];
          } ''
            export HOME=$TMPDIR
            export PYTHONDONTWRITEBYTECODE=1
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
            # Add generated API packages to PYTHONPATH
            export PYTHONPATH="${poag-client.packages.${system}.api-client-pkg}/${python.sitePackages}:${poag-server.packages.${system}.api-server-pkg}/${python.sitePackages}:$PYTHONPATH"

            # Copy source files to build directory
            cp -r ${./.} ./poag
            chmod -R +w ./poag
            cd ./poag

            # Run pytest
            ${poagEnv}/bin/pytest tests/ -v --tb=short

            # Create output directory (required for checks)
            mkdir -p $out
            echo "All integration tests passed" > $out/result
          '';
        };
      }
    );
}
