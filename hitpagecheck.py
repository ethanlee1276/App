#!/usr/bin/env python3
"""Is everything the MLB hit page now draws on file? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 hitpagecheck.py

Ethan, 2026-10-14: "And yes do the first 7 page items" — his runs and
stolen bases, each club's record on the day, the park and a View Game
button, barrels, MLB's own expected stats, the video of each at-bat and
his action photo (engine/mlb/charts, js/chart-mlb.js). One line or two
for each, in that order, off the database and the files the nightly and
the chart fill write; the last line asks MLB's photo server whether one
hitter's action photo is there (one HEAD request; `--no-probe` skips
it). Writes nothing.

* Runs and steals: the hitters with every game on file, of the hitters
  the play-by-play has; the rest are read a few hundred a night.
* Records: which way the league's figure runs (the record after the game
  or the day before it) and how many finals our own count agrees with —
  only those show a record. "neither" on most is the one to paste back.
* Barrels: the share of balls in play that are barrels by MLB's rule.
  The league's own runs about 7 to 8 per cent; far off that is a reading
  of the rule to look at.
"""

import argparse
import datetime as _dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _ro(path):
    """Read-only, never created: a missing file is an error, not an empty
    database the check made."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _one(conn, q, args=()):
    """One value; a table or column not there yet raises, and `report`
    says so on that part's line."""
    row = conn.execute(q, args).fetchone()
    return row[0] if row else None


def _pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "—"


def report(conn, today=None, probe=None) -> list[str]:
    """The check's lines. ``probe(url) -> str`` answers the photo line
    (None skips it). A part whose table the box has not made yet (the app
    makes them when it restarts on this code) is a line saying so."""
    today = today or _dt.date.today()
    season = today.year if today.month >= 3 else today.year - 1
    out = [f"hit page check — {today.isoformat()}, season {season}"]
    try:
        seasons = [int(s) for (s,) in conn.execute("SELECT DISTINCT season FROM mlb_pa ORDER BY season DESC")
                   if s is not None]
    except sqlite3.Error as exc:
        return out + [f"   no plate appearances to read ({exc})"]
    for n, part in enumerate(PARTS, 1):
        try:
            out += part(conn, today, season, seasons, probe)
        except sqlite3.Error as exc:
            out.append(f"{n}. not there yet: {exc} (the app makes it when it restarts on this code)")
    return out


def _runs(conn, today, season, seasons, probe):
    from engine.mlb import charts as MC
    out = []
    for s in seasons:
        hitters = _one(conn, "SELECT COUNT(DISTINCT batter_id) FROM mlb_pa WHERE season=?", (s,)) or 0
        owed = len(MC.bat_owed(conn, s))
        rows = _one(conn, "SELECT COUNT(*) FROM mlb_bat_games WHERE season=?", (s,)) or 0
        asked = _one(conn, "SELECT COUNT(*) FROM mlb_bat_games WHERE season=? AND runs IS NULL", (s,)) or 0
        out.append(f"1. runs and steals {s}: {hitters - owed:,} of {hitters:,} hitters have every game, "
                   f"{rows:,} game rows ({asked:,} asked and not carried), {owed:,} hitters still to read")
    return out


def _records(conn, today, season, seasons, probe):
    from engine.mlb import charts as MC
    out = []
    for s in seasons[:1] or [season]:
        rows = conn.execute(
            "SELECT game_pk, home, away, home_score, away_score, home_w, home_l, away_w, away_l FROM mlb_games "
            "WHERE season=? AND game_type='R' ORDER BY date, game_number, game_pk", (s,)).fetchall()
        tally: dict = {}
        how = {"after": 0, "before": 0, "neither": 0}
        for _pk, h, a, hs, as_, hw, hl, aw, al in rows:
            if hs is None or as_ is None:
                continue
            before = {t: tally.get(t, (0, 0)) for t in (h, a)}
            for t, mine, theirs in ((h, hs, as_), (a, as_, hs)):
                w, l = before[t]  # noqa: E741
                tally[t] = (w + (mine > theirs), l + (mine < theirs))
            for t, league in ((h, (hw, hl)), (a, (aw, al))):
                how["after" if league == tally[t] else "before" if league == before[t] else "neither"] += 1
        shown = sum(1 for r in MC._standing(conn, s).values() for x in r if x)
        out.append(f"2. records {s}: {len(rows):,} regular-season finals stored; the league's figure is the "
                   f"record after the game on {how['after']:,} club-games, the day before on {how['before']:,}, "
                   f"neither on {how['neither']:,}; {shown:,} records shown")
        last = conn.execute(
            "SELECT date, home, away, home_score, away_score, home_w, home_l, away_w, away_l FROM mlb_games "
            "WHERE season=? AND game_type='R' AND 'NYY' IN (home, away) ORDER BY date DESC, game_number DESC LIMIT 3",
            (s,)).fetchall()
        for date, h, a, hs, as_, hw, hl, aw, al in reversed(last):
            mine = (hw, hl) if h == "NYY" else (aw, al)
            out.append(f"   NYY {date} {a}@{h} {as_}-{hs}: the league says {mine[0]}-{mine[1]}")
    return out


def _parks(conn, today, season, seasons, probe):
    out = []
    games = _one(conn, "SELECT COUNT(*) FROM mlb_games") or 0
    parks = _one(conn, "SELECT COUNT(*) FROM mlb_games WHERE venue != ''") or 0
    post = conn.execute("SELECT game_pk, venue, series, series_game FROM mlb_games WHERE game_type != 'R' "
                        "ORDER BY date DESC LIMIT 1").fetchone()
    by = ", ".join(f"{s}: {n:,}" for s, n in conn.execute(
        "SELECT season, COUNT(*) FROM mlb_games GROUP BY season ORDER BY season DESC"))
    out.append(f"3. parks: {parks:,} of {games:,} games have one ({by or 'none stored'})"
               + (f"; latest October game {post[0]} at {post[1]}, {post[2]} game {post[3]} → "
                  f"https://www.mlb.com/gameday/{post[0]}" if post else ""))
    return out


def _barrels(conn, today, season, seasons, probe):
    from engine.mlb import charts as MC
    out = []
    for s in seasons[:1]:
        balls = conn.execute("SELECT launch_speed, launch_angle FROM mlb_pa WHERE season=? AND launch_speed IS NOT NULL",
                             (s,)).fetchall()
        brl = sum(1 for ev, la in balls if MC.barrel(ev, la))
        out.append(f"4. barrels {s}: {brl:,} of {len(balls):,} balls in play by MLB's rule ({_pct(brl, len(balls))}; "
                   f"the league's runs about 7 to 8%)")
    return out


def _savant(conn, today, season, seasons, probe):
    from engine.mlb.sources import savant
    out = []
    for s in (season, season - 1):
        names = savant.page_names(s)
        files = [savant.CACHE_DIR / n for n in names]
        if not any(f.exists() for f in files):
            out.append(f"5. Baseball Savant {s}: no file yet ({', '.join(names)})")
            continue
        board = savant.page_board(s)
        xs = sum(1 for v in board.values() if v.get("xba") is not None)
        bs = sum(1 for v in board.values() if v.get("brl_pct") is not None)
        at = next(iter(board.values()), {}).get("at", "")
        j = board.get(592450) or {}
        out.append(f"5. Baseball Savant {s}: expected stats for {xs:,} hitters, barrel rates for {bs:,}, as of {at}"
                   + (f"; Aaron Judge xBA {j.get('xba')} xSLG {j.get('xslg')} barrels {j.get('brl_pct')}" if j else ""))
    return out


def _video(conn, today, season, seasons, probe):
    from engine.mlb import charts as MC
    out = []
    for s in seasons[:1]:
        last = _one(conn, "SELECT MAX(date) FROM mlb_pa WHERE season=?", (s,))
        since = (_dt.date.fromisoformat(str(last)[:10]) - _dt.timedelta(days=MC.PLAY_IDS_DAYS)).isoformat() if last else ""
        n = _one(conn, "SELECT COUNT(*) FROM mlb_pa WHERE season=? AND date>=?", (s, since)) or 0
        ids = _one(conn, "SELECT COUNT(*) FROM mlb_pa WHERE season=? AND date>=? AND play_id != ''", (s, since)) or 0
        unread = _one(conn, "SELECT COUNT(DISTINCT game_pk) FROM mlb_pa WHERE season=? AND date>=? AND play_id IS NULL",
                      (s, since)) or 0
        one = _one(conn, "SELECT play_id FROM mlb_pa WHERE season=? AND play_id != '' ORDER BY date DESC LIMIT 1", (s,))
        out.append(f"6. video {s}: {ids:,} of {n:,} plate appearances since {since} carry MLB's video id, "
                   f"{unread:,} games still to read again"
                   + (f"; e.g. https://baseballsavant.mlb.com/sporty-videos?playId={one}" if one else ""))
    return out


def _photo(conn, today, season, seasons, probe):
    from engine.mlb.sources import mlbstats
    url = mlbstats.action_url(592450)
    return [f"7. action photo: {url}" + (f" → {probe(url)}" if probe else " (not asked)")]


#: The seven, in the order Ethan listed them.
PARTS = (_runs, _records, _parks, _barrels, _savant, _video, _photo)


def _head(url) -> str:
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return f"{resp.status} {resp.headers.get('Content-Type', '')}"
    except Exception as exc:                                       # noqa: BLE001
        return f"not there: {exc}"


def main(argv=None) -> int:
    from engine import db
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(db.DEFAULT_DB))
    ap.add_argument("--no-probe", action="store_true", help="skip the one HEAD request for the photo")
    a = ap.parse_args(argv)
    conn = _ro(a.db)
    try:
        for line in report(conn, probe=None if a.no_probe else _head):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
