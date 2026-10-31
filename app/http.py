"""Tiny async HTTP helper on the standard library (no extra dependency)."""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _request(method: str, url: str, headers: dict | None, body: bytes | None, timeout: float) -> HttpResponse:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return HttpResponse(r.status, r.read(), dict(r.headers))
    except urllib.error.HTTPError as e:
        return HttpResponse(e.code, e.read() or b"", dict(e.headers or {}))


async def request(method: str, url: str, *, headers: dict | None = None, json_body=None,
                  body: bytes | None = None, timeout: float = 30) -> HttpResponse:
    headers = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    return await asyncio.to_thread(_request, method, url, headers, body, timeout)
