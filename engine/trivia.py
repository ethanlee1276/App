"""Trivia in the stoppages: one question off the season logs at a timeout,
a break between periods or between innings, answered on the game page.

From the ideas list (docs/IDEAS.md, the live game list's eleventh): "At a
timeout or between innings, one question off the season logs ('Who leads
CIN in receiving yards?'), answered in the chat." A break in a game is the
part nobody watches; this gives it something to do.

WHEN A QUESTION IS ASKED. Read off the game's own deep file
(web/data/pbp/{league}_{id}.json), the one Call it reads (`stoppage`):
  * baseball — between half-innings (the scoreboard's "Middle 5th",
    "End 5th");
  * the rest — a timeout or the two-minute warning as the last play, the
    clock run out at the end of a period, or the scoreboard holding
    ("Halftime", "End of 3rd", a delay).
One question a break: the break's key names it, and the room keeps the
question it was asked (`trivia_asked`) so every reader sees the same one
and no question comes back in the same game.

WHAT IS ASKED. Who leads one of the two teams in a stat this season, or
who has the most of it across both, four names to choose from: the season
logs the boards read (player_game_logs, the history database), a team's
rows under every spelling the feeds use for it. A team with fewer than
MIN_TEAM_GAMES games logged this season is asked about last season, and
the question says so. A stat whose top two are tied is not asked.

ANSWERED ONCE. A free account answers a question once, while its break
lasts; the right name and how the room answered show at once, as counts.
Kept: each answer with its account (``trivia_answers``), named in the
Privacy Policy, deleted with the account, and pruned with the question
after KEEP_S. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

LEAGUES = ("nfl", "cfb", "nba", "wnba", "nhl", "mlb")
#: The stats asked about, per kind of game: (market in the logs, words).
STATS = {
    "football": (("rec_yds", "receiving yards"), ("rush_yds", "rushing yards"), ("receptions", "catches"),
                 ("rec_td", "receiving touchdowns"), ("rush_td", "rushing touchdowns")),
    "hoops": (("pts", "points"), ("reb", "rebounds"), ("ast", "assists"), ("fg3m", "threes"),
              ("stl", "steals"), ("blk", "blocks")),
    "hockey": (("goals", "goals"), ("assists", "assists"), ("points", "points"), ("sog", "shots on goal"),
               ("hits", "hits")),
    "mlb": (("hits", "hits"), ("home_runs", "home runs"), ("total_bases", "total bases"),
            ("strikeouts", "strikeouts pitched")),
}
#: Names to choose from.
OPTIONS = 4
#: Games a team needs logged this season before this season is asked about.
MIN_TEAM_GAMES = 4
#: A game's questions are built once an hour at most (the logs move nightly).
BANK_TTL_S = 3600
#: Questions and answers are kept this long.
KEEP_S = 3 * 86400

_HOLD = re.compile(r"halftime|end of|delay|suspend", re.I)
_TIMEOUT = re.compile(r"timeout|two[- ]minute", re.I)
_INNING_BREAK = re.compile(r"^(middle|mid|end)\b", re.I)
_RUN_OUT = {"0:00", "0.0", "0:00.0", "00:00"}
_bank: dict = {}


def ensure_tables(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS trivia_asked (
        room TEXT NOT NULL, qkey TEXT NOT NULL, q TEXT NOT NULL, at REAL NOT NULL,
        PRIMARY KEY (room, qkey));
      CREATE TABLE IF NOT EXISTS trivia_answers (
        user_id INTEGER NOT NULL, room TEXT NOT NULL, qkey TEXT NOT NULL,
        pick INTEGER NOT NULL, at REAL NOT NULL,
        PRIMARY KEY (user_id, room, qkey));
      CREATE INDEX IF NOT EXISTS trivia_answers_q ON trivia_answers (room, qkey);
    """)
    conn.commit()


def _kind(league: str) -> str:
    return {"nfl": "football", "cfb": "football", "nba": "hoops", "wnba": "hoops",
            "nhl": "hockey", "mlb": "mlb"}.get(league, "")


def room_of(doc: dict) -> str:
    return f"{(doc or {}).get('league') or ''}_{(doc or {}).get('event_id') or ''}"


def stoppage(doc: dict) -> str | None:
    """The key of the break the game is in now, or None while play is on.
    js/detail.js trStop reads the same file the same way, so the page asks
    only when there is something to ask."""
    live = (doc or {}).get("live") or {}
    if str(live.get("state") or "") != "live":
        return None
    period = str(live.get("period") or "").strip()
    if (doc or {}).get("league") == "mlb":
        return f"inn:{period}" if _INNING_BREAK.match(period) else None
    hold = str(live.get("hold") or "").strip()
    if hold and _HOLD.search(hold):
        return f"hold:{period}:{hold.lower()[:24]}"
    plays = [p for p in (doc or {}).get("plays") or [] if isinstance(p, dict)]
    last = plays[-1] if plays else {}
    if _TIMEOUT.search(str(last.get("event") or "")):
        return f"to:{last.get('id') or len(plays)}"
    if str(live.get("clock") or "").strip() in _RUN_OUT:
        return f"brk:{period}"
    return None


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def _shuffled(items: list, seed: int) -> list:
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        seed = (seed * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        j = seed % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def _totals(hist, league: str, team: str, markets) -> tuple:
    """({market: [(total, player)] best first}, season label) for one team:
    this season's, or last season's when this one is too young."""
    from .divisions import spellings
    names = spellings(league, team) or [team]
    marks = ",".join("?" * len(names))
    row = hist.execute("SELECT MAX(season) FROM player_game_logs WHERE sport=?", (league,)).fetchone()
    season = row[0] if row else None
    if season is None:
        return {}, ""
    when = "this season"
    games = hist.execute(f"SELECT COUNT(DISTINCT game_id) FROM player_game_logs WHERE sport=? AND season=? "
                         f"AND team IN ({marks})", (league, season, *names)).fetchone()[0]
    if games < MIN_TEAM_GAMES:
        season, when = season - 1, "last season"
    mk = ",".join("?" * len(markets))
    out: dict = {}
    for player, market, total in hist.execute(
            f"SELECT player, market, SUM(value) FROM player_game_logs WHERE sport=? AND season=? "
            f"AND team IN ({marks}) AND market IN ({mk}) GROUP BY player, market",
            (league, season, *names, *markets)):
        if player and total and total > 0:
            out.setdefault(market, []).append((float(total), str(player)))
    for rows in out.values():
        rows.sort(key=lambda r: (-r[0], r[1]))
    return out, when


def _num(v: float) -> str:
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.1f}"


def bank(hist, league: str, home: str, away: str, now: float | None = None) -> list:
    """Every question this game can ask: [{text, options, answer, why}],
    in a fixed order for the game. Built once an hour at most."""
    t = time.time() if now is None else now
    key = (league, home, away)
    hit = _bank.get(key)
    if hit and t - hit[0] < BANK_TTL_S:
        return hit[1]
    stats = STATS.get(_kind(league), ())
    markets = [m for m, _w in stats]
    per = {team: _totals(hist, league, team, markets) for team in (away, home) if team}
    out = []
    for market, words in stats:
        for team, (totals, when) in per.items():
            rows = totals.get(market) or []
            if len(rows) < OPTIONS or rows[0][0] == rows[1][0]:
                continue
            verb = "leads" if when == "this season" else "led"
            out.append(_question(f"Who {verb} {team} in {words} {when}?", rows[:OPTIONS], words,
                                 _seed(league, home, away, market, team)))
        both = [r for team, (totals, _w) in per.items() for r in (totals.get(market) or [])[:2]]
        whens = {w for _t, w in per.values()}
        if len(per) == 2 and len(both) == OPTIONS and len(whens) == 1:
            both.sort(key=lambda r: (-r[0], r[1]))
            when = whens.pop()
            if both[0][0] != both[1][0]:
                out.append(_question(f"Who {'has' if when == 'this season' else 'had'} the most {words} {when} "
                                     f"of these four?", both, words, _seed(league, home, away, market, "both")))
    out = _shuffled(out, _seed(league, home, away))
    _bank[key] = (t, out)
    return out


def _question(text: str, rows: list, words: str, seed: int) -> dict:
    """Four names, the leader among them in a shuffled place."""
    best = rows[0]
    order = _shuffled(rows, seed)
    return {"text": text, "options": [p for _v, p in order], "answer": order.index(best),
            "why": f"{best[1]}: {_num(best[0])} {words}"}


def _asked(conn, room: str, qkey: str):
    row = conn.execute("SELECT q, at FROM trivia_asked WHERE room=? AND qkey=?", (room, qkey)).fetchone()
    return (json.loads(row[0]), row[1]) if row else (None, None)


def ask(conn, hist, doc: dict, now: float | None = None) -> tuple:
    """(qkey, question) for the break the game is in, asking the room's
    next question the first time the break is seen; (None, None) while
    play is on or when the game has no question left."""
    t = time.time() if now is None else now
    qkey = stoppage(doc)
    if not qkey:
        return None, None
    room = room_of(doc)
    q, _at = _asked(conn, room, qkey)
    if q is not None:
        return qkey, q
    used = {json.loads(r[0]).get("text") for r in conn.execute("SELECT q FROM trivia_asked WHERE room=?", (room,))}
    pool = bank(hist, str(doc.get("league") or ""), str(doc.get("home") or ""), str(doc.get("away") or ""), t)
    fresh = next((x for x in pool if x["text"] not in used), None)
    if fresh is None:
        return None, None
    conn.execute("INSERT OR IGNORE INTO trivia_asked (room, qkey, q, at) VALUES (?, ?, ?, ?)",
                 (room, qkey, json.dumps(fresh), t))
    prune(conn, t)  # a new question is rare (a break a game): the time to sweep
    q, _at = _asked(conn, room, qkey)
    return qkey, q


def _split(conn, room: str, qkey: str) -> list:
    counts = [0] * OPTIONS
    for pick, n in conn.execute("SELECT pick, COUNT(*) FROM trivia_answers WHERE room=? AND qkey=? GROUP BY pick",
                                (room, qkey)):
        if 0 <= int(pick) < OPTIONS:
            counts[int(pick)] = int(n)
    return counts


def _mine(conn, user_id, room: str, qkey: str):
    if not user_id:
        return None
    row = conn.execute("SELECT pick FROM trivia_answers WHERE user_id=? AND room=? AND qkey=?",
                       (int(user_id), room, qkey)).fetchone()
    return int(row[0]) if row else None


def _view(conn, user_id, room: str, qkey: str, q: dict, open_: bool, at=None) -> dict:
    """A question as the page draws it: the answer and the room's split only
    once this reader has answered, or once its break is over."""
    mine = _mine(conn, user_id, room, qkey)
    out = {"qkey": qkey, "text": q["text"], "options": q["options"], "mine": mine, "open": open_}
    if mine is not None or not open_:
        out.update(answer=q["answer"], why=q["why"], split=_split(conn, room, qkey))
    if at is not None:
        out["at"] = at
    return out


def state(conn, hist, user_id, doc: dict, now: float | None = None) -> dict:
    """The page's card: the open question (or the last one, with its
    answer), and whether this reader can answer."""
    t = time.time() if now is None else now
    room = room_of(doc)
    qkey, q = ask(conn, hist, doc, t)
    out = {"signed_in": bool(user_id), "open": None, "last": None}
    if q is not None:
        out["open"] = _view(conn, user_id, room, qkey, q, True)
    row = conn.execute("SELECT qkey, q, at FROM trivia_asked WHERE room=? AND qkey<>? ORDER BY at DESC LIMIT 1",
                       (room, qkey or "")).fetchone()
    if row:
        out["last"] = _view(conn, user_id, room, row[0], json.loads(row[1]), False, at=row[2])
    return out


def answer(conn, hist, user_id, doc: dict, qkey: str, pick, now: float | None = None) -> tuple:
    """(code, body): one answer per account per question, while its break lasts."""
    t = time.time() if now is None else now
    cur, q = ask(conn, hist, doc, t)
    if q is None or qkey != cur:
        return 409, {"error": "That question is over — the next one comes at the next break."}
    try:
        pick = int(pick)
    except (TypeError, ValueError):
        return 400, {"error": "Pick one of the four names."}
    if not 0 <= pick < len(q["options"]):
        return 400, {"error": "Pick one of the four names."}
    room = room_of(doc)
    if _mine(conn, user_id, room, qkey) is not None:
        return 409, {"error": "You already answered this one."}
    conn.execute("INSERT OR IGNORE INTO trivia_answers (user_id, room, qkey, pick, at) VALUES (?, ?, ?, ?, ?)",
                 (int(user_id), room, qkey, pick, t))
    conn.commit()
    return 200, _view(conn, user_id, room, qkey, q, True)


def prune(conn, now: float | None = None) -> None:
    old = (time.time() if now is None else now) - KEEP_S
    conn.execute("DELETE FROM trivia_answers WHERE at<?", (old,))
    conn.execute("DELETE FROM trivia_asked WHERE at<?", (old,))
    conn.commit()
