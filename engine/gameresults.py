"""What happened to every pick on a finished game (2026-11-16).

Ethan, 2026-11-16, with a finished Pacers at 76ers page: "when a game is
already over and someone goes and clicks on this game page ... we need to
show in all of these ... what the outcome was of the game and if these props
won or lost and if the parlays won or lost and what legs won and lost and if
our game report and reads was correct ... for all sports."

The journal already grades every pick a board posts (engine/ledger: the
Most Likely rows, the edge picks, the matchup picks, every parlay leg, the
long shots), each against the box score with its own rules: name spellings,
summed markets, doubleheader legs, a player who did not play voided. This
reads those verdicts back for the board being published and stamps them on
it (`stamp`, from engine/gate.publish, so every league's board gets it from
one place): {"<player>|<market>": {"a": the actual number}} for a graded
pick, {"v": 1} for a voided one. The page grades each pick it shows at that
pick's own line and side, the journal's way (ledger._grade_side_aware), so a
parlay's legs, the report's picks and the reads' picks are marked from the
same numbers as the Most Likely cards; a game bet is graded off the final
score. A pick the journal has not graded yet has no entry, and the page says
it is waiting on the box score. Paid, as the picks are (engine/gate.PAID_KEYS).
"""
from __future__ import annotations

import re
import unicodedata

KEY = "pick_results"
#: The journal's game markets (engine/ledger.GAME_MARKETS), graded off the score on the page.
GAME_MARKETS = ("moneyline", "total", "spread", "team_total")
SPORTS = ("nfl", "cfb", "mlb", "nba", "wnba", "cbb", "nhl")
#: The two original boards name no sport in their payload: the file says it
#: (engine/gate's board list). The NFL's went out without its results for it.
LABEL_SPORT = {"recommendations.json": "nfl", "mlb_recommendations.json": "mlb"}


def norm(name) -> str:
    """A player's name as the page and this module both key it: accents
    dropped, lower case, letters and digits only."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]", "", s)


def key(player, market, leg=None) -> str:
    """``"<player>|<market>"``, and ``|<leg>`` for a doubleheader's second game."""
    k = f"{norm(player)}|{str(market or '').strip().lower()}"
    try:
        n = int(leg or 1)
    except (TypeError, ValueError):
        n = 1
    return f"{k}|{n}" if n > 1 else k


def bet_of(r) -> dict | None:
    """A pick in the shape the page grades it on a finished game: the
    market, the side and the line, with who (a player) or which club and
    against whom (a game bet, graded off the final score). None for a row
    that is no pick."""
    if not isinstance(r, dict) or not r.get("market"):
        return None
    market = str(r["market"])
    out = {"market": market, "side": str(r.get("side") or "").lower(), "line": r.get("line")}
    for k in ("player", "team", "opponent", "home", "away"):
        if r.get(k):
            out[k] = r[k]
    if r.get("kind") == "game" or r.get("_game_leg") or market in GAME_MARKETS:
        out["game"] = True
        out.pop("player", None)
    if r.get("leg"):
        out["leg"] = r["leg"]
    return out


def read_bet(r) -> dict | None:
    """The pick a read stands on: its Most Likely pick, else its matchup
    pick unless the board held it back (gamereport.read_pick's order)."""
    if not isinstance(r, dict):
        return None
    for k in ("pick", "matchup_pick"):
        p = r.get(k)
        if isinstance(p, dict) and p and not (k == "matchup_pick" and p.get("held_note")):
            return bet_of(dict(p, player=p.get("player") or r.get("player"), team=p.get("team") or r.get("team")))
    return None


def read(sport: str, date: str, path=None) -> dict:
    """The journal's verdicts for one board (sport, the board's own date
    label), read-only: a board's publish never writes the journal. {} when
    the journal is not there or has graded nothing for it yet."""
    import sqlite3
    from pathlib import Path
    if not sport or not date:
        return {}
    if path is None:
        from . import ledger
        path = ledger.DEFAULT_DB
    p = Path(str(path))
    if not p.exists():
        return {}
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(bets)")}
        leg = "leg" if "leg" in cols else "NULL"
        marks = ",".join("?" * len(GAME_MARKETS))
        rows = conn.execute(
            f"SELECT player, market, status, actual, {leg} FROM bets WHERE sport=? AND date=? "
            f"AND status IN ('won', 'lost', 'push', 'void') AND market NOT IN ({marks})",
            (sport, date, *GAME_MARKETS)).fetchall()
    finally:
        conn.close()
    out: dict = {}
    for player, market, status, actual, n in rows:
        if not player or not market:
            continue
        k = key(player, market, n)
        if status == "void":
            out.setdefault(k, {"v": 1})
        elif actual is not None:
            # A graded copy wins over a voided one: the box scored him.
            out[k] = {"a": round(float(actual), 2)}
    return out


def stamp(payload: dict, label: str = "", path=None) -> int:
    """The board's graded picks, stamped under KEY when it has any; the
    number stamped. A board of another kind, or no journal, is left alone."""
    if not isinstance(payload, dict):
        return 0
    from pathlib import Path
    sport = str(payload.get("sport") or LABEL_SPORT.get(Path(str(label or "")).name, "")).lower()
    if sport not in SPORTS or not isinstance(payload.get("games"), list):
        return 0
    got = read(sport, str(payload.get("date") or ""), path)
    if got:
        payload[KEY] = got
    else:
        payload.pop(KEY, None)
    return len(got)
