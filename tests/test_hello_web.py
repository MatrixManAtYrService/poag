"""
Integration tests for hello-web WASM application.

This test suite builds the hello-web package, serves it via HTTP,
and uses a headless browser to verify the UI functionality.
"""

import subprocess
import http.server
import socketserver
import threading
import socket
import time
import os
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options


@pytest.fixture(scope="session")
def docker_compose_file():
    """Return the path to the docker-compose.yml file."""
    return Path(__file__).parent / "docker-compose.yml"


@pytest.fixture(scope="session")
def selenium_service(docker_compose_file):
    """
    Start Selenium Grid using docker-compose and return the URL.

    Uses docker-compose to start a Firefox Selenium Grid container.
    Waits for the service to be healthy before returning.
    Automatically tears down the service when tests complete.
    """
    project_name = "hello-web-tests"
    compose_cmd_base = ["docker-compose", "-f", str(docker_compose_file), "-p", project_name]

    # Print info about pause behavior
    pause_after = os.environ.get("PYTEST_PAUSE_AFTER", "0") == "1"
    print(f"\n🐳 Starting Selenium Grid")
    if pause_after:
        print(f"💡 Pause enabled: Browser will remain open after tests at http://localhost:7900")
    else:
        print(f"💡 Tip: Set PYTEST_PAUSE_AFTER=1 to pause after tests and inspect browser state")

    # Start the services
    subprocess.run(compose_cmd_base + ["up", "-d"], check=True)

    # Wait for Selenium to be ready
    selenium_url = "http://localhost:4444"
    max_wait = 60
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            # Check if Selenium is responding
            result = subprocess.run(
                ["docker-compose", "-f", str(docker_compose_file), "-p", project_name,
                 "exec", "-T", "selenium-firefox", "curl", "-f", "http://localhost:4444/wd/hub/status"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                break
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        time.sleep(1)
    else:
        # Cleanup on failure
        subprocess.run(compose_cmd_base + ["down", "-v"], check=False)
        raise RuntimeError(f"Selenium Grid did not become ready within {max_wait} seconds")

    yield selenium_url

    # Always cleanup
    subprocess.run(compose_cmd_base + ["down", "-v"], check=False)


@pytest.fixture(scope="session")
def build_hello_web():
    """
    Build the hello-web package using nix and return the output path.

    This runs once per test session to avoid rebuilding for each test.
    """
    result = subprocess.run(
        ["nix", "build", ".#hello-web", "--print-out-paths"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        check=True
    )

    nix_store_path = result.stdout.strip()
    assert Path(nix_store_path).exists(), f"Build output path does not exist: {nix_store_path}"

    return Path(nix_store_path)


def find_available_port():
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(scope="session")
def web_server(build_hello_web):
    """
    Start an HTTP server serving the built hello-web application.

    Returns the port number the server is running on.
    Automatically stops the server when tests complete.
    """
    port = find_available_port()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(build_hello_web), **kwargs)

        def log_message(self, format, *args):
            # Suppress server logs during testing
            pass

    server = socketserver.TCPServer(("127.0.0.1", port), Handler)

    # Start server in background thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    timeout = 5
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.1)
    else:
        raise RuntimeError(f"Server did not start within {timeout} seconds")

    yield port

    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def browser(selenium_service, web_server, request):
    """
    Create a remote Firefox browser instance via Selenium Grid and navigate to the hello-web app.

    Waits for the page to load (checks for "Demo" text).
    Returns the WebDriver instance connected to Selenium Grid.
    """
    options = Options()
    # Don't use headless mode so we can see it in VNC
    # options.add_argument('--headless')

    driver = webdriver.Remote(
        command_executor=f"{selenium_service}/wd/hub",
        options=options
    )

    try:
        # Navigate to the application
        driver.get(f"http://host.docker.internal:{web_server}/")

        # Wait for page to load - check for "Demo" text in title
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Demo')]"))
        )

        yield driver
    finally:
        # Check if -s flag is used (capture is disabled)
        capture_disabled = request.config.getoption("--capture") == "no"
        pause_after = os.environ.get("PYTEST_PAUSE_AFTER", "0") == "1"

        # Only pause if both -s is used AND PYTEST_PAUSE_AFTER=1
        if capture_disabled and pause_after:
            print("\n⏸️  Tests complete! Browser is still open at http://localhost:7900")
            print("   Press Enter to close browser and cleanup...")
            input()

        driver.quit()


def test_hello_world_greeting(browser):
    """
    Test that entering 'world' and clicking the button produces the correct greeting.
    """
    # Find the name input field
    name_input = browser.find_element(By.ID, "nameInput")

    # Find the button
    button = browser.find_element(By.XPATH, "//button[contains(text(), 'Say Hello')]")

    # Find the result div
    result_div = browser.find_element(By.ID, "result")

    # Enter "world" into the input
    name_input.clear()
    name_input.send_keys("world")

    # Click the button
    button.click()

    # Wait for the result to appear and verify it
    WebDriverWait(browser, 5).until(
        lambda d: result_div.text != "" and "Enter a name" not in result_div.text
    )

    # Assert the greeting is correct
    # Based on the WIT interface and Rust implementation, this should return "hello world"
    # formatted with proper styling
    assert "hello world" in result_div.text.lower(), f"Expected greeting with 'hello world', got: {result_div.text}"


def test_empty_input_validation(browser):
    """
    Test that clicking the button with an empty input shows an error message.
    """
    name_input = browser.find_element(By.ID, "nameInput")
    button = browser.find_element(By.XPATH, "//button[contains(text(), 'Say Hello')]")
    result_div = browser.find_element(By.ID, "result")

    # Clear the input
    name_input.clear()

    # Click the button
    button.click()

    # Wait for error message
    WebDriverWait(browser, 5).until(
        lambda d: "enter a name" in result_div.text.lower()
    )

    assert "enter a name" in result_div.text.lower()


def test_multiple_names(browser):
    """
    Test that different names produce different greetings.
    """
    name_input = browser.find_element(By.ID, "nameInput")
    button = browser.find_element(By.XPATH, "//button[contains(text(), 'Say Hello')]")
    result_div = browser.find_element(By.ID, "result")

    test_names = ["alice", "bob", "world"]

    for name in test_names:
        name_input.clear()
        name_input.send_keys(name)
        button.click()

        # Wait for result to update
        WebDriverWait(browser, 5).until(
            lambda d: name in result_div.text.lower()
        )

        assert name in result_div.text.lower(), f"Expected '{name}' in greeting, got: {result_div.text}"
