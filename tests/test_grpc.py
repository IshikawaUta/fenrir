"""Tests for fenrir.grpc — gRPC support."""
import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════
# gRPC Module Tests
# ═══════════════════════════════════════════════════════════════════════

class TestGRPC:
    def test_import_without_grpcio(self):
        """Test that grpc module can be imported without grpcio."""
        import fenrir.grpc as grpc_module
        assert grpc_module is not None

    def test_grpc_service_creation(self):
        """Test GRPCService creation."""
        from fenrir.grpc import GRPCService
        
        class TestServicer(GRPCService):
            service_name = "TestService"
        
        servicer = TestServicer()
        assert servicer.service_name == "TestService"

    def test_grpc_service_handlers(self):
        """Test GRPCService handler registration."""
        from fenrir.grpc import GRPCService
        
        class TestServicer(GRPCService):
            service_name = "TestService"
        
        servicer = TestServicer()
        
        @servicer.rpc_handler("GetUser")
        async def get_user(request, context):
            return {"id": 1}
        
        assert "GetUser" in servicer._handlers

    def test_grpc_context(self):
        """Test GRPCContext creation."""
        from fenrir.grpc import GRPCContext
        
        context = GRPCContext(metadata={"key": "value"})
        assert context.metadata == {"key": "value"}
        assert context.code == 0
        
        context.set_code(1)
        assert context.code == 1
        
        context.set_details("test details")
        assert context.details == "test details"

    def test_grpc_context_abort(self):
        """Test GRPCContext abort."""
        from fenrir.grpc import GRPCContext
        
        context = GRPCContext()
        context.abort(1, "test error")
        
        assert context.code == 1
        assert context.details == "test error"
        assert context._cancelled is True

    def test_grpc_server_creation(self):
        """Test GRPCServer creation."""
        from fenrir.grpc import GRPCServer
        
        server = GRPCServer(max_workers=5)
        assert server._max_workers == 5
        assert server._running is False

    def test_grpc_server_add_service(self):
        """Test GRPCServer add service."""
        from fenrir.grpc import GRPCServer, GRPCService
        
        class TestServicer(GRPCService):
            service_name = "TestService"
        
        server = GRPCServer()
        servicer = TestServicer()
        server.add_service(servicer)
        
        assert servicer in server._services

    def test_grpc_server_add_interceptor(self):
        """Test GRPCServer add interceptor."""
        from fenrir.grpc import GRPCServer, GRPCInterceptor
        
        class TestInterceptor(GRPCInterceptor):
            async def intercept(self, method, request, context):
                return await method(request, context)
        
        server = GRPCServer()
        interceptor = TestInterceptor()
        server.add_interceptor(interceptor)
        
        assert interceptor in server._interceptors

    def test_grpc_client_creation(self):
        """Test GRPCClient creation."""
        from fenrir.grpc import GRPCClient
        
        client = GRPCClient("localhost:50051")
        assert client._target == "localhost:50051"
        assert client._channel is None
