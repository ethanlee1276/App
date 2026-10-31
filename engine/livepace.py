"""Prop pace on a live game's page: every prop priced on the game, where the
player stands, the pace he is on, and the chance he clears the line —
free, and built from the market and the box score alone.

Ethan's research (2026-10-29): "Live prop pace vs. line: per-player pace
projection vs. the prop line ... Unique. Neither Apple Sports nor Real
offers it", a column of the live page it specifies (player, stat, line,
current, pace projection, % to hit), and in the free half of its funnel
("Free: live pages, Sweat Board for your own bets, prop pace, model win
probability").

WHAT IT READS. The props come off the league's board (the private copy,
gate.board_source: the full prop list lives under `recommendations`), but
only their MARKET half travels: the player, the market, the line and the
books' best over and under prices at that line (`all_lines`). Never the
side we took, our chance, the edge, the tier or the projection — the
paid half — and every prop priced on the game is listed alike, so nothing
here says which of them are our picks. Where he stands comes off the live
loop's own files (engine/sliplive.live_state: the box score, the clock).

THE NUMBERS. "On pace for" is his number divided by the share of
regulation played, once a sixth of the game is gone (before that a pace is
noise). The chance is engine/proplive's race — what he has banked and the
rest of the game to bank the remainder — anchored at the MARKET's no-vig
chance for the over at kickoff (the same function a saved slip's leg uses,
with the price in place of our number) and the market's own generic
dispersion, so it is the market's question watched live, not our model.
Baseball has no clock; its rows say where he stands and print no chance.

Cached CACHE_S per game: one read of the files per game however many
people have the page open. Standard library only.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
CACHE_S = 20
#: A pace before this share of the game is played is not printed.
PACE_FROM = 1 / 6
MAX_ROWS = 80
EVENT = re.compile(r"^\d{1,14}$")
_cache: dict = {}


def _read(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _game(league: str, event: str, web: Path) -> dict | None:
    from engine.sliplive import MLB_FILE
    doc = _read(web / "data" / (MLB_FILE if league == "mlb" else f"live_{league}.json")) or {}
    for g in doc.get("games") or []:
        if str(g.get("event_id") or g.get("game_pk") or "") == event:
            return g
    return None


def _best(lines, line, side: str):
    """The best price for a side at this line, and the book's pair for the fair."""
    at = [x for x in lines or [] if isinstance(x, dict) and x.get("line") is not None
          and abs(float(x["line"]) - float(line)) < 0.01 and x.get(f"{side}_odds") is not None]
    from engine.betclv import decimal
    return max(at, key=lambda x: decimal(x.get(f"{side}_odds")) or 0)[f"{side}_odds"] if at else None


def _fair_over(lines, line) -> float | None:
    from engine.odds import devig_two_way
    fairs = []
    for x in lines or []:
        try:
            if abs(float(x.get("line")) - float(line)) < 0.01 and x.get("over_odds") and x.get("under_odds"):
                f, _ = devig_two_way(x["over_odds"], x["under_odds"])
                if 0 < f < 1:
                    fairs.append(f)
        except (TypeError, ValueError):
            continue
    fairs.sort()
    return fairs[len(fairs) // 2] if fairs else None


def rows_for(league: str, event: str, web: Path = WEB, now: float | None = None) -> dict:
    """{"state", "share_left", "rows": [...]} for one game; rows each
    {player, team, market, line, over, under, current, pace, chance}."""
    from engine import gate
    from engine import proplive as PL
    from engine import sliplive as SL
    league, event = str(league or "").lower(), str(event or "")
    if league not in SL.FAST_LEAGUES + ("mlb",) or not EVENT.match(event):
        return {"rows": [], "state": ""}
    t = time.time() if now is None else float(now)
    key = (league, event, str(web))
    hit = _cache.get(key)
    if hit and t - hit[0] < CACHE_S:
        return hit[1]
    game = _game(league, event, Path(web))
    out: dict = {"rows": [], "state": ""}
    if game:
        home, away = str(game.get("home") or ""), str(game.get("away") or "")
        board = _read(gate.board_source(Path(web) / "data" / f"{league}.json")) or {}
        seen: set = set()
        rows = []
        for r in board.get("recommendations") or []:
            if not isinstance(r, dict) or r.get("market") in SL.GAME_MARKETS or r.get("line") is None:
                continue
            team, opp = str(r.get("team") or ""), str(r.get("opponent") or "")
            if team not in (home, away) or (opp and opp not in (home, away)):
                continue
            k = (str(r.get("player")), str(r.get("market")), float(r["line"]))
            if k in seen:
                continue
            seen.add(k)
            leg = {"league": league, "player": r.get("player"), "market": r.get("market"), "side": "over",
                   "line": r.get("line"), "row": {"home": home, "away": away}}
            lv = SL.live_state(leg, Path(web) / "data", t) or {}
            share = lv.get("share_left")
            cur = lv.get("current")
            pace = None
            if isinstance(cur, (int, float)) and isinstance(share, (int, float)) and 1 - share >= PACE_FROM:
                pace = round(cur / (1 - share), 1)
            fair = _fair_over(r.get("all_lines"), r["line"])
            chance = None
            if fair is not None and lv.get("state") == "live":
                got = PL.clock_chance(dict(leg, live=lv, prob=None, needs=fair, row=None), row={})
                chance = (got or {}).get("p")
            rows.append({"player": str(r.get("player") or "")[:60], "team": str(r.get("team") or "")[:8],
                         "market": str(r.get("market_label") or r.get("market") or "")[:32],
                         "line": r.get("line"), "over": _best(r.get("all_lines"), r["line"], "over"),
                         "under": _best(r.get("all_lines"), r["line"], "under"),
                         "current": cur, "pace": pace, "chance": chance, "result": lv.get("result")})
            out["state"] = lv.get("state") or out["state"]
            if isinstance(share, (int, float)):
                out["share_left"] = round(share, 3)
        # The biggest gaps between pace and line first; then by name.
        rows.sort(key=lambda x: (-(abs((x["pace"] or 0) - float(x["line"])) / max(1.0, float(x["line"])))
                                 if x["pace"] is not None else 1, x["player"]))
        out["rows"] = rows[:MAX_ROWS]
    _cache[key] = (t, out)
    return out
