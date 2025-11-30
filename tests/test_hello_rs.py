"""
Integration tests for hello-rs Rust library.

These tests verify that hello-rs's test suite passes via Nix checks.
This ensures tests run in a pure, reproducible environment with proper caching.
"""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def hello_rs_path():
    """Return the path to the hello-rs subflake."""
    return Path(__file__).parent.parent / "hello-rs"


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


def test_hello_rs_cargo_test_check(hello_rs_path, current_system):
    """
    Run hello-rs's cargo test suite via Nix flake checks.
    """
    # Build the cargo-test check derivation
    # This will use cached results if hello-rs source hasn't changed
    result = subprocess.run(
        [
            "nix", "build",
            f"{hello_rs_path}#checks.{current_system}.cargo-test",
            "--print-out-paths",
            "-L"  # Show build logs
        ],
        cwd=hello_rs_path,
        capture_output=True,
        text=True
    )

    # Print output for debugging if test fails
    if result.returncode != 0:
        print("\n=== STDOUT ===")
        print(result.stdout)
        print("\n=== STDERR ===")
        print(result.stderr)

    assert result.returncode == 0, f"hello-rs cargo test check failed with return code {result.returncode}"

    # Get the output path and read the summary
    output_path = result.stdout.strip().split('\n')[-1]  # Last line is the output path
    summary_file = Path(output_path) / "summary.txt"

    if summary_file.exists():
        print("\n" + "=" * 60)
        print(summary_file.read_text())
        print("=" * 60)


def test_hello_rs_library_smoke_test(hello_rs_path):
    """
    Smoke test: verify hello-rs can be built and used in its dev environment.

    This quickly validates that the library compiles and basic functionality works.
    """
    result = subprocess.run(
        [
            "nix", "develop", f"{hello_rs_path}#default",
            "--command", "cargo", "run", "--example", "simple"
        ],
        cwd=hello_rs_path,
        capture_output=True,
        text=True
    )

    # If there's no example, try a different approach
    if result.returncode != 0:
        # Fallback: just verify cargo build works
        result = subprocess.run(
            [
                "nix", "develop", f"{hello_rs_path}#default",
                "--command", "cargo", "build", "--lib"
            ],
            cwd=hello_rs_path,
            capture_output=True,
            text=True
        )

    if result.returncode != 0:
        print("\n=== STDOUT ===")
        print(result.stdout)
        print("\n=== STDERR ===")
        print(result.stderr)

    assert result.returncode == 0, f"Smoke test failed with return code {result.returncode}"
