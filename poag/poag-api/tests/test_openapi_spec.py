"""Test that poag.json is a valid OpenAPI specification"""
import json
from pathlib import Path
import pytest
from openapi_spec_validator import validate_spec


def test_openapi_spec_exists():
    """Test that poag.json exists"""
    spec_path = Path(__file__).parent.parent / "poag.json"
    assert spec_path.exists(), "poag.json should exist"


def test_openapi_spec_is_valid_json():
    """Test that poag.json is valid JSON"""
    spec_path = Path(__file__).parent.parent / "poag.json"
    with open(spec_path) as f:
        spec = json.load(f)
    assert spec is not None, "poag.json should be valid JSON"
    assert "openapi" in spec, "Should have openapi version field"
    assert "info" in spec, "Should have info section"
    assert "paths" in spec, "Should have paths section"


def test_openapi_spec_validates():
    """Test that poag.json is a valid OpenAPI 3.0 specification"""
    spec_path = Path(__file__).parent.parent / "poag.json"
    with open(spec_path) as f:
        spec = json.load(f)

    # This will raise an exception if the spec is invalid
    validate_spec(spec)


def test_hello_endpoint_in_spec():
    """Test that the /hello endpoint is defined in the spec"""
    spec_path = Path(__file__).parent.parent / "poag.json"
    with open(spec_path) as f:
        spec = json.load(f)

    assert "/hello" in spec["paths"], "/hello endpoint should be defined"
    assert "get" in spec["paths"]["/hello"], "/hello should support GET method"

    hello_get = spec["paths"]["/hello"]["get"]
    assert "200" in hello_get["responses"], "/hello should define 200 response"

    response_schema = hello_get["responses"]["200"]["content"]["application/json"]["schema"]
    assert "properties" in response_schema, "Response should have properties"
    assert "message" in response_schema["properties"], "Response should have message field"
    assert response_schema["properties"]["message"]["type"] == "string", "message should be a string"
