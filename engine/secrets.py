"""Load local API keys from a gitignored ``secrets.local`` file.

Put your keys in ``secrets.local`` at the project root, one per line::

    ODDS_API_KEY=your_key_here
    ODDS_API_KEY_2=a_second_plans_key      # optional spare, tried when the
    ODDS_API_KEY_3=a_third                 # one above runs out of credits

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

#: The PRODUCTION secrets file, read by systemd as `EnvironmentFile=` when
#: it starts the service.
#:
#: LOADED HERE TOO, and that omission cost an evening. On the droplet the
#: keys live in /etc/qellys/env and nowhere else — there is no
#: secrets.local on that box. systemd injects them into the SERVICE, and
#: into nothing else. So `python3 launch.py --stripe`, `--stripe-setup`
#: and `--todo`, all run by hand over ssh, saw an empty environment and
#: reported five things missing that were correctly configured three
#: inches away. The advice that follows from that report — "put the key
#: in the file" — is advice to do again the thing that already worked.
#:
#: Read-only and additive: values already in the environment always win,
#: so the service (which has them from systemd) is unaffected, and this
#: only ever fills in gaps for a human at a prompt.
_SYSTEM_ENV_FILE = Path(os.environ.get("QB_ENV_FILE", "").strip()
                        or "/etc/qellys/env")

_loaded = False


def _read_into_environ(target: Path) -> None:
    """`KEY=VALUE` lines into os.environ. Missing or unreadable = no-op.

    UNREADABLE IS NOT AN ERROR. /etc/qellys/env is mode 600 and owned by
    root; a developer running a script as themselves gets a
    PermissionError, and that must be a quiet miss rather than a crash in
    every tool that touches a key.
    """
    try:
        if not target.is_file():
            return
        text = target.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        # Strip surrounding quotes if the user wrapped the value.
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


def load_local_secrets(path: Path | None = None) -> None:
    """Read ``secrets.local`` into ``os.environ`` (once). Missing file = no-op.

    Existing environment variables are never overwritten, so an explicit
    ``export`` still takes precedence over the file.
    """
    global _loaded
    if _loaded and path is None:
        return

    # The system file first, so a per-project secrets.local can still
    # override it — "never overwrite what is already set" makes the FIRST
    # reader win, and a developer's own file should beat the box's.
    if path is None:
        _read_into_environ(_SYSTEM_ENV_FILE)

    _read_into_environ(path or _SECRETS_FILE)

    if path is None:
        _loaded = True
