"""Fenrir Features - Easy setup for built-in monitoring."""
import os
from typing import Any


def init_fenrir_monitoring(app: Any, **kwargs):
    """Initialize the Fenrir monitoring dashboard.

    Usage in app.py:
        from fenrir.features import init_fenrir_monitoring
        init_fenrir_monitoring(app)

    Environment variables:
        MONITORING_ENABLED=true
        MONITORING_USER=admin
        MONITORING_PASSWORD=changeme
        MONITORING_SECRET_KEY=<random-secret>
        MONITORING_SITES=http://localhost:8000,https://example.com
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.getcwd(), ".env"))
    except ImportError:
        pass

    enabled = os.getenv("MONITORING_ENABLED", "false").lower() == "true"
    if not enabled and "enabled" not in kwargs:
        return

    from fenrir.monitoring.core import init_monitoring

    config = kwargs.get("config") or {}
    if "enabled" in kwargs:
        config["enabled"] = kwargs["enabled"]

    init_monitoring(app, config or None)

    # Only add request recording middleware if monitoring is enabled
    if not app.config.get("MONITORING_ENABLED"):
        return

    # Add request recording middleware
    @app.after_request
    async def _monitoring_record(req, resp):
        import time

        from fenrir.monitoring.core import record_request

        start_time = getattr(req, "_monitoring_start", None)
        if start_time:
            elapsed = time.time() - start_time
            record_request(
                path=req.path,
                method=req.method,
                status_code=resp.status if hasattr(resp, "status") else 200,
                response_time=round(elapsed * 1000, 2),
            )
        return resp

    @app.before_request
    async def _monitoring_timer(req):
        import time
        req._monitoring_start = time.time()
