import logging
import os

from pydantic import BaseModel

from fenrir import (
    Blueprint,
    Depends,
    Fenrir,
    Header,
    HTTPBadRequest,
    HTTPConflict,
    HTTPForbidden,
    HTTPInternalServerError,
    HTTPNotFound,
    HTTPUnauthorized,
    HTTPUnprocessableEntity,
    Query,
    Response,
    g,
    render_template,
    request,
)
from fenrir.features import init_fenrir_monitoring
from fenrir.response import JSONResponse

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
except ImportError:
    pass

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo")

# Initialize App
# dev_mode bisa diaktifkan lewat:
#   1. CLI:       fenrir run demo_app:app --dev
#   2. Env var:   FENRIR_DEV_MODE=1 fenrir run demo_app:app
#   3. Program:   Fenrir(dev_mode=True) di bawah ini
app = Fenrir(
    title="Fenrir Hybrid Framework Demo",
    version="4.3.0",
    dev_mode=os.getenv("FENRIR_DEV_MODE") == "1",
    # The demo intentionally shows the interactive docs; production apps get
    # them disabled by default (ENV=production) unless docs_enabled=True.
    docs_enabled=True,
)

# --- Enable Built-in Features ---
# Monitoring Dashboard: /monitoring (login: admin/changeme)
# Configure via .env or CLI: fenrir monitoring enable
init_fenrir_monitoring(app)

# --- 1. FastAPI-style Pydantic Validation & Dependency Injection ---
class UserRegister(BaseModel):
    username: str
    email: str
    age: int

async def verify_api_key(x_api_key: str = Header(default=None)):
    expected_key = os.getenv("API_KEY", "changeme-set-API_KEY-env")
    if x_api_key != expected_key:
        logger.warning("Invalid API key provided!")
    return x_api_key

# --- 2. Flask-style Decorators, Context-Locals, and Templating ---
@app.get("/")
async def home():
    # Use request context-local to access query params
    name = request.args.get("name", "Fenrir User")
    # Flask-style rendering
    return render_template("index.html", name=name)

@app.get("/logo.png")
async def get_logo():
    import os

    from fenrir import send_file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base_dir, "logo.png"))

@app.get("/favicon.ico")
async def get_favicon():
    import os

    from fenrir import send_file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base_dir, "logo.jpg"))

# Form & File Upload Endpoint
from fenrir import File, Form, UploadFile


@app.post("/upload")
async def handle_upload(
    title: str = Form(),
    file: UploadFile = File()
):
    content = await file.read()
    return {
        "title": title,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content)
    }

# WebSocket Echo Endpoint
from fenrir import WebSocket, WebSocketDisconnect


@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            await ws.send_text(f"Fenrir Chat Echo: {msg}")
    except WebSocketDisconnect:
        logger.info("Chat WebSocket disconnected")

# --- 3. Falcon-style Class-based Resources ---
class ItemResource:
    async def on_get(self, req, resp, item_id: int):
        resp.status = 200
        resp.media = {
            "item_id": item_id,
            "status": "active",
            "msg": f"Fetched item {item_id} (Falcon Resource style)"
        }

    async def on_post(self, req, resp, item_id: int):
        # Read pre-fetched JSON body (Sanic/FastAPI style property)
        data = req.json
        resp.status = 201
        resp.media = {
            "item_id": item_id,
            "received_body": data,
            "msg": f"Created sub-item for item {item_id} (Falcon Resource style)"
        }

# Register Falcon Resource
app.add_route("/items/<item_id:int>", ItemResource())

# --- 4. Sanic-style Listeners and Middlewares ---
@app.listener("before_server_start")
async def setup_db(app_instance):
    logger.info("[Listener] Initializing mock database connection pool...")
    app_instance.db_pool = "Connected"

@app.listener("after_server_stop")
async def teardown_db(app_instance):
    logger.info("[Listener] Closing database connection pool...")

@app.middleware("request")
async def log_request_path(req):
    logger.info(f"[Middleware] Request received: {req.method} {req.path}")
    # Store request-specific state in Flask-style g object
    g.user_type = "guest"

@app.middleware("response")
async def add_custom_powered_by(req, resp):
    logger.info(f"[Middleware] Response sent: {resp.status}")
    resp.headers["X-Powered-By"] = "Fenrir Framework"

# --- 5. Flask/Sanic-style Blueprint modular routing ---
api_bp = Blueprint("api", url_prefix="/api")

@api_bp.post("/register")
async def register_user(
    body: UserRegister,
    api_key: str = Depends(verify_api_key),
    role: str = Query(default="member")
):
    # Returns Pydantic model or dict directly, automatically serialized to JSON
    return {
        "status": "success",
        "user_type": g.user_type, # Retrieved from context g populated by middleware
        "role": role,
        "api_key_used": api_key,
        "registered_user": body.model_dump()
    }

# Register Blueprint
app.register_blueprint(api_bp)

# --- 6. Custom Exception Handler ---
@app.exception(ValueError)
async def handle_value_error(req, exc):
    return Response(f"Custom Value Error: {exc}", status=400)

@app.get("/trigger-error")
async def trigger_error():
    raise ValueError("Something went wrong!")

@app.get("/error/zero-division")
async def zero_division_error():
    result = 1 / 0
    return JSONResponse({"result": result})


# ╔══════════════════════════════════════════════════════════════════╗
# ║  CONTOH SEMUA JENIS ERROR (untuk testing debug page)            ║
# ║  Jalankan dengan: fenrir run demo_app:app --dev                 ║
# ╚══════════════════════════════════════════════════════════════════╝

class LoginBody(BaseModel):
    username: str
    password: str

async def dep_user_id(user_id: int = Query(default=None)):
    if user_id is None:
        raise HTTPBadRequest("user_id wajib diisi")
    return user_id

async def dep_auth_fail():
    raise HTTPUnauthorized("Token tidak valid atau expired")


# 1. HTTP 400 - Bad Request
@app.get("/error/400")
async def err_400():
    raise HTTPBadRequest("Request tidak valid")


# 2. HTTP 401 - Unauthorized
@app.get("/error/401")
async def err_401():
    raise HTTPUnauthorized("Kamu harus login dulu")


# 3. HTTP 403 - Forbidden
@app.get("/error/403")
async def err_403():
    raise HTTPForbidden("Kamu tidak punya akses ke resource ini")


# 4. HTTP 404 - Not Found
@app.get("/error/404")
async def err_404():
    raise HTTPNotFound("Halaman tidak ditemukan")


# 5. HTTP 409 - Conflict
@app.get("/error/409")
async def err_409():
    raise HTTPConflict("Data sudah ada, tidak boleh duplikat")


# 6. HTTP 422 - Unprocessable Entity
@app.get("/error/422")
async def err_422():
    raise HTTPUnprocessableEntity("Format data benar tapi isinya salah")


# 7. HTTP 500 - Internal Server Error
@app.get("/error/500")
async def err_500():
    raise HTTPInternalServerError("Server error internal")


# 8. ValueError (handled by custom handler -> JSONResponse)
@app.get("/error/value")
async def err_value():
    raise ValueError("Ini ditangkap custom handler, bukan debug page")


# 9. ZeroDivisionError (unhandled -> debug page)
@app.get("/error/zero")
async def err_zero():
    x = 1 / 0
    return {"result": x}


# 10. RuntimeError tanpa detail
@app.get("/error/runtime")
async def err_runtime():
    raise RuntimeError()


# 11. Exception dari Depends
@app.get("/error/dep")
async def err_dep(uid: int = Depends(dep_user_id)):
    return {"user_id": uid}


# 12. Exception dari Depends (auth gagal)
@app.get("/error/auth")
async def err_auth(x=Depends(dep_auth_fail)):
    return {"x": x}


# 13. Pydantic validation error (422 otomatis)
@app.post("/error/pydantic")
async def err_pydantic(body: LoginBody):
    return {"user": body.username}


# 14. Custom exception tanpa handler
class AppCustomError(Exception):
    def __init__(self, msg="custom app error"):
        self.msg = msg
        super().__init__(msg)

@app.exception(AppCustomError)
async def handle_custom(req, exc):
    return JSONResponse({"custom_error": exc.msg}, status=500)

@app.get("/error/custom")
async def err_custom():
    raise AppCustomError("Ini error kustom aplikasi")


# 15. ASGI middleware error
class BrokenMiddleware:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/error/mw"):
            raise RuntimeError("ASGI middleware error!")
        await self.app(scope, receive, send)

app.add_middleware(BrokenMiddleware)

@app.get("/error/mw")
async def err_middleware():
    return {"msg": "tidak akan sampai ke sini"}

# --- 7. Bottle-style Built-in Server Runner (runs programmatically via Asteri) ---
if __name__ == "__main__":
    monitoring_enabled = os.getenv("MONITORING_ENABLED", "false").lower() == "true"

    logger.info("Starting Fenrir Web Application...")
    logger.info(f"  Monitoring: {'ENABLED at /monitoring' if monitoring_enabled else 'DISABLED (run: fenrir monitoring enable)'}")
    logger.info("")
    logger.info("CLI Commands:")
    logger.info("  fenrir monitoring enable       - Enable monitoring dashboard")
    logger.info("  fenrir monitoring disable      - Disable monitoring dashboard")
    logger.info("  fenrir monitoring set-password - Set dashboard password")
    logger.info("  fenrir run app --disable-dashboard - Disable Asteri built-in dashboard")
    logger.info("")

    app.run(host="127.0.0.1", port=8000, workers=2, app_path="demo_app:app")
