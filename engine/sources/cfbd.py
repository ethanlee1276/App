"""CollegeFootballData — the high-school layer, and the only feed that has it.

The college model's biggest parked item was §6: recruiting composites,
blue-chip ratio, returning production, the portal. All four are versions of
the same question — *how good are these players before they have played a
game against anyone* — and in September that question is the whole
projection. A 12-game season with annual roster turnover means Week 3
results are nearly meaningless on their own; the preseason prior is what
carries the number until the season accumulates.

That prior is built from high-school recruiting. A blue-chip ratio is
literally the share of a roster that was rated 4- or 5-star coming out of
high school, and the talent composite is those ratings rolled up across
four classes.

**This feed needs a free key.** api.collegefootballdata.com issues them at
collegefootballdata.com/key — put ``CFBD_API_KEY`` in ``secrets.local``
alongside the odds key. Without one, every function here raises
:class:`DataUnavailable` and the model degrades the way it already does
for a missing source: the talent prior is absent, the build says so, and
ratings fall back to results-only shrinkage toward the league mean. That
is a worse model in September and an identical one in November — which is
exactly the shape of the thing the prior is for.

Endpoints used (all GET, Bearer auth, generous free tier):

  /talent                  → team talent composite, one row per team-year
  /recruiting/teams        → class rankings and points
  /recruiting/players      → individual recruits with star ratings
  /player/returning        → returning production (PPA share)
  /player/portal           → transfer portal moves

Everything is cached hard: a recruiting class does not change after
signing day, and returning production does not change during the season.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .fetch import CACHE_DIR, DataUnavailable
from ..secrets import load_local_secrets

BASE = "https://api.collegefootballdata.com"
UA = "qellys-book/0.1 (college football talent layer)"

# A signed recruiting class is immutable; returning production is fixed at
# the start of a season. Nothing here is worth re-fetching often.
SEASON_TTL = 30 * 24 * 3600
# 4- and 5-star recruits. The blue-chip ratio is the share of a roster
# drawn from these, and it is the single most durable predictor in the
# sport — no team has won a national title with a ratio under ~50%.
BLUE_CHIP_STARS = 4


class CFBDUnavailable(DataUnavailable):
    """No key, or the key was refused."""


def get_api_key(explicit: str | None = None) -> str:
    load_local_secrets()
    key = explicit or os.environ.get("CFBD_API_KEY")
    if not key:
        raise CFBDUnavailable(
            "No CollegeFootballData key. The recruiting/talent layer needs "
            "one — it is free at https://collegefootballdata.com/key. Put "
            "CFBD_API_KEY in secrets.local. Until then the college board "
            "runs without a preseason prior, which mostly costs accuracy in "
            "September.")
    return key


def _get(path: str, params: dict, cache_name: str,
         api_key: str | None = None, ttl: int = SEASON_TTL) -> list:
    """GET a CFBD endpoint with a long disk cache.

    A stale cache is preferred to an exception on a network failure: last
    year's talent composite is a fine answer, and losing the prior entirely
    because a request timed out would be the worse outcome.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path_c = CACHE_DIR / cache_name
    import time
    if path_c.exists() and (time.time() - path_c.stat().st_mtime) < ttl:
        try:
            return json.loads(path_c.read_text())
        except ValueError:
            pass

    key = get_api_key(api_key)
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}", "User-Agent": UA,
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise CFBDUnavailable(
                f"CollegeFootballData refused the key ({exc.code}). Check "
                f"CFBD_API_KEY in secrets.local.") from exc
        raise CFBDUnavailable(f"CFBD HTTP {exc.code}") from exc
    except Exception as exc:
        if path_c.exists():
            try:
                return json.loads(path_c.read_text())
            except ValueError:
                pass
        raise CFBDUnavailable(f"CFBD request failed: {exc}") from exc

    path_c.write_text(body)
    try:
        return json.loads(body)
    except ValueError as exc:
        raise CFBDUnavailable("CFBD returned something that isn't JSON") from exc


# --- parsers (pure) ---------------------------------------------------------
def parse_talent(rows: list) -> dict[str, float]:
    """``{school: composite talent rating}``.

    This is the four-class recruiting roll-up — the high-school ratings of
    everyone currently on the roster, summed and weighted.
    """
    out: dict[str, float] = {}
    for r in rows or []:
        school = (r.get("school") or r.get("team") or "").strip()
        try:
            val = float(r.get("talent"))
        except (TypeError, ValueError):
            continue
        if school:
            out[school] = val
    return out


def parse_blue_chip(rows: list) -> dict[str, dict]:
    """``{school: {blue_chips, recruits, ratio}}`` from individual recruits.

    Counted from star ratings rather than taken from a summary field, so
    the number means the same thing every year regardless of how a
    provider decides to present its class rankings.
    """
    agg: dict[str, list[int]] = {}
    for r in rows or []:
        school = (r.get("committedTo") or r.get("school") or "").strip()
        if not school:
            continue
        try:
            stars = int(r.get("stars") or 0)
        except (TypeError, ValueError):
            stars = 0
        slot = agg.setdefault(school, [0, 0])
        slot[1] += 1
        if stars >= BLUE_CHIP_STARS:
            slot[0] += 1
    return {s: {"blue_chips": bc, "recruits": n,
                "ratio": round(bc / n, 4) if n else 0.0}
            for s, (bc, n) in agg.items()}


def parse_returning(rows: list) -> dict[str, dict]:
    """``{school: {overall, offense, defense}}`` share of production back.

    A talented roster that lost most of its production is a different team
    from the same roster with everyone back, and the recruiting composite
    alone cannot tell them apart.
    """
    out: dict[str, dict] = {}
    for r in rows or []:
        school = (r.get("team") or r.get("school") or "").strip()
        if not school:
            continue

        def _pct(*keys):
            for k in keys:
                v = r.get(k)
                if v is not None:
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        continue
                    return v / 100.0 if v > 1.5 else v
            return None

        out[school] = {
            "overall": _pct("percentPPA", "percent_ppa"),
            "offense": _pct("percentPassingPPA", "percent_passing_ppa"),
            "defense": _pct("percentReceivingPPA", "percent_receiving_ppa"),
            "usage": _pct("usage", "percentUsage"),
        }
    return out


def parse_portal(rows: list) -> dict[str, dict]:
    """``{school: {in, out, net_stars}}`` from transfer-portal moves."""
    agg: dict[str, dict] = {}
    for r in rows or []:
        try:
            stars = float(r.get("stars") or 0)
        except (TypeError, ValueError):
            stars = 0.0
        dest = (r.get("destination") or "").strip()
        orig = (r.get("origin") or "").strip()
        if dest:
            a = agg.setdefault(dest, {"in": 0, "out": 0, "net_stars": 0.0})
            a["in"] += 1
            a["net_stars"] += stars
        if orig:
            a = agg.setdefault(orig, {"in": 0, "out": 0, "net_stars": 0.0})
            a["out"] += 1
            a["net_stars"] -= stars
    for a in agg.values():
        a["net_stars"] = round(a["net_stars"], 1)
    return agg


# --- fetch wrappers ---------------------------------------------------------
def fetch_talent(year: int, api_key: str | None = None) -> dict[str, float]:
    return parse_talent(_get("/talent", {"year": year},
                             f"cfbd_talent_{year}.json", api_key))


def fetch_blue_chip(year: int, api_key: str | None = None) -> dict[str, dict]:
    return parse_blue_chip(_get(
        "/recruiting/players",
        {"year": year, "classification": "HighSchool"},
        f"cfbd_recruits_{year}.json", api_key))


def fetch_returning(year: int, api_key: str | None = None) -> dict[str, dict]:
    return parse_returning(_get("/player/returning", {"year": year},
                                f"cfbd_returning_{year}.json", api_key))


def fetch_portal(year: int, api_key: str | None = None) -> dict[str, dict]:
    return parse_portal(_get("/player/portal", {"year": year},
                             f"cfbd_portal_{year}.json", api_key))


def blue_chip_ratio(year: int, classes: int = 4,
                    api_key: str | None = None) -> dict[str, dict]:
    """Blue-chip ratio across the last ``classes`` recruiting classes.

    Four is the right window because it is a roster: the players on the
    field this autumn were recruited across roughly four cycles, and a
    single class is far too noisy to describe a team.
    """
    agg: dict[str, list[int]] = {}
    seen = 0
    for y in range(year, year - classes, -1):
        try:
            rows = fetch_blue_chip(y, api_key)
        except DataUnavailable:
            continue
        seen += 1
        for school, d in rows.items():
            slot = agg.setdefault(school, [0, 0])
            slot[0] += d["blue_chips"]
            slot[1] += d["recruits"]
    if not seen:
        raise CFBDUnavailable("no recruiting classes could be fetched")
    return {s: {"blue_chips": bc, "recruits": n,
                "ratio": round(bc / n, 4) if n else 0.0, "classes": seen}
            for s, (bc, n) in agg.items()}
