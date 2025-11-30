"""
Integration tests for hello-py Python FFI library.

These tests verify that hello-py's test suite passes via Nix checks.
This ensures tests run in a pure, reproducible environment with proper caching.
"""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def hello_py_path():
    """Return the path to the hello-py subflake."""
    return Path(__file__).parent.parent / "hello-py"


@pytest.fixture(scope="module")
def current_system():
    """Get the current Nix system identifier."""
    result = subprocess.run(
        ["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.strip()


def test_hello_py_pytest_check(hello_py_path, current_system):
    """
    Run hello-py's pytest suite via Nix flake checks.
    """
    # Build the pytest check derivation
    # This will use cached results if hello-py source hasn't changed
    result = subprocess.run(
        [
            "nix", "build",
            f"{hello_py_path}#checks.{current_system}.pytest",
            "--print-out-paths",
            "-L"  # Show build logs
        ],
        cwd=hello_py_path,
        capture_output=True,
        text=True
    )

    # Print output for debugging if test fails
    if result.returncode != 0:
        print("\n=== STDOUT ===")
        print(result.stdout)
        print("\n=== STDERR ===")
        print(result.stderr)

    assert result.returncode == 0, f"hello-py pytest check failed with return code {result.returncode}"

    # Get the output path and read the summary
    output_path = result.stdout.strip().split('\n')[-1]  # Last line is the output path
    summary_file = Path(output_path) / "summary.txt"

    if summary_file.exists():
        print("\n" + "=" * 60)
        print(summary_file.read_text())
        print("=" * 60)


def test_hello_py_import_smoke_test(hello_py_path):
    """
    Smoke test: verify hello-py can be imported in its test environment.

    This quickly validates that the package is properly installed
    and the basic FFI bindings work.
    """
    result = subprocess.run(
        [
            "nix", "develop", f"{hello_py_path}#default",
            "--command", "python", "-c",
            "from hello_py import hello; print(hello('nix'))"
        ],
        cwd=hello_py_path,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("\n=== STDOUT ===")
        print(result.stdout)
        print("\n=== STDERR ===")
        print(result.stderr)

    assert result.returncode == 0, f"Import test failed with return code {result.returncode}"
    assert "hello nix" in result.stdout, f"Unexpected output: {result.stdout}"
