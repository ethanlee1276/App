"""Call it: before each at-bat or drive, call how it ends; the box grades it.

Ethan, 2026-10-25: "create things I've never even thought of." A game you
are watching becomes one you play along with: before the next batter, Hit,
Out, Strikeout or Walk; before the next drive, Touchdown, Field goal, Punt
or Turnover. The live loop's own deep file says how it ended a few seconds
later, and the room keeps score. No money, no prices, nothing the model
thinks — a game about the game, free like the score.

WHAT IS OPEN, AND WHEN IT LOCKS. One unit at a time per game, read off the
deep file (web/data/pbp/{league}_{id}.json):
  * baseball — the at-bat being played (MLB numbers them; ``ab{index}``),
    open until its second pitch is thrown, and between at-bats for the one
    coming up;
  * football — the next drive to finish (``dr{n}``, n the drives already
    ended), open between drives and through the drive's first two plays.
A call can be changed while its unit is open and never after. A unit the
game ends without (the half runs out, a batter reaches on an error) is
void: it counts for nobody and breaks nobody's streak.

GRADED LAZILY. Anybody looking at a game grades that game's open calls off
the file in hand, so no clock runs for it and a call is graded the first
time someone looks after the play.

KEPT: each call with its account (``callit_calls``), named in the Privacy
Policy and deleted with the account. Standard library only.
"""
from __future__ import annotations

import time

FOOTBALL = ("nfl", "cfb")
CHOICES = {
    "mlb": (("hit", "Hit"), ("out", "Out"), ("k", "Strikeout"), ("walk", "Walk")),
    "football": (("td", "Touchdown"), ("fg", "Field goal"), ("punt", "Punt"), ("turnover", "Turnover")),
}
#: An at-bat stays open through this many pitches.
AB_OPEN_PITCHES = 1
#: A drive stays open through this many plays.
DRIVE_OPEN_PLAYS = 2
BOARD_N = 5

_MLB = {"single": "hit", "double": "hit", "triple": "hit", "home_run": "hit",
        "strikeout": "k", "strikeout_double_play": "k", "strikeout_triple_play": "k",
        "walk": "walk", "intent_walk": "walk", "hit_by_pitch": "walk"}
#: Results that are no call's: the batter reached without a hit or a walk,
#: or the at-bat ended on something other than him.
_MLB_VOID = {"field_error", "catcher_interf", "batter_interference", "fan_interference",
             "pickoff_1b", "pickoff_2b", "pickoff_3b", "caught_stealing_2b", "caught_stealing_3b",
             "caught_stealing_home", "other_out", "wild_pitch", "passed_ball", "balk",
             "stolen_base_2b", "stolen_base_3b", "stolen_base_home"}


def ensure_tables(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS callit_calls (
        user_id INTEGER NOT NULL, game TEXT NOT NULL, unit TEXT NOT NULL,
        call TEXT NOT NULL, at REAL NOT NULL, result TEXT, won INTEGER,
        PRIMARY KEY (user_id, game, unit));
      CREATE INDEX IF NOT EXISTS callit_game ON callit_calls (game);
    """)
    conn.commit()


def _kind(league: str) -> str:
    return "mlb" if league == "mlb" else "football" if league in FOOTBALL else ""


def game_key(doc: dict) -> str:
    return f"{doc.get('league')}_{doc.get('event_id')}"


def _atbats(doc: dict) -> list:
    return [e for e in doc.get("events") or [] if isinstance(e, dict) and e.get("kind") == "atbat"]


def _ended_drives(doc: dict) -> list:
    return [d for d in doc.get("drives") or [] if isinstance(d, dict) and d.get("result")]


def open_unit(doc: dict) -> dict | None:
    """``{unit, prompt, choices}`` for the call open on this game now, or None."""
    league = str(doc.get("league") or "")
    kind = _kind(league)
    if not kind or str((doc.get("live") or {}).get("state") or "") not in ("live", "in"):
        return None
    if kind == "mlb":
        done = [e.get("at_bat") for e in _atbats(doc) if isinstance(e.get("at_bat"), int)]
        nxt = (max(done) + 1) if done else 0
        cur = doc.get("current") or {}
        if cur and int(cur.get("pitches") or 0) > AB_OPEN_PITCHES:
            return None
        prompt = (f"{cur['batter']} up against {cur['pitcher']}" if cur.get("batter") and cur.get("pitcher")
                  else "The next batter")
        return {"unit": f"ab{nxt}", "prompt": prompt, "choices": [list(c) for c in CHOICES[kind]]}
    cur = doc.get("drive") or {}
    if cur and int(cur.get("plays") or 0) > DRIVE_OPEN_PLAYS:
        return None
    n = len(_ended_drives(doc))
    prompt = f"{cur['team']}'s drive" if cur.get("team") else "The next drive"
    return {"unit": f"dr{n}", "prompt": prompt, "choices": [list(c) for c in CHOICES[kind]]}


def _drive_word(label: str) -> str:
    """A drive's ending as a call, "void" for one no call covers."""
    s = str(label or "").lower()
    if "touchdown" in s and "interception" not in s and "fumble" not in s and "return" not in s:
        return "td"
    if s.startswith("field goal") or s == "fg":
        return "fg"
    if s.startswith("punt") and "block" not in s and "return" not in s:
        return "punt"
    if "end of" in s or "half" in s or "game" in s:
        return "void"
    if any(w in s for w in ("interception", "fumble", "downs", "missed", "blocked", "safety", "turnover")):
        return "turnover"
    return "void"


def result_of(doc: dict, unit: str) -> str:
    """How a unit ended — a choice's key, "void", or "" while it hasn't."""
    league = str(doc.get("league") or "")
    try:
        idx = int(str(unit)[2:])
    except ValueError:
        return "void"
    if league == "mlb" and str(unit).startswith("ab"):
        for e in _atbats(doc):
            if e.get("at_bat") == idx:
                et = str(e.get("event_type") or "").lower()
                if et in _MLB:
                    return _MLB[et]
                return "void" if et in _MLB_VOID or not et else "out"
        return ""
    if league in FOOTBALL and str(unit).startswith("dr"):
        ended = _ended_drives(doc)
        return _drive_word(ended[idx].get("result")) if idx < len(ended) else ""
    return "void"


def grade(conn, doc: dict) -> int:
    """Grade this game's open calls off the file in hand; returns how many."""
    ensure_tables(conn)
    game = game_key(doc)
    pending = conn.execute("SELECT DISTINCT unit FROM callit_calls WHERE game = ? AND result IS NULL",
                           (game,)).fetchall()
    n = 0
    for (unit,) in pending:
        res = result_of(doc, unit)
        if not res:
            continue
        if res == "void":
            cur = conn.execute("UPDATE callit_calls SET result = 'void', won = NULL "
                               "WHERE game = ? AND unit = ? AND result IS NULL", (game, unit))
        else:
            cur = conn.execute("UPDATE callit_calls SET result = ?, won = (call = ?) "
                               "WHERE game = ? AND unit = ? AND result IS NULL", (res, res, game, unit))
        n += cur.rowcount
    conn.commit()
    return n


def call(conn, user_id, doc: dict, unit: str, choice: str, now: float | None = None) -> tuple:
    """Store (or change) a call on the unit open now."""
    ensure_tables(conn)
    op = open_unit(doc)
    if not op or str(unit) != op["unit"]:
        return 409, {"error": "That one is locked — the next call opens in a moment."}
    if choice not in {k for k, _ in op["choices"]}:
        return 400, {"error": "Pick one of the four."}
    t = time.time() if now is None else now
    conn.execute("INSERT INTO callit_calls (user_id, game, unit, call, at) VALUES (?, ?, ?, ?, ?) "
                 "ON CONFLICT(user_id, game, unit) DO UPDATE SET call = excluded.call, at = excluded.at "
                 "WHERE callit_calls.result IS NULL",
                 (int(user_id), game_key(doc), op["unit"], choice, t))
    conn.commit()
    return 200, {"ok": True, "unit": op["unit"], "call": choice}


def streaks(conn, user_id) -> tuple:
    """``(current, best)`` over every graded call, voids skipped."""
    cur = best = run = 0
    first = True
    for (right,) in conn.execute("SELECT won FROM callit_calls WHERE user_id = ? AND won IS NOT NULL "
                                 "ORDER BY at DESC LIMIT 5000", (int(user_id),)):
        if first:
            if right:
                cur += 1
            else:
                first = False
        run = run + 1 if right else 0
        best = max(best, run)
    return cur, best


def board(conn, game: str) -> list:
    """The room's best callers in this game, by calls right. A username
    comes from the feed's profiles when that table exists (a fresh
    database has none yet, and everyone is "a fan")."""
    named = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'feed_profiles'").fetchone()
    handle = "p.handle" if named else "NULL"
    join = "LEFT JOIN feed_profiles p ON p.user_id = c.user_id " if named else ""
    rows = conn.execute(
        f"SELECT c.user_id, SUM(c.won) AS r, COUNT(*) AS n, {handle} FROM callit_calls c {join}"
        "WHERE c.game = ? AND c.won IS NOT NULL GROUP BY c.user_id HAVING r > 0 "
        "ORDER BY r DESC, n ASC LIMIT ?", (game, BOARD_N)).fetchall()
    return [{"handle": r[3] or "a fan", "right": int(r[1] or 0), "total": int(r[2] or 0)} for r in rows]


def state(conn, user_id, doc: dict) -> dict:
    """What the game page's card draws: the open call (and theirs on it),
    their last graded one, the game so far, their streak, the room's best."""
    ensure_tables(conn)
    grade(conn, doc)
    game = game_key(doc)
    out = {"open": open_unit(doc), "kind": _kind(str(doc.get("league") or "")),
           "board": board(conn, game), "signed_in": bool(user_id)}
    if not user_id:
        return out
    uid = int(user_id)
    if out["open"]:
        row = conn.execute("SELECT call FROM callit_calls WHERE user_id = ? AND game = ? AND unit = ?",
                           (uid, game, out["open"]["unit"])).fetchone()
        out["mine"] = row[0] if row else ""
    last = conn.execute("SELECT unit, call, result, won FROM callit_calls WHERE user_id = ? AND game = ? "
                        "AND result IS NOT NULL ORDER BY at DESC LIMIT 1", (uid, game)).fetchone()
    if last:
        out["last"] = {"unit": last[0], "call": last[1], "result": last[2],
                       "right": None if last[3] is None else bool(last[3])}
    r = conn.execute("SELECT COALESCE(SUM(won), 0), COUNT(won) FROM callit_calls WHERE user_id = ? "
                     "AND game = ?", (uid, game)).fetchone()
    out["game"] = {"right": int(r[0] or 0), "total": int(r[1] or 0)}
    out["streak"], out["best"] = streaks(conn, uid)
    return out
