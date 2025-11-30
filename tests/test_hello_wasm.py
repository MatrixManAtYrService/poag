"""
Integration tests for hello-wasm WebAssembly Component.

These tests verify that hello-wasm's wasmtime test suite passes via Nix checks.
This ensures tests run in a pure, reproducible environment with proper caching.
"""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def hello_wasm_path():
    """Return the path to the hello-wasm subflake."""
    return Path(__file__).parent.parent / "hello-wasm"


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


def test_hello_wasm_wasmtime_check(hello_wasm_path, current_system):
    """
    Run hello-wasm's wasmtime test suite via Nix flake checks.

    This builds the WASM component and runs it with wasmtime to verify
    the component works correctly and produces expected outputs.
    """
    # Build the wasmtime-test check derivation
    # This will use cached results if hello-wasm source hasn't changed
    result = subprocess.run(
        [
            "nix", "build",
            f"{hello_wasm_path}#checks.{current_system}.wasmtime-test",
            "--print-out-paths",
            "-L"  # Show build logs
        ],
        cwd=hello_wasm_path,
        capture_output=True,
        text=True
    )

    # Print output for debugging if test fails
    if result.returncode != 0:
        print("\n=== STDOUT ===")
        print(result.stdout)
        print("\n=== STDERR ===")
        print(result.stderr)

    assert result.returncode == 0, f"hello-wasm wasmtime check failed with return code {result.returncode}"

    # Get the output path and read the summary
    output_path = result.stdout.strip().split('\n')[-1]  # Last line is the output path
    summary_file = Path(output_path) / "summary.txt"

    if summary_file.exists():
        print("\n" + "=" * 60)
        print(summary_file.read_text())
        print("=" * 60)


def test_hello_wasm_component_smoke_test(hello_wasm_path):
    """
    Smoke test: verify hello-wasm component can be built and inspected.

    This quickly validates that the WASM component builds successfully
    and has the expected WIT interface.
    """
    result = subprocess.run(
        [
            "nix", "develop", f"{hello_wasm_path}#default",
            "--command", "sh", "-c",
            # Build and inspect the component
            "cargo build --target wasm32-wasip2 --release && "
            "wasm-tools component wit target/wasm32-wasip2/release/hello_wasm.wasm"
        ],
        cwd=hello_wasm_path,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("\n=== STDOUT ===")
        print(result.stdout)
        print("\n=== STDERR ===")
        print(result.stderr)

    assert result.returncode == 0, f"Smoke test failed with return code {result.returncode}"

    # Verify the WIT interface is present in the output
    assert "hello:" in result.stdout or "greeter" in result.stdout, \
        f"Expected WIT interface not found in output: {result.stdout}"
