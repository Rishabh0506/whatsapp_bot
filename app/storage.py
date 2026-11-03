"""The bot's own database (SQLite): messages, photos, diagnoses, and each customer's open conversation.

Every conversation is one *case* (`cases` table); its messages, photos and diagnoses carry the case id.
What happens to a case when its conversation closes is set by `records.keep_after_close` in settings:
kept (testing) or deleted (real customers). Model cost numbers (`usage_log`) are always kept, without any
customer data, so models can be compared on cost either way."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, wa_id TEXT, direction TEXT, type TEXT, ts INTEGER, payload TEXT, created_at REAL,
  case_id TEXT);
CREATE TABLE IF NOT EXISTS media (
  media_id TEXT PRIMARY KEY, wa_id TEXT, message_id TEXT, path TEXT, mime TEXT, sha256 TEXT,
  size INTEGER, caption TEXT, created_at REAL, case_id TEXT);
CREATE TABLE IF NOT EXISTS diagnoses (
  id INTEGER PRIMARY KEY AUTOINCREMENT, wa_id TEXT, message_ids TEXT, media_ids TEXT, status TEXT,
  provider TEXT, model TEXT, prompt_version TEXT, decision TEXT, result TEXT, raw_output TEXT,
  error TEXT, latency_ms INTEGER, created_at REAL, case_id TEXT, try_no INTEGER, lang TEXT, reply TEXT,
  customer_text TEXT);
CREATE TABLE IF NOT EXISTS statuses (
  message_id TEXT, status TEXT, ts INTEGER, payload TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS sessions (
  wa_id TEXT PRIMARY KEY, name TEXT, last_inbound_ts INTEGER, state TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, wa_id TEXT, lang TEXT, started_at REAL, ended_at REAL, end_reason TEXT,
  outcome TEXT, tries INTEGER);
CREATE TABLE IF NOT EXISTS usage_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL, status TEXT, provider TEXT, model TEXT,
  prompt_version TEXT, routed_to TEXT, input_tokens INTEGER, output_tokens INTEGER, thinking_tokens INTEGER,
  total_tokens INTEGER, cost_usd REAL, latency_ms INTEGER, image_count INTEGER);
CREATE INDEX IF NOT EXISTS ix_diag_wa ON diagnoses(wa_id, id);
"""

# Columns added after the first version: added to an existing data/bot.db automatically.
NEW_COLUMNS = {
    "messages": ["case_id TEXT"],
    "media": ["case_id TEXT"],
    "diagnoses": ["case_id TEXT", "try_no INTEGER", "lang TEXT", "reply TEXT", "customer_text TEXT"],
}


class Storage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)
            for table, cols in NEW_COLUMNS.items():
                have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
                for col in cols:
                    if col.split()[0] not in have:
                        self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            self.db.execute("CREATE INDEX IF NOT EXISTS ix_diag_case ON diagnoses(case_id)")
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
    def add_message(self, msg_id, wa_id, direction, type_, ts, payload, case_id=None) -> bool:
        """False if this message id was already stored (WhatsApp can deliver an event twice)."""
        try:
            self._exec("INSERT INTO messages (id,wa_id,direction,type,ts,payload,created_at,case_id) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (msg_id, wa_id, direction, type_, ts, json.dumps(payload, ensure_ascii=False),
                        time.time(), case_id))
            return True
        except sqlite3.IntegrityError:
            return False

    def set_message_case(self, msg_id, case_id):
        self._exec("UPDATE messages SET case_id=? WHERE id=?", (case_id, msg_id))

    def add_status(self, message_id, status, ts, payload):
        self._exec("INSERT INTO statuses VALUES (?,?,?,?,?)",
                   (message_id, status, ts, json.dumps(payload), time.time()))

    # media ------------------------------------------------------------------
    def add_media(self, media_id, wa_id, message_id, path, mime, sha256, size, caption, case_id=None):
        self._exec("INSERT OR REPLACE INTO media (media_id,wa_id,message_id,path,mime,sha256,size,caption,"
                   "created_at,case_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (media_id, wa_id, message_id, str(path), mime, sha256, size, caption, time.time(), case_id))

    def set_media_case(self, media_id, case_id):
        self._exec("UPDATE media SET case_id=? WHERE media_id=?", (case_id, media_id))

    def media_path(self, media_id) -> str | None:
        rows = self._all("SELECT path FROM media WHERE media_id=?", (media_id,))
        return rows[0]["path"] if rows else None

    # sessions + open conversation ---------------------------------------------
    def touch_session(self, wa_id, name, ts):
        self._exec("""INSERT INTO sessions VALUES (?,?,?,?,?)
                      ON CONFLICT(wa_id) DO UPDATE SET name=excluded.name,
                      last_inbound_ts=excluded.last_inbound_ts, updated_at=excluded.updated_at""",
                   (wa_id, name, ts, None, time.time()))

    def last_inbound_ts(self, wa_id) -> int | None:
        rows = self._all("SELECT last_inbound_ts FROM sessions WHERE wa_id=?", (wa_id,))
        return rows[0]["last_inbound_ts"] if rows else None

    def get_state(self, wa_id) -> dict | None:
        """The customer's open conversation, or None when no conversation is open."""
        rows = self._all("SELECT state FROM sessions WHERE wa_id=?", (wa_id,))
        if not rows or not rows[0]["state"]:
            return None
        try:
            state = json.loads(rows[0]["state"])
        except json.JSONDecodeError:          # older databases stored the word "idle" here
            return None
        return state if isinstance(state, dict) else None

    def set_state(self, wa_id, state: dict | None):
        value = json.dumps(state, ensure_ascii=False) if state else None
        cur = self._exec("UPDATE sessions SET state=?, updated_at=? WHERE wa_id=?", (value, time.time(), wa_id))
        if cur.rowcount == 0 and state:
            self._exec("INSERT INTO sessions VALUES (?,?,?,?,?)", (wa_id, "", None, value, time.time()))

    def open_conversations(self) -> list[tuple[str, dict]]:
        out = []
        for r in self._all("SELECT wa_id, state FROM sessions WHERE state IS NOT NULL AND state LIKE '{%'"):
            try:
                out.append((r["wa_id"], json.loads(r["state"])))
            except json.JSONDecodeError:
                pass
        return out

    def delete_session(self, wa_id):
        self._exec("DELETE FROM sessions WHERE wa_id=?", (wa_id,))

    def session_name(self, wa_id) -> str:
        rows = self._all("SELECT name FROM sessions WHERE wa_id=?", (wa_id,))
        return (rows[0]["name"] or "") if rows else ""

    # cases ------------------------------------------------------------------
    def start_case(self, case_id, wa_id, started_at):
        self._exec("INSERT OR IGNORE INTO cases (id,wa_id,started_at) VALUES (?,?,?)", (case_id, wa_id, started_at))

    def update_case(self, case_id, **values):
        if not values:
            return
        cols = ", ".join(f"{k}=?" for k in values)
        self._exec(f"UPDATE cases SET {cols} WHERE id=?", (*values.values(), case_id))

    def get_case(self, case_id) -> dict | None:
        rows = self._all("SELECT * FROM cases WHERE id=?", (case_id,))
        return rows[0] if rows else None

    def delete_case(self, case_id):
        """Removes everything about one conversation: photos (files too), diagnoses, message content, statuses.
        Message ids stay (without content or phone number) so a late duplicate delivery is still recognised."""
        for row in self._all("SELECT path FROM media WHERE case_id=?", (case_id,)):
            try:
                Path(row["path"]).unlink(missing_ok=True)
            except OSError:
                pass
        with self.lock:
            ids = [r[0] for r in self.db.execute("SELECT id FROM messages WHERE case_id=?", (case_id,))]
            self.db.executemany("DELETE FROM statuses WHERE message_id=?", [(i,) for i in ids])
            self.db.execute("UPDATE messages SET wa_id=NULL, payload=NULL WHERE case_id=?", (case_id,))
            self.db.execute("DELETE FROM media WHERE case_id=?", (case_id,))
            self.db.execute("DELETE FROM diagnoses WHERE case_id=?", (case_id,))
            self.db.execute("DELETE FROM cases WHERE id=?", (case_id,))
            self.db.commit()

    # diagnoses --------------------------------------------------------------
    def add_diagnosis(self, wa_id, message_ids, media_ids, result: dict | None, error: str | None,
                      case_id=None, try_no=None, lang=None, customer_text=None) -> int:
        meta = (result or {}).get("meta", {})
        cur = self._exec(
            "INSERT INTO diagnoses (wa_id,message_ids,media_ids,status,provider,model,prompt_version,decision,"
            "result,raw_output,error,latency_ms,created_at,case_id,try_no,lang,customer_text) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wa_id, json.dumps(message_ids), json.dumps(media_ids), "error" if error else "ok",
             meta.get("provider"), meta.get("model"), meta.get("prompt_version"),
             ((result or {}).get("decision") or {}).get("action"),
             json.dumps(result, ensure_ascii=False) if result else None,
             (result or {}).get("raw_model_output"), error, meta.get("latency_ms"), time.time(),
             case_id, try_no, lang, customer_text))
        self.log_usage(result, error)
        return cur.lastrowid

    def set_diagnosis_reply(self, diag_id, reply):
        self._exec("UPDATE diagnoses SET reply=? WHERE id=?", (reply, diag_id))

    def log_usage(self, result: dict | None, error: str | None):
        """Cost and tokens of one model call. No phone number, photo or text: kept even when records are not."""
        meta = (result or {}).get("meta", {})
        u = meta.get("usage") or {}
        self._exec("INSERT INTO usage_log (created_at,status,provider,model,prompt_version,routed_to,input_tokens,"
                   "output_tokens,thinking_tokens,total_tokens,cost_usd,latency_ms,image_count) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (time.time(), "error" if error else "ok", meta.get("provider"), meta.get("model"),
                    meta.get("prompt_version"), u.get("routed_to"), u.get("input_tokens"), u.get("output_tokens"),
                    u.get("thinking_tokens"), u.get("total_tokens"), u.get("cost_usd"), meta.get("latency_ms"),
                    meta.get("image_count")))

    def list_diagnoses(self, wa_id: str | None = None, limit: int = 20) -> list[dict]:
        sql = ("SELECT d.*, s.name FROM diagnoses d LEFT JOIN sessions s ON s.wa_id = d.wa_id"
               + (" WHERE d.wa_id=?" if wa_id else "") + " ORDER BY d.id DESC LIMIT ?")
        rows = self._all(sql, ((wa_id,) if wa_id else ()) + (limit,))
        for r in rows:
            r["result"] = json.loads(r["result"]) if r["result"] else None
            r["message_ids"] = json.loads(r["message_ids"] or "[]")
            r["media_ids"] = json.loads(r["media_ids"] or "[]")
        return rows
