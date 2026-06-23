"""Tests for fenrir.graphql module."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import inspect


# ═══════════════════════════════════════════════════════════════════════
# GraphQLRouter Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGraphQLRouter:
    def test_init_defaults(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema)
        assert router._schema is schema
        assert router._path == "/graphql"
        assert router._graphiql is True
        assert router._introspection is True
        assert router._max_depth == 10
        assert router._context_factory is None

    def test_init_custom(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(
            schema,
            path="/gql",
            graphiql=False,
            introspection=False,
            max_depth=5,
            context_factory=lambda req: {},
        )
        assert router._path == "/gql"
        assert router._graphiql is False
        assert router._introspection is False
        assert router._max_depth == 5
        assert router._context_factory is not None

    def test_init_strips_trailing_slash(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema, path="/graphql/")
        assert router._path == "/graphql"

    def test_mount_registers_post(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema)
        app = MagicMock()
        router.mount(app)
        app.post.assert_called_once_with("/graphql")

    def test_mount_custom_path(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema, path="/graphql")
        app = MagicMock()
        router.mount(app, path="/custom")
        app.post.assert_called_once_with("/custom")

    def test_mount_graphiql_registers_get(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema, graphiql=True)
        app = MagicMock()
        router.mount(app)
        app.get.assert_called_once_with("/graphql")

    def test_mount_no_graphiql(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema, graphiql=False)
        app = MagicMock()
        router.mount(app)
        app.get.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# handle_request Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGraphQLHandleRequest:
    @pytest.mark.anyio
    async def test_no_query_returns_400(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema)
        req = MagicMock(json={"query": ""})
        result = await router.handle_request(req)
        assert result.status == 400

    @pytest.mark.anyio
    async def test_empty_body_returns_400(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema)
        req = MagicMock(json=None)
        result = await router.handle_request(req)
        assert result.status == 400

    @pytest.mark.anyio
    async def test_successful_query(self):
        from fenrir.graphql import GraphQLRouter
        schema = AsyncMock()
        schema.execute = AsyncMock(return_value=MagicMock(data={"user": {"name": "Alice"}}, errors=None))
        router = GraphQLRouter(schema)
        req = MagicMock(json={"query": "{ user { name } }"})
        result = await router.handle_request(req)
        assert result.status == 200

    @pytest.mark.anyio
    async def test_query_with_errors(self):
        from fenrir.graphql import GraphQLRouter
        schema = AsyncMock()
        schema.execute = AsyncMock(return_value=MagicMock(data=None, errors=[MagicMock(str="Not found")]))
        router = GraphQLRouter(schema)
        req = MagicMock(json={"query": "{ user { name } }"})
        result = await router.handle_request(req)
        assert result.status == 200

    @pytest.mark.anyio
    async def test_query_with_variables(self):
        from fenrir.graphql import GraphQLRouter
        schema = AsyncMock()
        schema.execute = AsyncMock(return_value=MagicMock(data={"user": {"name": "Alice"}}, errors=None))
        router = GraphQLRouter(schema)
        req = MagicMock(json={"query": "query($id: Int!) { user(id: $id) { name } }", "variables": {"id": 1}})
        result = await router.handle_request(req)
        call_args = schema.execute.call_args
        assert call_args[0][0] == "query($id: Int!) { user(id: $id) { name } }"
        assert call_args[1]["variables"] == {"id": 1}

    @pytest.mark.anyio
    async def test_context_factory_async(self):
        from fenrir.graphql import GraphQLRouter
        schema = AsyncMock()
        schema.execute = AsyncMock(return_value=MagicMock(data={}, errors=None))
        context_factory = AsyncMock(return_value={"user": "admin"})
        router = GraphQLRouter(schema, context_factory=context_factory)
        req = MagicMock(json={"query": "{ __typename }"})
        result = await router.handle_request(req)
        context_factory.assert_called_once_with(req)

    @pytest.mark.anyio
    async def test_context_factory_sync(self):
        from fenrir.graphql import GraphQLRouter
        schema = AsyncMock()
        schema.execute = AsyncMock(return_value=MagicMock(data={}, errors=None))
        context_factory = MagicMock(return_value={"user": "admin"})
        router = GraphQLRouter(schema, context_factory=context_factory)
        req = MagicMock(json={"query": "{ __typename }"})
        result = await router.handle_request(req)
        assert result.status == 200

    @pytest.mark.anyio
    async def test_exception_returns_500(self):
        from fenrir.graphql import GraphQLRouter
        schema = AsyncMock()
        schema.execute = AsyncMock(side_effect=RuntimeError("boom"))
        router = GraphQLRouter(schema)
        req = MagicMock(json={"query": "{ __typename }"})
        result = await router.handle_request(req)
        assert result.status == 500


# ═══════════════════════════════════════════════════════════════════════
# GraphiQL HTML Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGraphiQLHTML:
    def test_get_graphiql_html(self):
        from fenrir.graphql import GraphQLRouter
        schema = MagicMock()
        router = GraphQLRouter(schema)
        html = router._get_graphiql_html("/graphql")
        assert "GraphiQL" in html
        assert "/graphql" in html
        assert "<!DOCTYPE html>" in html


# ═══════════════════════════════════════════════════════════════════════
# Lazy import Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLazyImport:
    def test_get_strawberry_not_installed(self):
        import fenrir.graphql as gql_module
        gql_module._strawberry = None
        with patch.dict("sys.modules", {"strawberry": None}):
            with pytest.raises(ImportError, match="strawberry-graphql is required"):
                gql_module._get_strawberry()

    def test_getattr_strawberry(self):
        import fenrir.graphql as gql_module
        gql_module._strawberry = MagicMock()
        result = gql_module.__getattr__("strawberry")
        assert result is gql_module._strawberry

    def test_getattr_invalid(self):
        import fenrir.graphql as gql_module
        with pytest.raises(AttributeError):
            gql_module.__getattr__("nonexistent")
