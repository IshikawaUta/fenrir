"""Fenrir Monitoring - Built-in health check and traffic analysis dashboard."""
import os
import json
import time
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path
from collections import defaultdict


# In-memory storage for monitoring data
_monitoring_data: Dict[str, Any] = {
    "health_checks": {},
    "health_history": {},
    "traffic_log": [],
    "alerts": [],
    "sites": [],
    "start_time": None,
    "request_count": 0,
    "error_count": 0,
}

_DEFAULT_SECRET = None


def _get_default_secret() -> str:
    """Generate a random secret key if none is configured."""
    global _DEFAULT_SECRET
    if _DEFAULT_SECRET is None:
        import secrets
        _DEFAULT_SECRET = secrets.token_hex(32)
        import logging
        logging.warning(
            "MONITORING_SECRET_KEY not set. Using random key (sessions will not survive restart). "
            "Set MONITORING_SECRET_KEY in your .env file for persistent sessions."
        )
    return _DEFAULT_SECRET


def _get_data_dir() -> Path:
    """Get the data directory for persistent storage."""
    data_dir = Path(os.getcwd()) / ".fenrir_monitoring"
    try:
        data_dir.mkdir(exist_ok=True)
    except OSError as e:
        import logging
        logging.warning(f"Cannot create monitoring data directory {data_dir}: {e}")
    return data_dir


def _load_config() -> Dict[str, Any]:
    """Load monitoring configuration from environment variables."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.getcwd(), ".env"))
    except ImportError:
        pass

    return {
        "enabled": os.getenv("MONITORING_ENABLED", "false").lower() == "true",
        "user": os.getenv("MONITORING_USER", "admin"),
        "password_hash": None,
        "secret_key": os.getenv("MONITORING_SECRET_KEY") or _get_default_secret(),
        "sites": [
            s.strip()
            for s in os.getenv("MONITORING_SITES", "http://localhost:8000").split(",")
            if s.strip()
        ],
        "check_interval": int(os.getenv("MONITORING_CHECK_INTERVAL", "60")),
    }


def _hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify password against bcrypt hash."""
    import bcrypt
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _generate_token(user: str, secret_key: str, expires_in: int = 86400) -> str:
    """Generate a session token with expiration (default 24 hours)."""
    expires_at = int(time.time()) + expires_in
    payload = f"{user}:{expires_at}:{secret_key}"
    token_hash = hashlib.sha256(payload.encode()).hexdigest()
    return f"{token_hash}:{expires_at}"


def _validate_token(token: str, user: str, secret_key: str) -> bool:
    """Validate a session token, checking expiration."""
    if not token or ":" not in token:
        return False
    try:
        token_hash, expires_at_str = token.rsplit(":", 1)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        return False
    if int(time.time()) > expires_at:
        return False
    expected_payload = f"{user}:{expires_at}:{secret_key}"
    expected_hash = hashlib.sha256(expected_payload.encode()).hexdigest()
    return hmac.compare_digest(token_hash, expected_hash)


def _save_data():
    """Save monitoring data to disk."""
    data_dir = _get_data_dir()
    data_file = data_dir / "monitoring_data.json"
    
    serializable = {
        "traffic_log": _monitoring_data["traffic_log"][-2000:],
        "alerts": _monitoring_data["alerts"][-200:],
        "sites": _monitoring_data["sites"],
        "health_history": {
            k: v[-100:] for k, v in _monitoring_data.get("health_history", {}).items()
        },
        "request_count": _monitoring_data.get("request_count", 0),
        "error_count": _monitoring_data.get("error_count", 0),
    }
    
    try:
        with open(data_file, "w") as f:
            json.dump(serializable, f, indent=2, default=str)
    except Exception:
        pass


def _load_data():
    """Load monitoring data from disk."""
    data_dir = _get_data_dir()
    data_file = data_dir / "monitoring_data.json"
    
    if data_file.exists():
        try:
            with open(data_file) as f:
                data = json.load(f)
            _monitoring_data["traffic_log"] = data.get("traffic_log", [])
            _monitoring_data["alerts"] = data.get("alerts", [])
            _monitoring_data["health_history"] = data.get("health_history", {})
            _monitoring_data["request_count"] = data.get("request_count", 0)
            _monitoring_data["error_count"] = data.get("error_count", 0)
        except Exception:
            pass


def init_monitoring(app: Any, config: Optional[Dict[str, Any]] = None):
    """Initialize the monitoring system and register routes on the app."""
    from fenrir.monitoring.routes import register_monitoring_routes
    
    env_config = _load_config()
    
    if config is None:
        config = env_config
    else:
        for key in ("user", "secret_key", "sites", "check_interval"):
            if key not in config or config[key] is None:
                config[key] = env_config[key]
            elif key == "sites" and not config[key]:
                config[key] = env_config[key]
    
    enabled = config.get("enabled", False)
    app.config["MONITORING_ENABLED"] = enabled
    app.config["MONITORING_USER"] = config.get("user", "admin")
    app.config["MONITORING_SECRET_KEY"] = config.get("secret_key") or _get_default_secret()
    app.config["MONITORING_SITES"] = config.get("sites", [])
    app.config["MONITORING_CHECK_INTERVAL"] = config.get("check_interval", 60)
    
    password = os.getenv("MONITORING_PASSWORD", "changeme")
    allow_default = os.getenv("MONITORING_ALLOW_DEFAULT_PASSWORD", "").lower() == "true"
    if password == "changeme" and enabled and not allow_default:
        raise ValueError(
            "MONITORING_PASSWORD must be set when MONITORING_ENABLED=true. "
            "Set MONITORING_PASSWORD in your .env file, or set "
            "MONITORING_ALLOW_DEFAULT_PASSWORD=true to override (not recommended for production)."
        )
    if password == "changeme":
        import logging
        logging.warning(
            "MONITORING_PASSWORD not set. Using default 'changeme'. "
            "Set MONITORING_PASSWORD in your .env file for production."
        )
    app.config["MONITORING_PASSWORD_HASH"] = _hash_password(password)
    
    if not enabled:
        return
    
    _monitoring_data["sites"] = config.get("sites", [])
    _monitoring_data["start_time"] = datetime.now().isoformat()
    
    _load_data()
    register_monitoring_routes(app)


def record_request(path: str, method: str, status_code: int, response_time: float):
    """Record a request for traffic analysis."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "path": path,
        "method": method,
        "status_code": status_code,
        "response_time": response_time,
    }
    _monitoring_data["traffic_log"].append(entry)
    _monitoring_data["request_count"] += 1
    
    if status_code >= 400:
        _monitoring_data["error_count"] += 1
    
    if len(_monitoring_data["traffic_log"]) > 5000:
        _monitoring_data["traffic_log"] = _monitoring_data["traffic_log"][-5000:]
    
    if len(_monitoring_data["traffic_log"]) % 100 == 0:
        _save_data()


def check_site_health(url: str) -> Dict[str, Any]:
    """Check the health of a single site (synchronous, use in thread for async)."""
    import urllib.request
    import urllib.error
    
    result = {
        "url": url,
        "status": "unknown",
        "status_code": None,
        "response_time": None,
        "checked_at": datetime.now().isoformat(),
        "error": None,
    }
    
    try:
        start = time.time()
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Fenrir-Monitoring/1.0")
        
        with urllib.request.urlopen(req, timeout=10) as response:
            elapsed = time.time() - start
            result["status_code"] = response.status
            result["response_time"] = round(elapsed * 1000, 2)
            result["status"] = "healthy" if 200 <= response.status < 400 else "degraded"
    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["status"] = "degraded"
        result["error"] = str(e)
    except Exception as e:
        result["status"] = "down"
        result["error"] = str(e)
    
    _monitoring_data["health_checks"][url] = result
    
    if url not in _monitoring_data["health_history"]:
        _monitoring_data["health_history"][url] = []
    _monitoring_data["health_history"][url].append({
        "timestamp": result["checked_at"],
        "status": result["status"],
        "status_code": result["status_code"],
        "response_time": result["response_time"],
    })
    if len(_monitoring_data["health_history"][url]) > 100:
        _monitoring_data["health_history"][url] = _monitoring_data["health_history"][url][-100:]
    
    return result


async def check_site_health_async(url: str) -> Dict[str, Any]:
    """Check the health of a single site (async wrapper using thread pool)."""
    from fenrir.compat import to_thread
    return await to_thread(check_site_health, url)


def get_uptime_stats() -> Dict[str, Any]:
    """Get uptime statistics for all monitored sites."""
    stats = {}
    for url, checks in _monitoring_data.get("health_history", {}).items():
        if not checks:
            stats[url] = {"percentage": 0, "total_checks": 0, "healthy_checks": 0}
            continue
        
        total = len(checks)
        healthy = sum(1 for c in checks if c.get("status") == "healthy")
        percentage = round((healthy / total) * 100, 2) if total > 0 else 0
        
        stats[url] = {
            "percentage": percentage,
            "total_checks": total,
            "healthy_checks": healthy,
            "last_check": checks[-1].get("timestamp") if checks else None,
            "current_status": checks[-1].get("status") if checks else "unknown",
        }
    return stats


def get_response_time_history(url: str, hours: int = 24) -> List[Dict[str, Any]]:
    """Get response time history for a specific site."""
    history = _monitoring_data.get("health_history", {}).get(url, [])
    cutoff = datetime.now() - timedelta(hours=hours)
    
    result = []
    for entry in history:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= cutoff:
                result.append({
                    "timestamp": entry["timestamp"],
                    "response_time": entry.get("response_time"),
                    "status": entry.get("status"),
                })
        except (ValueError, KeyError):
            continue
    return result


def get_traffic_stats() -> Dict[str, Any]:
    """Get traffic statistics for the current day."""
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    
    today_requests = []
    yesterday_requests = []
    
    for entry in _monitoring_data["traffic_log"]:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= today_start:
                today_requests.append(entry)
            elif ts >= yesterday_start:
                yesterday_requests.append(entry)
        except (ValueError, KeyError):
            continue
    
    def calc_stats(requests):
        if not requests:
            return {
                "total": 0,
                "avg_response_time": 0,
                "error_rate": 0,
                "status_codes": {},
                "paths": {},
                "methods": {},
            }
        
        total = len(requests)
        avg_rt = sum(r.get("response_time", 0) for r in requests) / total
        errors = sum(1 for r in requests if r.get("status_code", 200) >= 400)
        
        status_codes = {}
        paths = {}
        methods = {}
        
        for r in requests:
            sc = str(r.get("status_code", 0))
            status_codes[sc] = status_codes.get(sc, 0) + 1
            
            path = r.get("path", "/")
            paths[path] = paths.get(path, 0) + 1
            
            method = r.get("method", "GET")
            methods[method] = methods.get(method, 0) + 1
        
        return {
            "total": total,
            "avg_response_time": round(avg_rt, 2),
            "error_rate": round((errors / total) * 100, 2),
            "status_codes": status_codes,
            "paths": dict(sorted(paths.items(), key=lambda x: -x[1])[:10]),
            "methods": methods,
        }
    
    today_stats = calc_stats(today_requests)
    yesterday_stats = calc_stats(yesterday_requests)
    
    change_pct = 0
    if yesterday_stats["total"] > 0:
        change_pct = round(
            ((today_stats["total"] - yesterday_stats["total"]) / yesterday_stats["total"]) * 100, 2
        )
    
    return {
        "today": today_stats,
        "yesterday": yesterday_stats,
        "change_percentage": change_pct,
        "uptime_start": _monitoring_data.get("start_time"),
    }


def get_hourly_traffic(hours: int = 24) -> List[Dict[str, Any]]:
    """Get hourly traffic aggregation for the last N hours."""
    now = datetime.now()
    hourly = []
    
    for i in range(hours - 1, -1, -1):
        hour_start = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)
        
        count = 0
        errors = 0
        total_rt = 0
        
        for entry in _monitoring_data["traffic_log"]:
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                if hour_start <= ts < hour_end:
                    count += 1
                    if entry.get("status_code", 200) >= 400:
                        errors += 1
                    total_rt += entry.get("response_time", 0)
            except (ValueError, KeyError):
                continue
        
        avg_rt = round(total_rt / count, 2) if count > 0 else 0
        
        hourly.append({
            "hour": hour_start.strftime("%H:00"),
            "timestamp": hour_start.isoformat(),
            "requests": count,
            "errors": errors,
            "avg_response_time": avg_rt,
        })
    
    return hourly


def get_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent alerts."""
    return list(reversed(_monitoring_data["alerts"][-limit:]))


def add_alert(title: str, message: str, level: str = "info"):
    """Add an alert to the monitoring system."""
    alert = {
        "timestamp": datetime.now().isoformat(),
        "title": title,
        "message": message,
        "level": level,
    }
    _monitoring_data["alerts"].append(alert)
    
    if len(_monitoring_data["alerts"]) > 200:
        _monitoring_data["alerts"] = _monitoring_data["alerts"][-200:]
    
    _save_data()
    return alert


def get_summary() -> Dict[str, Any]:
    """Get a comprehensive summary of all monitoring data."""
    uptime = get_uptime_stats()
    traffic = get_traffic_stats()
    hourly = get_hourly_traffic(24)
    
    sites_status = []
    for url, check in _monitoring_data.get("health_checks", {}).items():
        sites_status.append({
            "url": url,
            "status": check.get("status", "unknown"),
            "response_time": check.get("response_time"),
            "last_check": check.get("checked_at"),
            "uptime": uptime.get(url, {}).get("percentage", 0),
        })
    
    return {
        "overview": {
            "total_requests": _monitoring_data.get("request_count", 0),
            "total_errors": _monitoring_data.get("error_count", 0),
            "error_rate": round(
                (_monitoring_data.get("error_count", 0) / max(_monitoring_data.get("request_count", 1), 1)) * 100, 2
            ),
            "sites_monitored": len(_monitoring_data.get("sites", [])),
            "sites_healthy": sum(1 for s in sites_status if s["status"] == "healthy"),
            "uptime_start": _monitoring_data.get("start_time"),
        },
        "sites": sites_status,
        "traffic": traffic,
        "hourly_traffic": hourly,
        "uptime": uptime,
        "alerts": get_alerts(10),
    }
