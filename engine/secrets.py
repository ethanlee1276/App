"""Load local API keys from a gitignored ``secrets.local`` file.

Put your keys in ``secrets.local`` at the project root, one per line::

    ODDS_API_KEY=your_key_here

That file is gitignored, so your keys stay on your machine and never get
committed or pushed. Values already set in the real environment win, so you can
still override with ``export ODDS_API_KEY=...`` when you want to.

Standard library only — nothing to install.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root = one level up from this file (engine/secrets.py -> project/).
_SECRETS_FILE = Path(__file__).resolve().parent.parent / "secrets.local"

_loaded = False


def load_local_secrets(path: Path | None = None) -> None:
    """Read ``secrets.local`` into ``os.environ`` (once). Missing file = no-op.

    Existing environment variables are never overwritten, so an explicit
    ``export`` still takes precedence over the file.
    """
    global _loaded
    if _loaded and path is None:
        return

    target = path or _SECRETS_FILE
    if target.is_file():
        for raw in target.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            # Strip surrounding quotes if the user wrapped the value.
            value = value.strip().strip('"').strip("'")
            if name and name not in os.environ:
                os.environ[name] = value

    if path is None:
        _loaded = True
