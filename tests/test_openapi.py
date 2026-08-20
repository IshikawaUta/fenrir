"""Tests for fenrir.openapi — OpenAPI schema generation."""
from enum import Enum

from pydantic import BaseModel

from fenrir.openapi import _fix_refs


class TestFixRefs:
    def test_fix_refs_simple(self):
        """Test $ref replacement in simple dict."""
        obj = {"$ref": "#/$defs/AccountType"}
        _fix_refs(obj)
        assert obj["$ref"] == "#/components/schemas/AccountType"

    def test_fix_refs_nested(self):
        """Test $ref replacement in nested dict."""
        obj = {
            "properties": {
                "account_type": {"$ref": "#/$defs/AccountType"}
            }
        }
        _fix_refs(obj)
        assert obj["properties"]["account_type"]["$ref"] == "#/components/schemas/AccountType"

    def test_fix_refs_in_list(self):
        """Test $ref replacement in list."""
        obj = [
            {"$ref": "#/$defs/Type1"},
            {"$ref": "#/$defs/Type2"}
        ]
        _fix_refs(obj)
        assert obj[0]["$ref"] == "#/components/schemas/Type1"
        assert obj[1]["$ref"] == "#/components/schemas/Type2"

    def test_fix_refs_mixed(self):
        """Test $ref replacement in complex nested structure."""
        obj = {
            "allOf": [
                {"$ref": "#/$defs/Base"},
                {"properties": {"type": {"$ref": "#/$defs/Type"}}}
            ]
        }
        _fix_refs(obj)
        assert obj["allOf"][0]["$ref"] == "#/components/schemas/Base"
        assert obj["allOf"][1]["properties"]["type"]["$ref"] == "#/components/schemas/Type"

    def test_fix_refs_preserves_other_refs(self):
        """Test that non-$defs refs are not modified."""
        obj = {"$ref": "#/components/schemas/Other"}
        _fix_refs(obj)
        assert obj["$ref"] == "#/components/schemas/Other"

    def test_fix_refs_no_refs(self):
        """Test that dict without $ref is unchanged."""
        obj = {"type": "string", "enum": ["a", "b"]}
        _fix_refs(obj)
        assert obj == {"type": "string", "enum": ["a", "b"]}

    def test_fix_refs_returns_obj(self):
        """Test that _fix_refs returns the object."""
        obj = {"$ref": "#/$defs/Test"}
        result = _fix_refs(obj)
        assert result is obj


class TestOpenAPIWithPydanticV2:
    def test_schema_with_defs(self):
        """Test that $defs are properly moved and refs updated."""
        from fenrir.openapi import get_openapi
        from fenrir.routing import Route

        class AccountType(str, Enum):
            asset = "asset"
            liability = "liability"

        class AccountCreate(BaseModel):
            name: str
            account_type: AccountType

        async def create_account(body: AccountCreate):
            pass

        route = Route(
            path_pattern="/accounts",
            handler=create_account,
            methods=["POST"],
        )

        schema = get_openapi("Test", "1.0.0", [route])

        # $defs should be moved to components/schemas
        assert "AccountType" in schema["components"]["schemas"]
        assert "$defs" not in schema["components"]["schemas"]

        # The main schema should have refs pointing to components/schemas
        account_schema = schema["components"]["schemas"]["AccountCreate"]
        assert account_schema["properties"]["account_type"]["$ref"] == "#/components/schemas/AccountType"

    def test_response_model_with_defs(self):
        """Test that response model $defs are properly handled."""
        from fenrir.openapi import get_openapi
        from fenrir.routing import Route

        class Status(str, Enum):
            active = "active"
            inactive = "inactive"

        class UserResponse(BaseModel):
            name: str
            status: Status

        async def get_user():
            pass

        route = Route(
            path_pattern="/users",
            handler=get_user,
            methods=["GET"],
            response_model=UserResponse,
        )

        schema = get_openapi("Test", "1.0.0", [route])

        # $defs should be moved
        assert "Status" in schema["components"]["schemas"]

        # Refs should point to components/schemas
        user_schema = schema["components"]["schemas"]["UserResponse"]
        assert user_schema["properties"]["status"]["$ref"] == "#/components/schemas/Status"
