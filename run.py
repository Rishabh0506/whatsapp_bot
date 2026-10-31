"""Start the bot:  python run.py
Then open http://127.0.0.1:8000 for the WhatsApp simulator (when channel.mode is 'simulator')."""
import uvicorn

from app.config import Settings
from app.main import build_app

if __name__ == "__main__":
    settings = Settings.load()
    app = build_app(settings)
    host, port = settings.get("app.host", "127.0.0.1"), settings.get("app.port", 8000)
    print(f"\n  Footwear bot running.  Simulator: http://{host}:{port}/sim/\n")
    uvicorn.run(app, host=host, port=port, log_level="info")
