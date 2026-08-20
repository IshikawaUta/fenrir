"""Tests for fenrir.graphql — GraphQL support."""
from unittest.mock import MagicMock

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


class TestQueryDepth:
    def test_simple_query_depth(self):
        """Test depth calculation for simple query."""
        from fenrir.graphql import GraphQLRouter

        query = "{ user { name } }"
        assert GraphQLRouter._query_depth(query) == 2

    def test_nested_query_depth(self):
        """Test depth calculation for deeply nested query."""
        from fenrir.graphql import GraphQLRouter

        query = "{ user { posts { comments { author { name } } } }"
        assert GraphQLRouter._query_depth(query) == 5

    def test_single_brace_depth(self):
        """Test depth calculation for single brace."""
        from fenrir.graphql import GraphQLRouter

        query = "{ user }"
        assert GraphQLRouter._query_depth(query) == 1

    def test_query_with_string_depth(self):
        """Test depth calculation ignores braces in strings."""
        from fenrir.graphql import GraphQLRouter

        query = '{ user { name } }'
        assert GraphQLRouter._query_depth(query) == 2

    def test_query_with_fragment_depth(self):
        """Test depth calculation with fragments."""
        from fenrir.graphql import GraphQLRouter

        query = """
        query {
            user {
                ...UserFields
            }
        }
        """
        assert GraphQLRouter._query_depth(query) == 2

    def test_empty_query_depth(self):
        """Test depth calculation for empty query."""
        from fenrir.graphql import GraphQLRouter

        query = ""
        assert GraphQLRouter._query_depth(query) == 0

    def test_mutation_depth(self):
        """Test depth calculation for mutation."""
        from fenrir.graphql import GraphQLRouter

        query = "mutation { createUser(name: \"test\") { id name } }"
        assert GraphQLRouter._query_depth(query) == 2
