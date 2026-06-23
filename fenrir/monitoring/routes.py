"""Monitoring routes - login, dashboard, health checks, traffic analysis."""
import os
import html
import hmac
from datetime import datetime
from typing import Any

from fenrir import render_template, HTMLResponse, JSONResponse, redirect
from fenrir.monitoring.core import (
    _monitoring_data,
    _generate_token,
    _verify_password,
    check_site_health,
    check_site_health_async,
    get_traffic_stats,
    get_alerts,
    add_alert,
    _save_data,
    get_uptime_stats,
    get_response_time_history,
    get_hourly_traffic,
    get_summary,
)

from fenrir.json import json_loads


def register_monitoring_routes(app: Any):
    """Register all monitoring routes on the app."""
    prefix = "/monitoring"

    def _check_token(token: str) -> bool:
        """Validate the monitoring token."""
        if not token:
            return False
        from fenrir.monitoring.core import _validate_token
        secret_key = app.config.get("MONITORING_SECRET_KEY", "")
        user = app.config.get("MONITORING_USER", "admin")
        return _validate_token(token, user, secret_key)

    @app.get(prefix)
    async def monitoring_index():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return redirect(f"{prefix}/login")
        return redirect(f"{prefix}/dashboard")

    @app.get(f"{prefix}/login")
    async def monitoring_login_page():
        import secrets
        csrf_token = secrets.token_hex(32)
        from fenrir.response import Response
        resp = Response(
            body=_render_login_page(csrf_token=csrf_token),
            status=200,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Set-Cookie": f"monitoring_csrf={csrf_token}; Path=/; SameSite=Lax; Max-Age=300",
            },
        )
        return resp

    @app.post(f"{prefix}/login")
    async def monitoring_login():
        from fenrir.context import request
        
        body = request.body
        try:
            body_str = body.decode("utf-8", errors="replace") if body else ""
        except Exception:
            body_str = ""
        form_data = _parse_form(body_str)
        
        username = form_data.get("username", "")
        password = form_data.get("password", "")
        csrf_form = form_data.get("csrf_token", "")
        
        csrf_cookie = request.cookies.get("monitoring_csrf", "")
        if not csrf_form or not csrf_cookie or not hmac.compare_digest(csrf_form, csrf_cookie):
            import secrets
            new_csrf = secrets.token_hex(32)
            from fenrir.response import Response
            resp = Response(
                body=_render_login_page(error="Invalid request. Please try again.", csrf_token=new_csrf),
                status=403,
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": f"monitoring_csrf={new_csrf}; Path=/; SameSite=Lax; Max-Age=300",
                },
            )
            return resp
        
        config_user = app.config.get("MONITORING_USER", "admin")
        config_hash = app.config.get("MONITORING_PASSWORD_HASH", "")
        
        if username == config_user and _verify_password(password, config_hash):
            token = _generate_token(username, app.config.get("MONITORING_SECRET_KEY", ""))
            secure_flag = "; Secure" if os.getenv("MONITORING_SECURE_COOKIES", "").lower() == "true" else ""
            from fenrir.response import Response
            resp = Response(
                body="",
                status=302,
                headers={
                    "Location": f"{prefix}/dashboard",
                    "Set-Cookie": f"monitoring_token={token}; Path={prefix}; HttpOnly; SameSite=Lax{secure_flag}",
                },
            )
            return resp
        
        import secrets
        new_csrf = secrets.token_hex(32)
        from fenrir.response import Response
        resp = Response(
            body=_render_login_page(error="Invalid credentials", csrf_token=new_csrf),
            status=401,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Set-Cookie": f"monitoring_csrf={new_csrf}; Path=/; SameSite=Lax; Max-Age=300",
            },
        )
        return resp

    @app.post(f"{prefix}/logout")
    async def monitoring_logout():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return redirect(f"{prefix}/login")
        
        body = request.body
        try:
            body_str = body.decode("utf-8", errors="replace") if body else ""
        except Exception:
            body_str = ""
        form_data = _parse_form(body_str)
        csrf_form = form_data.get("csrf_token", "")
        csrf_cookie = request.cookies.get("monitoring_csrf", "")
        if not csrf_form or not csrf_cookie or not hmac.compare_digest(csrf_form, csrf_cookie):
            return redirect(f"{prefix}/dashboard")
        
        from fenrir.response import Response
        resp = Response(
            body="",
            status=302,
            headers={
                "Location": f"{prefix}/login",
                "Set-Cookie": f"monitoring_token=; Path={prefix}; HttpOnly; Max-Age=0",
            },
        )
        return resp

    @app.get(f"{prefix}/dashboard")
    async def monitoring_dashboard():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return redirect(f"{prefix}/login")
        
        traffic = get_traffic_stats()
        alerts = get_alerts(20)
        sites = _monitoring_data.get("sites", [])
        
        health_results = []
        for site in sites:
            hc = _monitoring_data.get("health_checks", {}).get(site)
            if hc:
                health_results.append(hc)
            else:
                health_results.append({
                    "url": site,
                    "status": "pending",
                    "status_code": None,
                    "response_time": None,
                    "checked_at": None,
                })
        
        return HTMLResponse(_render_dashboard_page(traffic, health_results, alerts))

    @app.get(f"{prefix}/api/health")
    async def monitoring_api_health():
        import asyncio
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        sites = _monitoring_data.get("sites", [])
        results = await asyncio.gather(*[check_site_health_async(site, sites) for site in sites])
        _save_data()
        return JSONResponse({"sites": list(results)})

    @app.get(f"{prefix}/api/traffic")
    async def monitoring_api_traffic():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        stats = get_traffic_stats()
        return JSONResponse(stats)

    @app.get(f"{prefix}/api/alerts")
    async def monitoring_api_alerts():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        try:
            limit = int(request.args.get("limit", "50"))
            limit = max(1, min(limit, 500))
        except (ValueError, TypeError):
            limit = 50
        alerts = get_alerts(limit)
        return JSONResponse({"alerts": alerts})

    @app.post(f"{prefix}/api/check")
    async def monitoring_api_check():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        body = request.body
        try:
            body_str = body.decode("utf-8", errors="replace") if body else ""
        except Exception:
            body_str = ""
        data = _parse_json(body_str)
        url = data.get("url")
        
        if not url:
            return JSONResponse({"error": "url is required"}, status=400)
        
        allowed_sites = _monitoring_data.get("sites", [])
        if url not in allowed_sites:
            return JSONResponse({"error": "url not in monitored sites"}, status=403)
        
        result = await check_site_health_async(url, allowed_sites)
        _save_data()
        return JSONResponse(result)

    @app.get(f"{prefix}/api/stats")
    async def monitoring_api_stats():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        traffic = get_traffic_stats()
        sites_count = len(_monitoring_data.get("sites", []))
        healthy = sum(
            1 for s in _monitoring_data.get("health_checks", {}).values()
            if s.get("status") == "healthy"
        )
        
        return JSONResponse({
            "traffic": traffic,
            "sites_total": sites_count,
            "sites_healthy": healthy,
            "uptime_start": _monitoring_data.get("start_time"),
        })

    @app.get(f"{prefix}/api/uptime")
    async def monitoring_api_uptime():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        uptime = get_uptime_stats()
        return JSONResponse(uptime)

    @app.get(f"{prefix}/api/response-times")
    async def monitoring_api_response_times():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        try:
            hours = int(request.args.get("hours", "24"))
            hours = max(1, min(hours, 168))
        except (ValueError, TypeError):
            hours = 24
        url = request.args.get("url", "")
        if not url:
            all_history = []
            for site_url in _monitoring_data.get("sites", []):
                all_history.extend(get_response_time_history(site_url, hours))
            return JSONResponse({"history": all_history})
        history = get_response_time_history(url, hours)
        return JSONResponse({"history": history})

    @app.get(f"{prefix}/api/hourly")
    async def monitoring_api_hourly():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        try:
            days = int(request.args.get("days", "7"))
            days = max(1, min(days, 30))
        except (ValueError, TypeError):
            days = 7
        hourly = get_hourly_traffic(days * 24)
        return JSONResponse({"hourly": hourly})

    @app.get(f"{prefix}/api/summary")
    async def monitoring_api_summary():
        from fenrir.context import request
        token = request.cookies.get("monitoring_token")
        if not _check_token(token):
            return JSONResponse({"error": "unauthorized"}, status=401)
        summary = get_summary()
        return JSONResponse(summary)


def _parse_form(body: str) -> dict:
    """Parse URL-encoded form data."""
    from urllib.parse import unquote_plus
    result = {}
    for pair in body.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[unquote_plus(key)] = unquote_plus(value)
    return result


def _parse_json(body: str) -> dict:
    """Parse JSON body."""
    try:
        return json_loads(body)
    except Exception:
        return {}


def _render_login_page(error: str = None, csrf_token: str = "") -> str:
    """Render the monitoring login page."""
    error_html = ""
    if error:
        error_html = f'<div class="error">{html.escape(error)}</div>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fenrir Monitoring - Login</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.8);
            --border: rgba(99, 102, 241, 0.2);
            --text: #f3f4f6;
            --text-secondary: #9ca3af;
            --primary: #6366f1;
            --primary-hover: #818cf8;
            --accent-green: #10b981;
            --accent-red: #ef4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            background-image:
                radial-gradient(circle at 20% 50%, rgba(99, 102, 241, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(168, 85, 247, 0.06) 0%, transparent 50%);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .login-card {{
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 48px 40px;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
        }}
        .login-header {{
            text-align: center;
            margin-bottom: 36px;
        }}
        .login-header h1 {{
            font-size: 1.6rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff 30%, #c7d2fe 100%);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        .login-header p {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        .form-group label {{
            display: block;
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}
        .form-group input {{
            width: 100%;
            padding: 12px 16px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: var(--text);
            font-size: 0.95rem;
            font-family: 'Inter', sans-serif;
            transition: border-color 0.2s;
        }}
        .form-group input:focus {{
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
        }}
        .btn {{
            width: 100%;
            padding: 13px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 0.95rem;
            font-weight: 600;
            font-family: 'Inter', sans-serif;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
        }}
        .btn:hover {{
            background: var(--primary-hover);
            transform: translateY(-1px);
        }}
        .btn:active {{
            transform: translateY(0);
        }}
        .error {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: var(--accent-red);
            padding: 12px;
            border-radius: 10px;
            font-size: 0.85rem;
            margin-bottom: 20px;
            text-align: center;
        }}
        .footer {{
            text-align: center;
            margin-top: 24px;
            font-size: 0.8rem;
            color: rgba(255, 255, 255, 0.3);
        }}
    </style>
</head>
<body>
    <div class="login-card">
        <div class="login-header">
            <h1>Fenrir Monitoring</h1>
            <p>Sign in to access the dashboard</p>
        </div>
        {error_html}
        <form method="POST" action="/monitoring/login">
            <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autocomplete="username" autofocus>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="btn">Sign In</button>
        </form>
        <div class="footer">Powered by Fenrir Framework</div>
    </div>
</body>
</html>"""


def _render_dashboard_page(traffic: dict, health_results: list, alerts: list) -> str:
    """Render the monitoring dashboard page."""
    today = traffic.get("today", {})
    yesterday = traffic.get("yesterday", {})
    change_pct = traffic.get("change_percentage", 0)
    
    change_class = "positive" if change_pct >= 0 else "negative"
    change_icon = "+" if change_pct >= 0 else ""
    
    uptime = get_uptime_stats()
    if uptime:
        total_checks = sum(s.get("total_checks", 0) for s in uptime.values())
        healthy_checks = sum(s.get("healthy_checks", 0) for s in uptime.values())
        uptime_pct = round((healthy_checks / total_checks) * 100, 2) if total_checks > 0 else 100.0
    else:
        uptime_pct = 100.0
    uptime_color = "var(--green)" if uptime_pct >= 99 else "var(--yellow)" if uptime_pct >= 95 else "var(--red)"
    
    health_cards = ""
    for site in health_results:
        status = site.get("status", "unknown")
        status_class = {"healthy": "ok", "degraded": "warn", "down": "error"}.get(status, "unknown")
        rt = site.get("response_time")
        rt_display = f"{rt}ms" if rt is not None else "N/A"
        code = site.get("status_code") or "-"
        
        health_cards += f"""
        <div class="health-card {status_class}">
            <div class="health-status">
                <span class="status-dot {status_class}"></span>
                <span class="status-text">{html.escape(status.upper())}</span>
            </div>
            <div class="health-url">{html.escape(site['url'])}</div>
            <div class="health-meta">
                <span>HTTP {code}</span>
                <span>{rt_display}</span>
            </div>
        </div>"""
    
    alerts_html = ""
    for alert in alerts[:10]:
        level = alert.get("level", "info")
        level_class = {"warning": "warn", "error": "error", "info": "ok"}.get(level, "ok")
        ts = alert.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            ts_display = dt.strftime("%H:%M:%S")
        except Exception:
            ts_display = ts[:10]
        
        alerts_html += f"""
        <div class="alert-item {level_class}">
            <span class="alert-time">{ts_display}</span>
            <span class="alert-title">{html.escape(alert.get('title', ''))}</span>
            <span class="alert-msg">{html.escape(alert.get('message', ''))}</span>
        </div>"""
    
    if not alerts_html:
        alerts_html = '<div class="alert-item ok"><span class="alert-msg">No recent alerts</span></div>'
    
    status_codes_html = ""
    for code, count in sorted(today.get("status_codes", {}).items()):
        bar_width = min(count * 100 / max(today.get("total", 1), 1), 100)
        status_codes_html += f"""
        <div class="bar-row">
            <span class="bar-label">{html.escape(str(code))}</span>
            <div class="bar-track"><div class="bar-fill" style="width:{bar_width}%"></div></div>
            <span class="bar-value">{count}</span>
        </div>"""
    
    top_paths_html = ""
    for path, count in list(today.get("paths", {}).items())[:5]:
        top_paths_html += f"""
        <div class="path-row">
            <span class="path-name">{html.escape(path)}</span>
            <span class="path-count">{count}</span>
        </div>"""
    
    methods_html = ""
    for method, count in today.get("methods", {}).items():
        methods_html += f'<span class="method-badge">{html.escape(method)} {count}</span>'
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fenrir Monitoring - Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.7);
            --border: rgba(99, 102, 241, 0.15);
            --border-hover: rgba(139, 92, 246, 0.4);
            --text: #f3f4f6;
            --text-secondary: #9ca3af;
            --primary: #6366f1;
            --green: #10b981;
            --yellow: #f59e0b;
            --red: #ef4444;
            --blue: #3b82f6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            background-image:
                radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.06) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(168, 85, 247, 0.06) 0%, transparent 40%);
            color: var(--text);
            min-height: 100vh;
        }}
        .navbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 32px;
            border-bottom: 1px solid var(--border);
            background: rgba(11, 15, 25, 0.9);
            backdrop-filter: blur(12px);
            position: sticky;
            top: 0;
            z-index: 100;
        }}
        .navbar-brand {{
            font-size: 1.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff 30%, #c7d2fe 100%);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .navbar-brand span {{
            font-weight: 400;
            font-size: 0.85rem;
            -webkit-text-fill-color: var(--text-secondary);
        }}
        .navbar-actions a {{
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.85rem;
            margin-left: 16px;
            transition: color 0.2s;
        }}
        .navbar-actions a:hover {{ color: var(--text); }}
        .container {{
            max-width: 1280px;
            margin: 0 auto;
            padding: 32px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }}
        .stat-card {{
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            transition: border-color 0.3s;
        }}
        .stat-card:hover {{ border-color: var(--border-hover); }}
        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
        }}
        .stat-change {{
            font-size: 0.8rem;
            margin-top: 8px;
        }}
        .stat-change.positive {{ color: var(--green); }}
        .stat-change.negative {{ color: var(--red); }}
        .section {{
            margin-bottom: 32px;
        }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .section-title {{
            font-size: 1.1rem;
            font-weight: 600;
        }}
        .health-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 16px;
        }}
        .health-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            transition: border-color 0.3s;
        }}
        .health-card:hover {{ border-color: var(--border-hover); }}
        .health-card.ok {{ border-left: 3px solid var(--green); }}
        .health-card.warn {{ border-left: 3px solid var(--yellow); }}
        .health-card.error {{ border-left: 3px solid var(--red); }}
        .health-card.unknown {{ border-left: 3px solid var(--text-secondary); }}
        .health-status {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        .status-dot.ok {{ background: var(--green); box-shadow: 0 0 8px var(--green); }}
        .status-dot.warn {{ background: var(--yellow); box-shadow: 0 0 8px var(--yellow); }}
        .status-dot.error {{ background: var(--red); box-shadow: 0 0 8px var(--red); }}
        .status-dot.unknown {{ background: var(--text-secondary); }}
        .status-text {{ font-size: 0.75rem; font-weight: 600; letter-spacing: 0.5px; }}
        .health-url {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 12px;
            word-break: break-all;
        }}
        .health-meta {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}
        .panel {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 24px;
        }}
        .bar-row {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }}
        .bar-label {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            width: 40px;
            color: var(--text-secondary);
        }}
        .bar-track {{
            flex: 1;
            height: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            overflow: hidden;
        }}
        .bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--blue));
            border-radius: 4px;
            transition: width 0.5s;
        }}
        .bar-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            width: 50px;
            text-align: right;
            color: var(--text-secondary);
        }}
        .path-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 0.85rem;
        }}
        .path-name {{
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-secondary);
        }}
        .path-count {{
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
        }}
        .method-badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 8px;
            margin-bottom: 8px;
            background: rgba(99, 102, 241, 0.15);
            color: var(--primary);
        }}
        .alert-item {{
            display: flex;
            gap: 12px;
            align-items: center;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 0.85rem;
        }}
        .alert-item.ok {{ background: rgba(16, 185, 129, 0.08); }}
        .alert-item.warn {{ background: rgba(245, 158, 11, 0.08); }}
        .alert-item.error {{ background: rgba(239, 68, 68, 0.08); }}
        .alert-time {{
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-secondary);
            font-size: 0.8rem;
        }}
        .alert-title {{ font-weight: 600; }}
        .alert-msg {{ color: var(--text-secondary); }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 768px) {{
            .container {{ padding: 16px; }}
            .stats-grid {{ grid-template-columns: 1fr; }}
            .grid-2 {{ grid-template-columns: 1fr; }}
            .health-grid {{ grid-template-columns: 1fr; }}
            .navbar {{ padding: 12px 16px; }}
        }}
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="navbar-brand">Fenrir <span>Monitoring</span></div>
        <div class="navbar-actions">
            <a href="/monitoring/dashboard">Dashboard</a>
            <a href="/monitoring/api/stats">Stats</a>
            <a href="/monitoring/api/summary">Summary</a>
            <form method="POST" action="/monitoring/logout" style="display:inline">
                <input type="hidden" name="csrf_token" id="csrf-token-logout" value="">
                <button type="submit" style="background:none;border:none;color:var(--text-secondary);cursor:pointer;margin-left:16px;text-decoration:underline;">Logout</button>
            </form>
        </div>
    </nav>

    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Requests (Today)</div>
                <div class="stat-value">{today.get('total', 0)}</div>
                <div class="stat-change {change_class}">{change_icon}{change_pct}% vs yesterday</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Response Time</div>
                <div class="stat-value">{today.get('avg_response_time', 0)}<span style="font-size:0.9rem">ms</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Uptime</div>
                <div class="stat-value" style="color:{uptime_color}">{uptime_pct}%</div>
                <div class="stat-change positive">Since {str(_monitoring_data.get('start_time') or 'N/A')[:10]}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Error Rate</div>
                <div class="stat-value" style="color: {'var(--red)' if today.get('error_rate', 0) > 5 else 'var(--green)'}">{today.get('error_rate', 0)}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Yesterday</div>
                <div class="stat-value">{yesterday.get('total', 0)}</div>
            </div>
        </div>

        <div class="section">
            <div class="section-header">
                <div class="section-title">Site Health</div>
                <button onclick="refreshHealth()" style="background:var(--primary);border:none;color:white;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:0.8rem;">Refresh</button>
            </div>
            <div class="health-grid" id="health-grid">
                {health_cards}
            </div>
        </div>

        <div class="grid-2">
            <div class="section">
                <div class="section-title" style="margin-bottom:16px">Status Codes</div>
                <div class="panel">
                    {status_codes_html if status_codes_html else '<div style="color:var(--text-secondary);font-size:0.85rem;">No data yet</div>'}
                </div>
            </div>
            <div class="section">
                <div class="section-title" style="margin-bottom:16px">Top Paths</div>
                <div class="panel">
                    {top_paths_html if top_paths_html else '<div style="color:var(--text-secondary);font-size:0.85rem;">No data yet</div>'}
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title" style="margin-bottom:16px">HTTP Methods</div>
            <div class="panel" style="padding:16px">
                {methods_html if methods_html else '<span style="color:var(--text-secondary);font-size:0.85rem;">No data yet</span>'}
            </div>
        </div>

        <div class="section">
            <div class="section-title" style="margin-bottom:16px">Recent Alerts</div>
            <div class="panel">
                {alerts_html}
            </div>
        </div>
    </div>

    <script>
        function escapeHtml(str) {{
            if (!str) return '';
            return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }}

        function getCookie(name) {{
            const value = `; ${{document.cookie}}`;
            const parts = value.split(`; ${{name}}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return '';
        }}

        // Set CSRF token for logout form
        document.getElementById('csrf-token-logout').value = getCookie('monitoring_csrf');

        async function refreshHealth() {{
            const grid = document.getElementById('health-grid');
            grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;color:var(--text-secondary);padding:20px;">Checking sites...</div>';
            try {{
                const resp = await fetch('/monitoring/api/health');
                const data = await resp.json();
                grid.innerHTML = '';
                for (const site of data.sites) {{
                    const statusClass = {{'healthy':'ok','degraded':'warn','down':'error'}}[site.status] || 'unknown';
                    const rt = site.response_time ? site.response_time + 'ms' : 'N/A';
                    const code = site.status_code || '-';
                    grid.innerHTML += `
                        <div class="health-card ${{statusClass}}">
                            <div class="health-status">
                                <span class="status-dot ${{statusClass}}"></span>
                                <span class="status-text">${{escapeHtml(site.status.toUpperCase())}}</span>
                            </div>
                            <div class="health-url">${{escapeHtml(site.url)}}</div>
                            <div class="health-meta">
                                <span>HTTP ${{escapeHtml(code)}}</span>
                                <span>${{escapeHtml(rt)}}</span>
                            </div>
                        </div>`;
                }}
            }} catch(e) {{
                grid.innerHTML = '<div style="grid-column:1/-1;color:var(--red);">Error checking health</div>';
            }}
        }}

        setInterval(refreshHealth, 60000);
    </script>
</body>
</html>"""
