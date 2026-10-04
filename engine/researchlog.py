"""Research picks written down before kickoff, for engine.scancard to grade.

Ethan, 2026-10-04: "do all of it" — the owner-only box where a research
report's picks are pasted before the games, so every week grades itself
the way the first weekend's six reports were graded by hand.

ONE LINE A PICK, in the order a report states it:

    Source | Player | TEAM | market | OVER/UNDER | line | chance | price

    TD scan | Chase Brown | CIN | anytime td | over | 0.5 | 60-62% | -145
    Deep scan | Tee Higgins | CIN | receptions | over | 4.5 | 67% | +106

The chance may be "62%", "0.62" or a range ("60-62%", read as its middle);
the price may be left as "-" when the report quoted none. A touchdown is
"anytime td", "td" or "atd" with the line 0.5. A line that does not read is
returned with its reason and stores nothing.

THE STORE is data/research_claims.json, never under web/ — these are the
owner's notes, not a public board. A pick is keyed by season, week,
source, player, market, side and line; posting it again keeps the FIRST
copy, because the claim that counts is the one made before the game.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "research_claims.json"
MAX_LINES = 200

MARKETS = {
    "anytime td": "anytime_td", "anytime_td": "anytime_td", "td": "anytime_td", "atd": "anytime_td",
    "anytime touchdown": "anytime_td", "touchdown": "anytime_td",
    "receptions": "receptions", "catches": "receptions", "rec": "receptions",
    "rec yds": "rec_yds", "receiving yards": "rec_yds", "rec_yds": "rec_yds", "receiving yds": "rec_yds",
    "rush yds": "rush_yds", "rushing yards": "rush_yds", "rush_yds": "rush_yds", "rushing yds": "rush_yds",
    "rush att": "rush_att", "rush attempts": "rush_att", "carries": "rush_att", "rush_att": "rush_att",
    "pass yds": "pass_yds", "passing yards": "pass_yds", "pass_yds": "pass_yds", "passing yds": "pass_yds",
    "pass td": "pass_td", "passing tds": "pass_td", "pass tds": "pass_td", "pass_td": "pass_td",
    "completions": "pass_cmp", "pass cmp": "pass_cmp", "pass_cmp": "pass_cmp",
    "pass att": "pass_att", "pass attempts": "pass_att", "pass_att": "pass_att",
}


def _path() -> Path:
    return Path(os.environ.get("QB_RESEARCH_STORE") or STORE)


def _chance(text: str) -> float | None:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")]
    if not nums:
        return None
    v = sum(nums[:2]) / min(len(nums), 2)
    v = v / 100.0 if v > 1 else v
    return round(v, 4) if 0 < v < 1 else None


def _price(text: str):
    t = (text or "").strip().replace("−", "-")
    if t in ("", "-", "—", "n/a", "na", "none"):
        return None
    if not re.fullmatch(r"[+-]?\d{3,5}", t):
        raise ValueError(f"price {text!r} is not an American price")
    return int(t)


def parse_line(line: str) -> dict:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) not in (7, 8):
        raise ValueError("needs 7 or 8 parts: Source | Player | TEAM | market | side | line | chance | price")
    src, player, team, market, side, ln, chance = parts[:7]
    price = parts[7] if len(parts) == 8 else ""
    mk = MARKETS.get(re.sub(r"\s+", " ", market.lower()))
    if not mk:
        raise ValueError(f"market {market!r} is not one this can grade")
    sd = side.strip().upper()
    sd = {"YES": "OVER", "O": "OVER", "U": "UNDER", "NO": "UNDER"}.get(sd, sd)
    if sd not in ("OVER", "UNDER"):
        raise ValueError(f"side {side!r} must be over or under")
    try:
        line_v = float(ln)
    except ValueError:
        raise ValueError(f"line {ln!r} is not a number") from None
    p = _chance(chance)
    if p is None:
        raise ValueError(f"chance {chance!r} does not read as a probability")
    if not src or not player or not re.fullmatch(r"[A-Za-z]{2,4}", team):
        raise ValueError("source, player and a 2-4 letter team are needed")
    return {"source": src[:40], "player": player[:60], "team": team.upper(), "market": mk,
            "side": sd, "line": line_v, "prob": p, "price": _price(price)}


def parse(text: str) -> tuple[list[dict], list[dict]]:
    """(claims, errors) — errors carry the line number and the reason."""
    claims, errors = [], []
    lines = [ln for ln in (text or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    for i, ln in enumerate(lines[:MAX_LINES], 1):
        try:
            claims.append(parse_line(ln))
        except ValueError as exc:
            errors.append({"line": i, "text": ln[:120], "error": str(exc)})
    if len(lines) > MAX_LINES:
        errors.append({"line": MAX_LINES + 1, "text": "", "error": f"only the first {MAX_LINES} lines are read"})
    return claims, errors


def _key(season: int, week: int, c: dict) -> str:
    from .tdmanfit import name_key
    return "|".join(str(x) for x in (season, week, c["source"].lower(), name_key(c["player"]),
                                      c["market"], c["side"], c["line"]))


def load_all(path=None) -> list[dict]:
    try:
        data = json.loads(Path(path or _path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data.get("claims", []) if isinstance(data, dict) else []


def load(season: int, week: int, path=None) -> list[dict]:
    return [c for c in load_all(path) if c.get("season") == season and c.get("week") == week]


def add(claims: list[dict], season: int, week: int, path=None, now=None) -> dict:
    """Store new claims; a claim already stored keeps its first copy."""
    p = Path(path or _path())
    have = load_all(p)
    keys = {_key(c["season"], c["week"], c) for c in have}
    stamp = now or _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    added = 0
    for c in claims:
        k = _key(season, week, c)
        if k in keys:
            continue
        keys.add(k)
        have.append({**c, "season": int(season), "week": int(week), "logged_at": stamp})
        added += 1
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"version": 1, "claims": have}, indent=1), encoding="utf-8")
    tmp.replace(p)
    return {"added": added, "kept_first": len(claims) - added,
            "week_total": sum(1 for c in have if c["season"] == season and c["week"] == week)}
