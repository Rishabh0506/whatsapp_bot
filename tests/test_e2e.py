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
from app.debug import build_dashboard
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
    dash_port = free_port()
    dash = start_server(build_dashboard(app), dash_port)
    app.state.dashboard_url = f"http://127.0.0.1:{dash_port}"
    yield f"http://127.0.0.1:{port}", app
    srv.should_exit = True
    dash.should_exit = True


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
    assert text.strip()
    # the customer never sees field names, scores or decision codes
    for internal in ("Glue Fix Possible", "Damage Mode", "Decision", "0.", "Test mode", "✅", "⚠️"):
        assert internal not in text, internal
    assert len(bots) == 1                                            # both photos -> ONE diagnosis

    dash = app.state.dashboard_url
    _, rows = http("GET", f"{dash}/api/diagnoses?wa_id={wa}")
    diag = json.loads(rows)
    assert len(diag) == 1 and len(diag[0]["media_ids"]) == 2 and diag[0]["status"] == "ok"
    assert diag[0]["reply"] == text                                  # dashboard shows what the customer was told
    assert diag[0]["name"] == "Asha"                                 # dashboard shows who sent it
    # photos were re-compressed like WhatsApp and resized for the model
    st, img = http("GET", f"{dash}/media/{diag[0]['media_ids'][0]}")
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
    assert "send a photo" in bots[0]["body"]["text"]["body"]


def test_dashboard_is_only_on_its_own_port(server):
    base, app = server
    dash = app.state.dashboard_url
    for path in ("/debug/api/diagnoses", "/debug/api/info", "/api/diagnoses", "/api/info"):
        assert http("GET", base + path)[0] == 404, path              # nothing internal on the bot's port
    st, page = http("GET", dash + "/")
    assert st == 200 and b"Backend dashboard" in page
    st, info = http("GET", dash + "/api/info")
    assert st == 200 and json.loads(info)["provider"] == "mock"
    st, sim = http("GET", base + "/sim/")
    assert st == 200 and b"Diagnoses" not in sim and b"debug" not in sim.lower()


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


def test_bot_shows_typing_like_whatsapp(server):
    """The Cloud API typing indicator: shown after a read receipt with typing_indicator, gone once the bot replies."""
    from app.config import SIM_ACCESS_TOKEN, SIM_PHONE_NUMBER_ID
    from app.whatsapp.payloads import read_receipt, text_message
    base, app = server
    wa, msg_id = "919800000009", "wamid.TEST1"
    app.state.sim.q("INSERT INTO messages (id,wa_id,sender,type,body,status,created_at) VALUES (?,?,?,?,?,?,?)",
                    (msg_id, wa, "user", "text", "{}", "sent", time.time()))
    graph = f"{base}/sim/graph/{SIM_PHONE_NUMBER_ID}/messages"
    auth = {"Authorization": f"Bearer {SIM_ACCESS_TOKEN}", "Content-Type": "application/json"}
    presence = lambda: json.loads(http("GET", f"{base}/sim/api/presence?wa_id={wa}")[1])["typing"]  # noqa: E731
    assert presence() is False
    http("POST", graph, json.dumps(read_receipt(msg_id, typing=True)).encode(), auth)
    assert presence() is True
    http("POST", graph, json.dumps(text_message(wa, "hello")).encode(), auth)
    assert presence() is False


class FakeOpenRouter(BaseHTTPRequestHandler):
    calls = []
    reject_json_schema = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOpenRouter.calls.append((self.path, dict(self.headers), body))
        fmt = body["response_format"]
        if FakeOpenRouter.reject_json_schema and fmt["type"] == "json_schema":
            self._send(404, {"error": {"code": 404, "message": "No endpoints found that can handle the requested "
                                                                "parameters: response_format json_schema"}})
            return
        props = fmt["json_schema"]["schema"]["properties"] if fmt["type"] == "json_schema" else None
        answer = {"visible_evidence": "fake", "observation_note": ""}
        if props:
            for k, v in props.items():
                if k in answer:
                    continue
                answer[k] = ({"value": v["properties"]["value"]["enum"][0], "confidence": 0.9} if "value" in v["properties"]
                             else {"issue_category": "None", "damage_mode": "None", "confidence": 0.9})
        else:
            answer["image_status"] = {"value": "Usable", "confidence": 0.9}
        self._send(200, {"id": "gen-1", "model": body["model"], "provider": "Google AI Studio",
                         "choices": [{"message": {"role": "assistant", "content": json.dumps(answer)},
                                      "finish_reason": "stop"}],
                         "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": 0.0012,
                                   "completion_tokens_details": {"reasoning_tokens": 7}}})

    _send = FakeGemini._send

    def log_message(self, *a):
        pass


@pytest.mark.parametrize("reject", [False, True])
def test_openrouter_provider_http(settings, reference, reject):
    import asyncio
    from app.core.pipeline import DiagnosisService
    from app.core.providers.openrouter import OpenRouterProvider
    port = free_port()
    srv = HTTPServer(("127.0.0.1", port), FakeOpenRouter)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    FakeOpenRouter.calls, FakeOpenRouter.reject_json_schema = [], reject
    try:
        provider = OpenRouterProvider("or-key", "google/gemini-test", f"http://127.0.0.1:{port}/api/v1",
                                      app_title="Footwear helpline bot")
        result = asyncio.run(DiagnosisService(settings, reference, provider).diagnose([jpeg((1, 2, 3))]))
    finally:
        srv.shutdown()
    path, headers, body = FakeOpenRouter.calls[-1]
    headers = {k.lower(): v for k, v in headers.items()}
    assert path == "/api/v1/chat/completions"
    assert headers["authorization"] == "Bearer or-key" and headers["x-title"] == "Footwear helpline bot"
    assert body["model"] == "google/gemini-test" and body["provider"] == {"require_parameters": True}
    user = body["messages"][1]["content"]
    assert user[0]["image_url"]["url"].startswith("data:image/jpeg;base64,") and user[-1]["type"] == "text"
    assert body["response_format"]["type"] == ("json_object" if reject else "json_schema")
    assert len(FakeOpenRouter.calls) == (2 if reject else 1)        # one fallback when JSON schema is rejected
    assert result["fields"]["image_status"]["value"] == "Usable"
    usage = result["meta"]["usage"]
    assert usage["total_tokens"] == 120 and usage["cost_usd"] == 0.0012 and usage["routed_to"] == "Google AI Studio"
    assert result["meta"]["provider"] == "openrouter" and result["meta"]["model"] == "google/gemini-test"
