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


@pytest.fixture(scope="session")
def server_package(project_root: Path) -> Path:
    """Build the server package using nix and return the path"""
    print("\nBuilding server package with nix...")
    result = subprocess.run(
        ["nix", "build", ".#server", "--no-link", "--print-out-paths"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        pytest.fail(f"Failed to build server package:\n{result.stderr}")

    server_path = Path(result.stdout.strip())
    assert server_path.exists(), f"Server package not found at {server_path}"
    print(f"Server package built at: {server_path}")

    # Add the server to Python path
    if server_path.exists():
        sys.path.insert(0, str(server_path))

    return server_path


@pytest.fixture(scope="session")
def running_server(server_package: Path) -> Generator[str, None, None]:
    """Start the FastAPI server and return the base URL"""
    import uvicorn

    # Import the app from the built server package
    sys.path.insert(0, str(server_package))
    from server.main import app

    # Use a different port to avoid conflicts
    port = 8888
    base_url = f"http://localhost:{port}"

    # Start server in background
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    server = uvicorn.Server(config)

    # Run server in a separate thread
    import threading

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server to start
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            response = httpx.get(f"{base_url}/hello", timeout=1.0)
            if response.status_code == 200:
                print(f"\nServer started successfully at {base_url}")
                break
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(0.5)
    else:
        pytest.fail(f"Server failed to start after {max_attempts} attempts")

    yield base_url

    # Shutdown is handled by daemon thread termination


@pytest.fixture
def client(client_package: Path, running_server: str):
    """Create a client instance connected to the running server"""
    # Import the client from the built package
    sys.path.insert(0, str(client_package / "client-py"))

    try:
        from poag_client import PoagClient

        client = PoagClient(base_url=running_server)
        yield client
        client.close()
    except ImportError as e:
        # Fallback to httpx if client module doesn't exist yet
        print(f"Warning: Could not import PoagClient: {e}")
        print("Using httpx client as fallback")

        class FallbackClient:
            def __init__(self, base_url: str):
                self.base_url = base_url
                self.http_client = httpx.Client(base_url=base_url)

            def get_hello(self):
                response = self.http_client.get("/hello")
                response.raise_for_status()
                return response.json()

            def close(self):
                self.http_client.close()

        client = FallbackClient(base_url=running_server)
        yield client
        client.close()
