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
"""

from __future__ import annotations

import datetime as _dt
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
                    "game_date": date, "kickoff": k, "live": begun})
    return out


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
    if old is None:
        conn.execute("INSERT INTO pickem_picks (user_id, sport, week, gid, home, away, game_date, kickoff, pick, "
                     "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (int(user_id), sport, week, g["gid"], g["home"], g["away"], g["game_date"], g["kickoff"],
                      team, now, now))
    else:
        conn.execute("UPDATE pickem_picks SET pick=?, updated_at=?, week=?, kickoff=? WHERE user_id=? AND sport=? AND gid=?",
                     (team, now, week, g["kickoff"], int(user_id), sport, g["gid"]))
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
        conn.commit()
    finally:
        try:
            hconn.close()
        except Exception:                                 # noqa: BLE001
            pass
    return n


def standings(conn, sport: str, week: str | None, viewer=None, now: float | None = None) -> dict:
    """The table: a person's wins, losses, pushes and open picks for one
    week, or the season (``week`` None: every week of the last
    SEASON_DAYS). Ranked by wins, then fewest losses. Only people with a
    Social handle are named; a block hides both ways, as on the feed."""
    from . import socialfeed as SF
    ensure_tables(conn)
    SF.ensure_tables(conn)
    now = time.time() if now is None else float(now)
    where, args = ("p.week=?", [week]) if week else ("p.kickoff>?", [now - SEASON_DAYS * 86400])
    rows = conn.execute(
        "SELECT p.user_id, f.handle, f.display_name, f.color, f.fav_team, f.verified, f.founder, "
        "SUM(p.result='won') AS w, SUM(p.result='lost') AS l, SUM(p.result='push') AS pu, "
        "SUM(p.result IS NULL) AS open FROM pickem_picks p JOIN feed_profiles f ON f.user_id=p.user_id "
        f"WHERE p.sport=? AND f.handle IS NOT NULL AND f.handle!='' AND {where} GROUP BY p.user_id",
        [sport] + args).fetchall()
    hide = SF.blocked_ids(conn, viewer)
    table = []
    for r in rows:
        if int(r["user_id"]) in hide:
            continue
        table.append({**SF._person(r), "w": int(r["w"] or 0), "l": int(r["l"] or 0), "p": int(r["pu"] or 0),
                      "open": int(r["open"] or 0), "me": viewer is not None and int(r["user_id"]) == int(viewer)})
    table.sort(key=lambda x: (-x["w"], x["l"], -x["p"], str(x["handle"]).lower()))
    rank = 0
    last = None
    for i, x in enumerate(table):
        k = (x["w"], x["l"])
        if k != last:
            rank, last = i + 1, k
        x["rank"] = rank
    me = next((x for x in table if x["me"]), None)
    return {"rows": table[:TOP], "me": me, "players": len(table)}


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
        for r in conn.execute("SELECT gid, pick, result FROM pickem_picks WHERE user_id=? AND sport=? AND week=?",
                              (int(viewer), sport, week)):
            mine[r["gid"]] = {"pick": r["pick"], "result": r["result"]}
    out = []
    for g in sorted(games.values(), key=lambda x: (x["kickoff"], x["gid"])):
        s = split.get(g["gid"], {})
        m = mine.get(g["gid"]) or {}
        out.append({"gid": g["gid"], "home": g["home"], "away": g["away"],
                    "kickoff": _dt.datetime.fromtimestamp(g["kickoff"], _dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                    "locked": _started(g, now), "pick": m.get("pick"), "result": m.get("result"),
                    "n_home": s.get(g["home"], 0), "n_away": s.get(g["away"], 0)})
    prof = SF.profile_of(conn, viewer) if viewer is not None else None
    return {"sport": sport, "week": week, "label": week_label(week), "current": week == current,
            "prev": shift(week, -1), "next": shift(week, 1) if week < current else None,
            "games": out, "week_table": standings(conn, sport, week, viewer, now),
            "season_table": standings(conn, sport, None, viewer, now),
            "signed_in": viewer is not None, "has_handle": bool(prof and prof.get("handle")),
            "season_days": SEASON_DAYS}

