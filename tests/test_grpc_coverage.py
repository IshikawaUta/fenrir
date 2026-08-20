"""Coverage tests for fenrir.grpc using mocked grpcio modules."""
import sys
import types
from unittest import mock

import pytest

from fenrir.grpc import GRPCClient, GRPCServer, GRPCService


def _install_fake_grpc(monkeypatch):
    grpc = types.ModuleType("grpc")
    server_mock = mock.MagicMock()
    grpc.server = mock.Mock(return_value=server_mock)

    aio = types.ModuleType("grpc.aio")
    chan = mock.MagicMock()
    chan.close = mock.AsyncMock()
    aio.insecure_channel = mock.Mock(return_value=chan)
    aio.secure_channel = mock.Mock(return_value=chan)
    grpc.aio = aio

    health = types.ModuleType("grpc_health")
    v1 = types.ModuleType("grpc_health.v1")
    health_pb2 = types.ModuleType("grpc_health.v1.health_pb2")
    health_pb2.HealthCheckResponse = mock.MagicMock()
    health_pb2.HealthCheckResponse.SERVING = 1
    health_pb2.HealthCheckResponse.NOT_FOUND = 5
    pb2_grpc = types.ModuleType("grpc_health.v1.health_pb2_grpc")
    pb2_grpc.HealthServicer = object
    pb2_grpc.add_HealthServicer_to_server = mock.Mock()
    v1.health_pb2 = health_pb2
    v1.health_pb2_grpc = pb2_grpc
    health.v1 = v1

    monkeypatch.setitem(sys.modules, "grpc", grpc)
    monkeypatch.setitem(sys.modules, "grpc.aio", aio)
    monkeypatch.setitem(sys.modules, "grpc_health", health)
    monkeypatch.setitem(sys.modules, "grpc_health.v1", v1)
    monkeypatch.setitem(sys.modules, "grpc_health.v1.health_pb2", health_pb2)
    monkeypatch.setitem(sys.modules, "grpc_health.v1.health_pb2_grpc", pb2_grpc)
    return grpc, server_mock


class _Service(GRPCService):
    service_name = "MyService"


class _FakeApp:
    def __init__(self):
        self.listeners = {}

    def listener(self, name):
        def deco(fn):
            self.listeners[name] = fn
            return fn
        return deco


def test_grpc_service_subclass_with_shared_handlers():
    class Base(GRPCService):
        service_name = "Base"

    Base._handlers = {"x": lambda *a: None}

    class Child(Base):
        service_name = "Child"

    assert "x" in Child._handlers


def test_grpc_server_start_already_running(monkeypatch, caplog):
    server = GRPCServer()
    server._running = True
    with caplog.at_level("WARNING", logger="fenrir.grpc"):
        server.start()
    assert "already running" in caplog.text


def test_grpc_server_start_stop(monkeypatch):
    grpc_mod, server_mock = _install_fake_grpc(monkeypatch)
    server = GRPCServer()

    svc = _Service()

    @svc.rpc_handler("GetUser")
    async def get_user(req, ctx):
        pass

    server.add_service(svc)
    server.start(host="0.0.0.0", port=5000)

    assert server.is_running
    assert server._registered_services["MyService"]["GetUser"] is get_user
    server_mock.add_insecure_port.assert_called_once_with("0.0.0.0:5000")
    server_mock.start.assert_called_once()

    server.stop(grace=1)
    assert not server.is_running
    server_mock.stop.assert_called_once_with(1)


def test_grpc_server_start_without_health(monkeypatch):
    grpc_mod, server_mock = _install_fake_grpc(monkeypatch)
    server = GRPCServer()
    with mock.patch.dict("sys.modules", {
        "grpc_health": None,
        "grpc_health.v1": None,
        "grpc_health.v1.health_pb2_grpc": None,
    }):
        server.start()
    assert server.is_running
    server.stop()


@pytest.mark.anyio
async def test_grpc_server_mount_lifecycle(monkeypatch):
    _install_fake_grpc(monkeypatch)
    server = GRPCServer()
    app = _FakeApp()
    server.mount(app, host="0.0.0.0", port=5000)
    await app.listeners["before_server_start"](None)
    assert server.is_running
    await app.listeners["after_server_stop"](None)
    assert not server.is_running


def test_grpc_health_servicer_check(monkeypatch):
    from types import SimpleNamespace

    _install_fake_grpc(monkeypatch)
    server = GRPCServer()
    server.add_service(_Service())
    servicer = server._create_health_servicer()
    assert servicer is not None
    servicer.Check(SimpleNamespace(service="MyService"), None)
    servicer.Check(SimpleNamespace(service="Unknown"), None)
    servicer.Check(SimpleNamespace(service=""), None)


def test_grpc_health_servicer_missing(monkeypatch):
    server = GRPCServer()
    with mock.patch.dict("sys.modules", {"grpc_health": None}):
        assert server._create_health_servicer() is None


@pytest.mark.anyio
async def test_grpc_client_connect_close(monkeypatch):
    grpc_mod, _ = _install_fake_grpc(monkeypatch)
    client = GRPCClient("localhost:5000")
    await client.connect()
    grpc_mod.aio.insecure_channel.assert_called_once_with("localhost:5000")
    assert client._channel is not None
    channel = client._channel
    await client.close()
    channel.close.assert_called()
    assert client._channel is None


@pytest.mark.anyio
async def test_grpc_client_connect_secure(monkeypatch):
    grpc_mod, _ = _install_fake_grpc(monkeypatch)
    client = GRPCClient("localhost:5000", credentials="cred")
    await client.connect()
    grpc_mod.aio.secure_channel.assert_called_once_with("localhost:5000", "cred")


@pytest.mark.anyio
async def test_grpc_client_context_manager(monkeypatch):
    _install_fake_grpc(monkeypatch)
    async with GRPCClient("localhost:5000") as client:
        assert client._channel is not None
    assert client._channel is None
