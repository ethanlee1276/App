"""Every plate appearance and every pitch, for the MLB hit tracker and pitch chart.

Ethan, 2026-10-13: "Can we do a hit tracker for mlb?", then "Yes do all of
them and don't stop till they are all done ... make sure they are all
routed correctly like nfl." The football pick pages draw a player's carry,
route and passing charts in place; this is baseball's pair.

WHAT THE RECORD HAS. The free MLB Stats API play-by-play
(`/game/{gamePk}/playByPlay`, engine/mlb/sources/pbp) carries, for every
plate appearance, the batter and his side, the pitcher and his hand, the
result, the runs driven in and every pitch thrown; and on a ball put in
play, `hitData`: exit velocity, launch angle, distance, the trajectory
(ground ball, line drive, fly ball, popup), the hardness, the fielder it
went to and where it landed (`coordinates`). The shape was printed off a
real payload on the box on 2026-09-05 (docs/DROPLET_CHECKS.md §2). Every
pitch carries its type, speed, spin, where it crossed the plate (`pX`,
`pZ`, feet from the middle of the plate and from the ground), the zone
and the umpire's call — the fields engine/mlb/velocity, csw and arsenal
already read every night.

TWO TABLES. `mlb_pa`, one row per completed plate appearance, is the hit
tracker; `mlb_pitches`, one row per pitch, is the pitch chart. A pitch is
stored with ids only (the names live on the plate appearance), so a
season of ~730,000 pitches stays near 60 MB.

WHERE IT COMES FROM. `ingest_range` reads every final game in a date range
the nightly MLB chores already ask for, and only the games it has not
stored (a final's pitches never change); `backfill` walks a season's
finals a nightly budget at a time, so a season of ~2,430 games is read
over a few nights rather than in one burst against a host that answers
429 when pressed.

THE CHARTS SAY WHAT THE RECORD SAYS. Hard-hit is the league's own cut
(95 mph or harder); the sweet spot is 8 to 32 degrees; pull, center and
opposite field are read off where the ball landed and the batter's side.
Nothing here is a model: no expected stats, no barrels (the league's
barrel table is not published in the feed, and a guessed one would be
printed beside his name as if it were the league's).
"""

from __future__ import annotations

import math

from ..carries import _fold

#: Regular season and the four postseason rounds; spring, exhibition and
#: the All-Star Game are not a player's record.
GAME_TYPES = ("R", "F", "D", "L", "W")
DEAD = {"C", "D", "T"}

#: The plays in `allPlays` that are not a plate appearance: an inning that
#: ends on the bases ends with the batter still at the plate.
NOT_PA_PREFIX = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch", "passed_ball",
                 "balk", "other_advance", "defensive_indiff", "runner_double_play",
                 "game_advisory", "batter_timeout", "mound_visit", "pitching_substitution",
                 "offensive_substitution", "defensive_switch", "defensive_sub")
HIT_BASES = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
NOT_AB = {"walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interf",
          "sac_fly_double_play", "sac_bunt_double_play"}
STRIKEOUTS = {"strikeout", "strikeout_double_play", "strikeout_triple_play"}
WALKS = {"walk", "intent_walk"}
#: The league's hard-hit line and its sweet spot.
HARD_HIT = 95.0
SWEET = (8.0, 32.0)
#: Where home plate sits in the feed's hit coordinates, and the spray
#: angle (degrees from straightaway centre) past which a ball is pulled
#: or hit the other way.
HOME_X, HOME_Y = 125.42, 198.27
PULL_DEG = 15.0
#: Pitch calls (statsapi `details.call.code`): the misses and the called
#: strikes the CSW measure already counts (engine/mlb/csw, arsenal), and
#: the rest of a swing — a foul, a foul tip, a ball in play.
CALLED = {"C"}
FOULS = {"F", "T", "L", "O", "R"}
IN_PLAY = {"X", "D", "E"}

PA_COLS = ["game_pk", "at_bat", "season", "date", "batter_id", "batter", "bat_side", "pitcher_id",
           "pitcher", "pitch_hand", "team", "opponent", "home", "inning", "half", "event",
           "event_type", "rbi", "pitches", "launch_speed", "launch_angle", "distance",
           "trajectory", "hardness", "location", "coord_x", "coord_y"]
PITCH_COLS = ["game_pk", "at_bat", "n", "season", "date", "pitcher_id", "batter_id", "bat_side",
              "inning", "pitch_type", "speed", "spin", "px", "pz", "sz_top", "sz_bot", "zone",
              "code", "balls", "strikes"]


def _whiffs() -> set:
    from .arsenal import WHIFF_CODES
    return set(WHIFF_CODES)


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _int(v):
    f = _num(v)
    return None if f is None else int(f)


# --- the games -------------------------------------------------------------------
def finals(schedule: dict) -> list[dict]:
    """``[{game_pk, date, home, away, type}]`` — every final regular-season
    or postseason game in a schedule payload."""
    from .sources.mlbstats import TEAM_ID_ABBR
    out = []
    for day in (schedule or {}).get("dates") or []:
        for g in day.get("games") or []:
            st = g.get("status") or {}
            if st.get("abstractGameState") != "Final" or (st.get("codedGameState") or "") in DEAD:
                continue
            kind = g.get("gameType") or "R"
            if kind not in GAME_TYPES or not g.get("gamePk"):
                continue
            teams = g.get("teams") or {}
            side = {}
            for k in ("home", "away"):
                t = (teams.get(k) or {}).get("team") or {}
                side[k] = TEAM_ID_ABBR.get(t.get("id"), t.get("abbreviation", "")) or ""
            if not side["home"] or not side["away"]:
                continue
            out.append({"game_pk": int(g["gamePk"]), "date": (g.get("officialDate") or g.get("gameDate", ""))[:10],
                        "home": side["home"], "away": side["away"], "type": kind})
    return out


def fold(payload: dict, game: dict) -> tuple[list, list]:
    """``(plate appearances, pitches)`` for one final game, as table rows.

    The batting side is read off the half inning (the away team bats in
    the top), so a row is keyed to the team keys the rest of MLB uses."""
    pas, pitches = [], []
    pk, date = int(game["game_pk"]), str(game["date"])
    season = int(date[:4])
    for play in (payload or {}).get("allPlays") or []:
        about = play.get("about") or {}
        matchup = play.get("matchup") or {}
        result = play.get("result") or {}
        event = str(result.get("event") or "").strip()
        etype = str(result.get("eventType") or "").strip()
        if not event:
            continue                                   # not finished
        ab = _int(about.get("atBatIndex"))
        if ab is None:
            continue
        half = str(about.get("halfInning") or "").lower()
        top = half == "top"
        batter = matchup.get("batter") or {}
        pitcher = matchup.get("pitcher") or {}
        bat_side = str((matchup.get("batSide") or {}).get("code") or "")
        hand = str((matchup.get("pitchHand") or {}).get("code") or "")
        inning = _int(about.get("inning"))
        hit, n = None, 0
        for ev in play.get("playEvents") or []:
            details = ev.get("details") or {}
            is_pitch = ev.get("isPitch")
            if is_pitch is None:
                is_pitch = details.get("isPitch")
            if not is_pitch:
                continue
            n += 1
            pd = ev.get("pitchData") or {}
            co = pd.get("coordinates") or {}
            cnt = ev.get("count") or {}
            pitches.append({
                "game_pk": pk, "at_bat": ab, "n": _int(ev.get("pitchNumber")) or n, "season": season,
                "date": date, "pitcher_id": _int(pitcher.get("id")), "batter_id": _int(batter.get("id")),
                "bat_side": bat_side, "inning": inning,
                "pitch_type": str((details.get("type") or {}).get("code") or ""),
                "speed": _num(pd.get("startSpeed")), "spin": _num((pd.get("breaks") or {}).get("spinRate")),
                "px": _num(co.get("pX")), "pz": _num(co.get("pZ")),
                "sz_top": _num(pd.get("strikeZoneTop")), "sz_bot": _num(pd.get("strikeZoneBottom")),
                "zone": _int(pd.get("zone")), "code": str((details.get("call") or {}).get("code") or ""),
                "balls": _int(cnt.get("balls")), "strikes": _int(cnt.get("strikes"))})
            if isinstance(ev.get("hitData"), dict):
                hit = ev["hitData"]
        if not etype or etype.startswith(NOT_PA_PREFIX):
            continue
        hd = hit or {}
        co = hd.get("coordinates") or {}
        pas.append({
            "game_pk": pk, "at_bat": ab, "season": season, "date": date,
            "batter_id": _int(batter.get("id")), "batter": str(batter.get("fullName") or ""),
            "bat_side": bat_side, "pitcher_id": _int(pitcher.get("id")),
            "pitcher": str(pitcher.get("fullName") or ""), "pitch_hand": hand,
            "team": game["away"] if top else game["home"], "opponent": game["home"] if top else game["away"],
            "home": 0 if top else 1, "inning": inning, "half": "T" if top else "B",
            "event": event, "event_type": etype, "rbi": _int(result.get("rbi")) or 0, "pitches": n,
            "launch_speed": _num(hd.get("launchSpeed")), "launch_angle": _num(hd.get("launchAngle")),
            "distance": _num(hd.get("totalDistance")), "trajectory": str(hd.get("trajectory") or ""),
            "hardness": str(hd.get("hardness") or ""), "location": str(hd.get("location") or ""),
            "coord_x": _num(co.get("coordX")), "coord_y": _num(co.get("coordY"))})
    return pas, pitches


# --- keeping it current ------------------------------------------------------------
def stored(conn, season: int | None = None) -> set:
    """The game ids already folded (a final's plays never change)."""
    q, args = "SELECT DISTINCT game_pk FROM mlb_pitches", ()
    if season is not None:
        q, args = q + " WHERE season=?", (int(season),)
    try:
        return {int(r[0]) for r in conn.execute(q, args)}
    except Exception:                                              # noqa: BLE001
        return set()


def ingest_games(conn, games: list, fetch=None, workers: int = 4) -> dict:
    """Fold and store every game in ``games`` not already stored.
    Returns ``{"games", "pas", "pitches", "failed"}``."""
    from .. import db
    from .sources import pbp as P
    from .sources.mlbstats import fetch_many
    fetch = fetch or P.fetch_playbyplay
    have = stored(conn)
    todo = [g for g in games if int(g["game_pk"]) not in have]
    out = {"games": 0, "pas": 0, "pitches": 0, "failed": 0}
    if not todo:
        return out
    payloads = fetch_many(fetch, [(g["game_pk"],) for g in todo], workers=workers)
    for g, payload in zip(todo, payloads):
        if not payload:
            out["failed"] += 1
            continue
        pas, pitches = fold(payload, g)
        if not pitches:
            out["failed"] += 1
            continue
        out["pas"] += db.upsert_mlb_pa(conn, pas)
        out["pitches"] += db.upsert_mlb_pitches(conn, pitches)
        out["games"] += 1
    return out


def ingest_range(conn, start: str, end: str, fetch=None) -> dict:
    """Every final in ``start..end`` (the nightly's own date range) not yet
    stored. The schedule is the cached one the results ingest just read."""
    from .sources.mlbstats import fetch_schedule
    return ingest_games(conn, finals(fetch_schedule(start, end)), fetch=fetch)


#: Games read per night by the season backfill: a season of ~2,430 finals
#: in about a week of nights, each night's reads spread over four workers.
BACKFILL_PER_NIGHT = 400


def read_once(game_pk) -> dict:
    """An older final's play-by-play for the backfill, read and let go.

    The cached copy (`mlb_pbp_{pk}.json`, ~640 KB) would sit in data/cache
    for the prune's month, and a season of them is ~1.5 GB that nothing
    reads again: the game's rows are in the tables by then. A copy that
    was already there (a starter's recent game the nightly reads for his
    velocity) is left exactly as it was."""
    from .sources import mlbstats as S, pbp as P
    path = S.CACHE_DIR / f"mlb_pbp_{int(game_pk)}.json"
    had = path.exists()
    try:
        return P.fetch_playbyplay(game_pk)
    finally:
        if not had:
            try:
                path.unlink()
            except OSError:
                pass


def backfill(conn, season: int, through: str, budget: int = BACKFILL_PER_NIGHT, fetch=None) -> dict:
    """The season's finals not yet stored, newest first, ``budget`` at a
    time: the games a page is likeliest to be asked about come first. Each
    is read without keeping its file (`read_once`)."""
    from .sources.mlbstats import fetch_schedule
    games = finals(fetch_schedule(f"{int(season)}-03-01", through))
    have = stored(conn, season)
    todo = sorted((g for g in games if g["game_pk"] not in have), key=lambda g: g["date"], reverse=True)
    out = ingest_games(conn, todo[:max(0, int(budget))], fetch=fetch or read_once)
    out["left"] = max(0, len(todo) - out["games"] - out["failed"])
    return out


# --- what the page draws -------------------------------------------------------------
def _resolve(conn, player: str, role: str) -> tuple:
    """``(id, stored name)`` for a batter or a pitcher, or (None, "")."""
    col = "batter" if role == "batter" else "pitcher"
    q = (player or "").strip()
    if not q:
        return None, ""
    row = conn.execute(f"SELECT {col}_id, {col} FROM mlb_pa WHERE {col}=? ORDER BY date DESC LIMIT 1",
                       (q,)).fetchone()
    if row:
        return row[0], row[1]
    want = _fold(q)
    if not want:
        return None, ""
    hits = {}
    for pid, name in conn.execute(f"SELECT DISTINCT {col}_id, {col} FROM mlb_pa"):
        if _fold(name) == want:
            hits[pid] = name
    return next(iter(hits.items())) if len(hits) == 1 else (None, "")


def spray_angle(x, y) -> float | None:
    """Degrees from straightaway centre field, negative toward left."""
    if x is None or y is None:
        return None
    dx, dy = x - HOME_X, HOME_Y - y
    if dy <= 0 and abs(dx) < 1e-9:
        return None
    return math.degrees(math.atan2(dx, dy))


def direction(x, y, side) -> str:
    """"pull", "center" or "oppo" for a ball in play, by his side."""
    a = spray_angle(x, y)
    if a is None or side not in ("L", "R"):
        return ""
    if abs(a) <= PULL_DEG:
        return "center"
    left = a < 0
    return "pull" if (left and side == "R") or (not left and side == "L") else "oppo"


def _hline(pas: list) -> dict:
    """A game's or a split's batting line, off his plate appearances."""
    n = len(pas)
    ab = [p for p in pas if p["et"] not in NOT_AB]
    hits = [p for p in pas if p["et"] in HIT_BASES]
    bip = [p for p in pas if p["ls"] is not None]
    ev = [p["ls"] for p in bip]
    la = [p["la"] for p in pas if p["la"] is not None]
    return {"n": n, "pa": n, "ab": len(ab), "h": len(hits), "tb": sum(HIT_BASES[p["et"]] for p in hits),
            "hr": sum(1 for p in hits if p["et"] == "home_run"),
            "xbh": sum(1 for p in hits if p["et"] in ("double", "triple", "home_run")),
            "bb": sum(1 for p in pas if p["et"] in WALKS), "k": sum(1 for p in pas if p["et"] in STRIKEOUTS),
            "rbi": sum(p["rbi"] for p in pas), "bip": len(bip),
            "hard": sum(1 for v in ev if v >= HARD_HIT),
            "ev": round(sum(ev) / len(ev), 1) if ev else None,
            "la": round(sum(la) / len(la), 1) if la else None,
            "sweet": sum(1 for v in la if SWEET[0] <= v <= SWEET[1]),
            "max_ev": max(ev) if ev else None,
            "avg": round(len(hits) / len(ab), 3) if ab else None}


def hits_chart(conn, player: str, season: int | None = None) -> dict:
    """Everything the hit tracker draws for one batter-season.

    ``{player, sport, seasons, season, team, side, games: [{id, date, opp,
    home, team, line, pas}], season_line, by_type, by_dir, by_hand}`` —
    games newest first, each plate appearance ``{inn, half, ev, et, p, ph,
    rbi, np, ls, la, d, tr, hd, loc, x, y}``. ``{}`` with nothing on file."""
    pid, name = _resolve(conn, player, "batter")
    if pid is None:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        "SELECT DISTINCT season FROM mlb_pa WHERE batter_id=? ORDER BY season DESC", (pid,))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    cur = conn.execute("SELECT * FROM mlb_pa WHERE batter_id=? AND season=? ORDER BY date, game_pk, at_bat",
                       (pid, pick))
    cols = [d[0] for d in cur.description]
    games: dict = {}
    side = ""
    for r in (dict(zip(cols, x)) for x in cur.fetchall()):
        side = r["bat_side"] or side
        g = games.setdefault(r["game_pk"], {"id": r["game_pk"], "date": r["date"], "opp": r["opponent"],
                                            "home": bool(r["home"]), "team": r["team"], "pas": []})
        g["pas"].append({"inn": r["inning"], "half": r["half"], "ev": r["event"], "et": r["event_type"],
                         "p": r["pitcher"], "ph": r["pitch_hand"], "rbi": r["rbi"], "np": r["pitches"],
                         "ls": r["launch_speed"], "la": r["launch_angle"], "d": r["distance"],
                         "tr": r["trajectory"], "hd": r["hardness"], "loc": r["location"],
                         "x": r["coord_x"], "y": r["coord_y"],
                         "dir": direction(r["coord_x"], r["coord_y"], r["bat_side"])})
    out_games = []
    for g in sorted(games.values(), key=lambda g: (g["date"], g["id"]), reverse=True):
        g["line"] = _hline(g["pas"])
        out_games.append(g)
    every = [p for g in out_games for p in g["pas"]]
    types = (("ground_ball", "Ground balls"), ("line_drive", "Line drives"), ("fly_ball", "Fly balls"),
             ("popup", "Popups"))
    by_type = [dict(_hline([p for p in every if p["tr"] == k]), key=k, name=label)
               for k, label in types if any(p["tr"] == k for p in every)]
    by_dir = [dict(_hline([p for p in every if p["dir"] == k]), key=k, name=label)
              for k, label in (("pull", "Pulled"), ("center", "Up the middle"), ("oppo", "Opposite field"))
              if any(p["dir"] == k for p in every)]
    by_hand = [dict(_hline([p for p in every if p["ph"] == h]), key=h, name=label)
               for h, label in (("R", "vs right-handers"), ("L", "vs left-handers"))
               if any(p["ph"] == h for p in every)]
    latest = out_games[0] if out_games else {}
    return {"player": name, "sport": "mlb", "seasons": seasons, "season": pick, "team": latest.get("team", ""),
            "side": side, "games": out_games, "season_line": _hline(every), "by_type": by_type,
            "by_dir": by_dir, "by_hand": by_hand}


def _pline(ps: list, pas: list) -> dict:
    """A start's or a split's pitching line: pitches, what they drew, and
    what the batters he faced did."""
    whiff_codes = _whiffs()
    n = len(ps)
    whiffs = sum(1 for p in ps if p[4] in whiff_codes)
    called = sum(1 for p in ps if p[4] in CALLED)
    swings = sum(1 for p in ps if p[4] in whiff_codes or p[4] in FOULS or p[4] in IN_PLAY)
    zone = sum(1 for p in ps if p[5] is not None and 1 <= p[5] <= 9)
    hits = [x for x in pas if x["event_type"] in HIT_BASES]
    return {"n": n, "pitches": n, "bf": len(pas), "k": sum(1 for x in pas if x["event_type"] in STRIKEOUTS),
            "bb": sum(1 for x in pas if x["event_type"] in WALKS), "h": len(hits),
            "hr": sum(1 for x in hits if x["event_type"] == "home_run"),
            "whiffs": whiffs, "called": called, "swings": swings,
            "csw": round((whiffs + called) / n, 3) if n else None,
            "whiff": round(whiffs / swings, 3) if swings else None,
            "zone": round(zone / n, 3) if n else None,
            "top": max((p[1] for p in ps if p[1] is not None), default=None)}


#: The fastballs a pitcher's velocity is read off, start to start.
FASTBALLS = ("FF", "SI", "FC")


def pitches_chart(conn, player: str, season: int | None = None) -> dict:
    """Everything the pitch chart draws for one pitcher-season.

    ``{player, sport, seasons, season, team, hand, games: [{id, date, opp,
    home, team, line, mix, p, faced}], season_line, mix, zones, velo}`` — games
    newest first; each pitch a compact ``[type, speed, px, pz, code, zone,
    sz_top, sz_bot, inning, at_bat, bat_side]``; ``mix`` his pitch types by
    share with their speed and whiff rate; ``zones`` the strike zone's
    nine boxes and the four outside it, each with pitches and whiffs;
    ``velo`` his main fastball's average speed start by start."""
    pid, name = _resolve(conn, player, "pitcher")
    if pid is None:
        return {}
    seasons = [int(s) for (s,) in conn.execute(
        "SELECT DISTINCT season FROM mlb_pitches WHERE pitcher_id=? ORDER BY season DESC", (pid,))]
    if not seasons:
        return {}
    pick = int(season) if season and int(season) in seasons else seasons[0]
    pcur = conn.execute("SELECT game_pk, pitch_type, speed, px, pz, code, zone, sz_top, sz_bot, inning, at_bat, "
                        "bat_side, date FROM mlb_pitches WHERE pitcher_id=? AND season=? "
                        "ORDER BY date, game_pk, at_bat, n", (pid, pick))
    by_game: dict = {}
    for gpk, t, v, px, pz, code, zone, top, bot, inn, ab, bs, date in pcur.fetchall():
        by_game.setdefault(gpk, {"date": date, "p": []})["p"].append(
            [t or "", v, px, pz, code or "", zone, top, bot, inn, ab, bs or ""])
    acur = conn.execute("SELECT * FROM mlb_pa WHERE pitcher_id=? AND season=?", (pid, pick))
    cols = [d[0] for d in acur.description]
    pas_by: dict = {}
    hand, team_of = "", {}
    for r in (dict(zip(cols, x)) for x in acur.fetchall()):
        pas_by.setdefault(r["game_pk"], []).append(r)
        hand = r["pitch_hand"] or hand
        # He pitched for the side that was NOT batting.
        team_of[r["game_pk"]] = (r["opponent"], r["team"], not bool(r["home"]))
    games = []
    for gpk, g in by_game.items():
        team, opp, home = team_of.get(gpk, ("", "", False))
        line = _pline(g["p"], pas_by.get(gpk, []))
        # Every batter he faced, in order: the list under the chart, and
        # what a tap on one lights up among the pitches (`ab`).
        faced = [{"inn": x["inning"], "half": x["half"], "b": x["batter"], "bs": x["bat_side"],
                  "ev": x["event"], "et": x["event_type"], "np": x["pitches"], "ab": x["at_bat"],
                  "rbi": x["rbi"]}
                 for x in sorted(pas_by.get(gpk, []), key=lambda x: x["at_bat"])]
        games.append({"id": gpk, "date": g["date"], "opp": opp, "home": home, "team": team, "line": line,
                      "mix": _mix(g["p"]), "p": g["p"], "faced": faced})
    games.sort(key=lambda g: (g["date"], g["id"]), reverse=True)
    every = [p for g in games for p in g["p"]]
    all_pas = [x for v in pas_by.values() for x in v]
    whiff_codes = _whiffs()
    zones = []
    for z in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14):
        zs = [p for p in every if p[5] == z]
        swings = [p for p in zs if p[4] in whiff_codes or p[4] in FOULS or p[4] in IN_PLAY]
        zones.append({"zone": z, "n": len(zs), "whiffs": sum(1 for p in zs if p[4] in whiff_codes),
                      "swings": len(swings), "share": round(len(zs) / len(every), 3) if every else None})
    mix = _mix(every)
    main = next((m["type"] for m in mix if m["type"] in FASTBALLS), mix[0]["type"] if mix else "")
    velo = []
    for g in sorted(games, key=lambda g: (g["date"], g["id"])):
        vs = [p[1] for p in g["p"] if p[0] == main and p[1] is not None]
        if vs:
            velo.append({"date": g["date"], "opp": g["opp"], "avg": round(sum(vs) / len(vs), 1), "n": len(vs)})
    latest = games[0] if games else {}
    return {"player": name, "sport": "mlb", "seasons": seasons, "season": pick, "team": latest.get("team", ""),
            "hand": hand, "games": games, "season_line": _pline(every, all_pas), "mix": mix,
            "zones": zones, "velo": velo, "velo_type": main}


def _mix(ps: list) -> list:
    """His pitch types by share, each with its average speed, its whiff
    rate (misses per swing) and its called-strike-plus-whiff rate."""
    whiff_codes = _whiffs()
    by: dict = {}
    for p in ps:
        by.setdefault(p[0] or "?", []).append(p)
    n = len(ps)
    out = []
    for t, xs in by.items():
        vs = [p[1] for p in xs if p[1] is not None]
        whiffs = sum(1 for p in xs if p[4] in whiff_codes)
        swings = sum(1 for p in xs if p[4] in whiff_codes or p[4] in FOULS or p[4] in IN_PLAY)
        called = sum(1 for p in xs if p[4] in CALLED)
        out.append({"type": t, "n": len(xs), "share": round(len(xs) / n, 3) if n else None,
                    "velo": round(sum(vs) / len(vs), 1) if vs else None,
                    "whiff": round(whiffs / swings, 3) if swings else None,
                    "csw": round((whiffs + called) / len(xs), 3) if xs else None})
    out.sort(key=lambda m: (-m["n"], m["type"]))
    return out
