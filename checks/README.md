# Checks

A self-contained Nix flake providing reusable code quality checks for hello-subflakes projects.

## Features

- **Self-contained**: Pure Python CLI tools packaged with Nix
- **Self-testing**: The checks can lint and format their own codebase
- **Reusable**: Easy to reference from other flakes' devShells
- **Git-aware**: Detects and reports file changes after running checks
- **CI-friendly**: Fails in CI if files are modified (encourages pre-commit)

## Available Checks

### check-python-ruff-check

Python linting with ruff (auto-fix enabled).

```bash
# Run from the checks directory
nix run . -- [paths...]

# Run with verbose output
nix run . -- --verbose src/

# Run from another directory
nix run ./checks#check-python-ruff-check -- src/ tests/

# Add to a devShell
{
  inputs.checks.url = "path:./checks";

  devShell = pkgs.mkShell {
    packages = [ checks.packages.${system}.default ];
  };
}
```

### check-python-ruff-format

Python formatting with ruff (auto-format enabled).

```bash
# Run formatting
nix run .#check-python-ruff-format -- src/ tests/
```

### check-python-ty

Python type checking with ty.

```bash
# Run type checking
nix run .#check-python-ty -- src/ tests/

# Run with verbose output
nix run .#check-python-ty -- --verbose
```

## Development

The checks package is itself a Python project with a full development environment:

```bash
# Enter the development shell
nix develop

# Inside the devShell, you have:
# - Python with all dependencies (typer, pytest)
# - PYTHONPATH set to include src/ (for editor "go to definition")
# - check-python-ruff-check, check-python-ruff-format, and check-python-ty commands
# - Direct access to ruff, ty, and git

# Check the checks package itself (dogfooding!)
check-python-ruff-check
nix run . -- src/

# Format the checks package
check-python-ruff-format
nix run .#check-python-ruff-format -- src/

# Type check the checks package
check-python-ty
nix run .#check-python-ty

# Run tests
pytest tests/ -v

# Build the package
nix build
```

### Editor Integration

The devShell sets up PYTHONPATH to include the local `src/` directory, so your editor's "go to definition" will work for:
- `checks.cli` module
- `checks.common` module
- All dependencies like `typer`

Configure your editor to use the Python from the Nix devShell.

## Adding New Checks

To add a new check:

1. Add a new function in `src/checks/cli.py`
2. Add the entry point in `pyproject.toml`
3. Add the app in `flake.nix` outputs
4. Test with `nix build && ./result/bin/check-your-new-check`

See the existing `ruff_check` and `ruff_format` functions as examples.
