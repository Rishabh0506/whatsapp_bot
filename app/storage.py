"""The bot's own log (SQLite): every message, photo and diagnosis. Feeds the debug panel now,
and model evaluation / new dataset material later."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, wa_id TEXT, direction TEXT, type TEXT, ts INTEGER, payload TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS media (
  media_id TEXT PRIMARY KEY, wa_id TEXT, message_id TEXT, path TEXT, mime TEXT, sha256 TEXT,
  size INTEGER, caption TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS diagnoses (
  id INTEGER PRIMARY KEY AUTOINCREMENT, wa_id TEXT, message_ids TEXT, media_ids TEXT, status TEXT,
  provider TEXT, model TEXT, prompt_version TEXT, decision TEXT, result TEXT, raw_output TEXT,
  error TEXT, latency_ms INTEGER, created_at REAL);
CREATE TABLE IF NOT EXISTS statuses (
  message_id TEXT, status TEXT, ts INTEGER, payload TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS sessions (
  wa_id TEXT PRIMARY KEY, name TEXT, last_inbound_ts INTEGER, state TEXT, updated_at REAL);
CREATE INDEX IF NOT EXISTS ix_diag_wa ON diagnoses(wa_id, id);
"""


class Storage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    def _exec(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # messages -------------------------------------------------------------
    def add_message(self, msg_id, wa_id, direction, type_, ts, payload) -> bool:
        """False if this message id was already stored (WhatsApp can deliver an event twice)."""
        try:
            self._exec("INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
                       (msg_id, wa_id, direction, type_, ts, json.dumps(payload), time.time()))
            return True
        except sqlite3.IntegrityError:
            return False

    def add_status(self, message_id, status, ts, payload):
        self._exec("INSERT INTO statuses VALUES (?,?,?,?,?)",
                   (message_id, status, ts, json.dumps(payload), time.time()))

    # media ------------------------------------------------------------------
    def add_media(self, media_id, wa_id, message_id, path, mime, sha256, size, caption):
        self._exec("INSERT OR REPLACE INTO media VALUES (?,?,?,?,?,?,?,?,?)",
                   (media_id, wa_id, message_id, str(path), mime, sha256, size, caption, time.time()))

    def media_path(self, media_id) -> str | None:
        rows = self._all("SELECT path FROM media WHERE media_id=?", (media_id,))
        return rows[0]["path"] if rows else None

    # sessions ---------------------------------------------------------------
    def touch_session(self, wa_id, name, ts):
        self._exec("""INSERT INTO sessions VALUES (?,?,?,?,?)
                      ON CONFLICT(wa_id) DO UPDATE SET name=excluded.name,
                      last_inbound_ts=excluded.last_inbound_ts, updated_at=excluded.updated_at""",
                   (wa_id, name, ts, "idle", time.time()))

    def last_inbound_ts(self, wa_id) -> int | None:
        rows = self._all("SELECT last_inbound_ts FROM sessions WHERE wa_id=?", (wa_id,))
        return rows[0]["last_inbound_ts"] if rows else None

    # diagnoses --------------------------------------------------------------
    def add_diagnosis(self, wa_id, message_ids, media_ids, result: dict | None, error: str | None) -> int:
        meta = (result or {}).get("meta", {})
        cur = self._exec(
            "INSERT INTO diagnoses (wa_id,message_ids,media_ids,status,provider,model,prompt_version,decision,"
            "result,raw_output,error,latency_ms,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wa_id, json.dumps(message_ids), json.dumps(media_ids), "error" if error else "ok",
             meta.get("provider"), meta.get("model"), meta.get("prompt_version"),
             ((result or {}).get("decision") or {}).get("action"),
             json.dumps(result, ensure_ascii=False) if result else None,
             (result or {}).get("raw_model_output"), error, meta.get("latency_ms"), time.time()))
        return cur.lastrowid

    def list_diagnoses(self, wa_id: str | None = None, limit: int = 20) -> list[dict]:
        sql = "SELECT * FROM diagnoses" + (" WHERE wa_id=?" if wa_id else "") + " ORDER BY id DESC LIMIT ?"
        rows = self._all(sql, ((wa_id,) if wa_id else ()) + (limit,))
        for r in rows:
            r["result"] = json.loads(r["result"]) if r["result"] else None
            r["message_ids"] = json.loads(r["message_ids"] or "[]")
            r["media_ids"] = json.loads(r["media_ids"] or "[]")
        return rows
