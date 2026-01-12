{
  description = "Reusable code quality checks for hello-subflakes projects";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        python = pkgs.python312;

        # Build the Python package with dependencies
        checksPackage = pkgs.python312Packages.buildPythonApplication {
          pname = "checks";
          version = "0.1.0";
          format = "pyproject";

          src = ./.;

          nativeBuildInputs = with pkgs.python312Packages; [
            hatchling
          ];

          propagatedBuildInputs = with pkgs.python312Packages; [
            typer
          ] ++ [
            pkgs.ruff
            pkgs.git
            pkgs.ty
          ];

          # Make ruff, git, and ty available in PATH
          makeWrapperArgs = [
            "--prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.ruff pkgs.git pkgs.ty ]}"
          ];
        };

        # Python environment for development (includes all dependencies)
        checksEnv = python.withPackages (ps: with ps; [
          typer
          pytest
        ]);

      in
      {
        packages = {
          default = checksPackage;
          checks = checksPackage;
        };

        apps = {
          check-python-ruff-check = {
            type = "app";
            program = "${checksPackage}/bin/check-python-ruff-check";
          };
          check-python-ruff-format = {
            type = "app";
            program = "${checksPackage}/bin/check-python-ruff-format";
          };
          check-python-ty = {
            type = "app";
            program = "${checksPackage}/bin/check-python-ty";
          };
          default = {
            type = "app";
            program = "${checksPackage}/bin/check-python-ruff-check";
          };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            checksEnv
            checksPackage  # Provides the check-python-* commands
            pkgs.python312Packages.python-lsp-ruff
            pkgs.ty
            pkgs.pyright
            pkgs.ruff
            pkgs.git
          ];

          shellHook = ''
            # Set up PYTHONPATH to include the local src directory
            export PYTHONPATH="${toString ./.}/src:$PYTHONPATH"

            echo ""
            echo "Checks development environment"
            echo ""
            echo "Available tools:"
            echo "  check-python-ruff-check [paths...]   # Lint Python code"
            echo "  check-python-ruff-format [paths...]  # Format Python code"
            echo "  check-python-ty [paths...]           # Type check with ty"
            echo "  pytest tests/ -v                     # Run tests"
            echo "  ruff check src/                      # Direct ruff usage"
            echo ""
            echo "Python environment: ${checksEnv}"
            echo "PYTHONPATH includes: ${toString ./.}/src"
          '';
        };
      }
    );
}
