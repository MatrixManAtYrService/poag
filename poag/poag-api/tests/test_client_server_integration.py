"""Integration tests for POAG API client and server"""
import pytest


def test_server_is_running(running_server: str):
    """Test that the server fixture starts successfully"""
    assert running_server.startswith("http://")
    assert "localhost" in running_server or "127.0.0.1" in running_server


def test_client_can_call_hello_endpoint(client):
    """Test that the client can successfully call the /hello endpoint"""
    response = client.get_hello()

    assert response is not None, "Response should not be None"
    assert "message" in response, "Response should have a 'message' field"
    assert response["message"] == "world", "Message should be 'world'"


def test_hello_endpoint_returns_correct_schema(client):
    """Test that the /hello endpoint returns data matching the OpenAPI schema"""
    response = client.get_hello()

    # Verify schema compliance
    assert isinstance(response, dict), "Response should be a dictionary"
    assert isinstance(response["message"], str), "message field should be a string"


def test_multiple_requests(client):
    """Test that the client can handle multiple requests"""
    for i in range(5):
        response = client.get_hello()
        assert response["message"] == "world", f"Request {i+1} should return 'world'"


@pytest.mark.asyncio
async def test_hello_endpoint_with_httpx(running_server: str):
    """Test the /hello endpoint directly with httpx"""
    import httpx

    async with httpx.AsyncClient(base_url=running_server) as client:
        response = await client.get("/hello")

        assert response.status_code == 200, "Should return 200 OK"
        data = response.json()
        assert data["message"] == "world", "Should return message='world'"
