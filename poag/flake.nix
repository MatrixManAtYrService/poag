{
  description = "POAG - Product Owner Agent Graph for Subflakes";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
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

        # Virtual environment with all dependencies
        poagEnv = pythonSet.mkVirtualEnv "poag-env" workspace.deps.default;

      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            poagEnv
            pkgs.uv
            pkgs.nix  # For running nix flake metadata
          ];

          shellHook = ''
            export ANTHROPIC_API_KEY=$(cat ~/.anthropic-api-key 2>/dev/null || echo "")
            if [ -z "$ANTHROPIC_API_KEY" ]; then
              echo "Warning: ANTHROPIC_API_KEY not found in ~/.anthropic-api-key" >&2
            fi
            echo "POAG development environment"
            echo "Run: poag plan 'your request'"
          '';
        };

        packages.default = poagEnv;
      }
    );
}
