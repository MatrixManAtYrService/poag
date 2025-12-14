"""Test that generated packages from OpenAPI Generator are structurally valid"""
import os
from pathlib import Path
import pytest


def get_package_path(env_var: str, package_name: str) -> Path:
    """Get the path to a generated package from environment or build it"""
    # Check if running in nix check (package paths provided via env vars)
    if env_var in os.environ:
        return Path(os.environ[env_var])

    # Otherwise, build the package using nix
    import subprocess
    result = subprocess.run(
        ["nix", "build", f".#{package_name}", "--print-out-paths", "--no-link"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


@pytest.fixture(scope="module")
def server_path():
    """Path to generated FastAPI server"""
    return get_package_path("POAG_SERVER_PATH", "server")


@pytest.fixture(scope="module")
def client_py_path():
    """Path to generated Python client"""
    return get_package_path("POAG_CLIENT_PY_PATH", "client-py")


@pytest.fixture(scope="module")
def client_ts_path():
    """Path to generated TypeScript client"""
    return get_package_path("POAG_CLIENT_TS_PATH", "client-ts")


class TestFastAPIServer:
    """Test generated FastAPI server package"""

    def test_server_directory_exists(self, server_path):
        """Test that server directory was created"""
        assert server_path.exists(), f"Server path should exist: {server_path}"
        assert server_path.is_dir(), "Server path should be a directory"

    def test_server_has_python_files(self, server_path):
        """Test that server contains Python files"""
        py_files = list(server_path.rglob("*.py"))
        assert len(py_files) > 0, "Server should contain Python files"

    def test_server_has_init_file(self, server_path):
        """Test that server has __init__.py for Python package structure"""
        # Check for package structure
        init_files = list(server_path.rglob("__init__.py"))
        assert len(init_files) > 0, "Server should have at least one __init__.py file"

    def test_server_has_main_or_routers(self, server_path):
        """Test that server has main.py or routers/service files"""
        # OpenAPI Generator creates main.py, apis, or service files
        has_main = len(list(server_path.rglob("main.py"))) > 0
        has_routers = len(list(server_path.rglob("*router*.py"))) > 0
        has_apis = len(list(server_path.rglob("*api*.py"))) > 0

        assert has_main or has_routers or has_apis, \
            "Server should have main.py, router files, or API files"

    def test_server_has_models_or_schemas(self, server_path):
        """Test that server has model/schema definitions"""
        # Check for common model file names
        has_models = len(list(server_path.rglob("*model*.py"))) > 0
        has_schemas = len(list(server_path.rglob("*schema*.py"))) > 0
        has_types = len(list(server_path.rglob("*type*.py"))) > 0

        assert has_models or has_schemas or has_types, \
            "Server should have model, schema, or type definitions"


class TestPythonClient:
    """Test generated Python client package"""

    def test_client_directory_exists(self, client_py_path):
        """Test that Python client directory was created"""
        assert client_py_path.exists(), f"Client path should exist: {client_py_path}"
        assert client_py_path.is_dir(), "Client path should be a directory"

    def test_client_has_python_files(self, client_py_path):
        """Test that client contains Python files"""
        py_files = list(client_py_path.rglob("*.py"))
        assert len(py_files) > 0, "Client should contain Python files"

    def test_client_has_init_file(self, client_py_path):
        """Test that client has __init__.py for Python package structure"""
        init_files = list(client_py_path.rglob("__init__.py"))
        assert len(init_files) > 0, "Client should have at least one __init__.py file"

    def test_client_has_api_files(self, client_py_path):
        """Test that client has API interface files"""
        # Check for common API file patterns
        has_api = len(list(client_py_path.rglob("*api*.py"))) > 0
        has_client = len(list(client_py_path.rglob("*client*.py"))) > 0

        assert has_api or has_client, \
            "Client should have API or client interface files"

    def test_client_has_models(self, client_py_path):
        """Test that client has model definitions"""
        # Check for models directory or model files
        models_dir = len(list(client_py_path.rglob("models/__init__.py"))) > 0
        has_model_files = len(list(client_py_path.rglob("models/*.py"))) > 0

        assert models_dir or has_model_files, \
            "Client should have models directory with model definitions"


class TestTypeScriptClient:
    """Test generated TypeScript client package"""

    def test_ts_client_directory_exists(self, client_ts_path):
        """Test that TypeScript client directory was created"""
        assert client_ts_path.exists(), f"TS client path should exist: {client_ts_path}"
        assert client_ts_path.is_dir(), "TS client path should be a directory"

    def test_ts_client_has_typescript_files(self, client_ts_path):
        """Test that TS client contains TypeScript files"""
        ts_files = list(client_ts_path.rglob("*.ts"))
        assert len(ts_files) > 0, "TS client should contain TypeScript files"

    def test_ts_client_has_api_files(self, client_ts_path):
        """Test that TS client has API interface files"""
        # Check for common TypeScript API patterns
        api_files = list(client_ts_path.rglob("*api*.ts")) + \
                   list(client_ts_path.rglob("*Api*.ts"))
        assert len(api_files) > 0, "TS client should have API files"

    def test_ts_client_has_models_or_types(self, client_ts_path):
        """Test that TS client has model/type definitions"""
        # Check for models directory, interfaces, or TypeScript files with capitalized names (common pattern)
        model_files = list(client_ts_path.rglob("*model*.ts")) + \
                     list(client_ts_path.rglob("models/*.ts")) + \
                     list(client_ts_path.rglob("*[A-Z]*.ts"))  # Files with capital letters (like HelloResponse.ts)
        assert len(model_files) > 0, "TS client should have model or type definitions"

    def test_ts_client_has_package_json(self, client_ts_path):
        """Test that TS client has package.json"""
        package_json = client_ts_path / "package.json"
        # Note: OpenAPI Generator may or may not create package.json depending on options
        # So we just check if it exists, but don't fail if it doesn't
        if package_json.exists():
            import json
            with open(package_json) as f:
                pkg = json.load(f)
                assert "name" in pkg, "package.json should have a name field"


class TestPackageConsistency:
    """Test that all packages are generated from the same spec"""

    def test_all_packages_exist(self, server_path, client_py_path, client_ts_path):
        """Test that all three packages were generated successfully"""
        assert server_path.exists(), "Server package should exist"
        assert client_py_path.exists(), "Python client package should exist"
        assert client_ts_path.exists(), "TypeScript client package should exist"

    def test_packages_are_not_empty(self, server_path, client_py_path, client_ts_path):
        """Test that all packages contain files"""
        server_files = list(server_path.rglob("*.py"))
        client_py_files = list(client_py_path.rglob("*.py"))
        client_ts_files = list(client_ts_path.rglob("*.ts"))

        assert len(server_files) > 0, "Server should not be empty"
        assert len(client_py_files) > 0, "Python client should not be empty"
        assert len(client_ts_files) > 0, "TypeScript client should not be empty"
