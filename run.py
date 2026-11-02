"""Start the bot:  python run.py

Starts two servers in one process (they share the same database):
  - the bot (WhatsApp webhook + simulator chat page)  -> http://127.0.0.1:8000/sim/
  - the backend dashboard (scores, decisions)         -> http://127.0.0.1:8001/
Ports and hosts are in config/settings.yaml (app.* and dashboard.*)."""
import asyncio
import socket
import sys

import uvicorn

from app.config import Settings
from app.core.providers import ProviderError
from app.debug import build_dashboard
from app.main import build_app


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


async def serve(settings: Settings):
    host, port = settings.get("app.host", "127.0.0.1"), settings.get("app.port", 8000)
    dash_host, dash_port = settings.get("dashboard.host", "127.0.0.1"), settings.get("dashboard.port", 8001)
    busy = [f"{h}:{p}" for h, p in ((host, port), (dash_host, dash_port)) if port_in_use(h, p)]
    if busy:
        print(f"\n  Can't start: {', '.join(busy)} is already in use.\n"
              "  Another copy of the bot is probably still running (an old Command Prompt window).\n"
              "  Close it (or press Ctrl+C in it), then start again.\n")
        sys.exit(1)

    try:
        app = build_app(settings)
    except ProviderError as e:        # e.g. the model API key is missing from .env
        print(f"\n  Can't start: {e}\n")
        sys.exit(1)

    bot = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info"))
    dashboard = uvicorn.Server(uvicorn.Config(build_dashboard(app), host=dash_host, port=dash_port, log_level="warning"))

    chat = f"http://{host}:{port}/sim/" if settings.get("channel.mode") == "simulator" else f"http://{host}:{port}"
    print(f"\n  Footwear bot running.\n  Chat (customer view):  {chat}\n"
          f"  Backend dashboard:     http://{dash_host}:{dash_port}/\n")

    dash_task = asyncio.create_task(dashboard.serve())
    await bot.serve()                 # Ctrl+C stops both
    dashboard.should_exit = True
    await dash_task


if __name__ == "__main__":
    asyncio.run(serve(Settings.load()))
