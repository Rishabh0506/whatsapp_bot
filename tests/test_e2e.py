"""End-to-end: real HTTP server, simulator -> signed webhook -> photo download -> diagnosis -> reply.
Also runs the Gemini provider against a fake Gemini server."""
import hashlib
import hmac
import io
import json
import socket
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import uvicorn
from PIL import Image

from app.config import SIM_APP_SECRET, Settings
from app.main import build_app


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError("server did not start")


def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def multipart(fields: dict, files: list[tuple[str, str, bytes]]):
    boundary = uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for name, filename, data in files:
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                  f"Content-Type: image/jpeg\r\n\r\n".encode() + data + b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def jpeg(color):
    b = io.BytesIO()
    Image.new("RGB", (3000, 2000), color).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def server(config_dir, tmp_path):
    port = free_port()
    settings = Settings.load(config_dir, tmp_path / "data", overrides={
        "core.provider": "mock", "channel.batch_wait_seconds": 1, "app.port": port,
        "app.public_base_url": f"http://127.0.0.1:{port}"})
    app = build_app(settings)
    srv = start_server(app, port)
    yield f"http://127.0.0.1:{port}", app
    srv.should_exit = True


def wait_for(fn, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.2)
    raise AssertionError("timed out")


def test_photos_to_diagnosis_reply(server):
    base, app = server
    wa = "919800000001"
    body, headers = multipart({"wa_id": wa, "name": "Asha", "text": "sole coming off"},
                              [("photos", "a.jpg", jpeg((200, 50, 50))), ("photos", "b.jpg", jpeg((50, 200, 50)))])
    st, res = http("POST", f"{base}/sim/api/send", body, headers)
    assert st == 200 and len(json.loads(res)["sent"]) == 2

    def bot_reply():
        _, rows = http("GET", f"{base}/sim/api/messages?wa_id={wa}")
        bots = [r for r in json.loads(rows) if r["sender"] == "bot"]
        return bots or None
    bots = wait_for(bot_reply)
    text = bots[0]["body"]["text"]["body"]
    assert "(2 photos)" in text and "10. Glue Fix Possible:" in text and "Decision:" in text
    assert len(bots) == 1                                            # both photos -> ONE diagnosis

    _, rows = http("GET", f"{base}/debug/api/diagnoses?wa_id={wa}")
    diag = json.loads(rows)
    assert len(diag) == 1 and len(diag[0]["media_ids"]) == 2 and diag[0]["status"] == "ok"
    # photos were re-compressed like WhatsApp and resized for the model
    st, img = http("GET", f"{base}/debug/media/{diag[0]['media_ids'][0]}")
    assert st == 200 and max(Image.open(io.BytesIO(img)).size) == 1600

    # read receipts reached the simulator
    _, rows = http("GET", f"{base}/sim/api/messages?wa_id={wa}")
    assert all(r["status"] == "read" for r in json.loads(rows) if r["sender"] == "user")
    # sent/delivered status webhooks were logged by the bot
    wait_for(lambda: app.state.storage._all("SELECT * FROM statuses WHERE status='delivered'"))


def test_text_message_gets_photo_request(server):
    base, _ = server
    body, headers = multipart({"wa_id": "919800000002", "text": "hello"}, [])
    http("POST", f"{base}/sim/api/send", body, headers)
    bots = wait_for(lambda: [r for r in json.loads(http("GET", f"{base}/sim/api/messages?wa_id=919800000002")[1])
                             if r["sender"] == "bot"])
    assert "only diagnose photos" in bots[0]["body"]["text"]["body"]


def signed(payload):
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SIM_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"Content-Type": "application/json", "X-Hub-Signature-256": sig}


def test_webhook_security_and_duplicates(server):
    base, app = server
    st, body = http("GET", f"{base}/webhook?hub.mode=subscribe&hub.verify_token=sim-verify-token&hub.challenge=42")
    assert st == 200 and body == b"42"
    assert http("GET", f"{base}/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=42")[0] == 403
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "919800000003", "profile": {"name": "R"}}],
        "messages": [{"from": "919800000003", "id": "wamid.DUP1", "timestamp": str(int(time.time())),
                      "type": "text", "text": {"body": "hi"}}]}}]}]}
    raw, headers = signed(payload)
    assert http("POST", f"{base}/webhook", raw, {**headers, "X-Hub-Signature-256": "sha256=bad"})[0] == 401
    assert http("POST", f"{base}/webhook", raw, headers)[0] == 200
    assert http("POST", f"{base}/webhook", raw, headers)[0] == 200        # same event delivered twice
    time.sleep(1.5)
    out = app.state.storage._all("SELECT * FROM messages WHERE wa_id='919800000003' AND direction='out'")
    assert len(out) == 1                                                 # answered once


class FakeGemini(BaseHTTPRequestHandler):
    calls = []
    reject_json_schema = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeGemini.calls.append((self.path, dict(self.headers), body))
        if FakeGemini.reject_json_schema and "responseJsonSchema" in body["generationConfig"]:
            self._send(400, {"error": {"message": "Invalid JSON payload. Unknown name \"responseJsonSchema\""}})
            return
        props = body["generationConfig"].get("responseJsonSchema") or body["generationConfig"]["responseSchema"]
        answer = {"visible_evidence": "fake"}
        for k, v in props["properties"].items():
            if k in ("visible_evidence", "observation_note"):
                answer[k] = ""
            elif "value" in v["properties"]:
                answer[k] = {"value": v["properties"]["value"]["enum"][0], "confidence": 0.9}
            else:
                answer[k] = {"issue_category": "None", "damage_mode": "None", "confidence": 0.9}
        self._send(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}, "finishReason": "STOP"}],
                         "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}})

    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.mark.parametrize("reject", [False, True])
def test_gemini_provider_http(settings, reference, reject):
    import asyncio
    from app.core.pipeline import DiagnosisService
    from app.core.providers.gemini import GeminiProvider
    port = free_port()
    srv = HTTPServer(("127.0.0.1", port), FakeGemini)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    FakeGemini.calls, FakeGemini.reject_json_schema = [], reject
    try:
        provider = GeminiProvider("test-key", "gemini-test", f"http://127.0.0.1:{port}/v1beta")
        result = asyncio.run(DiagnosisService(settings, reference, provider).diagnose([jpeg((1, 2, 3))]))
    finally:
        srv.shutdown()
    path, headers, body = FakeGemini.calls[-1]
    assert path == "/v1beta/models/gemini-test:generateContent"
    assert {k.lower(): v for k, v in headers.items()}.get("x-goog-api-key") == "test-key"
    assert ("responseSchema" in body["generationConfig"]) == reject
    assert result["fields"]["image_status"]["value"] == "Usable"
    assert result["meta"]["usage"]["total_tokens"] == 15 and result["meta"]["model"] == "gemini-test"
