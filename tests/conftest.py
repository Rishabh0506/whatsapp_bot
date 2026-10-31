import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.core.reference import Reference  # noqa: E402


def make_config(tmp: Path, use_real_reference: bool = False) -> Path:
    """A throwaway copy of config/ for tests. Uses the small fixture reference unless the real one exists."""
    cfg = tmp / "config"
    shutil.copytree(ROOT / "config", cfg, ignore=shutil.ignore_patterns("*.xlsx"))
    real = (ROOT / "config" / "reference" / "lists.json").exists()
    if not (use_real_reference and real):
        for name in ("lists.json", "universe.json"):
            shutil.copy(ROOT / "tests" / "fixtures" / name, cfg / "reference" / name)
    return cfg


@pytest.fixture
def config_dir(tmp_path):
    return make_config(tmp_path)


@pytest.fixture
def reference(config_dir):
    return Reference.load(config_dir)


@pytest.fixture
def settings(config_dir, tmp_path):
    return Settings.load(config_dir, tmp_path / "data", overrides={"core.provider": "mock"})
