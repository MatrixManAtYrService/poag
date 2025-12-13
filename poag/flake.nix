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

  outputs = { self, nixpkgs, flake-utils, beads, pyproject-nix, uv2nix, pyproject-build-systems }:
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

        # Virtual environment with all dependencies
        poagEnv = pythonSet.mkVirtualEnv "poag-env" workspace.deps.default;

        # Override beads with correct Go modules hash
        beadsFixed = beads.packages.${system}.default.overrideAttrs (old: {
          vendorHash = "sha256-KRR6dXzsSw8OmEHGBEVDBOoIgfoZ2p0541T9ayjGHlI=";
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
            export ANTHROPIC_API_KEY=$(cat ~/.anthropic-api-key 2>/dev/null || echo "")
            if [ -z "$ANTHROPIC_API_KEY" ]; then
              echo "Warning: ANTHROPIC_API_KEY not found in ~/.anthropic-api-key" >&2
            fi
            echo "POAG development environment"
            echo "Available commands:"
            echo "  poag plan 'request'  # Generate development plan"
            echo "  bd init              # Initialize issue tracker"
            echo "  bd list              # List issues"
          '';
        };

        packages.default = poagWithBeads;
      }
    );
}
