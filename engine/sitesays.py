"""What the running site says about its own switches, for the owner's reports.

The reports run as the qellys user (`sudo -u qellys python3 -m ...`), and
only root reads the service's settings file, so a report's own environment
has none of the switches the service was started with. Judged by that, on
2026-10-29 engine.analytics printed "Switched OFF: nothing is being
counted" and engine.engagement "Activity: OFF" in Ethan's catch-up while
the site was counting and keeping. The site answers for itself on the
box's loopback: GET /api/billing/status is public (the plans page reads it
before anybody signs in) and carries the switches (`analytics`,
`activity_switch`, `split_switch`, `closeboard_switch`). So when a report's
shell was not told a switch, it asks the site, and says which it went by.
"""
from __future__ import annotations

import json
import os
import urllib.request

URL = "http://127.0.0.1:8000/api/billing/status"
SITE = "the running site"
SHELL = "this shell"


def ask(key: str, url: str | None = None, timeout: float = 3.0):
    """The running site's answer for one switch: True or False, or None when
    nothing answers (the service is down, or this is not the box)."""
    try:
        with urllib.request.urlopen(url or URL, timeout=timeout) as r:   # noqa: S310 — the box's own loopback
            got = json.loads(r.read().decode("utf-8") or "{}")
    except Exception:                                                     # noqa: BLE001 — no answer is an answer
        return None
    v = got.get(key) if isinstance(got, dict) else None
    return v if isinstance(v, bool) else None


def switch(env: str, here, key: str) -> tuple:
    """(on, whose): this shell's own answer, ``here()``, when its environment
    names ``env`` at all; otherwise the running site's for ``key`` (on is
    None when it does not answer)."""
    if env in os.environ:
        return bool(here()), SHELL
    return ask(key), SITE
