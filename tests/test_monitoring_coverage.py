"""Targeted coverage tests for fenrir.monitoring (core + routes)."""
import copy
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from fenrir import Fenrir
from fenrir.monitoring import core
from fenrir.monitoring.core import (
    _build_pinned_opener,
    _get_default_secret,
    _load_config,
    _load_data,
    _monitoring_data,
    _PinnedHTTPConnection,
    _PinnedHTTPHandler,
    _PinnedHTTPSConnection,
    _PinnedHTTPSHandler,
    _resolve_public_ip,
    _save_data,
    _validate_url_for_ssrf,
    check_site_health,
    get_hourly_traffic,
    get_response_time_history,
    get_traffic_stats,
    get_uptime_stats,
    init_monitoring,
)
from fenrir.monitoring.routes import _client_ip, _parse_json

MONITORING_ENV = {
    "MONITORING_ENABLED": "true",
    "MONITORING_USER": "admin",
    "MONITORING_PASSWORD": "testpass",
    "MONITORING_SECRET_KEY": "test-secret",
}


@pytest.fixture(autouse=True)
def snapshot_monitoring_data():
    snap = copy.deepcopy(_monitoring_data)
    yield
    _monitoring_data.clear()
    _monitoring_data.update(snap)


@pytest.fixture(autouse=True)
def clean_default_secret():
    original = core._DEFAULT_SECRET
    core._DEFAULT_SECRET = None
    yield
    core._DEFAULT_SECRET = original


@pytest.fixture(autouse=True)
def clean_login_attempts():
    from fenrir.monitoring.core import _login_attempts
    yield
    _login_attempts.clear()


async def _login(client, secret="test-secret", user="admin"):
    from fenrir.monitoring.core import _generate_token
    token = _generate_token(user, secret)
    client.client.cookies.set("monitoring_token", token)
    return client


class TestDefaultSecret:
    def test_generates_and_caches(self):
        s1 = _get_default_secret()
        assert isinstance(s1, str) and len(s1) == 64
        assert core._DEFAULT_SECRET == s1
        s2 = _get_default_secret()
        assert s1 == s2


class TestLoadConfig:
    def test_load_config_basic(self):
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "bob",
            "MONITORING_SECRET_KEY": "sekret",
            "MONITORING_SITES": "http://a.test, http://b.test",
            "MONITORING_CHECK_INTERVAL": "120",
        }):
            cfg = _load_config()
        assert cfg["enabled"] is True
        assert cfg["user"] == "bob"
        assert cfg["secret_key"] == "sekret"
        assert cfg["sites"] == ["http://a.test", "http://b.test"]
        assert cfg["check_interval"] == 120

    def test_load_config_missing_dotenv(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "dotenv", None)
        with patch.dict(os.environ, {}, clear=True):
            cfg = _load_config()
        assert cfg["enabled"] is False
        assert cfg["user"] == "admin"

    def test_load_config_defaults(self):
        with patch("dotenv.load_dotenv", return_value=False), \
             patch.dict(os.environ, {}, clear=True):
            cfg = _load_config()
        assert cfg["secret_key"] == core._DEFAULT_SECRET
        assert cfg["sites"] == ["http://localhost:8000"]


class TestSaveLoadErrors:
    def test_save_data_error(self, tmp_path):
        with patch("fenrir.monitoring.core._get_data_dir", return_value=tmp_path), \
             patch("builtins.open", side_effect=OSError("disk full")):
            _save_data()

    def test_load_data_no_file(self, tmp_path):
        with patch("fenrir.monitoring.core._get_data_dir", return_value=tmp_path):
            _load_data()

    def test_load_data_corrupt(self, tmp_path):
        data_dir = tmp_path / ".fenrir_monitoring"
        data_dir.mkdir(exist_ok=True)
        (data_dir / "monitoring_data.json").write_text("{not valid json")
        with patch("fenrir.monitoring.core._get_data_dir", return_value=data_dir):
            _load_data()


class TestInitMonitoringMerge:
    def test_config_merge_missing_keys(self):
        app = Fenrir()
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app, config={
                "enabled": True, "user": None, "sites": [],
                "check_interval": None, "secret_key": None,
            })
        assert app.config["MONITORING_USER"] == "admin"
        assert app.config["MONITORING_ENABLED"] is True

    def test_config_keeps_provided_value(self):
        app = Fenrir()
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app, config={"enabled": True, "user": "bob"})
        assert app.config["MONITORING_USER"] == "bob"
        assert app.config["MONITORING_SITES"] == ["http://localhost:8000"]

    def test_no_password_enabled_raises(self):
        app = Fenrir()
        with patch("dotenv.load_dotenv", return_value=False), \
             patch.dict(os.environ, {"MONITORING_ENABLED": "true"}, clear=True):
            with pytest.raises(ValueError, match="MONITORING_PASSWORD must be set"):
                init_monitoring(app)

    def test_no_password_disabled_warns(self):
        app = Fenrir()
        with patch("dotenv.load_dotenv", return_value=False), \
             patch.dict(os.environ, {"MONITORING_ENABLED": "false"}, clear=True):
            init_monitoring(app)
        assert app.config["MONITORING_PASSWORD_HASH"]
        assert app.config["MONITORING_ENABLED"] is False


class TestResolvePublicIp:
    def test_oserror(self):
        with patch("socket.getaddrinfo", side_effect=OSError("dns")):
            assert _resolve_public_ip("example.com") is None

    def test_private_only(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 0))]):
            assert _resolve_public_ip("example.com") is None

    def test_valueerror_continue(self):
        with patch("socket.getaddrinfo", return_value=[
            (2, 1, 6, "", ("not-an-ip", 0)),
            (2, 1, 6, "", ("93.184.216.34", 0)),
        ]):
            assert _resolve_public_ip("example.com") == "93.184.216.34"

    def test_loopback_skip(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]):
            assert _resolve_public_ip("example.com") is None

    def test_public_ok(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            assert _resolve_public_ip("example.com") == "93.184.216.34"


class TestValidateUrlSsrf:
    def test_bad_scheme(self):
        assert _validate_url_for_ssrf("ftp://example.com") is False

    def test_no_hostname(self):
        assert _validate_url_for_ssrf("http:///x") is False

    def test_private_ip(self):
        assert _validate_url_for_ssrf("http://192.168.1.5/x") is False

    def test_blocked_hostname(self):
        assert _validate_url_for_ssrf("http://localhost/x") is False

    def test_no_public_ip(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", return_value=None):
            assert _validate_url_for_ssrf("http://example.com") is False

    def test_ok(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", return_value="93.184.216.34"):
            assert _validate_url_for_ssrf("http://example.com") is True

    def test_public_literal_ip(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", return_value="93.184.216.34"):
            assert _validate_url_for_ssrf("http://93.184.216.34/x") is True

    def test_resolve_raises(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", side_effect=Exception("boom")):
            assert _validate_url_for_ssrf("http://example.com") is False


class TestPinnedConnections:
    def test_http_connect(self):
        conn = _PinnedHTTPConnection("example.com", "1.2.3.4")
        fake_sock = object()
        with patch.object(conn, "_create_connection", return_value=fake_sock):
            conn.connect()
        assert conn.sock is fake_sock

    def test_http_connect_tunnel(self):
        conn = _PinnedHTTPConnection("example.com", "1.2.3.4")
        conn.set_tunnel("proxy.example.com", 8080)
        fake_sock = object()
        with patch.object(conn, "_create_connection", return_value=fake_sock), \
             patch.object(conn, "_tunnel") as tunnel:
            conn.connect()
        tunnel.assert_called_once()

    def test_https_connect(self):
        conn = _PinnedHTTPSConnection("example.com", "1.2.3.4")
        fake_sock = object()
        ctx = MagicMock()
        with patch.object(conn, "_create_connection", return_value=fake_sock), \
             patch.object(conn, "_context", ctx):
            conn.connect()
        ctx.wrap_socket.assert_called_once_with(fake_sock, server_hostname="example.com")

    def test_https_connect_tunnel(self):
        conn = _PinnedHTTPSConnection("example.com", "1.2.3.4")
        conn.set_tunnel("proxy.example.com", 8080)
        fake_sock = object()
        ctx = MagicMock()
        with patch.object(conn, "_create_connection", return_value=fake_sock), \
             patch.object(conn, "_context", ctx), \
             patch.object(conn, "_tunnel") as tunnel:
            conn.connect()
        tunnel.assert_called_once()


class TestPinnedHandlers:
    def test_http_handler(self):
        import urllib.request
        handler = _PinnedHTTPHandler("1.2.3.4")
        req = urllib.request.Request("http://example.com")
        with patch.object(handler, "do_open", return_value="opened") as do_open:
            result = handler.http_open(req)
        assert result == "opened"
        factory = do_open.call_args[0][0]
        conn = factory("example.com", timeout=10)
        assert isinstance(conn, _PinnedHTTPConnection)
        assert conn._pinned_ip == "1.2.3.4"

    def test_https_handler(self):
        import urllib.request
        handler = _PinnedHTTPSHandler("1.2.3.4")
        req = urllib.request.Request("https://example.com")
        with patch.object(handler, "do_open", return_value="opened") as do_open:
            result = handler.https_open(req)
        assert result == "opened"
        factory = do_open.call_args[0][0]
        conn = factory("example.com", timeout=10)
        assert isinstance(conn, _PinnedHTTPSConnection)
        assert conn._pinned_ip == "1.2.3.4"


class TestBuildPinnedOpener:
    def test_bad_scheme(self):
        assert _build_pinned_opener("ftp://example.com") is None

    def test_no_hostname(self):
        assert _build_pinned_opener("http:///x") is None

    def test_private_ip(self):
        assert _build_pinned_opener("http://10.0.0.1/x") is None

    def test_blocked_hostname(self):
        assert _build_pinned_opener("http://localhost/x") is None

    def test_no_public_ip(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", return_value=None):
            assert _build_pinned_opener("http://example.com") is None

    def test_ok(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", return_value="93.184.216.34"):
            opener = _build_pinned_opener("http://example.com/x")
        assert opener is not None
        handler_types = [type(h) for h in opener.handlers]
        assert _PinnedHTTPHandler in handler_types
        assert _PinnedHTTPSHandler in handler_types

    def test_public_literal_ip(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", return_value="93.184.216.34"):
            opener = _build_pinned_opener("http://93.184.216.34/x")
        assert opener is not None

    def test_resolve_raises(self):
        with patch("fenrir.monitoring.core._resolve_public_ip", side_effect=Exception("boom")):
            assert _build_pinned_opener("http://example.com") is None


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, exc=None, status=200):
        self._exc = exc
        self._status = status

    def open(self, req, timeout=10):
        if self._exc is not None:
            raise self._exc
        return FakeResponse(self._status)


class TestCheckSiteHealth:
    def test_pinned_healthy(self):
        with patch("fenrir.monitoring.core._build_pinned_opener", return_value=FakeOpener(status=200)):
            result = check_site_health("http://example.com")
        assert result["status"] == "healthy"
        assert result["status_code"] == 200
        assert result["response_time"] is not None

    def test_pinned_degraded_status(self):
        with patch("fenrir.monitoring.core._build_pinned_opener", return_value=FakeOpener(status=503)):
            result = check_site_health("http://example.com")
        assert result["status"] == "degraded"
        assert result["status_code"] == 503

    def test_pinned_http_error(self):
        import urllib.error
        err = urllib.error.HTTPError("http://example.com", 404, "Not Found", {}, None)
        with patch("fenrir.monitoring.core._build_pinned_opener", return_value=FakeOpener(exc=err)):
            result = check_site_health("http://example.com")
        assert result["status"] == "degraded"
        assert result["status_code"] == 404

    def test_pinned_down(self):
        import urllib.error
        err = urllib.error.URLError("no route")
        with patch("fenrir.monitoring.core._build_pinned_opener", return_value=FakeOpener(exc=err)):
            result = check_site_health("http://example.com")
        assert result["status"] == "down"
        assert result["error"]

    def test_allowed_site_urlopen(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(status=200)):
            result = check_site_health("http://example.com", allowed_sites=["http://example.com"])
        assert result["status"] == "healthy"

    def test_blocked_private(self):
        result = check_site_health("http://127.0.0.1/x")
        assert result["status"] == "error"
        assert "blocked" in result["error"]

    def test_history_truncated(self):
        url = "http://example.com"
        _monitoring_data["health_history"][url] = [
            {"timestamp": "t", "status": "healthy", "status_code": 200, "response_time": 1}
            for _ in range(100)
        ]
        with patch("fenrir.monitoring.core._build_pinned_opener", return_value=FakeOpener(status=200)):
            check_site_health(url)
        assert len(_monitoring_data["health_history"][url]) == 100


class TestUptimeStatsEdges:
    def test_empty_checks_list(self):
        _monitoring_data["health_history"]["http://empty.test"] = []
        stats = get_uptime_stats()
        assert stats["http://empty.test"]["percentage"] == 0
        assert stats["http://empty.test"]["total_checks"] == 0


class TestResponseTimeHistoryEdges:
    def test_old_and_invalid_skipped(self):
        from datetime import datetime, timedelta
        _monitoring_data["health_history"]["http://x"] = [
            {"timestamp": (datetime.now() - timedelta(hours=48)).isoformat(), "status": "healthy"},
            {"timestamp": "not-a-date", "status": "healthy"},
            {"timestamp": (datetime.now() - timedelta(minutes=1)).isoformat(), "status": "healthy"},
            {"status": "healthy"},
        ]
        history = get_response_time_history("http://x", hours=24)
        assert len(history) == 1


class TestTrafficStatsEdges:
    def test_bad_entry_skipped(self):
        _monitoring_data["traffic_log"] = [
            {"timestamp": "garbage", "status_code": 500},
            {"path": "/", "method": "GET", "status_code": 200, "response_time": 1, "timestamp": "garbage2"},
        ]
        stats = get_traffic_stats()
        assert stats["today"]["total"] == 0

    def test_yesterday_change(self):
        from datetime import datetime, timedelta
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        _monitoring_data["traffic_log"] = [
            {"timestamp": yesterday, "path": "/", "method": "GET", "status_code": 200, "response_time": 1}
        ]
        stats = get_traffic_stats()
        assert stats["yesterday"]["total"] == 1
        assert stats["change_percentage"] == -100.0

    def test_yesterday_and_today(self):
        from datetime import datetime, timedelta
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        today = datetime.now().isoformat()
        _monitoring_data["traffic_log"] = [
            {"timestamp": yesterday, "path": "/y", "method": "GET", "status_code": 200, "response_time": 10},
            {"timestamp": today, "path": "/t", "method": "GET", "status_code": 200, "response_time": 20},
            {"timestamp": today, "path": "/t", "method": "GET", "status_code": 500, "response_time": 30},
        ]
        stats = get_traffic_stats()
        assert stats["today"]["total"] == 2
        assert stats["today"]["paths"] == {"/t": 2}
        assert stats["yesterday"]["total"] == 1
        assert stats["change_percentage"] == 100.0


class TestHourlyTrafficEdges:
    def test_errors_and_bad_entries(self):
        from datetime import datetime
        _monitoring_data["traffic_log"] = [
            {"timestamp": datetime.now().isoformat(), "status_code": 500, "response_time": 5},
            {"timestamp": "bad-timestamp", "status_code": 200},
        ]
        hourly = get_hourly_traffic(1)
        assert len(hourly) == 1
        assert hourly[0]["errors"] == 1
        assert hourly[0]["requests"] == 1


class TestPinnedClientIp:
    def _req(self, scope=None, headers=None):
        return SimpleNamespace(scope=scope, headers=headers or {})

    def test_scope_client(self):
        r = self._req(scope={"client": ["1.2.3.4", 1234]})
        assert _client_ip(r) == "1.2.3.4"

    def test_scope_client_wrong_type(self):
        r = self._req(scope={"client": "nope"})
        assert _client_ip(r) == "unknown"

    def test_no_scope_forwarded(self):
        r = self._req(headers={"x-forwarded-for": "9.9.9.9, 8.8.8.8"})
        assert _client_ip(r) == "9.9.9.9"

    def test_no_scope_real_ip(self):
        r = self._req(headers={"x-real-ip": "7.7.7.7"})
        assert _client_ip(r) == "7.7.7.7"

    def test_no_scope_host(self):
        r = self._req(headers={"host": "example.com:8080"})
        assert _client_ip(r) == "example.com"

    def test_no_scope_no_host(self):
        r = self._req(headers={"x-other": "1"})
        assert _client_ip(r) == "unknown"

    def test_no_scope_no_headers(self):
        assert _client_ip(None) == "unknown"

    def test_no_scope_empty_headers(self):
        assert _client_ip(self._req()) == "unknown"


class TestParseJson:
    def test_valid(self):
        assert _parse_json('{"a": 1}') == {"a": 1}

    def test_invalid(self):
        assert _parse_json("{not json") == {}

    def test_empty(self):
        assert _parse_json("") == {}


@pytest.mark.anyio
class TestMonitoringRoutesEdges:
    async def _init(self, app, extra=None):
        env = dict(MONITORING_ENV)
        env.update(extra or {})
        with patch.dict(os.environ, env):
            init_monitoring(app)
        return app.test_client()

    async def test_index_valid_token_redirects_dashboard(self, app):
        client = await self._init(app)
        await _login(client)
        resp = await client.get("/monitoring")
        assert resp.status_code in (302, 307)
        assert "/monitoring/dashboard" in resp.headers.get("location", "")

    async def test_logout_success_with_csrf(self, app):
        client = await self._init(app)
        resp = await client.get("/monitoring/login")
        csrf = ""
        for cookie in resp.headers.get_list("set-cookie"):
            if "monitoring_csrf=" in cookie:
                csrf = cookie.split("monitoring_csrf=")[1].split(";")[0]
        client.client.cookies.set("monitoring_csrf", csrf)
        resp = await client.post(
            "/monitoring/login",
            content=f"username=admin&password=testpass&csrf_token={csrf}".encode(),
        )
        assert resp.status_code == 302
        resp = await client.post(
            "/monitoring/logout",
            content=f"csrf_token={csrf}".encode(),
        )
        assert resp.status_code == 302
        assert "/monitoring/login" in resp.headers.get("location", "")

    async def test_logout_csrf_mismatch(self, app):
        client = await self._init(app)
        await _login(client)
        resp = await client.post("/monitoring/logout", content=b"csrf_token=wrong")
        assert resp.status_code in (302, 307)
        assert "/monitoring/dashboard" in resp.headers.get("location", "")

    async def test_dashboard_pending_site(self, app):
        client = await self._init(app, {"MONITORING_SITES": "http://a.test,http://b.test"})
        _monitoring_data["health_checks"] = {
            "http://a.test": {"url": "http://a.test", "status": "healthy", "response_time": 1,
                              "status_code": 200, "checked_at": "now"},
        }
        await _login(client)
        resp = await client.get("/monitoring/dashboard")
        assert resp.status_code == 200
        assert "PENDING" in resp.text
        assert "http://a.test" in resp.text
        assert "http://b.test" in resp.text

    async def test_dashboard_empty_uptime(self, app):
        client = await self._init(app)
        _monitoring_data["health_history"] = {}
        await _login(client)
        resp = await client.get("/monitoring/dashboard")
        assert resp.status_code == 200

    async def test_dashboard_bad_alert_timestamp(self, app):
        client = await self._init(app)
        _monitoring_data["alerts"] = [
            {"timestamp": "not-a-timestamp", "title": "X", "message": "m", "level": "info"}
        ]
        await _login(client)
        resp = await client.get("/monitoring/dashboard")
        assert resp.status_code == 200

    async def test_dashboard_no_alerts(self, app):
        client = await self._init(app)
        _monitoring_data["alerts"] = []
        await _login(client)
        resp = await client.get("/monitoring/dashboard")
        assert resp.status_code == 200
        assert "No recent alerts" in resp.text

    async def test_api_unauthorized(self, app):
        client = await self._init(app)
        for path in (
            "/monitoring/api/health",
            "/monitoring/api/traffic",
            "/monitoring/api/alerts",
            "/monitoring/api/stats",
            "/monitoring/api/uptime",
            "/monitoring/api/response-times",
            "/monitoring/api/hourly",
            "/monitoring/api/summary",
        ):
            resp = await client.get(path)
            assert resp.status_code == 401, path
            assert resp.json()["error"] == "unauthorized"

    async def test_api_response_times_invalid_hours(self, app):
        client = await self._init(app)
        await _login(client)
        resp = await client.get("/monitoring/api/response-times?url=http://localhost:8000&hours=abc")
        assert resp.status_code == 200
        assert "history" in resp.json()

    async def test_api_response_times_all_sites(self, app):
        client = await self._init(app)
        await _login(client)
        resp = await client.get("/monitoring/api/response-times")
        assert resp.status_code == 200
        assert "history" in resp.json()

    async def test_api_hourly_invalid_days(self, app):
        client = await self._init(app)
        await _login(client)
        resp = await client.get("/monitoring/api/hourly?days=abc")
        assert resp.status_code == 200
        assert "hourly" in resp.json()
