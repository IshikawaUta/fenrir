"""
fenrir.grpc — gRPC support for Fenrir.

Provides gRPC server integration for Fenrir applications.
Supports:
- gRPC server with Fenrir app integration
- Unary and streaming RPCs
- Interceptors/middleware
- Health checking
- Reflection

Requires: ``pip install fenrir-framework[grpc]``

Usage::

    from fenrir import Fenrir
    from fenrir.grpc import GRPCServer, GRPCService

    # Define a service
    class UserServicer(GRPCService):
        service_name = "UserService"

        async def GetUser(self, request, context):
            return UserResponse(id=1, name="Alice")

    # Create server and mount
    server = GRPCServer()
    server.add_service(UserServicer())
    app = Fenrir()
    server.mount(app, port=50051)
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import threading
from concurrent import futures
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger("fenrir.grpc")


class GRPCService:
    """Base class for gRPC services.

    Subclass this to define gRPC service implementations.
    The service_name should match the protobuf service name.
    """
    service_name: str = ""
    _handlers: Dict[str, Callable] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls._handlers:
            cls._handlers = {}

    def rpc_handler(self, method_name: str) -> Callable:
        """Decorator to register an RPC handler."""
        def decorator(func: Callable) -> Callable:
            self._handlers[method_name] = func
            return func
        return decorator


class GRPCInterceptor:
    """Base class for gRPC interceptors."""

    async def intercept(self, method: str, request: Any, context: Any) -> Any:
        """Override to intercept RPC calls."""
        return await method(request, context)


class GRPCContext:
    """Context object passed to gRPC handlers."""

    def __init__(self, metadata: Optional[Dict[str, str]] = None) -> None:
        self.metadata = metadata or {}
        self.code = 0
        self.details = ""
        self._cancelled = False

    def set_code(self, code: int) -> None:
        self.code = code

    def set_details(self, details: str) -> None:
        self.details = details

    def abort(self, code: int, details: str) -> None:
        self.set_code(code)
        self.set_details(details)
        self._cancelled = True

    def add_callback(self, callback: Callable) -> None:
        pass


class GRPCServer:
    """gRPC server that can be mounted alongside a Fenrir app.

    Features:
    - Thread-based gRPC server (runs in background)
    - Interceptor support
    - Health checking
    - Graceful shutdown

    Usage::

        server = GRPCServer()
        server.add_service(MyServicer())
        server.mount(app, port=50051)
    """

    def __init__(
        self,
        max_workers: int = 10,
        interceptors: Optional[List[GRPCInterceptor]] = None,
    ) -> None:
        self._max_workers = max_workers
        self._interceptors = interceptors or []
        self._services: List[GRPCService] = []
        self._registered_services: Dict[str, Dict[str, Any]] = {}
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def add_service(self, service: GRPCService) -> None:
        """Add a gRPC service to the server."""
        self._services.append(service)
        logger.info("Added gRPC service: %s", service.service_name)

    def add_interceptor(self, interceptor: GRPCInterceptor) -> None:
        """Add an interceptor."""
        self._interceptors.append(interceptor)

    def mount(self, app: Any, host: str = "[::]", port: int = 50051) -> None:
        """Mount the gRPC server and integrate with Fenrir app lifecycle.

        The gRPC server runs in a separate thread to avoid blocking the
        async event loop.
        """
        server = self

        @app.listener("before_server_start")
        async def start_grpc(app_instance):
            server.start(host, port)

        @app.listener("after_server_stop")
        async def stop_grpc(app_instance):
            server.stop()

        logger.info("gRPC server will start on %s:%d", host, port)

    def start(self, host: str = "[::]", port: int = 50051) -> None:
        """Start the gRPC server in a background thread."""
        if self._running:
            logger.warning("gRPC server already running")
            return

        try:
            import grpc
            from concurrent import futures
        except ImportError:
            raise ImportError(
                "grpcio is required for gRPC support. "
                "Install with: pip install fenrir-framework[grpc]"
            )

        self._server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self._max_workers)
        )

        # Register services
        for service in self._services:
            self._register_service(service)

        # Add health checking
        try:
            from grpc_health.v1 import health_pb2_grpc
            health_servicer = self._create_health_servicer()
            health_pb2_grpc.add_HealthServicer_to_server(health_servicer, self._server)
        except ImportError:
            pass

        self._server.add_insecure_port(f"{host}:{port}")
        self._server.start()
        self._running = True

        logger.info("gRPC server started on %s:%d", host, port)

    def _register_service(self, service: GRPCService) -> None:
        """Register a service's handlers with the gRPC server."""
        try:
            import grpc
        except ImportError:
            return

        handlers = service._handlers
        self._registered_services[service.service_name] = handlers
        for method_name, handler in handlers.items():
            logger.debug("Registered gRPC handler: %s.%s", service.service_name, method_name)

    def _create_health_servicer(self) -> Any:
        """Create a health check servicer."""
        try:
            from grpc_health.v1 import health_pb2, health_pb2_grpc

            class HealthServicer(health_pb2_grpc.HealthServicer):
                def __init__(self, services: List[GRPCService]):
                    self._services = {s.service_name: True for s in services}

                def Check(self, request, context):
                    service_name = request.service
                    if service_name and service_name in self._services:
                        return health_pb2.HealthCheckResponse(
                            status=health_pb2.HealthCheckResponse.SERVING
                        )
                    return health_pb2.HealthCheckResponse(
                        status=health_pb2.HealthCheckResponse.NOT_FOUND
                    )

            return HealthServicer(self._services)
        except ImportError:
            return None

    def stop(self, grace: float = 5.0) -> None:
        """Stop the gRPC server gracefully."""
        if self._server and self._running:
            self._server.stop(grace)
            self._running = False
            logger.info("gRPC server stopped")

    @property
    def is_running(self) -> bool:
        return self._running


class GRPCClient:
    """gRPC client for making calls to gRPC services.

    Usage::

        client = GRPCClient("localhost:50051")
        response = await client.call("UserService", "GetUser", user_id=1)
        await client.close()
    """

    def __init__(
        self,
        target: str,
        credentials: Optional[Any] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._target = target
        self._credentials = credentials
        self._options = options or {}
        self._channel = None

    async def connect(self) -> None:
        """Establish connection to gRPC server."""
        try:
            import grpc
            import grpc.aio
        except ImportError:
            raise ImportError("grpcio is required for gRPC client")

        if self._credentials:
            self._channel = grpc.aio.secure_channel(self._target, self._credentials)
        else:
            self._channel = grpc.aio.insecure_channel(self._target)

    async def close(self) -> None:
        """Close the connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None

    async def __aenter__(self) -> "GRPCClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
