"""Tests for fenrir.grpc module."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════
# GRPCService Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGRPCService:
    def test_service_attributes(self):
        from fenrir.grpc import GRPCService
        class MyService(GRPCService):
            service_name = "MyService"
        svc = MyService()
        assert svc.service_name == "MyService"

    def test_rpc_handler_decorator(self):
        from fenrir.grpc import GRPCService
        class MyService(GRPCService):
            service_name = "MyService"
        svc = MyService()

        @svc.rpc_handler("GetUser")
        async def get_user(request, context):
            return {"id": 1}

        assert "GetUser" in svc._handlers
        assert svc._handlers["GetUser"] is get_user

    def test_handlers_per_class(self):
        from fenrir.grpc import GRPCService
        class ServiceA(GRPCService):
            service_name = "A"
        class ServiceB(GRPCService):
            service_name = "B"

        a = ServiceA()
        b = ServiceB()

        @a.rpc_handler("MethodA")
        async def method_a(req, ctx):
            pass

        @b.rpc_handler("MethodB")
        async def method_b(req, ctx):
            pass

        assert "MethodA" in a._handlers
        assert "MethodB" not in a._handlers
        assert "MethodB" in b._handlers
        assert "MethodA" not in b._handlers


# ═══════════════════════════════════════════════════════════════════════
# GRPCInterceptor Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGRPCInterceptor:
    @pytest.mark.anyio
    async def test_intercept_passthrough(self):
        from fenrir.grpc import GRPCInterceptor
        interceptor = GRPCInterceptor()
        method = AsyncMock(return_value="response")
        result = await interceptor.intercept(method, "request", "context")
        assert result == "response"
        method.assert_called_once_with("request", "context")


# ═══════════════════════════════════════════════════════════════════════
# GRPCContext Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGRPCContext:
    def test_init_defaults(self):
        from fenrir.grpc import GRPCContext
        ctx = GRPCContext()
        assert ctx.metadata == {}
        assert ctx.code == 0
        assert ctx.details == ""
        assert ctx._cancelled is False

    def test_init_with_metadata(self):
        from fenrir.grpc import GRPCContext
        ctx = GRPCContext(metadata={"key": "value"})
        assert ctx.metadata == {"key": "value"}

    def test_set_code(self):
        from fenrir.grpc import GRPCContext
        ctx = GRPCContext()
        ctx.set_code(5)
        assert ctx.code == 5

    def test_set_details(self):
        from fenrir.grpc import GRPCContext
        ctx = GRPCContext()
        ctx.set_details("error occurred")
        assert ctx.details == "error occurred"

    def test_abort(self):
        from fenrir.grpc import GRPCContext
        ctx = GRPCContext()
        ctx.abort(13, "internal error")
        assert ctx.code == 13
        assert ctx.details == "internal error"
        assert ctx._cancelled is True

    def test_add_callback(self):
        from fenrir.grpc import GRPCContext
        ctx = GRPCContext()
        ctx.add_callback(lambda: None)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════
# GRPCServer Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGRPCServer:
    def test_init_defaults(self):
        from fenrir.grpc import GRPCServer
        server = GRPCServer()
        assert server._max_workers == 10
        assert server._interceptors == []
        assert server._services == []
        assert server._running is False

    def test_init_custom(self):
        from fenrir.grpc import GRPCInterceptor, GRPCServer
        interceptor = GRPCInterceptor()
        server = GRPCServer(max_workers=5, interceptors=[interceptor])
        assert server._max_workers == 5
        assert len(server._interceptors) == 1

    def test_add_service(self):
        from fenrir.grpc import GRPCServer, GRPCService
        server = GRPCServer()
        class MyService(GRPCService):
            service_name = "MyService"
        svc = MyService()
        server.add_service(svc)
        assert svc in server._services

    def test_add_interceptor(self):
        from fenrir.grpc import GRPCInterceptor, GRPCServer
        server = GRPCServer()
        interceptor = GRPCInterceptor()
        server.add_interceptor(interceptor)
        assert interceptor in server._interceptors

    def test_is_running(self):
        from fenrir.grpc import GRPCServer
        server = GRPCServer()
        assert server.is_running is False

    def test_mount_registers_listeners(self):
        from fenrir.grpc import GRPCServer
        server = GRPCServer()
        app = MagicMock()
        server.mount(app, port=50051)
        app.listener.assert_any_call("before_server_start")
        app.listener.assert_any_call("after_server_stop")

    def test_start_without_grpc(self):
        from fenrir.grpc import GRPCServer
        server = GRPCServer()
        with patch.dict("sys.modules", {"grpc": None}):
            with pytest.raises(ImportError, match="grpcio is required"):
                server.start()

    def test_stop_when_not_running(self):
        from fenrir.grpc import GRPCServer
        server = GRPCServer()
        server.stop()  # Should not raise

    def test_register_service_without_grpc(self):
        from fenrir.grpc import GRPCServer, GRPCService
        server = GRPCServer()
        class MyService(GRPCService):
            service_name = "MyService"
        svc = MyService()

        @svc.rpc_handler("GetUser")
        async def get_user(req, ctx):
            pass

        server.add_service(svc)
        with patch.dict("sys.modules", {"grpc": None}):
            server._register_service(svc)
        # Without grpc installed, _register_service returns early
        assert "MyService" not in server._registered_services

    def test_register_service_with_grpc(self):
        from fenrir.grpc import GRPCServer, GRPCService
        server = GRPCServer()
        class MyService(GRPCService):
            service_name = "MyService"
        svc = MyService()

        @svc.rpc_handler("GetUser")
        async def get_user(req, ctx):
            pass

        server.add_service(svc)
        mock_grpc = MagicMock()
        with patch.dict("sys.modules", {"grpc": mock_grpc}):
            server._register_service(svc)
        assert "MyService" in server._registered_services


# ═══════════════════════════════════════════════════════════════════════
# GRPCClient Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGRPCClient:
    def test_init(self):
        from fenrir.grpc import GRPCClient
        client = GRPCClient("localhost:50051")
        assert client._target == "localhost:50051"
        assert client._credentials is None
        assert client._options == {}
        assert client._channel is None

    def test_init_with_options(self):
        from fenrir.grpc import GRPCClient
        client = GRPCClient("localhost:50051", options={"key": "value"})
        assert client._options == {"key": "value"}

    @pytest.mark.anyio
    async def test_connect_without_grpc(self):
        from fenrir.grpc import GRPCClient
        client = GRPCClient("localhost:50051")
        with patch.dict("sys.modules", {"grpc": None}):
            with pytest.raises(ImportError, match="grpcio is required"):
                await client.connect()

    @pytest.mark.anyio
    async def test_close_when_not_connected(self):
        from fenrir.grpc import GRPCClient
        client = GRPCClient("localhost:50051")
        await client.close()  # Should not raise
        assert client._channel is None

    @pytest.mark.anyio
    async def test_context_manager(self):
        from fenrir.grpc import GRPCClient
        client = GRPCClient("localhost:50051")
        with patch.dict("sys.modules", {"grpc": None}):
            with pytest.raises(ImportError):
                async with client:
                    pass
