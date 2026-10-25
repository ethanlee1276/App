"""Your players, live: each player you follow, his line in the game he is
playing right now, every league on one strip.

Ethan, 2026-10-25: "add more features ... create things I've never even
thought of." Real shows a game's plays; a fan who follows six players in
four games has to open four games to see how his guys are doing. This is
the one line per player — "Ja'Marr Chase · 6 rec, 94 yds, TD · Q3 4:12"
— from whichever game he is in, at the top of the Live tab.

WHAT IT READS. Nothing new is fetched. The fast loop already writes each
game's deep file (web/data/pbp/{league}_{id}.json, MLB's from live_build)
with the box score's `players` rows, and the hockey box beside it
(live_nhl_box.json, a different feed with the real skater lines). Each
file is read once per change (by mtime) and folded into one index of
lines by player name; a request is a dictionary lookup.

FREE. Box scores are public facts — the same numbers the game page's
Player stats tab draws to anyone, signed in or not. The watches are the
member's own (engine/alerts), so the strip is only theirs.

A game that ended stays on for FINAL_FOR_S after its file last changed,
so the line a player finished with is there when you look after the
game; a game not started has no line and is not shown.

Standard library only.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from engine.alerts import _fold

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web" / "data"
PBP_DIR = DATA / "pbp"
NHL_BOX = DATA / "live_nhl_box.json"
#: How long a finished game's lines stay on the strip after its last write.
FINAL_FOR_S = 6 * 3600
#: The most lines one strip carries (a follow list caps at twenty).
MAX_LINES = 20

_cache: dict = {}


def _n(v) -> int:
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return 0


def _join(parts) -> str:
    return ", ".join(p for p in parts if p)


def line(row: dict, league: str = "") -> str:
    """One player's game so far, in the words a box score uses, or "".

    The same reading as the play cards' (js/chat.js pcLine) so the strip
    and a card never describe one man two ways."""
    if not isinstance(row, dict):
        return ""
    L, s = row.get("line") or {}, row.get("stats") or {}
    if L.get("batting"):
        b = L["batting"]
        return _join([f"{_n(b.get('h'))}/{_n(b.get('ab'))}", f"{_n(b['hr'])} HR" if b.get("hr") else "",
                      f"{_n(b['rbi'])} RBI" if b.get("rbi") else "", f"{_n(b['bb'])} BB" if b.get("bb") else ""])
    if L.get("pitching"):
        q = L["pitching"]
        return _join([f"{q['ip']} IP" if q.get("ip") else "", f"{_n(q.get('k'))} K",
                      f"{_n(q['er'])} ER" if q.get("er") is not None else "", f"{_n(q['p'])} P" if q.get("p") else ""])
    if league == "nhl" or "sog" in s or "saves" in s:
        if "saves" in s or "shots_against" in s:
            return _join([f"{_n(s.get('saves'))} saves", f"{_n(s['goals_against'])} GA" if "goals_against" in s else ""])
        return _join([f"{_n(s['goals'])} G" if s.get("goals") else "", f"{_n(s['assists'])} A" if s.get("assists") else "",
                      f"{_n(s.get('sog'))} SOG"])
    parts = []
    if s.get("pass_att") or s.get("pass_yds"):
        cmp_att = f"{_n(s['pass_cmp'])}/{_n(s['pass_att'])}, " if s.get("pass_att") else ""
        parts.append(_join([f"{cmp_att}{_n(s.get('pass_yds'))} pass yds",
                            f"{_n(s['pass_td'])} TD" if s.get("pass_td") else "",
                            f"{_n(s['pass_int'])} INT" if s.get("pass_int") else ""]))
    if s.get("carries"):
        parts.append(_join([f"{_n(s['carries'])} car, {_n(s.get('rush_yds'))} yds",
                            f"{_n(s['rush_td'])} TD" if s.get("rush_td") else ""]))
    if s.get("receptions") or s.get("rec_yds"):
        parts.append(_join([f"{_n(s.get('receptions'))} rec, {_n(s.get('rec_yds'))} yds",
                            f"{_n(s['rec_td'])} TD" if s.get("rec_td") else ""]))
    if parts:
        return " · ".join(parts[:2])
    if s.get("pts") is not None:
        return _join([f"{_n(s['pts'])} pts", f"{_n(s['reb'])} reb" if s.get("reb") else "",
                      f"{_n(s['ast'])} ast" if s.get("ast") else "",
                      f"{_n(s['fg3m'])} 3PM" if s.get("fg3m") else ""])
    return ""


def _status(live: dict) -> tuple[str, str]:
    """``(state, words)`` — "live" with the clock as the board says it, or
    "final"; anything else is not on."""
    st = str((live or {}).get("state") or "").lower()
    if st in ("in", "live"):
        return "live", str(live.get("detail") or "").strip() or "Live"
    if st in ("post", "final"):
        return "final", "Final"
    return "", ""


def _from_doc(doc: dict, mtime: float, now: float) -> list[dict]:
    league = str(doc.get("league") or "")
    state, words = _status(doc.get("live") or {})
    if not state or (state == "final" and now - mtime > FINAL_FOR_S):
        return []
    home, away = str(doc.get("home") or ""), str(doc.get("away") or "")
    live = doc.get("live") or {}
    out = []
    for r in doc.get("players") or []:
        txt = line(r, league)
        name = str((r or {}).get("player") or "").strip()
        if not txt or not name:
            continue
        team = str(r.get("team") or "")
        out.append({"player": name, "team": team, "opp": away if team == home else home if team == away else "",
                    "league": league, "event_id": str(doc.get("event_id") or ""), "line": txt,
                    "state": state, "status": words,
                    "score": f"{away} {_n(live.get('away_score'))}–{_n(live.get('home_score'))} {home}"})
    return out


def _read(path: Path):
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None, 0.0
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1], mtime
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None, mtime
    _cache[str(path)] = (mtime, doc)
    return doc, mtime


def index(pbp_dir: Path = PBP_DIR, nhl_box: Path = NHL_BOX, now: float | None = None) -> dict:
    """``{folded name: [line, ...]}`` across every live or just-finished game."""
    t = time.time() if now is None else now
    idx: dict = {}
    nhl_games: dict = {}
    seen = set()
    for path in sorted(Path(pbp_dir).glob("*.json")) if Path(pbp_dir).is_dir() else []:
        seen.add(str(path))
        doc, mtime = _read(path)
        if not isinstance(doc, dict):
            continue
        if doc.get("league") == "nhl":
            # Hockey's lines come from the league's own box below; the deep
            # file only says which game id the page opens.
            nhl_games[(doc.get("away"), doc.get("home"))] = (doc, mtime)
            continue
        for e in _from_doc(doc, mtime, t):
            idx.setdefault(_fold(e["player"]), []).append(e)
    box, mtime = _read(Path(nhl_box))
    for g in (box or {}).get("games") or [] if isinstance(box, dict) else []:
        doc, _m = nhl_games.get((g.get("away"), g.get("home")), (None, 0.0))
        if not doc:
            continue
        merged = dict(doc, players=g.get("players") or [])
        for e in _from_doc(merged, mtime, t):
            idx.setdefault(_fold(e["player"]), []).append(e)
    for k in [k for k in _cache if k not in seen and k != str(nhl_box)]:
        _cache.pop(k, None)
    return idx


def mine(watches, idx: dict | None = None) -> list[dict]:
    """The lines for a member's player watches: live games first, in the
    order they were followed, one line per player per game."""
    idx = index() if idx is None else idx
    out, seen = [], set()
    for w in watches or []:
        key = _fold((w or {}).get("value"))
        if (w or {}).get("kind") != "player" or key in seen:
            continue
        seen.add(key)
        out.extend(idx.get(key, []))
    out.sort(key=lambda e: 0 if e["state"] == "live" else 1)
    return out[:MAX_LINES]
