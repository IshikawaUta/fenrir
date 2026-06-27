"""Demo app showing Fenrir monitoring feature."""
import os
import sys

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
except ImportError:
    pass

from fenrir import Fenrir, render_template, JSONResponse
from fenrir.features import init_fenrir_monitoring

# Create the app
app = Fenrir(title="Fenrir Features Demo", version="4.1.1")

# Enable monitoring feature
# This will only activate if MONITORING_ENABLED=true in .env
init_fenrir_monitoring(app)


@app.get("/")
async def home():
    monitoring_enabled = os.getenv("MONITORING_ENABLED", "false").lower() == "true"
    
    return JSONResponse({
        "app": app.title,
        "version": app.version,
        "features": {
            "monitoring": {
                "enabled": monitoring_enabled,
                "url": "/monitoring" if monitoring_enabled else None,
            },
        },
        "endpoints": {
            "home": "/",
            "monitoring": "/monitoring" if monitoring_enabled else "disabled",
        },
    })


@app.get("/api/hello")
async def api_hello():
    return {"message": "Hello from Fenrir!"}


if __name__ == "__main__":
    print(f"Starting {app.title} v{app.version}...")
    print(f"Monitoring: {'ENABLED' if os.getenv('MONITORING_ENABLED', 'false').lower() == 'true' else 'DISABLED'}")
    print()
    print("CLI Commands:")
    print("  fenrir monitoring enable       - Enable monitoring dashboard")
    print("  fenrir monitoring disable      - Disable monitoring dashboard")
    print("  fenrir monitoring status       - Show monitoring status")
    print("  fenrir monitoring set-password - Set monitoring password")
    print("  fenrir run app --disable-dashboard - Disable Asteri built-in dashboard")
    print()
    
    app.run(host="127.0.0.1", port=8000, workers=1, app_path="demo_features:app")
