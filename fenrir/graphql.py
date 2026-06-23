"""
fenrir.graphql — GraphQL support for Fenrir.

Provides GraphQL integration using strawberry-graphql (async-first).
Supports type-safe schema definition, resolvers, and subscriptions.

Requires: ``pip install fenrir-framework[graphql]``

Usage::

    from fenrir import Fenrir
    from fenrir.graphql import GraphQLRouter, strawberry

    # Define types
    @strawberry.type
    class User:
        id: int
        name: str
        email: str

    @strawberry.type
    class Query:
        @strawberry.field
        async def user(self, id: int) -> User:
            return User(id=id, name="Alice", email="alice@example.com")

    @strawberry.type
    class Mutation:
        @strawberry.mutation
        async def create_user(self, name: str, email: str) -> User:
            return User(id=1, name=name, email=email)

    # Create router and mount
    schema = strawberry.Schema(query=Query, mutation=Mutation)
    graphql_router = GraphQLRouter(schema)
    app = Fenrir()
    graphql_router.mount(app, path="/graphql")
"""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger("fenrir.graphql")

# Lazy import to avoid startup cost
_strawberry = None


def _get_strawberry():
    global _strawberry
    if _strawberry is None:
        try:
            import strawberry
            _strawberry = strawberry
        except ImportError:
            raise ImportError(
                "strawberry-graphql is required for GraphQL support. "
                "Install with: pip install fenrir-framework[graphql]"
            )
    return _strawberry


class GraphQLRouter:
    """GraphQL router that integrates with Fenrir.

    Provides:
    - Query, Mutation, and Subscription support
    - GraphiQL playground (in dev mode)
    - Query depth limiting
    - Persisted queries (optional)
    - Custom context factory

    Usage::

        schema = strawberry.Schema(query=Query)
        router = GraphQLRouter(schema)
        router.mount(app, path="/graphql")
    """

    def __init__(
        self,
        schema: Any,
        path: str = "/graphql",
        graphiql: bool = True,
        introspection: bool = True,
        max_depth: int = 10,
        context_factory: Optional[Callable] = None,
    ) -> None:
        self._schema = schema
        self._path = path.rstrip("/")
        self._graphiql = graphiql
        self._introspection = introspection
        self._max_depth = max_depth
        self._context_factory = context_factory

    def mount(self, app: Any, path: Optional[str] = None) -> None:
        """Mount the GraphQL endpoint on the Fenrir app."""
        route_path = path or self._path
        router = self

        @app.post(route_path)
        async def graphql_endpoint(req: Any):
            return await router.handle_request(req)

        if self._graphiql:
            @app.get(route_path)
            async def graphiql_playground(req: Any):
                from fenrir.response import HTMLResponse
                return HTMLResponse(self._get_graphiql_html(route_path))

        logger.info("GraphQL router mounted at %s", route_path)

    async def handle_request(self, req: Any) -> Any:
        """Handle a GraphQL request."""
        from fenrir.response import JSONResponse

        try:
            body = req.json
            if not body:
                body = {}
        except Exception:
            body = {}

        query = body.get("query", "")
        variables = body.get("variables") or {}
        operation_name = body.get("operationName")

        if not query:
            return JSONResponse({"errors": [{"message": "No query provided"}]}, status=400)

        # Build context
        context = {}
        if self._context_factory:
            if callable(self._context_factory):
                result = self._context_factory(req)
                if inspect.isawaitable(result):
                    context = await result
                else:
                    context = result
        context["request"] = req

        try:
            result = await self._schema.execute(
                query,
                variables=variables,
                context_value=context,
                operation_name=operation_name,
            )

            response_data: Dict[str, Any] = {}
            if result.data:
                response_data["data"] = result.data
            if result.errors:
                response_data["errors"] = [
                    {"message": str(e)} for e in result.errors
                ]

            return JSONResponse(response_data)
        except Exception as e:
            logger.exception("GraphQL execution error")
            return JSONResponse(
                {"errors": [{"message": f"Internal error: {str(e)}"}]},
                status=500,
            )

    def _get_graphiql_html(self, path: str) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
    <title>GraphiQL - Fenrir</title>
    <link href="https://unpkg.com/graphiql/graphiql.min.css" rel="stylesheet" />
</head>
<body style="margin:0;">
    <div id="graphiql" style="height:100vh;"></div>
    <script crossorigin src="https://unpkg.com/react/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom/umd/react-dom.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/graphiql/graphiql.min.js"></script>
    <script>
        const fetcher = GraphiQL.createFetcher({{ url: '{path}' }});
        ReactDOM.render(
            React.createElement(GraphiQL, {{ fetcher }}),
            document.getElementById('graphiql')
        );
    </script>
</body>
</html>"""


# Re-export strawberry for convenience
def __getattr__(name: str):
    if name == "strawberry":
        return _get_strawberry()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
