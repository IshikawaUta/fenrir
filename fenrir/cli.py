import argparse
import asyncio
import os
import sys
import time
from typing import Any

from fenrir import __version__


def print_banner(app_title: str = None):
    """Print the bold blue Fenrir ASCII banner."""
    ascii_art = r"""
     _______  _______  _        _______ _________ _______ 
    (  ____ \(  ____ \( (    /|(  ____ )\__   __/(  ____ )
    | (    \/| (    \/|  \  ( || (    )|   ) (   | (    )|
    | (__    | (__    |   \ | || (____)|   | |   | (____)|
    |  __)   |  __)   | (\ \) ||     __)   | |   |     __)
    | (      | (      | | \   || (\ (      | |   | (\ (   
    | )      | (____/\| )  \  || ) \ \_____) (___| ) \ \__
    |/       (_______/|/    )_)|/   \__/\_______/|/   \__/
                                                      
"""
    # Now build the full banner string
    banner = f"\033[1;34m{ascii_art}\033[0m"
    banner += f"\033[94m   Fenrir Web Framework - Version {__version__}\033[0m"
    if app_title:
        banner += f"\033[36m | App: {app_title}\033[0m"
    banner += "\n"
    print(banner)

def format_col(text: str, width: int, color_code: str = "") -> str:
    """Pad plain text to width first, then apply color code to avoid alignment issues."""
    padded = text.ljust(width)
    if color_code:
        return f"{color_code}{padded}\033[0m"
    return padded


def load_app(target: str) -> Any:
    """Load application object from target string (e.g. 'demo_app:app' or 'app.py')."""
    import importlib.util

    app_name = "app"
    if ":" in target:
        path_part, app_name = target.split(":", 1)
    else:
        path_part = target

    # Check if path_part is a python file
    if path_part.endswith(".py") and os.path.exists(path_part):
        spec = importlib.util.spec_from_file_location("fenrir_cli_target", path_part)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec for file '{path_part}'")
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, os.path.dirname(os.path.abspath(path_part)))
        sys.modules["fenrir_cli_target"] = module
        spec.loader.exec_module(module)
    else:
        sys.path.insert(0, os.getcwd())
        try:
            module = importlib.import_module(path_part)
        except Exception as e:
            py_file = path_part + ".py"
            if os.path.exists(py_file):
                spec = importlib.util.spec_from_file_location("fenrir_cli_target", py_file)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load spec for file '{py_file}'") from None
                module = importlib.util.module_from_spec(spec)
                sys.path.insert(0, os.path.dirname(os.path.abspath(py_file)))
                sys.modules["fenrir_cli_target"] = module
                spec.loader.exec_module(module)
            else:
                raise ImportError(f"Could not import module '{path_part}': {e}") from e

    try:
        return getattr(module, app_name)
    except AttributeError:
        if app_name == "app":
            try:
                return module.application
            except AttributeError:
                pass
        raise AttributeError(f"Module '{path_part}' has no attribute '{app_name}'") from None


def run_with_reloader(target_func, interval=1.0):
    """Run a target function in a separate process, and restart it when .py files change."""
    import multiprocessing
    import time

    def get_py_files():
        py_files = []
        for root, _, filenames in os.walk("."):
            for filename in filenames:
                if filename.endswith(".py"):
                    py_files.append(os.path.join(root, filename))
        return py_files

    def get_mtimes(files):
        mtimes = {}
        for f in files:
            try:
                mtimes[f] = os.stat(f).st_mtime
            except Exception:
                pass
        return mtimes

    files = get_py_files()
    mtimes = get_mtimes(files)

    print("\033[94mAuto-reload enabled (fallback polling/mtime)...\033[0m")

    p = multiprocessing.Process(target=target_func)
    p.start()

    try:
        while True:
            time.sleep(interval)

            # Check if files changed
            current_files = get_py_files()
            current_mtimes = get_mtimes(current_files)

            changed = False
            if set(current_files) != set(files):
                changed = True
            else:
                for f in current_files:
                    if current_mtimes.get(f) != mtimes.get(f):
                        changed = True
                        break

            if changed:
                print("\033[33mChange detected! Restarting server...\033[0m")
                # Kill old process
                p.terminate()
                p.join()

                # Start new process
                p = multiprocessing.Process(target=target_func)
                p.start()

                files = current_files
                mtimes = current_mtimes
    except KeyboardInterrupt:
        p.terminate()
        p.join()


def cmd_run(args):
    """Run command handler."""
    reload_mode = args.dev or args.reload
    app = load_app(args.target)

    if args.dev:
        os.environ["FENRIR_DEV_MODE"] = "1"
        app.dev_mode = True
        if hasattr(app, "config"):
            app.config["DEBUG"] = True

    # Print our beautiful blue banner
    print_banner(app.title)
    print(f"\033[94mStarting Fenrir App '{app.title}' v{app.version}...\033[0m")

    try:
        from asteri.arbiter import Arbiter
        from asteri.workers.asgi import ASGIWorker

        arbiter = Arbiter(
            app_path=args.target,
            worker_class=ASGIWorker,
            num_workers=args.workers,
            binds=[f"{args.host}:{args.port}"],
            reload=reload_mode,
            disable_dashboard=args.disable_dashboard,
        )
        arbiter.start()
    except ImportError:
        print("\033[91mError: asteri is required for production mode.\033[0m")
        print("Install with: pip install asteri")
        print("Or use --dev mode: fenrir run app:app --dev")
        sys.exit(1)
    except KeyboardInterrupt:
        pass


def cmd_routes(args):
    """Routes command handler."""
    app = load_app(args.target)
    print_banner(app.title)

    routes = app.router.routes
    websocket_routes = getattr(app.router, "websocket_routes", [])

    if not routes and not websocket_routes:
        print("\033[33mNo routes registered.\033[0m")
        return

    headers = ["Path", "Methods", "Handler", "Blueprint"]
    rows = []

    for route in routes:
        blueprint = app._route_blueprints.get(route)
        bp_name = blueprint.name if blueprint else "-"

        if route.is_falcon_resource():
            handler_name = route.handler.__class__.__name__
            methods = []
            for attr in dir(route.handler):
                if attr.startswith("on_") and callable(getattr(route.handler, attr)):
                    methods.append(attr[3:].upper())
            methods_str = ", ".join(sorted(methods))
        else:
            handler_name = getattr(route.handler, "__name__", str(route.handler))
            methods_str = ", ".join(sorted(route.methods))

        rows.append((route.path_pattern, methods_str, handler_name, bp_name))

    for route in websocket_routes:
        blueprint = app._route_blueprints.get(route)
        bp_name = blueprint.name if blueprint else "-"
        handler_name = getattr(route.handler, "__name__", str(route.handler))
        rows.append((route.path_pattern, "WEBSOCKET", handler_name, bp_name))

    col_widths = [max(len(str(r[i])) for r in [headers] + rows) for i in range(4)]
    separator = "\033[94m" + "-" * (sum(col_widths) + 6) + "\033[0m"

    print(separator)
    header_cols = [format_col(headers[i], col_widths[i], "\033[1;34m") for i in range(4)]
    print("\033[94m  \033[0m".join(header_cols))
    print(separator)
    for row in rows:
        path, methods, handler, bp = row
        method_color = "\033[96m" if methods == "WEBSOCKET" else "\033[92m"

        col_path = format_col(path, col_widths[0], "\033[36m")
        col_methods = format_col(methods, col_widths[1], method_color)
        col_handler = format_col(handler, col_widths[2], "")
        col_bp = format_col(bp, col_widths[3], "")

        print("\033[94m  \033[0m".join([col_path, col_methods, col_handler, col_bp]))
    print(separator)


def cmd_shell(args):
    """Shell command handler."""
    app = load_app(args.target)
    print_banner(app.title)

    import code

    from fenrir import Blueprint, HTMLResponse, JSONResponse, Response, g, request

    banner = (
        f"\033[1;34mFenrir {__version__} Interactive Shell\033[0m\n"
        f"\033[94mApp: {app.title} [{app.openapi_url}]\033[0m\n"
        f"\033[36mAvailable in context: 'app', 'request', 'g', 'Response', 'JSONResponse', 'HTMLResponse', 'Blueprint'\033[0m"
    )
    local_vars = {
        "app": app,
        "request": request,
        "g": g,
        "Response": Response,
        "JSONResponse": JSONResponse,
        "HTMLResponse": HTMLResponse,
        "Blueprint": Blueprint,
    }
    code.interact(banner=banner, local=local_vars)


async def run_benchmark(app, path: str, method: str, iterations: int, trials: int):
    """Perform in-memory benchmark using HTTPX ASGITransport."""
    import importlib.util
    if importlib.util.find_spec("httpx") is None:
        print("\033[31mHTTPX is required for benchmarking. Install it with: pip install httpx\033[0m")
        sys.exit(1)

    print(f"\033[94mBenchmarking {method} {path} ({iterations} iterations x {trials} trials)...\033[0m")

    # Silence noisy INFO logs from the app's middleware/handlers and httpx so
    # the benchmark output stays clean. Restore afterwards.
    import logging
    logging.disable(logging.INFO)
    try:
        return await _benchmark_requests(app, path, method, iterations, trials)
    finally:
        logging.disable(logging.NOTSET)


async def _benchmark_requests(app, path, method, iterations, trials):
    import httpx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://benchmark") as client:
        # Warmup
        print("\033[94mWarming up pipeline...\033[0m")
        for _ in range(50):
            await client.request(method, path)

        print("\033[94mRunning trials...\033[0m")
        all_trials_rps = []
        all_latencies = []

        for t in range(1, trials + 1):
            start_time = time.perf_counter()
            trial_latencies = []

            for _ in range(iterations):
                req_start = time.perf_counter()
                await client.request(method, path)
                trial_latencies.append(time.perf_counter() - req_start)

            elapsed = time.perf_counter() - start_time
            rps = iterations / elapsed
            all_trials_rps.append(rps)
            all_latencies.extend(trial_latencies)
            print(f"  \033[36mTrial {t}:\033[0m \033[92m{rps:.2f} rps\033[0m (elapsed: {elapsed:.3f}s)")

        avg_rps = sum(all_trials_rps) / len(all_trials_rps)
        avg_latency_ms = (sum(all_latencies) / len(all_latencies)) * 1000
        min_latency_ms = min(all_latencies) * 1000
        max_latency_ms = max(all_latencies) * 1000

        print("\n\033[1;34m" + "="*40)
        print("FENRIR BENCHMARK RESULTS")
        print("="*40 + "\033[0m")
        print(f"\033[36mTarget:\033[0m          {method} {path}")
        print(f"\033[36mAverage RPS:\033[0m     \033[1;92m{avg_rps:.2f} req/sec\033[0m")
        print(f"\033[36mMin Latency:\033[0m     {min_latency_ms:.3f} ms")
        print(f"\033[36mMax Latency:\033[0m     {max_latency_ms:.3f} ms")
        print(f"\033[36mAvg Latency:\033[0m     {avg_latency_ms:.3f} ms")
        print("\033[1;34m" + "="*40 + "\033[0m")


def cmd_bench(args):
    """Bench command handler."""
    app = load_app(args.target)
    print_banner(app.title)
    asyncio.run(run_benchmark(app, args.path, args.method, args.iterations, args.trials))


def cmd_new(args):
    """Scaffold a new project directory structure."""
    print_banner()
    # Sanitize project name to prevent path traversal via ..
    project_name = args.name.strip()
    if ".." in project_name.replace(os.sep, "/").split("/"):
        print(f"\033[31mError: Invalid project name '{args.name}'. Path must not contain '..'.\033[0m")
        sys.exit(1)
    project_dir = project_name
    if os.path.exists(project_dir):
        print(f"\033[31mError: Directory '{project_dir}' already exists.\033[0m")
        sys.exit(1)

    print(f"\033[94mScaffolding a new Fenrir project '{project_dir}'...\033[0m")

    import shutil
    try:
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, "static"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "templates"), exist_ok=True)

        # Copy logo.png and create favicon.ico from logo.jpg (if it exists)
        # First try from fenrir package directory (for installed packages)
        fenrir_dir = os.path.dirname(os.path.abspath(__file__))
        core_logo_path = os.path.join(fenrir_dir, "logo.png")

        # Fallback to parent directory if not in fenrir folder (for dev mode)
        if not os.path.exists(core_logo_path):
            core_logo_path = os.path.join(os.path.dirname(fenrir_dir), "logo.png")

        # Last fallback to current working directory
        if not os.path.exists(core_logo_path):
            core_logo_path = os.path.join(os.getcwd(), "logo.png")

        if os.path.exists(core_logo_path):
            shutil.copy(core_logo_path, os.path.join(project_dir, "logo.png"))

        core_jpg_path = os.path.join(fenrir_dir, "logo.jpg")
        if not os.path.exists(core_jpg_path):
            core_jpg_path = os.path.join(os.path.dirname(fenrir_dir), "logo.jpg")

        if not os.path.exists(core_jpg_path):
            core_jpg_path = os.path.join(os.getcwd(), "logo.jpg")

        if os.path.exists(core_jpg_path):
            shutil.copy(core_jpg_path, os.path.join(project_dir, "favicon.ico"))
        elif os.path.exists(core_logo_path):
            shutil.copy(core_logo_path, os.path.join(project_dir, "favicon.ico"))

        # Write app.py
        app_content = """import os
import sys

from fenrir import Fenrir, render_template, send_file

app = Fenrir(title="My Fenrir Application", version="4.3.1")

@app.get("/")
async def home():
    return render_template("index.html", python_version=sys.version)

@app.get("/logo.png")
async def get_logo():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base_dir, "logo.png"))

@app.get("/favicon.ico")
async def get_favicon():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base_dir, "favicon.ico"))

@app.get("/api/hello")
async def api_hello():
    return {"message": "Hello World from Fenrir!"}

if __name__ == "__main__":
    app.run()
"""
        with open(os.path.join(project_dir, "app.py"), "w") as f:
            f.write(app_content)

        # Write templates/index.html
        index_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Fenrir Application</title>
    <!-- Favicon link -->
    <link rel="icon" type="image/jpeg" href="/favicon.ico">
    <!-- Premium Typography -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 24, 39, 0.7);
            --border-color: rgba(99, 102, 241, 0.15);
            --border-hover: rgba(139, 92, 246, 0.4);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --primary-glow: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            --accent-green: #10b981;
            --neon-purple: #8b5cf6;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.08) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(168, 85, 247, 0.08) 0%, transparent 40%);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 20px;
            overflow-x: hidden;
        }

        .container {
            max-width: 700px;
            width: 100%;
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            padding: 50px 40px;
            border-radius: 24px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4), 
                        inset 0 1px 0 rgba(255, 255, 255, 0.1);
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            position: relative;
            transition: border-color 0.3s ease, box-shadow 0.3s ease;
        }

        .container:hover {
            border-color: var(--border-hover);
            box-shadow: 0 20px 60px rgba(139, 92, 246, 0.05), 0 20px 50px rgba(0, 0, 0, 0.4);
        }

        .logo-wrapper {
            margin-bottom: 25px;
            display: flex;
            justify-content: center;
            align-items: center;
            width: 100%;
        }

        .logo-img {
            width: 140px;
            height: 140px;
            object-fit: contain;
            filter: drop-shadow(0 0 15px rgba(139, 92, 246, 0.5));
            animation: float 4s ease-in-out infinite;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-8px); }
        }

        .success-badge {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: var(--accent-green);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            padding: 8px 16px;
            border-radius: 50px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            margin-bottom: 30px;
        }

        .pulse {
            width: 8px;
            height: 8px;
            background: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--accent-green);
            animation: beat 1.5s infinite alternate;
        }

        @keyframes beat {
            0% { transform: scale(1); opacity: 0.6; }
            100% { transform: scale(1.4); opacity: 1; }
        }

        h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #ffffff 30%, #c7d2fe 100%);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 16px;
            letter-spacing: -0.5px;
        }

        .tagline {
            font-size: 1.1rem;
            color: var(--text-secondary);
            max-width: 500px;
            margin: 0 auto 35px auto;
            line-height: 1.6;
        }

        .info-box {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 20px;
            border-radius: 16px;
            text-align: left;
            margin-bottom: 35px;
            width: 100%;
        }

        .info-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            font-size: 0.95rem;
        }

        .info-item:last-child {
            border-bottom: none;
        }

        .info-label {
            color: var(--text-secondary);
            font-weight: 500;
        }

        .info-value {
            font-family: 'JetBrains Mono', monospace;
            color: #a5b4fc;
        }

        .next-steps {
            text-align: left;
            margin-bottom: 35px;
            width: 100%;
        }

        .steps-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--text-primary);
        }

        .step-card {
            background: rgba(99, 102, 241, 0.05);
            border: 1px dashed rgba(99, 102, 241, 0.2);
            padding: 15px;
            border-radius: 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
            color: #d1d5db;
        }

        .step-card span {
            color: #818cf8;
        }

        footer {
            margin-top: 30px;
            font-size: 0.8rem;
            color: rgba(255, 255, 255, 0.3);
            text-align: center;
        }

        /* Responsive design */
        @media (max-width: 640px) {
            body {
                padding: 15px;
            }

            .container {
                padding: 35px 20px;
                border-radius: 18px;
            }

            .logo-wrapper {
                display: flex;
                justify-content: center;
                align-items: center;
                margin: 0 auto 25px auto;
            }

            .logo-img {
                width: 110px;
                height: 110px;
            }

            h1 {
                font-size: 2rem;
            }

            .tagline {
                font-size: 1rem;
                margin-bottom: 25px;
            }

            .info-box {
                padding: 15px;
            }

            .info-item {
                font-size: 0.85rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-badge">
            <span class="pulse"></span>
            PROJECT CREATED SUCCESSFULLY
        </div>

        <!-- Premium Logo.png -->
        <div class="logo-wrapper">
            <img class="logo-img" src="/logo.png" alt="Fenrir Logo">
        </div>

        <h1>Fenrir Scaffold</h1>
        
        <p class="tagline">
            Your new high-performance web application has been scaffolded and is ready for development.
        </p>

        <div class="info-box">
            <div class="info-item">
                <span class="info-label">Application Status</span>
                <span class="info-value" style="color: var(--accent-green);">Active & Running</span>
            </div>
            <div class="info-item">
                <span class="info-label">Python Environment</span>
                <span class="info-value">{{ python_version }}</span>
            </div>
            <div class="info-item">
                <span class="info-label">Framework Engine</span>
                <span class="info-value">Fenrir v4.3.1</span>
            </div>
        </div>

        <div class="next-steps">
            <div class="steps-title">Getting Started</div>
            <div class="step-card">
                <span># Open app.py to start coding your endpoints</span><br>
                <span># Run with auto-reload:</span><br>
                fenrir run app.py --dev
            </div>
        </div>
    </div>

    <footer>
        Powered by Fenrir Web Framework
    </footer>
</body>
</html>
"""
        with open(os.path.join(project_dir, "templates", "index.html"), "w") as f:
            f.write(index_content)

        # Write a dummy requirements.txt
        req_content = "fenrir\n"
        with open(os.path.join(project_dir, "requirements.txt"), "w") as f:
            f.write(req_content)

        # Write dummy static file
        with open(os.path.join(project_dir, "static", "style.css"), "w") as f:
            f.write("body { font-family: sans-serif; background-color: #f0f4f8; color: #102a43; }")

        print(f"\033[92mSuccess! Project '{project_dir}' initialized.\033[0m\n")
        print("\033[36mTo get started:\033[0m")
        print(f"  cd {project_dir}")
        print("  fenrir run app.py --dev")
    except Exception as e:
        print(f"\033[31mError during scaffolding: {e}\033[0m")
        sys.exit(1)


def _update_env_var(key: str, value: str):
    """Update or add a variable in the .env file."""
    import tempfile
    # Sanitize key and value to prevent newline injection
    key = key.strip().replace("\r", "").replace("\n", "")
    value = value.replace("\r", "").replace("\n", "")
    env_file = os.path.join(os.getcwd(), ".env")
    lines = []
    found = False

    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0] == key:
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        lines.append(f"{key}={value}\n")

    # Atomic write: write to temp file, then rename
    dir_name = os.path.dirname(env_file) or "."
    with tempfile.NamedTemporaryFile(mode="w", dir=dir_name, delete=False) as tmp:
        tmp.writelines(lines)
        tmp_path = tmp.name
    os.replace(tmp_path, env_file)


def cmd_monitoring(args):
    """Monitoring enable/disable/status command handler."""
    print_banner("Fenrir Monitoring")

    if args.monitoring_action == "enable":
        _update_env_var("MONITORING_ENABLED", "true")
        print("\033[92mMonitoring dashboard enabled.\033[0m")
        print("\033[36mConfigure credentials in .env:\033[0m")
        print("  MONITORING_USER=admin")
        print("  MONITORING_PASSWORD=changeme")
        print("  MONITORING_SECRET_KEY=<random-secret>")
        print("\n\033[36mRestart your server to apply changes.\033[0m")

    elif args.monitoring_action == "disable":
        _update_env_var("MONITORING_ENABLED", "false")
        print("\033[33mMonitoring dashboard disabled.\033[0m")
        print("\033[36mRestart your server to apply changes.\033[0m")

    elif args.monitoring_action == "status":
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.getcwd(), ".env"))
        except ImportError:
            pass

        enabled = os.getenv("MONITORING_ENABLED", "false").lower() == "true"
        user = os.getenv("MONITORING_USER", "admin")
        sites = os.getenv("MONITORING_SITES", "http://localhost:8000")

        status_color = "\033[92mENABLED\033[0m" if enabled else "\033[33mDISABLED\033[0m"
        print(f"\033[36mStatus:\033[0m    {status_color}")
        print(f"\033[36mUser:\033[0m      {user}")
        print(f"\033[36mSites:\033[0m     {sites}")
        print("\033[36mEndpoint:\033[0m  /monitoring")

    elif args.monitoring_action == "set-password":
        import getpass
        password = getpass.getpass("\033[36mEnter new monitoring password:\033[0m ")
        if not password:
            print("\033[31mPassword cannot be empty.\033[0m")
            return
        _update_env_var("MONITORING_PASSWORD", password)

        import secrets
        secret_key = secrets.token_hex(32)
        _update_env_var("MONITORING_SECRET_KEY", secret_key)

        print("\033[92mPassword updated successfully.\033[0m")
        print("\033[36mRestart your server to apply changes.\033[0m")


def cmd_info(args):
    """Print system environment & loaded Fenrir app details."""
    app = None
    if args.target:
        try:
            app = load_app(args.target)
        except Exception as e:
            print(f"\033[31mWarning: Could not load target '{args.target}': {e}\033[0m\n")

    print_banner(app.title if app else None)

    import platform
    import sys as sys_module

    print("\033[1;34m" + "="*45)
    print("SYSTEM ENVIRONMENT")
    print("="*45 + "\033[0m")
    print(f"\033[36mFenrir version:\033[0m      {__version__}")
    print(f"\033[36mPython version:\033[0m      {platform.python_version()}")
    print(f"\033[36mPython executable:\033[0m   {sys_module.executable}")
    print(f"\033[36mOS Platform:\033[0m         {platform.system()} {platform.release()}")

    # Check dependencies/compatibilities dynamically
    has_pydantic = "No"
    try:
        import pydantic
        has_pydantic = "Yes"
        if hasattr(pydantic, "__version__"):
            has_pydantic += f" (v{pydantic.__version__})"
        elif hasattr(pydantic, "VERSION"):
            has_pydantic += f" (v{pydantic.VERSION})"
    except ImportError:
        pass

    has_asteri = "No"
    try:
        import asteri
        has_asteri = "Yes"
        if hasattr(asteri, "__version__"):
            has_asteri += f" (v{asteri.__version__})"
        elif hasattr(asteri, "VERSION"):
            has_asteri += f" (v{asteri.VERSION})"
    except ImportError:
        pass

    print(f"\033[36mPydantic installed:\033[0m  {has_pydantic}")
    print(f"\033[36mAsteri installed:\033[0m    {has_asteri}")

    if app:
        print("\033[1;34m" + "="*45)
        print("APPLICATION DETAILS")
        print("="*45 + "\033[0m")
        print(f"\033[36mApp Title:\033[0m           {app.title}")
        print(f"\033[36mApp Version:\033[0m         {app.version}")

        routes_count = len(app.router.routes)
        ws_count = len(getattr(app.router, "websocket_routes", []))
        mw_count = len(app.middleware_stack) if hasattr(app, "middleware_stack") else 0
        if not mw_count and hasattr(app, "_asgi_middlewares"):
            mw_count = len(app._asgi_middlewares)

        print(f"\033[36mHTTP Routes:\033[0m         {routes_count}")
        print(f"\033[36mWebSocket Routes:\033[0m    {ws_count}")
        print(f"\033[36mMiddlewares:\033[0m         {mw_count}")

        # Compat status
        compat_layers = []
        if "flask" in sys_module.modules:
            compat_layers.append("Flask")
        if "fastapi" in sys_module.modules:
            compat_layers.append("FastAPI")
        if "bottle" in sys_module.modules:
            compat_layers.append("Bottle")
        if "falcon" in sys_module.modules:
            compat_layers.append("Falcon")
        if "sanic" in sys_module.modules:
            compat_layers.append("Sanic")

        compat_str = ", ".join(compat_layers) if compat_layers else "None active in process"
        print(f"\033[36mCompat Layers Active:\033[0m {compat_str}")

    print("\033[1;34m" + "="*45 + "\033[0m")


def main():
    parser = argparse.ArgumentParser(
        description="Fenrir CLI - The hybrid web framework command line interface.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    ascii_art = r"""
 ____  ____  __ _  ____  __  ____ 
(  __)(  __)(  ( \(  _ \(  )(  _ \
 ) _)  ) _) /    / )   / )(  )   /
(__)  (____)\_)__)(__\_)(__)(__\_)
"""
    version_str = f"\033[1;34m{ascii_art}\033[0m\n\033[94mFenrir Web Framework - Version {__version__}\033[0m"

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=version_str,
        help="Show Fenrir framework version and exit."
    )

    subparsers = parser.add_subparsers(title="subcommands", dest="command", required=True)

    # 1. Run subcommand
    run_parser = subparsers.add_parser("run", help="Run a Fenrir development or production server.")
    run_parser.add_argument("target", help="The app path in format 'module:app' or 'app.py'.")
    run_parser.add_argument("-H", "--host", default="127.0.0.1", help="Host address [default: 127.0.0.1]")
    run_parser.add_argument("-p", "--port", type=int, default=8000, help="Port to serve on [default: 8000]")
    run_parser.add_argument("-w", "--workers", type=int, default=1, help="Number of workers [default: 1]")
    run_parser.add_argument("-d", "--dev", action="store_true", help="Run in development mode (with auto-reload)")
    run_parser.add_argument("--reload", action="store_true", help="Restart workers on code changes.")
    run_parser.add_argument("--disable-dashboard", action="store_true", help="Disable Asteri built-in dashboard (/asteri-status)")
    run_parser.set_defaults(func=cmd_run)

    # 2. Routes subcommand
    routes_parser = subparsers.add_parser("routes", help="Show all registered routes for the app.")
    routes_parser.add_argument("target", help="The app path in format 'module:app' or 'app.py'.")
    routes_parser.set_defaults(func=cmd_routes)

    # 3. Shell subcommand
    shell_parser = subparsers.add_parser("shell", help="Run a Python shell in the app context.")
    shell_parser.add_argument("target", help="The app path in format 'module:app' or 'app.py'.")
    shell_parser.set_defaults(func=cmd_shell)

    # 4. Bench subcommand
    bench_parser = subparsers.add_parser("bench", help="Run in-memory framework speed benchmark.")
    bench_parser.add_argument("target", help="The app path in format 'module:app' or 'app.py'.")
    bench_parser.add_argument("-i", "--iterations", type=int, default=1000, help="Iterations per trial [default: 1000]")
    bench_parser.add_argument("-t", "--trials", type=int, default=5, help="Number of trials [default: 5]")
    bench_parser.add_argument("-p", "--path", default="/", help="The HTTP path to query [default: /]")
    bench_parser.add_argument("-m", "--method", default="GET", help="The HTTP method to use [default: GET]")
    bench_parser.set_defaults(func=cmd_bench)

    # 5. New subcommand
    new_parser = subparsers.add_parser("new", help="Scaffold a new Fenrir project directory.")
    new_parser.add_argument("name", help="Name of the new project directory.")
    new_parser.set_defaults(func=cmd_new)

    # 6. Info subcommand
    info_parser = subparsers.add_parser("info", help="Display environment, dependency status, and application details.")
    info_parser.add_argument("target", nargs="?", default=None, help="Optional app path in format 'module:app' or 'app.py'.")
    info_parser.set_defaults(func=cmd_info)

    # 7. Monitoring subcommand
    monitoring_parser = subparsers.add_parser("monitoring", help="Manage the built-in monitoring dashboard.")
    monitoring_sub = monitoring_parser.add_subparsers(dest="monitoring_action", required=True)

    monitoring_sub.add_parser("enable", help="Enable the monitoring dashboard.")
    monitoring_sub.add_parser("disable", help="Disable the monitoring dashboard.")
    monitoring_sub.add_parser("status", help="Show monitoring configuration status.")
    monitoring_sub.add_parser("set-password", help="Set a new monitoring dashboard password.")

    monitoring_parser.set_defaults(func=cmd_monitoring)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
