import logging
from pydantic import BaseModel
from fenrir import (
    Fenrir,
    Blueprint,
    request,
    g,
    Depends,
    Query,
    Header,
    render_template,
    Response,
    HTTPBadRequest,
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo")

# Initialize App
app = Fenrir(title="Fenrir Hybrid Framework Demo", version="3.0.0")

# --- 1. FastAPI-style Pydantic Validation & Dependency Injection ---
class UserRegister(BaseModel):
    username: str
    email: str
    age: int

async def verify_api_key(x_api_key: str = Header(default=None)):
    if x_api_key != "super-secret-key":
        # Raise HTTPException or return value
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
    from fenrir import send_file
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base_dir, "logo.png"))

@app.get("/favicon.ico")
async def get_favicon():
    from fenrir import send_file
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base_dir, "logo.jpg"))

# Form & File Upload Endpoint
from fenrir import Form, File, UploadFile
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

# --- 7. Bottle-style Built-in Server Runner (runs programmatically via Asteri) ---
if __name__ == "__main__":
    logger.info("Starting Fenrir Web Application...")
    app.run(host="127.0.0.1", port=8000, workers=2, app_path="demo_app:app")
