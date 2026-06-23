"""Tests for fenrir.monitoring module."""
import os
import json
import pytest
from unittest.mock import patch

from fenrir import Fenrir
from fenrir.monitoring.core import (
    _hash_password,
    _verify_password,
    _generate_token,
    _validate_token,
    record_request,
    check_site_health,
    get_traffic_stats,
    add_alert,
    get_alerts,
    _monitoring_data,
    init_monitoring,
    _save_data,
    _load_data,
    get_uptime_stats,
    get_response_time_history,
    get_hourly_traffic,
    get_summary,
    _get_data_dir,
)
from fenrir.monitoring.routes import register_monitoring_routes, _parse_form


MONITORING_ENV = {
    "MONITORING_ENABLED": "true",
    "MONITORING_USER": "admin",
    "MONITORING_PASSWORD": "testpass",
    "MONITORING_SECRET_KEY": "test-secret",
}


async def _login(client):
    """Login and set auth cookies on the client."""
    from fenrir.monitoring.core import _generate_token
    token = _generate_token("admin", "test-secret")
    client.client.cookies.set("monitoring_token", token)
    return client


# ── Core Functions ────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_password_returns_string(self):
        result = _hash_password("testpass")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_verify_password_correct(self):
        password_hash = _hash_password("mypassword")
        assert _verify_password("mypassword", password_hash) is True

    def test_verify_password_wrong(self):
        password_hash = _hash_password("mypassword")
        assert _verify_password("wrongpassword", password_hash) is False

    def test_different_hashes_for_same_password(self):
        h1 = _hash_password("same")
        h2 = _hash_password("same")
        assert h1 != h2


class TestTokenGeneration:
    def test_generate_token_returns_string(self):
        token = _generate_token("admin", "secret")
        assert isinstance(token, str)
        assert ":" in token  # format: hash:expires_at
        token_hash, expires_at = token.rsplit(":", 1)
        assert len(token_hash) == 64  # SHA256 hex digest
        assert int(expires_at) > 0

    def test_different_tokens_for_different_users(self):
        t1 = _generate_token("user1", "secret")
        t2 = _generate_token("user2", "secret")
        assert t1 != t2

    def test_different_tokens_for_different_secrets(self):
        t1 = _generate_token("admin", "secret1")
        t2 = _generate_token("admin", "secret2")
        assert t1 != t2


class TestTokenValidation:
    def test_valid_token(self):
        token = _generate_token("admin", "secret")
        assert _validate_token(token, "admin", "secret") is True

    def test_expired_token(self):
        token = "a" * 64 + ":1"
        assert _validate_token(token, "admin", "secret") is False

    def test_wrong_secret(self):
        token = _generate_token("admin", "wrong_secret")
        assert _validate_token(token, "admin", "correct_secret") is False

    def test_wrong_user(self):
        token = _generate_token("admin", "secret")
        assert _validate_token(token, "user2", "secret") is False

    def test_malformed_no_colon(self):
        assert _validate_token("nocolon", "admin", "secret") is False

    def test_malformed_non_numeric_expires(self):
        assert _validate_token("hash:notanumber", "admin", "secret") is False

    def test_empty_token(self):
        assert _validate_token("", "admin", "secret") is False

    def test_none_token(self):
        assert _validate_token(None, "admin", "secret") is False


class TestRecordRequest:
    def setup_method(self):
        _monitoring_data["traffic_log"] = []

    def test_record_single_request(self):
        record_request("/", "GET", 200, 0.05)
        assert len(_monitoring_data["traffic_log"]) == 1
        entry = _monitoring_data["traffic_log"][0]
        assert entry["path"] == "/"
        assert entry["method"] == "GET"
        assert entry["status_code"] == 200
        assert entry["response_time"] == 0.05

    def test_record_multiple_requests(self):
        for i in range(5):
            record_request(f"/path{i}", "GET", 200, 0.01)
        assert len(_monitoring_data["traffic_log"]) == 5

    def test_record_request_with_different_status(self):
        record_request("/error", "GET", 500, 0.02)
        entry = _monitoring_data["traffic_log"][0]
        assert entry["status_code"] == 500


class TestTrafficStats:
    def setup_method(self):
        _monitoring_data["traffic_log"] = []

    def test_empty_stats(self):
        stats = get_traffic_stats()
        assert stats["today"]["total"] == 0
        assert stats["yesterday"]["total"] == 0
        assert stats["change_percentage"] == 0

    def test_stats_with_requests(self):
        for _ in range(10):
            record_request("/", "GET", 200, 50.0)
        stats = get_traffic_stats()
        assert stats["today"]["total"] == 10
        assert stats["today"]["avg_response_time"] == 50.0

    def test_stats_tracks_status_codes(self):
        record_request("/", "GET", 200, 0.01)
        record_request("/error", "GET", 500, 0.01)
        stats = get_traffic_stats()
        assert "200" in stats["today"]["status_codes"]
        assert "500" in stats["today"]["status_codes"]

    def test_stats_tracks_methods(self):
        record_request("/", "GET", 200, 0.01)
        record_request("/", "POST", 201, 0.01)
        stats = get_traffic_stats()
        assert "GET" in stats["today"]["methods"]
        assert "POST" in stats["today"]["methods"]

    def test_error_rate_calculation(self):
        record_request("/", "GET", 200, 0.01)
        record_request("/", "GET", 200, 0.01)
        record_request("/", "GET", 500, 0.01)
        stats = get_traffic_stats()
        assert stats["today"]["error_rate"] == 33.33


class TestHealthCheck:
    def test_check_health_returns_dict(self):
        result = check_site_health("http://localhost:99999")
        assert isinstance(result, dict)
        assert result["url"] == "http://localhost:99999"
        # SSRF protection blocks localhost, so status is "error"
        assert result["status"] in ("healthy", "degraded", "down", "unknown", "error")

    def test_check_health_records_result(self):
        check_site_health("http://localhost:99999")
        assert "http://localhost:99999" in _monitoring_data["health_checks"]


class TestUptimeStats:
    def setup_method(self):
        _monitoring_data["traffic_log"] = []
        _monitoring_data["health_history"] = {}
        _monitoring_data["start_time"] = "2024-01-01T00:00:00"

    def test_empty_uptime(self):
        stats = get_uptime_stats()
        assert isinstance(stats, dict)

    def test_uptime_with_data(self):
        _monitoring_data["health_history"]["http://example.com"] = [
            {"status": "healthy", "timestamp": "2024-01-01T00:00:00"},
            {"status": "healthy", "timestamp": "2024-01-01T00:01:00"},
        ]
        stats = get_uptime_stats()
        assert "http://example.com" in stats
        assert stats["http://example.com"]["percentage"] == 100.0
        assert stats["http://example.com"]["total_checks"] == 2


class TestResponseTimeHistory:
    def setup_method(self):
        _monitoring_data["health_history"] = {}

    def test_empty_history(self):
        history = get_response_time_history("http://example.com", hours=24)
        assert isinstance(history, list)

    def test_history_with_data(self):
        from datetime import datetime
        now = datetime.now().isoformat()
        _monitoring_data["health_history"]["http://example.com"] = [
            {"status": "healthy", "timestamp": now, "response_time": 0.05},
        ]
        history = get_response_time_history("http://example.com", hours=24)
        assert isinstance(history, list)
        assert len(history) == 1
        assert history[0]["response_time"] == 0.05


class TestHourlyTraffic:
    def setup_method(self):
        _monitoring_data["traffic_log"] = []

    def test_empty_hourly(self):
        hourly = get_hourly_traffic(hours=24)
        assert isinstance(hourly, list)

    def test_hourly_with_data(self):
        record_request("/", "GET", 200, 0.01)
        hourly = get_hourly_traffic(hours=24)
        assert isinstance(hourly, list)
        assert len(hourly) > 0


class TestSummary:
    def setup_method(self):
        _monitoring_data["traffic_log"] = []
        _monitoring_data["alerts"] = []
        _monitoring_data["health_history"] = {}

    def test_empty_summary(self):
        summary = get_summary()
        assert "overview" in summary
        assert "sites" in summary
        assert "hourly_traffic" in summary

    def test_summary_with_data(self):
        record_request("/", "GET", 200, 0.01)
        add_alert("Test", "msg", "info")
        summary = get_summary()
        assert "overview" in summary
        assert len(summary["sites"]) > 0


class TestAlerts:
    def setup_method(self):
        _monitoring_data["alerts"] = []

    def test_add_alert(self):
        alert = add_alert("Test Title", "Test message", "warning")
        assert alert["title"] == "Test Title"
        assert alert["level"] == "warning"

    def test_get_alerts(self):
        add_alert("Alert 1", "msg1", "info")
        add_alert("Alert 2", "msg2", "warning")
        alerts = get_alerts()
        assert len(alerts) == 2
        # Alerts are returned in reverse order (newest first)
        assert alerts[0]["title"] == "Alert 2"

    def test_get_alerts_limit(self):
        for i in range(10):
            add_alert(f"Alert {i}", f"msg{i}", "info")
        alerts = get_alerts(limit=3)
        assert len(alerts) == 3


class TestSaveLoadData:
    def test_save_and_load_data(self, tmp_path):
        with patch("fenrir.monitoring.core._get_data_dir", return_value=tmp_path):
            _monitoring_data["traffic_log"] = [
                {"path": "/", "method": "GET", "status_code": 200, "response_time": 0.05, "timestamp": "2024-01-01T00:00:00"}
            ]
            _monitoring_data["alerts"] = [
                {"title": "Test", "message": "msg", "level": "info", "timestamp": "2024-01-01T00:00:00"}
            ]
            _save_data()

            # Reset and load
            _monitoring_data["traffic_log"] = []
            _monitoring_data["alerts"] = []
            _load_data()

            assert len(_monitoring_data["traffic_log"]) == 1
            assert len(_monitoring_data["alerts"]) == 1


class TestInitMonitoring:
    def test_raises_on_default_password_when_enabled(self):
        app = Fenrir()
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_PASSWORD": "changeme",
        }):
            with pytest.raises(ValueError, match="MONITORING_PASSWORD must be set"):
                init_monitoring(app)

    def test_allows_default_password_with_override(self):
        app = Fenrir()
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_PASSWORD": "changeme",
            "MONITORING_ALLOW_DEFAULT_PASSWORD": "true",
        }):
            init_monitoring(app)
            assert app.config["MONITORING_ENABLED"] is True

    def test_no_error_when_disabled_with_default_password(self):
        app = Fenrir()
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "false",
            "MONITORING_PASSWORD": "changeme",
        }):
            init_monitoring(app)
            assert app.config["MONITORING_ENABLED"] is False


class TestGetDataDir:
    def test_handles_oserror(self, tmp_path):
        with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
            result = _get_data_dir()
            assert result.name == ".fenrir_monitoring"


class TestTrafficEdgeCases:
    def test_error_count_increments(self):
        _monitoring_data["traffic_log"] = []
        _monitoring_data["error_count"] = 0
        record_request("/error", "GET", 500, 0.1)
        assert _monitoring_data["error_count"] == 1

    def test_traffic_log_truncated_at_5000(self):
        _monitoring_data["traffic_log"] = [
            {"path": "/", "method": "GET", "status_code": 200, "response_time": 0.01, "timestamp": "2024-01-01T00:00:00"}
            for _ in range(5001)
        ]
        record_request("/new", "GET", 200, 0.01)
        assert len(_monitoring_data["traffic_log"]) <= 5000


class TestAlertEdgeCases:
    def test_alerts_truncated_at_200(self):
        _monitoring_data["alerts"] = [
            {"title": f"Alert {i}", "message": "msg", "level": "info", "timestamp": "2024-01-01T00:00:00"}
            for i in range(200)
        ]
        add_alert("New Alert", "msg", "info")
        assert len(_monitoring_data["alerts"]) <= 200

    def test_add_alert_all_levels(self):
        for level in ("info", "warning", "error"):
            alert = add_alert(f"Test {level}", "msg", level)
            assert alert["level"] == level


# ── Routes ────────────────────────────────────────────────────────


class TestParseForm:
    def test_parse_simple_form(self):
        result = _parse_form("username=admin&password=secret")
        assert result["username"] == "admin"
        assert result["password"] == "secret"

    def test_parse_empty_form(self):
        result = _parse_form("")
        assert result == {}

    def test_parse_encoded_chars(self):
        result = _parse_form("name=hello+world")
        assert result["name"] == "hello world"


@pytest.mark.anyio
class TestMonitoringRoutes:
    async def test_monitoring_index_redirects_to_login(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "admin",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "test-secret",
        }):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring")
        assert resp.status_code in (302, 307)
        assert "/monitoring/login" in resp.headers.get("location", "")

    async def test_monitoring_login_page_renders(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "admin",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "test-secret",
        }):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring/login")
        assert resp.status_code == 200
        assert "Fenrir Monitoring" in resp.text

    async def test_monitoring_login_with_wrong_credentials(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "admin",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "test-secret",
        }):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring/login")
        csrf_token = ""
        for cookie in resp.headers.get_list("set-cookie"):
            if "monitoring_csrf=" in cookie:
                csrf_token = cookie.split("monitoring_csrf=")[1].split(";")[0]
        
        client.client.cookies.set("monitoring_csrf", csrf_token)
        resp = await client.post(
            "/monitoring/login",
            content=f"username=admin&password=wrong&csrf_token={csrf_token}".encode(),
        )
        assert resp.status_code == 401

    async def test_monitoring_api_health(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "sites" in data

    async def test_monitoring_api_traffic(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/traffic")
        assert resp.status_code == 200
        data = resp.json()
        assert "today" in data
        assert "yesterday" in data

    async def test_monitoring_api_alerts(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data

    async def test_monitoring_api_stats(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "traffic" in data
        assert "sites_total" in data

    async def test_monitoring_dashboard_requires_auth(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "admin",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "test-secret",
        }):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring/dashboard")
        # Should redirect to login without token
        assert resp.status_code in (302, 307)

    async def test_monitoring_api_alerts_invalid_limit(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/alerts?limit=invalid")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data

    async def test_monitoring_api_alerts_limit_clamped(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/alerts?limit=9999")
        assert resp.status_code == 200

    async def test_monitoring_api_check_missing_url(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.post(
            "/monitoring/api/check",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_monitoring_login_empty_credentials(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "admin",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "test-secret",
        }):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring/login")
        csrf_token = ""
        for cookie in resp.headers.get_list("set-cookie"):
            if "monitoring_csrf=" in cookie:
                csrf_token = cookie.split("monitoring_csrf=")[1].split(";")[0]
        
        client.client.cookies.set("monitoring_csrf", csrf_token)
        resp = await client.post(
            "/monitoring/login",
            content=f"username=&password=&csrf_token={csrf_token}".encode(),
        )
        assert resp.status_code == 401

    async def test_monitoring_logout(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, {
            "MONITORING_ENABLED": "true",
            "MONITORING_USER": "admin",
            "MONITORING_PASSWORD": "testpass",
            "MONITORING_SECRET_KEY": "test-secret",
        }):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.post("/monitoring/logout")
        assert resp.status_code in (302, 307)
        assert "/monitoring/login" in resp.headers.get("location", "")

    async def test_monitoring_api_uptime(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/uptime")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    async def test_monitoring_api_response_times(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/response-times?url=http://example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data

    async def test_monitoring_api_response_times_clamp(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/response-times?url=http://example.com&hours=999")
        assert resp.status_code == 200

    async def test_monitoring_api_hourly(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/hourly")
        assert resp.status_code == 200
        data = resp.json()
        assert "hourly" in data

    async def test_monitoring_api_hourly_clamp(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/hourly?hours=999")
        assert resp.status_code == 200

    async def test_monitoring_api_summary(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/api/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "overview" in data
        assert "sites" in data
        assert "hourly_traffic" in data

    async def test_monitoring_login_success_sets_cookie(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring/login")
        csrf_token = ""
        for cookie in resp.headers.get_list("set-cookie"):
            if "monitoring_csrf=" in cookie:
                csrf_token = cookie.split("monitoring_csrf=")[1].split(";")[0]

        client.client.cookies.set("monitoring_csrf", csrf_token)
        resp = await client.post(
            "/monitoring/login",
            content=f"username=admin&password=testpass&csrf_token={csrf_token}".encode(),
        )
        assert resp.status_code == 302
        assert "/monitoring/dashboard" in resp.headers.get("location", "")

    async def test_monitoring_login_csrf_mismatch(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring/login")
        csrf_token = ""
        for cookie in resp.headers.get_list("set-cookie"):
            if "monitoring_csrf=" in cookie:
                csrf_token = cookie.split("monitoring_csrf=")[1].split(";")[0]

        client.client.cookies.set("monitoring_csrf", csrf_token)
        resp = await client.post(
            "/monitoring/login",
            content=f"username=admin&password=testpass&csrf_token=wrong_token".encode(),
        )
        assert resp.status_code == 403

    async def test_monitoring_dashboard_renders_with_auth(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.get("/monitoring/dashboard")
        assert resp.status_code == 200
        assert "Fenrir" in resp.text

    async def test_monitoring_api_check_valid_url(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.post(
            "/monitoring/api/check",
            content=json.dumps({"url": "http://localhost:8000"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "http://localhost:8000"

    async def test_monitoring_api_check_url_not_in_sites(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        await _login(client)
        resp = await client.post(
            "/monitoring/api/check",
            content=json.dumps({"url": "http://evil.com"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 403

    async def test_monitoring_login_page_sets_csrf_cookie(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.get("/monitoring/login")
        assert resp.status_code == 200
        csrf_cookie_found = False
        for cookie in resp.headers.get_list("set-cookie"):
            if "monitoring_csrf=" in cookie:
                csrf_cookie_found = True
                assert "SameSite=Lax" in cookie
                assert "Max-Age=300" in cookie
        assert csrf_cookie_found

    async def test_monitoring_api_check_unauthenticated(self, app):
        from fenrir.monitoring.core import init_monitoring
        with patch.dict(os.environ, MONITORING_ENV):
            init_monitoring(app)

        client = app.test_client()
        resp = await client.post(
            "/monitoring/api/check",
            content=json.dumps({"url": "http://localhost:8000"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401
