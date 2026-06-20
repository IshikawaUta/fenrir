"""Tests for fenrir.graphql — GraphQL support."""
import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
# GraphQL Module Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGraphQL:
    def test_import_without_strawberry(self):
        """Test that graphql module can be imported without strawberry."""
        import fenrir.graphql as gql
        assert gql is not None

    def test_graphql_router_creation(self):
        """Test GraphQLRouter creation."""
        from fenrir.graphql import GraphQLRouter
        
        mock_schema = MagicMock()
        router = GraphQLRouter(mock_schema, path="/graphql")
        assert router._path == "/graphql"
        assert router._graphiql is True

    def test_graphql_router_config(self):
        """Test GraphQLRouter configuration."""
        from fenrir.graphql import GraphQLRouter
        
        mock_schema = MagicMock()
        router = GraphQLRouter(
            mock_schema,
            path="/api/graphql",
            graphiql=False,
            introspection=False,
            max_depth=5,
        )
        assert router._path == "/api/graphql"
        assert router._graphiql is False
        assert router._introspection is False
        assert router._max_depth == 5

    def test_graphql_html_generation(self):
        """Test GraphiQL HTML generation."""
        from fenrir.graphql import GraphQLRouter
        
        mock_schema = MagicMock()
        router = GraphQLRouter(mock_schema, path="/graphql")
        html = router._get_graphiql_html("/graphql")
        
        assert "GraphiQL" in html
        assert "/graphql" in html
