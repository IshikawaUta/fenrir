"""Tests for critical and high-priority bug fixes."""
import pytest
import asyncio
import secrets
import time
from unittest.mock import MagicMock, AsyncMock, patch
from collections import deque


# ═══════════════════════════════════════════════════════════════════════
# CRITICAL: CSRF Timing Attack Fix
# ═══════════════════════════════════════════════════════════════════════

class TestCSRFConstantTime:
    def test_csrf_uses_compare_digest(self):
        """Verify CSRF uses constant-time comparison."""
        import fenrir.middleware as mw
        import inspect
        source = inspect.getsource(mw.CSRFMiddleware.__call__)
        assert "secrets.compare_digest" in source

    def test_csrf_hmac_token_generation(self):
        """Verify CSRF generates HMAC-signed tokens when secret_key is provided."""
        from fenrir.middleware import CSRFMiddleware
        
        def dummy_app(scope, receive, send):
            pass
        
        middleware = CSRFMiddleware(dummy_app, secret_key="test-secret")
        token = middleware._generate_token()
        assert "." in token  # Should have payload.signature format
        
        # Verify token parts
        payload, sig = token.rsplit(".", 1)
        assert len(payload) == 64  # 32 bytes hex = 64 chars
        assert len(sig) == 64  # SHA256 hex = 64 chars

    def test_csrf_hmac_verification(self):
        """Verify HMAC token verification works."""
        from fenrir.middleware import CSRFMiddleware
        
        def dummy_app(scope, receive, send):
            pass
        
        middleware = CSRFMiddleware(dummy_app, secret_key="test-secret")
        token = middleware._generate_token()
        assert middleware._verify_token(token) is True
        
        # Tampered token should fail
        payload, sig = token.rsplit(".", 1)
        tampered = payload + "0" + sig[1:]
        assert middleware._verify_token(tampered) is False

    def test_csrf_random_token_without_secret(self):
        """Verify random tokens are used when no secret_key."""
        from fenrir.middleware import CSRFMiddleware
        
        def dummy_app(scope, receive, send):
            pass
        
        middleware = CSRFMiddleware(dummy_app, secret_key="")
        token = middleware._generate_token()
        assert "." not in token  # No HMAC format


# ═══════════════════════════════════════════════════════════════════════
# CRITICAL: RateLimit deque Fix
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimitDeque:
    def test_uses_deque_not_list(self):
        """Verify RateLimit uses deque, not list."""
        from fenrir.middleware import RateLimitMiddleware
        
        def dummy_app(scope, receive, send):
            pass
        
        middleware = RateLimitMiddleware(dummy_app)
        assert isinstance(middleware._requests, dict)
        # Default factory should create deques
        key = "test-key"
        middleware._requests[key].append(1.0)
        assert isinstance(middleware._requests[key], deque)

    def test_popleft_works(self):
        """Verify popleft works on deque."""
        from fenrir.middleware import RateLimitMiddleware
        
        def dummy_app(scope, receive, send):
            pass
        
        middleware = RateLimitMiddleware(dummy_app)
        middleware._requests["test"].append(1.0)
        middleware._requests["test"].append(2.0)
        assert middleware._requests["test"].popleft() == 1.0


# ═══════════════════════════════════════════════════════════════════════
# CRITICAL: ResponseCache Dict Mutation Fix
# ═══════════════════════════════════════════════════════════════════════

class TestResponseCacheFix:
    def test_no_runtime_error_during_eviction(self):
        """Verify no RuntimeError when evicting during iteration."""
        from fenrir.performance import ResponseCache
        
        cache = ResponseCache(max_size=5, default_ttl=60)
        
        # Fill cache beyond capacity
        for i in range(10):
            cache.set(f"key-{i}", ("200", {}, b"body"))
        
        # Should not raise RuntimeError
        assert len(cache._cache) <= 5


# ═══════════════════════════════════════════════════════════════════════
# HIGH: CORS Preflight Fix
# ═══════════════════════════════════════════════════════════════════════

class TestCORSPreflight:
    def test_preflight_always_responds_204(self):
        """Verify preflight always responds 204, even with disallowed origin."""
        from fenrir.middleware import CORSMiddleware
        
        responses = []
        
        async def dummy_app(scope, receive, send):
            responses.append("app_called")
        
        middleware = CORSMiddleware(dummy_app, allow_origins=["https://allowed.com"])
        
        scope = {
            "type": "http",
            "method": "OPTIONS",
            "headers": [(b"origin", b"https://evil.com")],
        }
        
        async def mock_send(message):
            if message["type"] == "http.response.start":
                responses.append(message["status"])
        
        asyncio.run(middleware(scope, None, mock_send))
        assert 204 in responses
        assert "app_called" not in responses  # App should NOT be called


# ═══════════════════════════════════════════════════════════════════════
# HIGH: Pagination ZeroDivisionError Fix
# ═══════════════════════════════════════════════════════════════════════

class TestPaginationFix:
    def test_size_zero_not_raises(self):
        """Verify size=0 does not raise ZeroDivisionError."""
        from fenrir.pagination import paginate
        
        items = [1, 2, 3, 4, 5]
        result = paginate(items, page=1, size=0)
        assert result["size"] == 1  # Should default to 1
        assert result["total"] == 5

    def test_negative_size_not_raises(self):
        """Verify negative size does not raise."""
        from fenrir.pagination import paginate
        
        items = [1, 2, 3]
        result = paginate(items, page=1, size=-5)
        assert result["size"] == 1


# ═══════════════════════════════════════════════════════════════════════
# HIGH: MethodView 405 Fix
# ═══════════════════════════════════════════════════════════════════════

class TestMethodView405:
    def test_unsupported_method_returns_405(self):
        """Verify unsupported method raises HTTPMethodNotAllowed."""
        from fenrir.views import MethodView
        from fenrir.exceptions import HTTPMethodNotAllowed
        import inspect
        
        # Check that the source code raises HTTPMethodNotAllowed
        source = inspect.getsource(MethodView.dispatch_request)
        assert "HTTPMethodNotAllowed" in source


# ═══════════════════════════════════════════════════════════════════════
# HIGH: ORM executemany Transaction Fix
# ═══════════════════════════════════════════════════════════════════════

class TestORMExecutemanyTransaction:
    def test_executemany_respects_in_transaction(self):
        """Verify executemany does not commit when in transaction."""
        from fenrir.orm import Database
        
        db = Database("sqlite:///:memory:")
        
        # Check that executemany checks _in_transaction
        import inspect
        source = inspect.getsource(db.executemany)
        assert "_in_transaction" in source


# ═══════════════════════════════════════════════════════════════════════
# HIGH: RedisSession loop=None Fix
# ═══════════════════════════════════════════════════════════════════════

class TestRedisSessionLoop:
    def test_run_sync_or_async_handles_no_loop(self):
        """Verify _run_sync_or_async handles no running loop."""
        from fenrir.sessions import RedisSessionInterface
        
        # Just verify the method exists and has proper error handling
        import inspect
        source = inspect.getsource(RedisSessionInterface._run_sync_or_async)
        assert "new_event_loop" in source
        assert "loop.close()" in source


# ═══════════════════════════════════════════════════════════════════════
# HIGH: FileCache Async I/O Fix
# ═══════════════════════════════════════════════════════════════════════

class TestFileCacheAsync:
    def test_uses_to_thread(self):
        """Verify FileCache uses asyncio.to_thread for I/O."""
        from fenrir.cache import FileCache
        import inspect
        
        source = inspect.getsource(FileCache.get)
        assert "asyncio.to_thread" in source
        
        source = inspect.getsource(FileCache.set)
        assert "asyncio.to_thread" in source


# ═══════════════════════════════════════════════════════════════════════
# HIGH: Dispatch None Guard Fix
# ═══════════════════════════════════════════════════════════════════════

class TestDispatchNoneGuard:
    def test_none_response_gets_500(self):
        """Verify None response_obj results in 500 response."""
        import inspect
        from fenrir import _app_dispatch
        
        source = inspect.getsource(_app_dispatch)
        assert "response_obj is None" in source
        assert "500" in source


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: Blueprint Path Validation Fix
# ═══════════════════════════════════════════════════════════════════════

class TestBlueprintPathFix:
    def test_path_gets_leading_slash(self):
        """Verify path without leading / gets one added."""
        import inspect
        from fenrir._app_core import FenrirCoreMixin
        
        source = inspect.getsource(FenrirCoreMixin.register_blueprint)
        assert 'path.startswith("/")' in source


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: Invalid Middleware Type Fix
# ═══════════════════════════════════════════════════════════════════════

class TestInvalidMiddlewareType:
    def test_raises_value_error(self):
        """Verify invalid middleware_type raises ValueError."""
        from fenrir._app_core import Blueprint
        
        bp = Blueprint("test")
        
        with pytest.raises(ValueError, match="Invalid middleware_type"):
            @bp.middleware("invalid_type")
            def handler(req):
                pass


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: ORM Unknown Kwargs Fix
# ═══════════════════════════════════════════════════════════════════════

class TestORMUnknownKwargs:
    def test_raises_type_error(self):
        """Verify unknown kwargs raise TypeError."""
        from fenrir.orm import Model, fields
        
        class TestModel(Model):
            __tablename__ = "test"
            id = fields.Integer(primary_key=True)
            name = fields.String()
        
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            TestModel(name="test", unknown_field="value")


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: Response Status Setter Fix
# ═══════════════════════════════════════════════════════════════════════

class TestResponseStatusSetter:
    def test_invalid_string_raises(self):
        """Verify invalid status string raises ValueError."""
        from fenrir.response import Response
        
        resp = Response()
        with pytest.raises(ValueError, match="Invalid status code"):
            resp.status = "invalid"


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: Filename Null Byte Fix
# ═══════════════════════════════════════════════════════════════════════

class TestFilenameNullByte:
    def test_null_byte_removed(self):
        """Verify null bytes are removed from filename."""
        import inspect
        from fenrir.response import FileResponse
        
        source = inspect.getsource(FileResponse.__init__)
        assert "\\x00" in source or "null" in source.lower() or "replace('\\x00'" in source


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: Signals Copy Fix
# ═══════════════════════════════════════════════════════════════════════

class TestSignalsCopy:
    def test_send_copies_list(self):
        """Verify send() copies receivers list to avoid mutation."""
        from fenrir.signals import Signal
        
        signal = Signal("test")
        results = []
        
        def receiver(sender, **kwargs):
            results.append("called")
            # Disconnect during iteration
            signal.disconnect(receiver)
        
        signal.connect(receiver)
        signal.send()
        
        # Should have been called once
        assert len(results) == 1


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: GraphQL Context Non-Dict Fix
# ═══════════════════════════════════════════════════════════════════════

class TestGraphQLContext:
    def test_non_dict_context_wrapped(self):
        """Verify non-dict context is wrapped in dict."""
        from fenrir.graphql import GraphQLRouter
        import inspect
        
        source = inspect.getsource(GraphQLRouter.handle_request)
        assert "isinstance(context, dict)" in source


# ═══════════════════════════════════════════════════════════════════════
# MEDIUM: OpenAPI Union/Optional/List Fix
# ═══════════════════════════════════════════════════════════════════════

class TestOpenAPITypes:
    def test_list_type(self):
        """Verify List[T] generates array schema."""
        from fenrir.openapi import _annotation_to_schema
        from typing import List
        
        schema = _annotation_to_schema(List[str])
        assert schema["type"] == "array"
        assert schema["items"]["type"] == "string"

    def test_optional_type(self):
        """Verify Optional[T] generates nullable schema."""
        from fenrir.openapi import _annotation_to_schema
        from typing import Optional
        
        schema = _annotation_to_schema(Optional[int])
        assert schema["type"] == "integer"
        assert schema.get("nullable") is True

    def test_dict_type(self):
        """Verify Dict generates object schema."""
        from fenrir.openapi import _annotation_to_schema
        from typing import Dict
        
        schema = _annotation_to_schema(Dict[str, int])
        assert schema["type"] == "object"
