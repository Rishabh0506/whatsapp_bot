"""Builds the bot's web app: WhatsApp webhook (+ the simulator when channel.mode is 'simulator').
The backend dashboard (scores, decisions) is a separate app on its own port; see app/debug.py.

Run:  python run.py        (starts both: bot on app.port, dashboard on dashboard.port)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

from .config import Settings, whatsapp_connection
from .conversation import ConversationManager
from .core.pipeline import DiagnosisService
from .core.providers import make_provider
from .core.reference import Reference
from .storage import Storage
from .whatsapp import webhook
from .whatsapp.client import WhatsAppClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def health(request):
    return JSONResponse({"ok": True})


def build_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.load()
    reference = Reference.load(settings.config_dir)
    storage = Storage(settings.data_dir / "bot.db")
    conn = whatsapp_connection(settings)
    service = DiagnosisService(settings, reference, make_provider(settings, reference))
    conversations = ConversationManager(settings, storage, WhatsAppClient(conn), service)

    routes = [Route("/health", health), *webhook.routes]
    simulator_on = settings.get("channel.mode", "simulator") == "simulator"
    if simulator_on:
        from .simulator.routes import SimStore
        from .simulator.routes import routes as sim_routes
        routes += sim_routes

    @asynccontextmanager
    async def lifespan(app):
        conversations.start()          # regular check that closes quiet conversations (5-minute rule)
        yield
        await conversations.stop()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.settings = settings
    app.state.reference = reference
    app.state.storage = storage
    app.state.wa_conn = conn
    app.state.service = service
    app.state.conversations = conversations
    if simulator_on:
        app.state.sim = SimStore(settings.data_dir / "simulator.db")
    logging.getLogger("app").info("channel=%s provider=%s model=%s", settings.get("channel.mode"),
                                  settings.get("core.provider"), getattr(service.provider, "model", ""))
    return app


def __getattr__(name):
    # `uvicorn app.main:app` builds the app on first access, so importing this module stays cheap
    if name == "app":
        global app
        app = build_app()
        return app
    raise AttributeError(name)
