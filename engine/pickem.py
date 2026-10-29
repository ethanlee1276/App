"""The weekly pick'em: pick the winner of every game on the board, free, graded from the final.

Ethan, 2026-10-15, the last of the sixteen ideas he asked to have built
("do every one for every sport"): a free weekly pick'em contest with a
leaderboard on Social.

THE GAME. Every board sport (NFL, college, MLB, NBA, WNBA, NHL) has a
pick'em: for each game on that sport's board, pick the team that wins.
A week runs Tuesday to Monday, Eastern time, so an NFL week — Thursday
night to Monday night — is always one contest; the daily sports add each
day's games as the board posts them. The standings rank the week and the
season (every week of the last SEASON_DAYS) by wins, then fewest losses.
Free: a signed-in account with a Social handle, no membership, no entry
fee, no prizes. Bragging rights.

THE RECORD CANNOT BE FAKED, the feed's rule. The page sends which game
and which team, never a result: the game is looked up on the sport's own
board, the team must be one of its two, and the pick is refused once the
game starts (the board's live flag, or its kickoff). A pick can be
changed until then and never after. Grading is the server's alone, from
the finals table every bet grades from (`history.db` `games`, matched on
the two teams and the date within a day, the way livescores matches a
final): more than one candidate row is ambiguity, refused rather than
guessed; a tie is a push; a game with no final ten days on is void.
Nothing here reads or writes a model number, and nothing on the board
moves for it.

IT COMES TO YOU (Ethan, 2026-10-28: "keep building and adding more
features"). A weekly game nobody is reminded of is a tab people forget, so:
a winner pays karma (+5, and +25 for a perfect week of five or more), the
standings have a friends table beside everyone's, the Live tab's karma card
carries one line while the NFL week's picks are open, and a phone hears
about three hours before a week's picks lock (football only: the week's
first kickoff, and a day's first kickoff of four games or more, so one a
day at most), for an account that has played in the last four weeks,
unless it says no.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
import time
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:                                         # noqa: BLE001
    ET = _dt.timezone(_dt.timedelta(hours=-5))

SPORTS = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl")
#: Grade a pick once its game has had time to finish.
GRADE_AFTER_S = 3 * 3600
GRADE_RETRY_S = 15 * 60
VOID_AFTER_S = 10 * 86400
SEASON_DAYS = 200
TOP = 50
#: A perfect week pays once it is over, with at least this many winners.
PERFECT_MIN = 5
#: The push before picks lock (engine/pushmine sends it, engine/pushalerts
#: carries the topic): on for an account that played in the last
#: PLAYER_DAYS, unless it said no (``pickem_prefs.remind`` REMIND_OFF; 0 is
#: never chosen, 1 on).
ALERT_TOPIC = "pickem"
REMIND_OFF = 2
PLAYER_DAYS = 28
REMIND_SPORTS = ("nfl", "cfb")
#: Sent between three and two hours before a kickoff worth it: the week's
#: first, or a day's first with BIG_SLOT games or more. One a day at most:
#: a college Saturday has four or five kickoffs that big.
REMIND_LEAD_S = (2 * 3600, 3 * 3600)
BIG_SLOT = 4
#: Tuesday's line on the week just over (Wednesday too, for a final that
#: came in late), in the day's hours, once every pick of it is graded.
RECAP_DAYS = (1, 2)
RECAP_HOURS = (10, 21)
SPORT_WORD = {"nfl": "NFL", "cfb": "College football"}


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS pickem_picks (
        user_id    INTEGER NOT NULL,
        sport      TEXT NOT NULL,
        week       TEXT NOT NULL,
        gid        TEXT NOT NULL,
        home       TEXT NOT NULL,
        away       TEXT NOT NULL,
        game_date  TEXT NOT NULL,
        kickoff    REAL NOT NULL,
        pick       TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        result     TEXT,
        graded_at  REAL,
        last_try   REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, sport, gid)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS pickem_week ON pickem_picks (sport, week)")
    conn.execute("""CREATE TABLE IF NOT EXISTS pickem_prefs (
        user_id INTEGER PRIMARY KEY,
        remind  INTEGER NOT NULL DEFAULT 0
    )""")
    # The week each sport's Tuesday line last went out ("nfl:2026-10-20").
    # Added rather than declared (the table shipped first), and raced: the
    # API and the push loop both come through here.
    if "recap" not in {r[1] for r in conn.execute("PRAGMA table_info(pickem_prefs)")}:
        from .db import column_exists_or_raise
        try:
            conn.execute("ALTER TABLE pickem_prefs ADD COLUMN recap TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError as exc:
            column_exists_or_raise(exc)
    # BEAT THE CLOSE (the second paper, 2026-10-29: "CLV pick'em ... leaderboard
    # ranked by beating the close, not by wins"): the market's chance for the
    # picked team when it was picked, and the last one seen before kickoff.
    have = {r[1] for r in conn.execute("PRAGMA table_info(pickem_picks)")}
    for col in ("p_pick", "p_close"):
        if col not in have:
            from .db import column_exists_or_raise
            try:
                conn.execute(f"ALTER TABLE pickem_picks ADD COLUMN {col} REAL")
            except sqlite3.OperationalError as exc:
                column_exists_or_raise(exc)


def _ts(iso) -> float | None:
    if not iso:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.timestamp()


def week_of(ts: float) -> str:
    """The contest week a moment falls in: the Tuesday (Eastern) that
    starts it, as YYYY-MM-DD."""
    d = _dt.datetime.fromtimestamp(float(ts), ET).date()
    return (d - _dt.timedelta(days=(d.weekday() - 1) % 7)).isoformat()


def week_label(week: str) -> str:
    a = _dt.date.fromisoformat(week)
    b = a + _dt.timedelta(days=6)
    return f"{a:%b} {a.day} – {b:%b} {b.day}" if a.month != b.month else f"{a:%b} {a.day} – {b.day}"


def shift(week: str, n: int) -> str:
    return (_dt.date.fromisoformat(week) + _dt.timedelta(days=7 * n)).isoformat()


def valid_week(w) -> bool:
    try:
        return _dt.date.fromisoformat(str(w)).weekday() == 1
    except ValueError:
        return False


def gid_of(g: dict) -> str:
    return f"{g.get('date') or ''}|{g.get('away') or ''}@{g.get('home') or ''}"


def board_games(sport: str, data_dir: Path | None = None) -> list[dict]:
    """The games on a sport's public board: who, when, and whether it has
    begun. A game without a kickoff cannot be locked, so it is left off."""
    from . import socialfeed as SF
    name = SF.SPORT_FILE.get(sport)
    if not name:
        return []
    payload = SF._read((data_dir or SF.DATA) / name) or {}
    out = []
    for g in payload.get("games") or []:
        if not isinstance(g, dict) or not g.get("home") or not g.get("away"):
            continue
        raw = g.get("kickoff") or g.get("commence_time")
        if raw and len(str(raw)) <= 5:
            # FOOTBALL'S KICKOFF IS A BARE EASTERN CLOCK ("13:00", nflverse's
            # gametime) beside the game's date; engine/fatigue joins the two,
            # as the ledger's kickoff map does. Read as an instant on its own,
            # every NFL game was left off (the box, 2026-10-16: "0 games").
            from .fatigue import kickoff_instant
            raw = kickoff_instant(str(g.get("date") or ""), str(raw))
        k = _ts(raw)
        if k is None:
            continue
        date = str(g.get("date") or _dt.datetime.fromtimestamp(k, ET).date().isoformat())[:10]
        # The scoreboard's status rides on every game, "scheduled" before
        # the start, so only a game it calls live or final has begun.
        lv = g.get("live")
        begun = lv is True or (isinstance(lv, dict) and str(lv.get("state") or "") in ("live", "final"))
        out.append({"gid": gid_of({**g, "date": date}), "home": str(g["home"]), "away": str(g["away"]),
                    "game_date": date, "kickoff": k, "live": begun,
                    "ml": (g.get("home_ml"), g.get("away_ml"))})
    return out


def chance(g: dict, team: str) -> float | None:
    """The market's chance for one of a game's teams, the two moneylines
    with the margin taken out; None without both."""
    from .odds import devig_two_way
    hm, am = (g.get("ml") or (None, None))[:2]
    try:
        if not hm or not am or abs(float(hm)) < 100 or abs(float(am)) < 100:
            return None
        ph, pa = devig_two_way(int(float(hm)), int(float(am)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    p = ph if team == g.get("home") else pa if team == g.get("away") else None
    return round(p, 4) if p is not None and 0 < p < 1 else None


def _started(g: dict, now: float) -> bool:
    return bool(g.get("live")) or float(g["kickoff"]) <= now


def pick(conn, user_id: int, sport, gid, team, now: float | None = None,
         data_dir: Path | None = None) -> tuple[int, dict]:
    """Make or change a pick. Which game and which team — nothing else is
    read from the page."""
    from . import socialfeed as SF
    ensure_tables(conn)
    now = time.time() if now is None else float(now)
    sport = str(sport or "").lower()
    if sport not in SPORTS:
        return 400, {"error": "no pick'em for that sport"}
    prof = SF.profile_of(conn, user_id)
    if not prof or not prof.get("handle"):
        return 409, {"error": "make your Social profile first — the standings show your handle"}
    g = next((x for x in board_games(sport, data_dir) if x["gid"] == str(gid or "")), None)
    if g is None:
        return 404, {"error": "that game is not on the board"}
    team = str(team or "")
    if team not in (g["home"], g["away"]):
        return 400, {"error": "pick one of the two teams"}
    if _started(g, now):
        return 409, {"error": "that game has started — picks lock at kickoff"}
    week = week_of(g["kickoff"])
    old = conn.execute("SELECT pick FROM pickem_picks WHERE user_id=? AND sport=? AND gid=?",
                       (int(user_id), sport, g["gid"])).fetchone()
    price = chance(g, team)
    if old is None:
        conn.execute("INSERT INTO pickem_picks (user_id, sport, week, gid, home, away, game_date, kickoff, pick, "
                     "created_at, updated_at, p_pick, p_close) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (int(user_id), sport, week, g["gid"], g["home"], g["away"], g["game_date"], g["kickoff"],
                      team, now, now, price, price))
    elif old[0] != team:
        conn.execute("UPDATE pickem_picks SET pick=?, updated_at=?, week=?, kickoff=?, p_pick=?, p_close=? "
                     "WHERE user_id=? AND sport=? AND gid=?",
                     (team, now, week, g["kickoff"], price, price, int(user_id), sport, g["gid"]))
    else:
        conn.execute("UPDATE pickem_picks SET updated_at=?, week=?, kickoff=? WHERE user_id=? AND sport=? AND gid=?",
                     (now, week, g["kickoff"], int(user_id), sport, g["gid"]))
    conn.commit()
    return 200, {"ok": True, "gid": g["gid"], "pick": team, "week": week}


def _final(hconn, sport: str, row) -> tuple | None:
    """``(home_score, away_score)`` for the pick's game from the finals
    table, oriented to the pick's own home and away; None when there is no
    single final to read."""
    d = _dt.date.fromisoformat(row["game_date"])
    lo, hi = (d - _dt.timedelta(days=1)).isoformat(), (d + _dt.timedelta(days=1)).isoformat()
    found = hconn.execute(
        "SELECT home, away, home_score, away_score FROM games WHERE sport=? AND "
        "((home=? AND away=?) OR (home=? AND away=?)) AND COALESCE(date, period) BETWEEN ? AND ?",
        (sport, row["home"], row["away"], row["away"], row["home"], lo, hi)).fetchall()
    finals = []
    for h, _away, hs, as_ in found:
        try:
            hs, as_ = float(hs), float(as_)
        except (TypeError, ValueError):
            continue
        finals.append((hs, as_) if h == row["home"] else (as_, hs))
    if len(set(finals)) != 1:
        return None                          # none yet, or ambiguous: never guessed
    return finals[0]


def grade(conn, opener, now: float | None = None, limit: int = 300) -> int:
    """Grade what can be graded — lazily, when the page is read, like the
    feed's parlays. ``opener`` opens the finals table read-only, and only
    when a pick is due."""
    ensure_tables(conn)
    now = time.time() if now is None else float(now)
    _pay_weeks(conn, now)
    due = conn.execute("SELECT rowid, * FROM pickem_picks WHERE result IS NULL AND kickoff<? AND last_try<? "
                       "ORDER BY kickoff LIMIT ?", (now - GRADE_AFTER_S, now - GRADE_RETRY_S, limit)).fetchall()
    if not due:
        return 0
    try:
        hconn = opener()
    except Exception:                                     # noqa: BLE001
        return 0
    n = 0
    finals: dict = {}
    try:
        for r in due:
            key = (r["sport"], r["gid"])
            if key not in finals:
                try:
                    finals[key] = _final(hconn, r["sport"], r)
                except Exception:                         # noqa: BLE001
                    finals[key] = None
            f = finals[key]
            result = None
            if f is not None:
                hs, as_ = f
                win = None if hs == as_ else (r["home"] if hs > as_ else r["away"])
                result = "push" if win is None else ("won" if r["pick"] == win else "lost")
            elif now - float(r["kickoff"]) > VOID_AFTER_S:
                result = "void"
            conn.execute("UPDATE pickem_picks SET result=?, graded_at=?, last_try=? WHERE rowid=?",
                         (result, now if result else None, now, r["rowid"]))
            n += result is not None
            if result == "won":
                _pay(conn, r["user_id"], "pickem_won", f"{r['sport']}:{r['gid']}", now)
        conn.commit()
    finally:
        try:
            hconn.close()
        except Exception:                                 # noqa: BLE001
            pass
    return n


def _pay(conn, user_id, kind: str, ref: str, now: float) -> int:
    """Karma for the pick'em (engine/karma), once a ref. A karma table that
    cannot be written never stops a grade."""
    from . import karma as K
    try:
        try:
            return K.award(conn, int(user_id), kind, ref, now=now, commit=False)
        except sqlite3.OperationalError:                  # karma's tables not made yet on this database
            K.ensure_tables(conn)
            return K.award(conn, int(user_id), kind, ref, now=now, commit=False)
    except Exception:                                     # noqa: BLE001
        return 0


def _pay_weeks(conn, now: float) -> int:
    """A perfect week pays once it is over: at least PERFECT_MIN winners,
    no loss and nothing still open in the two weeks before this one (a
    push or a void is not a loss). Over first, because a pick made later in
    the week could still lose."""
    this = week_of(now)
    weeks = (shift(this, -1), shift(this, -2))
    rows = conn.execute("SELECT user_id, sport, week FROM pickem_picks WHERE week IN (?,?) "
                        "GROUP BY user_id, sport, week HAVING SUM(result='lost')=0 AND SUM(result IS NULL)=0 "
                        "AND SUM(result='won')>=?", (*weeks, PERFECT_MIN)).fetchall()
    paid = sum(_pay(conn, r[0], "pickem_week", f"{r[1]}:{r[2]}", now) for r in rows)
    if rows:
        conn.commit()
    return paid


def standings(conn, sport: str, week: str | None, viewer=None, now: float | None = None,
              only: set | None = None) -> dict:
    """The table: a person's wins, losses, pushes and open picks for one
    week, or the season (``week`` None: every week of the last
    SEASON_DAYS). Ranked by wins, then fewest losses. Only people with a
    Social handle are named; a block hides both ways, as on the feed.
    ``only``: just these accounts (the friends table)."""
    from . import socialfeed as SF
    ensure_tables(conn)
    SF.ensure_tables(conn)
    now = time.time() if now is None else float(now)
    hide = SF.blocked_ids(conn, viewer)
    table = []
    for r in _lines(conn, sport, week, now):
        if int(r["user_id"]) in hide or (only is not None and int(r["user_id"]) not in only):
            continue
        table.append({**SF._person(r), "w": int(r["w"] or 0), "l": int(r["l"] or 0), "p": int(r["pu"] or 0),
                      "open": int(r["open"] or 0), "me": viewer is not None and int(r["user_id"]) == int(viewer)})
    _rank(table)
    me = next((x for x in table if x["me"]), None)
    return {"rows": table[:TOP], "me": me, "players": len(table)}


def _lines(conn, sport: str, week: str | None, now: float) -> list:
    """Each named player's line for one week, or the season (``week``
    None): the rows every table here ranks."""
    where, args = ("p.week=?", [week]) if week else ("p.kickoff>?", [now - SEASON_DAYS * 86400])
    return conn.execute(
        "SELECT p.user_id, f.handle, f.display_name, f.color, f.fav_team, f.verified, f.founder, "
        "SUM(p.result='won') AS w, SUM(p.result='lost') AS l, SUM(p.result='push') AS pu, "
        "SUM(p.result IS NULL) AS open FROM pickem_picks p JOIN feed_profiles f ON f.user_id=p.user_id "
        f"WHERE p.sport=? AND f.handle IS NOT NULL AND f.handle!='' AND {where} GROUP BY p.user_id",
        [sport] + args).fetchall()


def _rank(table: list[dict]) -> list[dict]:
    """Wins, then fewest losses; a tie shares the place (pushes, then the
    handle, only order its rows)."""
    table.sort(key=lambda x: (-x["w"], x["l"], -x["p"], str(x["handle"]).lower()))
    rank, last = 0, None
    for i, x in enumerate(table):
        k = (x["w"], x["l"])
        if k != last:
            rank, last = i + 1, k
        x["rank"] = rank
    return table


def _places(conn, sport: str, week: str | None, now: float) -> dict:
    """Every named player's line and place, by account, as the public
    table ranks them: the Tuesday line and a profile read it."""
    from . import socialfeed as SF
    SF.ensure_tables(conn)
    return {x["uid"]: x for x in _rank([
        {"uid": int(r["user_id"]), "handle": r["handle"], "w": int(r["w"] or 0), "l": int(r["l"] or 0),
         "p": int(r["pu"] or 0), "open": int(r["open"] or 0)} for r in _lines(conn, sport, week, now)])}


def season_lines(conn, user_id, now: float | None = None) -> list[dict]:
    """A profile's pick'em this season: the (at most two) sports it has
    the most graded picks in, each with its record and its place on that
    sport's season table."""
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    uid = int(user_id)
    out = []
    for (sport,) in conn.execute(
            "SELECT sport FROM pickem_picks WHERE user_id=? AND kickoff>? AND result IN ('won','lost','push') "
            "GROUP BY sport ORDER BY COUNT(*) DESC, sport LIMIT 2", (uid, t - SEASON_DAYS * 86400)).fetchall():
        places = _places(conn, sport, None, t)
        x = places.get(uid)
        if x:
            out.append({"sport": sport, "w": x["w"], "l": x["l"], "p": x["p"], "rank": x["rank"],
                        "players": len(places)})
    return out


# ─── beat the close ─────────────────────────────────────────────────────────
#: Picks with both prices it takes to be on a table: a week's, a season's.
CLV_MIN_WEEK, CLV_MIN_SEASON = 3, 10


def note_closes(conn, now: float | None = None, data_dir: Path | None = None) -> int:
    """Keep the market's latest chance for every pick on a game not yet
    begun; the last one kept before kickoff is the pick's close. Reads only
    the boards of sports with a pick still open. Returns picks noted."""
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    n = 0
    for (sport,) in conn.execute("SELECT DISTINCT sport FROM pickem_picks WHERE kickoff > ?", (t,)).fetchall():
        for g in board_games(sport, data_dir):
            if _started(g, t):
                continue
            ph, pa = chance(g, g["home"]), chance(g, g["away"])
            if ph is None or pa is None:
                continue
            cur = conn.execute("UPDATE pickem_picks SET p_close = CASE pick WHEN ? THEN ? ELSE ? END "
                               "WHERE sport = ? AND gid = ? AND kickoff > ?", (g["home"], ph, pa, sport, g["gid"], t))
            n += cur.rowcount
    conn.commit()
    return n


def clv_table(conn, sport: str, week: str | None, viewer=None, now: float | None = None,
              only: set | None = None) -> dict:
    """The table by beating the close: each named player's average, in
    points of the market's chance, of where it closed against where they
    picked — games begun only, CLV_MIN_* picks to be on it."""
    from . import socialfeed as SF
    ensure_tables(conn)
    SF.ensure_tables(conn)
    t = time.time() if now is None else float(now)
    where, args = ("p.week=?", [week]) if week else ("p.kickoff>?", [t - SEASON_DAYS * 86400])
    need = CLV_MIN_WEEK if week else CLV_MIN_SEASON
    hide = SF.blocked_ids(conn, viewer)
    rows = conn.execute(
        "SELECT p.user_id, f.handle, f.display_name, f.color, f.fav_team, f.verified, f.founder, "
        "AVG(p.p_close - p.p_pick) AS clv, COUNT(*) AS n, SUM(p.p_close > p.p_pick) AS beat "
        "FROM pickem_picks p JOIN feed_profiles f ON f.user_id=p.user_id "
        f"WHERE p.sport=? AND f.handle IS NOT NULL AND f.handle!='' AND {where} AND p.kickoff<=? "
        "AND p.p_pick IS NOT NULL AND p.p_close IS NOT NULL GROUP BY p.user_id HAVING COUNT(*) >= ?",
        [sport] + args + [t, need]).fetchall()
    table = []
    for r in rows:
        if int(r["user_id"]) in hide or (only is not None and int(r["user_id"]) not in only):
            continue
        table.append({**SF._person(r), "clv": round(float(r["clv"]) * 100, 1), "n": int(r["n"]),
                      "beat": int(r["beat"] or 0), "me": viewer is not None and int(r["user_id"]) == int(viewer)})
    table.sort(key=lambda x: (-x["clv"], -x["n"], str(x["handle"]).lower()))
    rank, last = 0, None
    for i, x in enumerate(table):
        if x["clv"] != last:
            rank, last = i + 1, x["clv"]
        x["rank"] = rank
    me = next((x for x in table if x["me"]), None)
    return {"rows": table[:TOP], "me": me, "players": len(table), "min": need}


def view(conn, sport: str, viewer=None, week: str | None = None, now: float | None = None,
         data_dir: Path | None = None) -> dict:
    """The page: this week's games with the viewer's pick and the room's
    split, the week's standings and the season's."""
    from . import socialfeed as SF
    ensure_tables(conn)
    now = time.time() if now is None else float(now)
    sport = sport if sport in SPORTS else "nfl"
    current = week_of(now)
    week = week if week and valid_week(week) else current
    games = {g["gid"]: g for g in board_games(sport, data_dir) if week_of(g["kickoff"]) == week}
    # A game the board has since dropped is still this week's: it comes
    # back from the picks people made on it.
    for r in conn.execute("SELECT gid, home, away, game_date, MAX(kickoff) AS kickoff FROM pickem_picks "
                          "WHERE sport=? AND week=? GROUP BY gid", (sport, week)):
        games.setdefault(r["gid"], {"gid": r["gid"], "home": r["home"], "away": r["away"],
                                    "game_date": r["game_date"], "kickoff": float(r["kickoff"]), "live": False})
    split: dict = {}
    for r in conn.execute("SELECT gid, pick, COUNT(*) AS n FROM pickem_picks WHERE sport=? AND week=? "
                          "GROUP BY gid, pick", (sport, week)):
        split.setdefault(r["gid"], {})[r["pick"]] = int(r["n"])
    mine = {}
    if viewer is not None:
        for r in conn.execute("SELECT gid, pick, result, p_pick, p_close FROM pickem_picks WHERE user_id=? AND sport=? "
                              "AND week=?", (int(viewer), sport, week)):
            mine[r["gid"]] = {"pick": r["pick"], "result": r["result"], "p_pick": r["p_pick"], "p_close": r["p_close"]}
    out = []
    for g in sorted(games.values(), key=lambda x: (x["kickoff"], x["gid"])):
        s = split.get(g["gid"], {})
        m = mine.get(g["gid"]) or {}
        out.append({"gid": g["gid"], "home": g["home"], "away": g["away"],
                    "kickoff": _dt.datetime.fromtimestamp(g["kickoff"], _dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                    "locked": _started(g, now), "pick": m.get("pick"), "result": m.get("result"),
                    "p_pick": m.get("p_pick"), "p_close": m.get("p_close"),
                    "n_home": s.get(g["home"], 0), "n_away": s.get(g["away"], 0)})
    prof = SF.profile_of(conn, viewer) if viewer is not None else None
    # The friends table: the viewer and their friends, both sides of the
    # friendship (engine/karma.friend_ids, the karma friends ladder's).
    pals = None
    if viewer is not None:
        from . import karma as K
        pals = K.friend_ids(conn, viewer) | {int(viewer)}
    return {"sport": sport, "week": week, "label": week_label(week), "current": week == current,
            "prev": shift(week, -1), "next": shift(week, 1) if week < current else None,
            "games": out, "week_table": standings(conn, sport, week, viewer, now),
            "season_table": standings(conn, sport, None, viewer, now),
            "week_friends": standings(conn, sport, week, viewer, now, only=pals) if pals else None,
            "season_friends": standings(conn, sport, None, viewer, now, only=pals) if pals else None,
            "week_clv": clv_table(conn, sport, week, viewer, now),
            "season_clv": clv_table(conn, sport, None, viewer, now),
            "week_clv_friends": clv_table(conn, sport, week, viewer, now, only=pals) if pals else None,
            "season_clv_friends": clv_table(conn, sport, None, viewer, now, only=pals) if pals else None,
            "friends": len(pals) - 1 if pals else 0,
            "remind": reminds(conn, viewer, switch_only=True) if viewer is not None else False,
            "signed_in": viewer is not None, "has_handle": bool(prof and prof.get("handle")),
            "season_days": SEASON_DAYS}


# ─── the push before picks lock ─────────────────────────────────────────────

def _remind_pref(conn, user_id) -> int:
    row = conn.execute("SELECT remind FROM pickem_prefs WHERE user_id=?", (int(user_id),)).fetchone()
    return int(row[0]) if row else 0


def played(conn, user_id, now: float | None = None) -> bool:
    """A pick'em pick in the last PLAYER_DAYS: a player, whom the push is for."""
    t = time.time() if now is None else float(now)
    return conn.execute("SELECT 1 FROM pickem_picks WHERE user_id=? AND created_at>? LIMIT 1",
                        (int(user_id), t - PLAYER_DAYS * 86400)).fetchone() is not None


def reminds(conn, user_id, switch_only: bool = False) -> bool:
    """Does this account want the push before picks lock? Yes for a player
    who has not said no (engine/pushalerts.subscribe asks, so a phone
    signed in to it carries the topic). ``switch_only``: the switch alone,
    as the Pick'em page shows it."""
    try:
        ensure_tables(conn)
        if _remind_pref(conn, user_id) == REMIND_OFF:
            return False
        return switch_only or played(conn, user_id)
    except Exception:                                     # noqa: BLE001
        return False


def set_remind(conn, user_id, on: bool) -> tuple[int, dict]:
    """The Pick'em page's switch: kept as chosen, and put on (or taken off)
    every phone signed in to the account."""
    from . import pushalerts as PA
    ensure_tables(conn)
    conn.execute("INSERT INTO pickem_prefs (user_id, remind) VALUES (?, ?) "
                 "ON CONFLICT(user_id) DO UPDATE SET remind=excluded.remind",
                 (int(user_id), 1 if on else REMIND_OFF))
    PA.relink(conn, user_id, ALERT_TOPIC, bool(on))
    conn.commit()
    return 200, {"ok": True, "remind": bool(on)}


def _slots(games: list[dict]) -> list[tuple[float, list[dict]]]:
    """The week's kickoffs, each with its games, in order."""
    by: dict = {}
    for g in games:
        by.setdefault(round(float(g["kickoff"]) / 60) * 60, []).append(g)
    return sorted(by.items())


def next_up(conn, viewer, sport: str = "nfl", now: float | None = None,
            data_dir: Path | None = None) -> dict | None:
    """The Live tab's line (js/karma.js): this week's picks still to make,
    while any game of the week is still ahead and unpicked. None otherwise.
    ``lock`` is the next unpicked kickoff in UTC: the phone words it in its
    own time zone."""
    if viewer is None:
        return None
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    week = week_of(t)
    games = [g for g in board_games(sport, data_dir) if week_of(g["kickoff"]) == week]
    if not games:
        return None
    mine = {r[0] for r in conn.execute("SELECT gid FROM pickem_picks WHERE user_id=? AND sport=? AND week=?",
                                       (int(viewer), sport, week))}
    open_ = [g for g in games if not _started(g, t) and g["gid"] not in mine]
    if not open_:
        return None
    lock = min(float(g["kickoff"]) for g in open_)
    return {"sport": sport, "picked": sum(g["gid"] in mine for g in games), "games": len(games),
            "lock": _dt.datetime.fromtimestamp(lock, _dt.timezone.utc).isoformat().replace("+00:00", "Z")}


def alerts_pass(conn, now: float | None = None, data_dir: Path | None = None) -> int:
    """Queue the push before picks lock (engine/pushmine sends it): between
    three and two hours before the week's first kickoff, and before a day's
    first kickoff of BIG_SLOT games or more, to each player (``reminds``)
    who has a game there still unpicked. One a day at most (the day's first
    such kickoff claims it, picked or not), once a kickoff (its id), never
    in the quiet hours. Grades what is due first, so a perfect week and a
    winner's karma land without anybody opening the page."""
    from . import pushalerts as PA
    from . import pushmine as PM
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    try:
        from .db import DEFAULT_DB
        grade(conn, lambda: sqlite3.connect(f"file:{DEFAULT_DB}?mode=ro", uri=True), now=t)
    except Exception:                                     # noqa: BLE001
        pass
    if PA.quiet_now(_dt.datetime.fromtimestamp(t, ET)):
        return 0
    week = week_of(t)
    lo, hi = REMIND_LEAD_S
    told = 0
    for sport in REMIND_SPORTS:
        games = [g for g in board_games(sport, data_dir) if week_of(g["kickoff"]) == week]
        slots = _slots(games)
        if not slots:
            continue
        first, days = slots[0][0], set()
        for at, gs in slots:
            if not (at == first or len(gs) >= BIG_SLOT):
                continue
            day = _dt.datetime.fromtimestamp(at, ET).date()
            if day in days:                                # the day's first big kickoff had it
                continue
            days.add(day)
            if not lo <= at - t < hi:
                continue
            gids = {g["gid"] for g in gs}
            players = conn.execute("SELECT DISTINCT user_id FROM pickem_picks WHERE sport=? AND created_at>?",
                                   (sport, t - PLAYER_DAYS * 86400)).fetchall()
            for (uid,) in players:
                uid = int(uid)
                if _remind_pref(conn, uid) == REMIND_OFF:
                    continue
                mine = {r[0] for r in conn.execute("SELECT gid FROM pickem_picks WHERE user_id=? AND sport=? "
                                                   "AND week=?", (uid, sport, week))}
                left = len(gids - mine)
                if not left:
                    continue
                if not PM.asked(conn, uid, ALERT_TOPIC) and PA.phones(conn, uid):
                    PA.relink(conn, uid, ALERT_TOPIC, True)
                todo = sum(g["gid"] not in mine and not _started(g, t) for g in games)
                h = round((at - t) / 3600)
                what = f"{gs[0]['away']} at {gs[0]['home']} kicks" if len(gs) == 1 else f"{len(gs)} games kick"
                told += PM.tell(conn, uid, f"pickem:{sport}:{int(at)}", ALERT_TOPIC,
                                f"{SPORT_WORD[sport]} Pick'em locks in {h} hour{'s' if h != 1 else ''}",
                                (f"{what} off then, and you have {todo} pick{'s' if todo != 1 else ''} left "
                                 f"this week."),
                                f"/#feed/pickem/{sport}", ttl="pickem", now=t)
    return told + recap_pass(conn, now=t)


def _nth(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _recapped(conn, uid: int) -> dict:
    row = conn.execute("SELECT recap FROM pickem_prefs WHERE user_id=?", (uid,)).fetchone()
    return dict(x.split(":", 1) for x in str(row[0] if row else "").split(",") if ":" in x)


def _mark_recap(conn, uid: int, sport: str, week: str) -> None:
    done = {**_recapped(conn, uid), sport: week}
    conn.execute("INSERT INTO pickem_prefs (user_id, recap) VALUES (?, ?) "
                 "ON CONFLICT(user_id) DO UPDATE SET recap=excluded.recap",
                 (uid, ",".join(f"{k}:{v}" for k, v in sorted(done.items()))))


def recap_pass(conn, now: float | None = None) -> int:
    """Tuesday's line on the week just over, once a sport a week, to each
    player who has not turned the pick'em pushes off and whose picks of it
    are all graded: the record, the place, and the place among the friends
    who played. A week still being graded waits (to Wednesday); a week of
    pushes and voids says nothing."""
    from . import karma as K
    from . import pushalerts as PA
    from . import pushmine as PM
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    et = _dt.datetime.fromtimestamp(t, ET)
    if et.weekday() not in RECAP_DAYS or not RECAP_HOURS[0] <= et.hour < RECAP_HOURS[1]:
        return 0
    week = shift(week_of(t), -1)
    told = 0
    for sport in REMIND_SPORTS:
        places = _places(conn, sport, week, t)
        for uid, x in places.items():
            if x["open"] or not x["w"] + x["l"]:
                continue
            if _remind_pref(conn, uid) == REMIND_OFF or _recapped(conn, uid).get(sport) == week:
                continue
            bits = [f"{_nth(x['rank'])} of {len(places)}"]
            pals = (K.friend_ids(conn, uid) & set(places)) - {uid}
            if pals:
                ahead = sum((places[f]["w"], -places[f]["l"]) > (x["w"], -x["l"]) for f in pals)
                bits.append(f"{_nth(ahead + 1)} of {len(pals) + 1} among your friends")
            if not x["l"] and x["w"] >= PERFECT_MIN:
                bits.append(f"a perfect week, +{K.RULES['pickem_week'][0]} karma")
            rec = f"{x['w']}-{x['l']}" + (f"-{x['p']}" if x["p"] else "")
            if not PM.asked(conn, uid, ALERT_TOPIC) and PA.phones(conn, uid):
                PA.relink(conn, uid, ALERT_TOPIC, True)
            told += PM.tell(conn, uid, f"pickem:recap:{sport}:{week}", ALERT_TOPIC,
                            f"Your {SPORT_WORD[sport]} pick'em week: {rec}",
                            f"{' · '.join(bits)}. This week's games are up.", f"/#feed/pickem/{sport}",
                            ttl="pickem_recap", now=t)
            _mark_recap(conn, uid, sport, week)
    conn.commit()
    return told
