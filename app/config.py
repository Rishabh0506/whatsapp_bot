"""Settings: config/settings.yaml for behaviour, .env for secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def load_env_file(path: Path) -> None:
    """Minimal .env reader (KEY=value per line). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Settings:
    """Nested settings with dotted access: settings.get("gemini.model")."""

    def __init__(self, data: dict, config_dir: Path = CONFIG_DIR, data_dir: Path = DATA_DIR):
        self.data = data
        self.config_dir = config_dir
        self.data_dir = data_dir

    @classmethod
    def load(cls, config_dir: Path = CONFIG_DIR, data_dir: Path = DATA_DIR, overrides: dict | None = None):
        load_env_file(config_dir.parent / ".env")
        data = yaml.safe_load((config_dir / "settings.yaml").read_text(encoding="utf-8")) or {}
        for dotted, value in (overrides or {}).items():
            node = data
            *parents, last = dotted.split(".")
            for p in parents:
                node = node.setdefault(p, {})
            node[last] = value
        return cls(data, config_dir, data_dir)

    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @staticmethod
    def secret(name: str, default: str = "") -> str:
        return os.environ.get(name, default)


@dataclass
class WhatsAppConnection:
    """Where the bot talks to 'WhatsApp': the built-in simulator or Meta's real Cloud API."""
    base_url: str          # Graph API base, e.g. https://graph.facebook.com/v23.0
    access_token: str
    phone_number_id: str
    verify_token: str      # for Meta's webhook verification handshake
    app_secret: str        # for checking the X-Hub-Signature-256 header on incoming webhooks


SIM_ACCESS_TOKEN = "SIM_ACCESS_TOKEN"
SIM_PHONE_NUMBER_ID = "100000000000001"
SIM_VERIFY_TOKEN = "sim-verify-token"
SIM_APP_SECRET = "sim-app-secret"


def whatsapp_connection(settings: Settings) -> WhatsAppConnection:
    if settings.get("channel.mode", "simulator") == "simulator":
        base = settings.get("app.public_base_url").rstrip("/")
        return WhatsAppConnection(f"{base}/sim/graph", SIM_ACCESS_TOKEN, SIM_PHONE_NUMBER_ID,
                                  SIM_VERIFY_TOKEN, SIM_APP_SECRET)
    version = settings.get("channel.graph_api_version", "v23.0")
    return WhatsAppConnection(
        f"https://graph.facebook.com/{version}",
        settings.secret("WHATSAPP_ACCESS_TOKEN"),
        settings.secret("WHATSAPP_PHONE_NUMBER_ID"),
        settings.secret("WHATSAPP_VERIFY_TOKEN"),
        settings.secret("WHATSAPP_APP_SECRET"),
    )
