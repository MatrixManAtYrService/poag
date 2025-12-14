"""Test that the /sessions endpoint is correctly defined in the OpenAPI spec"""
import json
from pathlib import Path


def test_sessions_endpoint_in_spec():
    """Test that the /sessions endpoint is defined in the spec"""
    spec_path = Path(__file__).parent.parent / "poag.json"
    with open(spec_path) as f:
        spec = json.load(f)

    assert "/sessions" in spec["paths"], "/sessions endpoint should be defined"
    assert "post" in spec["paths"]["/sessions"], "/sessions should support POST method"

    sessions_post = spec["paths"]["/sessions"]["post"]

    # Check request body
    assert "requestBody" in sessions_post, "/sessions should have requestBody"
    assert sessions_post["requestBody"]["required"] is True, "Request body should be required"

    request_schema = sessions_post["requestBody"]["content"]["application/json"]["schema"]
    assert "$ref" in request_schema, "Request should use $ref"
    assert request_schema["$ref"] == "#/components/schemas/CreateSessionRequest"

    # Check response
    assert "200" in sessions_post["responses"], "/sessions should define 200 response"
    response_schema = sessions_post["responses"]["200"]["content"]["application/json"]["schema"]
    assert "$ref" in response_schema, "Response should use $ref"
    assert response_schema["$ref"] == "#/components/schemas/SessionResponse"


def test_session_schemas_defined():
    """Test that session-related schemas are properly defined"""
    spec_path = Path(__file__).parent.parent / "poag.json"
    with open(spec_path) as f:
        spec = json.load(f)

    schemas = spec["components"]["schemas"]

    # CreateSessionRequest schema
    assert "CreateSessionRequest" in schemas
    create_req = schemas["CreateSessionRequest"]
    assert "properties" in create_req
    assert "cwd" in create_req["properties"]
    assert "pid" in create_req["properties"]
    assert create_req["properties"]["cwd"]["type"] == "string"
    assert create_req["properties"]["pid"]["type"] == "integer"
    assert set(create_req["required"]) == {"cwd", "pid"}

    # SessionResponse schema
    assert "SessionResponse" in schemas
    session_resp = schemas["SessionResponse"]
    assert "properties" in session_resp
    assert "session_id" in session_resp["properties"]
    assert "counter" in session_resp["properties"]
    assert session_resp["properties"]["session_id"]["type"] == "string"
    assert session_resp["properties"]["counter"]["type"] == "integer"
    assert set(session_resp["required"]) == {"session_id", "counter"}


def test_session_id_format():
    """Test that the session_id example follows the expected format"""
    spec_path = Path(__file__).parent.parent / "poag.json"
    with open(spec_path) as f:
        spec = json.load(f)

    session_response = spec["components"]["schemas"]["SessionResponse"]
    session_id_example = session_response["properties"]["session_id"].get("example")

    assert session_id_example is not None, "session_id should have an example"

    # Format should be {cwd}.{pid}.{counter}
    parts = session_id_example.rsplit(".", 2)
    assert len(parts) == 3, f"session_id should have 3 parts separated by dots, got: {session_id_example}"

    cwd, pid, counter = parts
    assert cwd.startswith("/"), "cwd should be an absolute path"
    assert pid.isdigit(), "pid should be numeric"
    assert counter.isdigit(), "counter should be numeric"
