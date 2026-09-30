"""Persisted settings: one JSON file in the user's home directory."""

from __future__ import annotations

import json
from pathlib import Path

# The _qt suffix is historical -- it kept this build's settings apart from the
# retired tkinter one. Kept as-is so existing installs do not lose their
# Luna path and folder list.
CONFIG_PATH = Path.home() / ".luna_tpx3_gui_qt.json"
LEGACY_CONFIG_PATH = Path.home() / ".tpx3dump_gui_qt.json"

def load_config() -> dict:
    # LEGACY_CONFIG_PATH is the pre-rename filename; read it once so an
    # existing Luna path, folder list and theme survive the rename. Nothing
    # writes back to it -- save_config() always uses the new name.
    for path in (CONFIG_PATH, LEGACY_CONFIG_PATH):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass  # a config we cannot persist is not worth interrupting the user
