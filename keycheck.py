#!/usr/bin/env python3
"""Which API keys are present, correctly named, and actually working.

    python3 keycheck.py

NEVER PRINTS A KEY. Not the value, not a prefix, not the last four
characters. It reports the NAME, whether something is set, how long it is,
and what the provider says when asked — which is everything you need to fix
a missing or dead key and nothing you would mind in a screenshot. Anything
in a chat log or a terminal recording should be treated as exposed, so this
is built so that pasting its whole output costs nothing.

WHY IT EXISTS. `secrets.local` is gitignored, so a key put in it lives only
on the machine that has it. "I'm sure I added that one" and "it is under the
name the code reads" are different claims, and the failure looks identical
from the board: the college prior quietly disappears, the odds layer quietly
falls back to proxy lines. Both degrade politely, which is correct behaviour
and also why nobody notices for a month.

IT DOES NOT SPEND ANYTHING.

  * The Odds API is asked for ``/sports``, which the provider documents as
    not counting against quota, and the reply's ``x-requests-remaining``
    header is the balance — so the check that proves the key works is also
    the one that tells you what is left on it.
  * CollegeFootballData gets one small request.
  * **Anthropic is checked for presence only.** Every call to that API costs
    money, and a key-validation endpoint that bills you is not a diagnostic
    worth running. Whether it works is answered by `hypotheses.py`, which
    you run deliberately.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.secrets import load_local_secrets

ROOT = Path(__file__).resolve().parent
SECRETS = ROOT / "secrets.local"


def _shape(value: str) -> str:
    """Something true about a key that is not the key."""
    v = (value or "").strip()
    if not v:
        return "empty"
    bits = [f"{len(v)} chars"]
    if v != value:
        bits.append("has surrounding whitespace")
    if v.startswith(("'", '"')):
        bits.append("QUOTED — the loader strips quotes, but check it")
    if " " in v:
        bits.append("CONTAINS A SPACE — probably a paste accident")
    return ", ".join(bits)


def _scrub(text: str, *secrets: str) -> str:
    """Any key that made it into a provider's own words, taken back out.

    The only thing printed from a failed request is the response body, and a
    provider is entitled to say "invalid API key: abc123" in it. That would
    put the key in the output through a path nothing else here can see, so
    the last step before printing is to remove the values we know.
    """
    out = text or ""
    for s in secrets:
        s = (s or "").strip()
        if len(s) >= 8:
            out = out.replace(s, "<key>")
    return out


def _check_odds() -> None:
    from engine.sources import oddsapi

    ring = oddsapi.api_keys()
    print(f"\n  ODDS API — {len(ring)} key(s) in the ring")
    if not ring:
        print("    MISSING. Names read, in order: ODDS_API_KEY, then")
        print("    ODDS_API_KEYS (comma-separated), then ODDS_API_KEY_2,")
        print("    _3, and so on. Free key at the-odds-api.com.")
        return
    names = ["ODDS_API_KEY"] + [f"ODDS_API_KEY_{i}" for i in range(2, 9)]
    present = [n for n in names if os.environ.get(n)]
    if os.environ.get("ODDS_API_KEYS"):
        present.append("ODDS_API_KEYS")
    print(f"    set under: {', '.join(present) or '(none by name)'}")
    for i, key in enumerate(ring, 1):
        # /sports does not count against quota, and the reply carries the
        # balance — so proving the key works and reading what is left on it
        # are the same request.
        url = f"{oddsapi.ODDS_BASE}/sports?apiKey={key}"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "qellys-keycheck"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                left = resp.headers.get("x-requests-remaining", "?")
                used = resp.headers.get("x-requests-used", "?")
                n = len(json.loads(resp.read().decode("utf-8")))
            state = f"OK  {n} sports listed · {left} credits left, {used} used"
            if str(left).isdigit() and int(left) == 0:
                state += "   <- SPENT, the ring will skip it"
        except urllib.error.HTTPError as exc:
            body = _scrub(exc.read().decode("utf-8", "replace")[:120], key)
            state = f"HTTP {exc.code} — {body}"
        except Exception as exc:                              # noqa: BLE001
            state = f"unreachable: {type(exc).__name__}"
        print(f"    key {i}: {_shape(key)}")
        print(f"            {state}")


def _check_cfbd() -> None:
    from engine.sources import cfbd

    print("\n  COLLEGEFOOTBALLDATA — CFBD_API_KEY")
    raw = os.environ.get("CFBD_API_KEY")
    if not raw:
        print("    MISSING under that exact name. Free at")
        print("    collegefootballdata.com/key. Without it the college board")
        print("    runs with no preseason talent prior.")
        return
    print(f"    set: {_shape(raw)}")
    try:
        rows = cfbd._get("/conferences", {}, "cfbd_keycheck.json", ttl=0)
        print(f"    OK  {len(rows)} rows came back")
    except Exception as exc:                                  # noqa: BLE001
        print(f"    {type(exc).__name__}: {_scrub(str(exc), raw)[:150]}")


def _check_anthropic() -> None:
    print("\n  ANTHROPIC — ANTHROPIC_API_KEY")
    raw = os.environ.get("ANTHROPIC_API_KEY")
    if not raw:
        print("    MISSING under that exact name. The hypothesis lab and the")
        print("    nightly prose fall back to templates without it.")
        return
    print(f"    set: {_shape(raw)}")
    print("    NOT CALLED — every request to this API costs money, and a")
    print("    validation that bills you is not a diagnostic. Run")
    print("    `python3 hypotheses.py --dry-run` when you want it exercised.")


def main() -> int:
    load_local_secrets()
    print("=" * 78)
    print("API KEYS — names, presence, and what each provider says")
    print("=" * 78)
    if SECRETS.is_file():
        lines = [l for l in SECRETS.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        named = sorted({l.split("=", 1)[0].strip() for l in lines if "=" in l})
        print(f"  secrets.local: {len(lines)} entries — {', '.join(named)}")
        odd = [l.split('=')[0].strip() for l in lines if "=" not in l]
        if odd:
            print(f"  lines with no '=' (ignored by the loader): {odd}")
    else:
        print(f"  secrets.local: NOT FOUND at {SECRETS}")
        print("  Nothing below can pass. One NAME=value per line, no quotes,")
        print("  no 'export'. The file is gitignored.")

    _check_odds()
    _check_cfbd()
    _check_anthropic()

    print("\n" + "=" * 78)
    print("  Names are exact and case-sensitive. A key under a name the code")
    print("  does not read is invisible to it, and every consumer here fails")
    print("  softly — which is correct, and is why a missing key can sit")
    print("  unnoticed for a month. No key value is printed above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
