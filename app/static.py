"""Serving the browser pages (simulator chat, backend dashboard)."""
from starlette.staticfiles import StaticFiles


class NoCacheStaticFiles(StaticFiles):
    """Static files the browser must re-check every time, so page changes show up on a normal reload."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response
