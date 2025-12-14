"""Pytest fixtures for POAG API tests"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Generator
import pytest
import httpx


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get the project root directory"""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def client_package(project_root: Path) -> Path:
    """Build the client package using nix and return the path"""
    print("\nBuilding client package with nix...")
    result = subprocess.run(
        ["nix", "build", ".#client-py", "--no-link", "--print-out-paths"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to build client package:\n{result.stderr}")

    client_path = Path(result.stdout.strip())
    assert client_path.exists(), f"Client package not found at {client_path}"
    print(f"Client package built at: {client_path}")

    # Add the client to Python path
    client_py_path = client_path / "client-py"
    if client_py_path.exists():
        sys.path.insert(0, str(client_py_path))

    return client_path


# Integration tests that actually run the server and client
# have been moved to a separate subflake for full integration testing
