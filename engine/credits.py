"""What is left on every paid key, printed where you will actually see it.

Ethan, 2026-08-09: "when we launch.py, start showing the quote for
credits left on the anthropic api key and also cfb api key and also both
odds api key."

`keycheck.py` already probes all four, and that is the problem — it is a
separate command, so the balance is only ever consulted by someone who
already suspects it is low. A quota runs out silently: the board still
builds, the odds adapter falls back to cached or proxy lines, and the
first symptom is prices that look a little stale for a few days.

WHAT EACH KEY CAN ACTUALLY TELL US, which is not the same for all four:

* **The Odds API** answers exactly. `/sports` does not count against
  quota and its reply carries `x-requests-remaining`, so proving a key
  works and reading its balance are one free request. Every key in the
  ring is checked, because the ring silently skips a spent key and
  "everything still works" is precisely how you fail to notice.

* **CollegeFootballData** publishes no balance. A call either works or it
  does not, so that is what gets reported — reachable, or the error.

* **Anthropic** has no credits-remaining endpoint at all. Reporting a
  guess would be worse than reporting nothing, so this shows SPEND, from
  the local ledger `hypotheses.py` already keeps: this month and all
  time. It costs no API call, which matters — a validation that bills you
  is not a diagnostic.

Never raises, never blocks for long. A banner that can break the launcher
is a banner that gets deleted the first time it does.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

#: Kept short deliberately. This runs before the site comes up, and a key
#: check is not worth making anyone wait for a hung socket.
TIMEOUT = 6


def _shape(key: str) -> str:
    """Enough to tell two keys apart, never enough to use one."""
    k = (key or "").strip()
    return f"…{k[-4:]}" if len(k) >= 4 else "(short)"


def odds_keys() -> list[dict]:
    """Balance for every key in the ring, via the free `/sports` call."""
    try:
        from .sources import oddsapi
        ring = oddsapi.api_keys()
    except Exception:                                       # noqa: BLE001
        return []
    out = []
    for key in ring:
        row = {"shape": _shape(key), "remaining": None, "used": None,
               "error": None}
        try:
            req = urllib.request.Request(
                f"{oddsapi.ODDS_BASE}/sports?apiKey={key}",
                headers={"User-Agent": "qellys-credits"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                row["remaining"] = resp.headers.get("x-requests-remaining")
                row["used"] = resp.headers.get("x-requests-used")
        except urllib.error.HTTPError as exc:
            # A spent key answers 401 with no balance header, so the code
            # is the reading. Saying "unknown" here would hide the one
            # state worth knowing.
            row["error"] = ("SPENT or rejected" if exc.code in (401, 403)
                            else f"HTTP {exc.code}")
        except Exception as exc:                            # noqa: BLE001
            row["error"] = type(exc).__name__
        out.append(row)
    return out


def cfbd() -> dict:
    """CollegeFootballData: reachable or not. It publishes no balance."""
    if not os.environ.get("CFBD_API_KEY"):
        return {"set": False}
    try:
        from .sources import cfbd as _c
        # Cached hard. This is a liveness check, not a data pull, and it
        # should not spend a call every time the launcher starts.
        rows = _c._get("/conferences", {}, "cfbd_credits.json", ttl=86400)
        return {"set": True, "ok": True, "rows": len(rows)}
    except Exception as exc:                                # noqa: BLE001
        return {"set": True, "ok": False, "error": type(exc).__name__}


def anthropic() -> dict:
    """SPEND, not balance — the API exposes no credits endpoint.

    Local ledger only, so this costs nothing and cannot itself be the
    thing that drains the key.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"set": False}
    try:
        from . import hypotheses
        r = hypotheses.llm_spend_report()
        return {"set": True, "month_usd": r["month_usd"],
                "total_usd": r["total_usd"], "runs": r["runs"]}
    except Exception:                                       # noqa: BLE001
        return {"set": True}


def lines(low_water: int = 500) -> list[str]:
    """The banner, as text lines. Empty when nothing is configured."""
    out: list[str] = []
    ring = odds_keys()
    if ring:
        parts, spent = [], 0
        for i, r in enumerate(ring, 1):
            if r["error"]:
                parts.append(f"#{i} {r['shape']} {r['error']}")
                spent += 1
            else:
                left = r["remaining"]
                parts.append(f"#{i} {r['shape']} {left} left")
                if str(left).isdigit() and int(left) <= low_water:
                    spent += 0      # low, not spent — flagged below
        out.append(f"  odds api ({len(ring)} key{'s' if len(ring) > 1 else ''}): "
                   + " · ".join(parts))
        # The total is what actually decides whether tonight's board can
        # be priced; a ring of three keys at 40 each is not "fine".
        nums = [int(r["remaining"]) for r in ring
                if r["remaining"] and str(r["remaining"]).isdigit()]
        if nums:
            total = sum(nums)
            flag = "  ← LOW" if total <= low_water else ""
            out.append(f"                  {total} credits across the ring{flag}")
        if spent:
            out.append(f"                  {spent} key(s) spent or rejected — "
                       f"the ring skips them silently")
    c = cfbd()
    if c.get("set"):
        out.append("  cfbd:            "
                   + ("reachable (no balance published by the API)"
                      if c.get("ok") else
                      f"FAILING — {c.get('error')}"))
    a = anthropic()
    if a.get("set"):
        if "month_usd" in a:
            out.append(f"  anthropic:       ${a['month_usd']:.2f} this month, "
                       f"${a['total_usd']:.2f} all time over {a['runs']} run(s)")
            out.append("                   (spend, not balance — the API "
                       "publishes no credits endpoint)")
        else:
            out.append("  anthropic:       key set")
    return out


def banner(low_water: int = 500) -> str:
    ls = lines(low_water)
    if not ls:
        return ""
    return "\nKeys and credits\n" + "\n".join(ls)
