"""The free streak game: pick 3, survive the day, keep the flame.

Ethan's roadmap, item 4: "A daily pick'em/streak survivor using your own
props: pick 3, keep your streak alive, leaderboard. No money = no MGCB
gating... makes people show up every single day or lose something
they've built. This also builds your user base before the paywall flips
on."

TWO HALVES IN ONE MODULE, deliberately, because they share the rules and
two copies of "what counts as surviving a day" would drift:

  * THE BUILD HALF (run/build_slate/grade_day) rides the launch sweep.
    It picks each day's questions off the boards, freezes them, grades
    them against the same history database the ledger settles from, and
    publishes ``streak.json`` through the gate.
  * THE PLAY HALF (record_pick/fold_user/leaders) is called by server.py
    with the accounts database connection. It stores picks, folds graded
    days into each account's streak, and answers the leaderboard.

THE GAME IS FREE AND THE FILE MUST STAY CLEAN. streak.json is in
FREE_FILES — anyone can curl it, signed in or not — so nothing the model
thinks is allowed in it. A question is a FACT: player, market, the
book's line, when the game starts. No side, no odds, no projection, no
edge, no "recommended". Selection is by PRICE BALANCE (the props priced
nearest a coin flip), not by edge, so even the choice of questions says
nothing about which side the model likes. The paid board and this slate
can share a player and disagree completely; a reader of the free file
cannot tell.

THE RULES, in one place because the page and the fold both state them:

  * Pick exactly 3 from the day's slate. Each pick locks at its own
    game's first pitch; you can change or clear it until then.
  * Win more picks than you lose and the streak lives. Pushes (and
    questions that void) count for neither side; an all-void day just
    doesn't count.
  * Fewer than 3 picks by lock, or a day you skip entirely, leaves the
    streak where it was. Only a played-and-lost day resets it. (ESPN's
    Streak works the same way: leagues go dark, people have lives, and
    punishing absence turns a daily habit into a chore people quit.)

WHY THE DAY IS EASTERN: the slate's "day" is the betting day, and a 9pm
Eastern first pitch is already tomorrow in UTC. A UTC day would roll
over mid-slate and split one night's picks across two "days". Lock
times are UTC instants, so the clock comparison itself has no timezone
in it.

NFL IS DELIBERATELY NOT A SLATE SPORT YET. Its player logs are filed by
season+week ("period 005"), not by ISO date, so a question dated
2026-09-13 would find no stat row and silently void — every NFL
question, every week, reading as a push. Adding NFL means mapping a
date to its week the way the ledger's _hist_where does for bets, and
that is a deliberate change, not a default.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from . import feedstate as _feedstate

STATE_PATH = Path(_feedstate.path("streak.json"))
OUT_PUBLIC = Path("web/data/streak.json")

#: The contract of the game, shared by the builder, the server and the
#: page copy. Three picks because two is a coin flip with no texture and
#: five is homework.
PICKS_REQUIRED = 3

#: Questions offered per day. Enough that three picks is a choice, few
#: enough that the page is a card and not a board.
SLATE_SIZE = 6

#: A slate is only frozen once it can actually be played.
MIN_SLATE = PICKS_REQUIRED

#: How balanced a price has to be to qualify: |implied − 0.5| at most
#: this. A −250 favorite side is not a question, it is a quiz with the
#: answer printed on it.
BALANCE_CAP = 0.10

#: At most this many questions from one game (a rainout must not wipe
#: the slate) and one question per player (two lines on one player grade
#: together and stop being independent picks).
MAX_PER_GAME = 2

#: Days of graded slates kept in the public file — the server folds
#: streaks from this window, and the page shows recent results from it.
KEEP_DAYS = 10

#: A question whose game left no stat line after this many days voids.
#: Postponements and data holes happen; a question that can never grade
#: must not block a streak forever.
VOID_AFTER_DAYS = 3

#: Sports whose player logs are filed by ISO date — see the module
#: docstring for why NFL is absent.
SLATE_SPORTS = ("mlb", "nba", "wnba", "cfb")

_EASTERN = ZoneInfo("America/New_York")

#: Display names: shown on a public leaderboard, so the rules are about
#: not leaking and not impersonating. Letters, digits, a few separators;
#: no "@" so nobody can publish an email address by accident.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{1,18}[A-Za-z0-9]$")


def eastern_today(now: _dt.datetime | None = None) -> str:
    t = now or _dt.datetime.now(tz=_dt.timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.astimezone(_EASTERN).date().isoformat()


def _parse_utc(stamp: str) -> _dt.datetime | None:
    """A kickoff string as an aware UTC instant, or None.

    Boards carry Z-stamped ISO from their sources; naive strings are
    refused rather than guessed at — a lock time in an unknown timezone
    is a lock that fires at the wrong moment.
    """
    try:
        t = _dt.datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return None
    return t.astimezone(_dt.timezone.utc)


def _qid(date: str, sport: str, player: str, market: str, line) -> str:
    raw = f"{date}|{sport}|{player}|{market}|{line}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _implied(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


# --- the build half ---------------------------------------------------------

def question_pool(board: dict, sport: str, date: str,
                  now: _dt.datetime) -> list[dict]:
    """Candidate questions from one board — pure.

    Facts only. The internal ``_bal``/``_game`` keys steer selection and
    are stripped before anything is frozen; nothing derived from the
    model survives into a question.
    """
    games = {}
    for g in board.get("games") or []:
        lock = _parse_utc(g.get("kickoff"))
        if lock is None or lock <= now:
            continue                       # unstated or already started
        label = f"{g.get('away', '')} @ {g.get('home', '')}"
        for team in (g.get("home"), g.get("away")):
            if team:
                games[team] = {"lock": lock, "label": label}
    out = []
    for r in board.get("recommendations") or []:
        player, market = r.get("player"), r.get("market")
        line = r.get("line")
        if not player or not market or not isinstance(line, (int, float)):
            continue
        if r.get("has_market") is False:
            continue                       # no real book price = no question
        g = games.get(r.get("team") or "")
        if g is None:
            continue
        p = _implied(r.get("odds"))
        if p is None or abs(p - 0.5) > BALANCE_CAP:
            continue
        out.append({
            "qid": _qid(date, sport, player, market, line),
            "sport": sport,
            "player": player,
            "team": r.get("team") or "",
            "opp": r.get("opponent") or "",
            "game": g["label"],
            "market": market,
            "label": r.get("market_label") or market,
            "line": float(line),
            "lock": g["lock"].isoformat().replace("+00:00", "Z"),
            "_bal": abs(p - 0.5),
            "_game": g["label"],
        })
    return out


def build_slate(pools: list[list[dict]]) -> list[dict]:
    """Pick the day's questions from every sport's candidates — pure.

    Most balanced prices first, then name for determinism; one question
    per player, at most MAX_PER_GAME from one game. Returns [] rather
    than a slate too small to play.
    """
    ranked = sorted((q for pool in pools for q in pool),
                    key=lambda q: (q["_bal"], q["player"]))
    picked: list[dict] = []
    per_game: dict[str, int] = {}
    seen_players = set()
    for q in ranked:
        if len(picked) >= SLATE_SIZE:
            break
        key = (q["sport"], q["player"])
        if key in seen_players:
            continue
        if per_game.get(q["_game"], 0) >= MAX_PER_GAME:
            continue
        seen_players.add(key)
        per_game[q["_game"]] = per_game.get(q["_game"], 0) + 1
        picked.append({k: v for k, v in q.items() if not k.startswith("_")})
    return picked if len(picked) >= MIN_SLATE else []


def grade_question(hist_conn, q: dict, today: str) -> tuple[str | None, float | None]:
    """(result, actual) for one question — "over"/"under"/"void", or None
    while the game is still unplayed or ungraded.

    THE LEDGER'S EVIDENCE RULES, not a copy of them. _hist_where,
    _neighbour_day_rows and _too_early_to_grade are the guards that
    stopped the journal grading tonight's bets against last night's box
    scores; a second, simpler reading of player_game_logs here would
    re-import every bug they were built to end. The pseudo-bet dict is
    the shape those helpers already accept.
    """
    from . import ledger as _led
    from .sources.oddsapi import normalize_name

    b = {"date": q["date"] if "date" in q else today, "sport": q["sport"],
         "market": q["market"], "player": q["player"]}
    where, wargs = _led._hist_where(b)
    rows = hist_conn.execute(
        f"SELECT player, value, team, game_id FROM player_game_logs "
        f"WHERE {where} AND market=? AND player=?",
        (*wargs, b["market"], b["player"])).fetchall()
    if not rows:
        target = normalize_name(b["player"])
        rows = [c for c in hist_conn.execute(
                    f"SELECT player, value, team, game_id "
                    f"FROM player_game_logs WHERE {where} AND market=?",
                    (*wargs, b["market"]))
                if normalize_name(c["player"]) == target]
    if not rows:
        rows, wargs = _led._neighbour_day_rows(hist_conn, b, where, wargs)
    if not rows:
        # No stat line. Recent = still waiting; stale = the game never
        # produced one (postponed, scratched, a data hole) and the
        # question voids so the streak can move on.
        try:
            age = (_dt.date.fromisoformat(today)
                   - _dt.date.fromisoformat(b["date"])).days
        except ValueError:
            age = 0
        return ("void", None) if age >= VOID_AFTER_DAYS else (None, None)
    if _led._too_early_to_grade(hist_conn, where, wargs, rows[0], b["date"]):
        return None, None
    if len(rows) > 1:
        # A doubleheader day. The journal knows which leg a bet belongs
        # to; a streak question frozen pre-game does not, and grading
        # against a coin-flip choice of game would put a wrong result on
        # somebody's streak. Void is the honest answer.
        return "void", None
    actual = float(rows[0]["value"])
    line = float(q["line"])
    if actual > line:
        return "over", actual
    if actual < line:
        return "under", actual
    return "void", actual                  # a push is nobody's win


def grade_day(hist_conn, day: dict, date: str, today: str,
              now: _dt.datetime | None = None) -> bool:
    """Grade every ungraded question of one archived day, in place.

    Returns True when something changed. Stamps ``final`` once every
    question carries a result — the fold refuses non-final days, so a
    half-graded night can never cost anyone a streak.
    """
    t = now or _dt.datetime.now(tz=_dt.timezone.utc)
    changed = False
    for q in day.get("questions") or []:
        if q.get("result"):
            continue
        lock = _parse_utc(q.get("lock"))
        if lock and lock > t:
            continue                       # not even started yet
        result, actual = grade_question(
            hist_conn, {**q, "date": date}, today)
        if result:
            q["result"] = result
            if actual is not None:
                q["actual"] = actual
            changed = True
    final = all(q.get("result") for q in day.get("questions") or [])
    if bool(day.get("final")) != final:
        day["final"] = final
        changed = True
    return changed


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(STATE_PATH)


def payload(state: dict, today: str, now_iso: str) -> dict:
    days = state.get("days") or {}
    keep = dict(sorted(days.items())[-KEEP_DAYS:])
    return {
        "generated_at": now_iso,
        "date": today,
        "picks_required": PICKS_REQUIRED,
        "questions": (keep.get(today) or {}).get("questions") or [],
        "days": keep,
    }


def run(boards: dict | None = None, today: str | None = None,
        quiet: bool = True, now: _dt.datetime | None = None,
        hist_conn=None) -> dict:
    """The sweep entry: freeze today's slate if new, grade the archive,
    publish. Called from launch.py's refresh loop; every failure is the
    caller's try/except problem, not a crashed build."""
    from . import gate

    t = now or _dt.datetime.now(tz=_dt.timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    day = today or eastern_today(t)
    state = _load_state()
    days = state.setdefault("days", {})

    # Freeze today's slate ONCE. Lines move all afternoon; a question
    # whose line changed under a made pick is a different question, so
    # the first viable slate of the day is the day's slate.
    if day not in days and boards:
        pools = []
        for sport, path in boards.items():
            if sport not in SLATE_SPORTS:
                continue
            try:
                board = json.loads(
                    Path(gate.board_source(path)).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(board, dict) or board.get("locked"):
                continue
            pools.append(question_pool(board, sport, day, t))
        slate = build_slate(pools)
        if slate:
            days[day] = {"questions": slate, "final": False}
            if not quiet:
                print(f"  streak: slate frozen — {len(slate)} question(s)")

    # Grade whatever can be graded, today's early finals included.
    close_after = None
    if hist_conn is None:
        try:
            from . import db as _db
            hist_conn = _db.connect()
            close_after = hist_conn
        except Exception:                                 # noqa: BLE001
            hist_conn = None
    if hist_conn is not None:
        try:
            for date, d in days.items():
                if not d.get("final"):
                    grade_day(hist_conn, d, date, day, now=t)
        finally:
            if close_after is not None:
                close_after.close()

    # Old days age out of the state file too, not just the payload.
    for date in sorted(days)[:-KEEP_DAYS] if len(days) > KEEP_DAYS else []:
        days.pop(date, None)

    _save_state(state)
    doc = payload(state, day, t.isoformat(timespec="seconds"))
    gate.publish(doc, OUT_PUBLIC, "streak.json")
    return doc


# --- the play half ----------------------------------------------------------
# Called from server.py with the ACCOUNTS database connection. The slate
# document is the public streak.json, read by the caller — this half
# never touches the boards or the history database.

def ensure_tables(conn) -> None:
    """Additive, safe on every call — same posture as accounts._migrate."""
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS streak_picks (
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date       TEXT NOT NULL,
        qid        TEXT NOT NULL,
        side       TEXT NOT NULL CHECK (side IN ('over','under')),
        created_at REAL NOT NULL,
        PRIMARY KEY (user_id, qid)
      );
      CREATE INDEX IF NOT EXISTS streak_picks_day ON streak_picks(user_id, date);
      CREATE TABLE IF NOT EXISTS streak_state (
        user_id        INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        name           TEXT NOT NULL DEFAULT '',
        current        INTEGER NOT NULL DEFAULT 0,
        best           INTEGER NOT NULL DEFAULT 0,
        folded_through TEXT NOT NULL DEFAULT '',
        last_day       TEXT NOT NULL DEFAULT '',
        last_result    TEXT NOT NULL DEFAULT '',
        updated_at     REAL
      );
    """)
    conn.commit()


def name_problem(name: str) -> str | None:
    n = " ".join(str(name or "").split())
    if not n:
        return None                        # clearing the name is allowed
    if not NAME_RE.match(n):
        return ("3–20 characters: letters, digits, spaces, . _ or -. "
                "It goes on a public leaderboard, so no email addresses.")
    return None


def set_name(conn, user_id: int, name: str) -> tuple[int, dict]:
    n = " ".join(str(name or "").split())
    why = name_problem(n)
    if why:
        return 400, {"error": why}
    ensure_tables(conn)
    conn.execute(
        "INSERT INTO streak_state (user_id, name, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, "
        "updated_at=excluded.updated_at",
        (int(user_id), n, time.time()))
    conn.commit()
    return 200, {"name": n}


def record_pick(conn, user_id: int, slate: dict, qid: str, side: str,
                now: _dt.datetime | None = None) -> tuple[int, dict]:
    """Make, change or clear one pick against the frozen slate.

    The slate document is the authority for everything: which questions
    exist today, what date they belong to, and when each locks. The
    server clock only ever answers "is it past lock" — in UTC, against
    the question's own UTC instant.
    """
    t = now or _dt.datetime.now(tz=_dt.timezone.utc)
    date = str(slate.get("date") or "")
    q = next((x for x in slate.get("questions") or []
              if x.get("qid") == qid), None)
    if q is None or not date:
        return 404, {"error": "That question isn’t on today’s slate."}
    lock = _parse_utc(q.get("lock"))
    if lock is None or t >= lock:
        return 409, {"error": "That game has started — the pick is locked."}
    ensure_tables(conn)
    if side == "clear":
        conn.execute("DELETE FROM streak_picks WHERE user_id=? AND qid=?",
                     (int(user_id), qid))
        conn.commit()
        return 200, {"picks": day_picks(conn, user_id, date)}
    if side not in ("over", "under"):
        return 400, {"error": "Pick over or under."}
    have = {r["qid"] for r in conn.execute(
        "SELECT qid FROM streak_picks WHERE user_id=? AND date=?",
        (int(user_id), date))}
    if qid not in have and len(have) >= PICKS_REQUIRED:
        return 409, {"error": f"All {PICKS_REQUIRED} picks are used — "
                              f"clear one first."}
    conn.execute(
        "INSERT INTO streak_picks (user_id, date, qid, side, created_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(user_id, qid) DO UPDATE SET "
        "side=excluded.side",
        (int(user_id), date, qid, side, time.time()))
    conn.commit()
    return 200, {"picks": day_picks(conn, user_id, date)}


def day_picks(conn, user_id: int, date: str) -> dict:
    return {r["qid"]: r["side"] for r in conn.execute(
        "SELECT qid, side FROM streak_picks WHERE user_id=? AND date=?",
        (int(user_id), date))}


def judge_day(picks: dict, day: dict) -> str:
    """One played day's verdict from the shared rules — pure.

    "survived" / "lost" / "skip". Fewer than PICKS_REQUIRED picks is a
    skip, not a loss; so is an all-void day. Wins must OUTNUMBER losses:
    1-1 with a push dies, 2-1 lives, 1-0 with two pushes lives.
    """
    if len(picks) < PICKS_REQUIRED:
        return "skip"
    results = {q.get("qid"): q.get("result")
               for q in day.get("questions") or []}
    wins = losses = 0
    for qid, side in picks.items():
        r = results.get(qid)
        if r not in ("over", "under"):
            continue                       # void — nobody's win
        if side == r:
            wins += 1
        else:
            losses += 1
    if wins + losses == 0:
        return "skip"
    return "survived" if wins > losses else "lost"


def fold_user(conn, user_id: int, slate: dict) -> dict:
    """Fold every graded day since the last fold into this account's
    streak. Idempotent; stops at the first non-final day so grading
    order can never be jumped."""
    ensure_tables(conn)
    row = conn.execute("SELECT * FROM streak_state WHERE user_id=?",
                       (int(user_id),)).fetchone()
    st = {"name": row["name"] if row else "",
          "current": int(row["current"]) if row else 0,
          "best": int(row["best"]) if row else 0,
          "folded_through": row["folded_through"] if row else "",
          "last_day": row["last_day"] if row else "",
          "last_result": row["last_result"] if row else ""}
    days = slate.get("days") or {}
    pick_days = sorted({r["date"] for r in conn.execute(
        "SELECT DISTINCT date FROM streak_picks WHERE user_id=?",
        (int(user_id),))})
    changed = False
    for date in pick_days:
        if date <= st["folded_through"]:
            continue
        day = days.get(date)
        if day is None:
            # Older than the archive window — nothing to grade against,
            # the day just doesn't count.
            st["folded_through"] = date
            changed = True
            continue
        if not day.get("final"):
            break
        verdict = judge_day(day_picks(conn, user_id, date), day)
        if verdict == "survived":
            st["current"] += 1
            st["best"] = max(st["best"], st["current"])
        elif verdict == "lost":
            st["current"] = 0
        if verdict != "skip":
            st["last_day"], st["last_result"] = date, verdict
        st["folded_through"] = date
        changed = True
    if changed:
        conn.execute(
            "INSERT INTO streak_state (user_id, name, current, best, "
            "folded_through, last_day, last_result, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "current=excluded.current, best=excluded.best, "
            "folded_through=excluded.folded_through, "
            "last_day=excluded.last_day, last_result=excluded.last_result, "
            "updated_at=excluded.updated_at",
            (int(user_id), st["name"], st["current"], st["best"],
             st["folded_through"], st["last_day"], st["last_result"],
             time.time()))
        conn.commit()
    return st


def fold_all(conn, slate: dict) -> None:
    """Every account with picks newer than its fold, before a leaderboard
    is served — a board showing a streak its owner already lost is the
    leaderboard lying."""
    ensure_tables(conn)
    ids = [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT p.user_id FROM streak_picks p "
        "LEFT JOIN streak_state s ON s.user_id = p.user_id "
        "WHERE s.user_id IS NULL OR p.date > s.folded_through")]
    for uid in ids:
        fold_user(conn, uid, slate)


def playing_today(conn, date: str) -> int:
    """How many accounts have a full slate of picks in for `date`.

    The leaderboard's day-one problem: nobody appears on it until a
    night has GRADED, so the first players all stared at "Nobody on the
    board yet" right after picking — which reads as the game being
    broken, not young (Ethan hit exactly this on launch day). A count
    of tonight's players is the honest thing that exists immediately.
    Names stay out of it: playing is not the same consent as being
    ranked in public."""
    ensure_tables(conn)
    if not date:
        return 0
    return int(conn.execute(
        "SELECT COUNT(*) FROM (SELECT user_id FROM streak_picks "
        "WHERE date=? GROUP BY user_id HAVING COUNT(*) >= ?)",
        (str(date), PICKS_REQUIRED)).fetchone()[0])


def leaders(conn, limit: int = 20) -> list[dict]:
    """Top streaks, named accounts only. An account with no display name
    plays in private — that is the deal the name box states."""
    ensure_tables(conn)
    return [{"name": r["name"], "current": int(r["current"]),
             "best": int(r["best"])}
            for r in conn.execute(
                "SELECT name, current, best FROM streak_state "
                "WHERE name != '' AND best > 0 "
                "ORDER BY current DESC, best DESC, name ASC LIMIT ?",
                (int(limit),))]


def me(conn, user_id: int, slate: dict) -> dict:
    """Everything the page needs about one signed-in player."""
    st = fold_user(conn, user_id, slate)
    dates = sorted(slate.get("days") or {})
    picks: dict[str, dict] = {}
    if dates:
        for r in conn.execute(
                "SELECT date, qid, side FROM streak_picks "
                "WHERE user_id=? AND date >= ?", (int(user_id), dates[0])):
            picks.setdefault(r["date"], {})[r["qid"]] = r["side"]
    return {"name": st["name"], "current": st["current"], "best": st["best"],
            "last_day": st["last_day"], "last_result": st["last_result"],
            "picks": picks}
