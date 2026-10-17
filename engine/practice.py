"""Practice reports and how honest each club's "questionable" is.

Ethan, 2026-10-16: "add everything now. 1-13" — idea 5. Every club files
an injury report each week: a game designation (Questionable, Doubtful,
Out) and how the man practised (did not, limited, full). nflverse has
published every one since 2009, and this box already downloads it twice a
day — and reads only the designation. Two things in it nobody prices:

  * HOW HE PRACTISED. A questionable man who was limited on Friday and a
    questionable man who did not practise at all are not the same bet.
  * WHO FILED IT. Some clubs list half the roster questionable and play
    them all; some list a man questionable only when they mean it. The
    same word, two different chances.

WHAT IS MEASURED, on every listed player-week the box holds:
    played      a snap share above zero in that game (nflverse snap counts)
    snap ratio  his share that game over his average of the four before

per (designation, how he practised), and per club and season for the
questionable designation, shrunk toward the league by PRIOR_N listings
so a club with six questionable players does not get its own number.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. On the seasons held out: the
club-and-practice chance a questionable man plays must beat the
league-wide chance by log loss, with a paired t ≥ MIN_T over at least
MIN_LISTED listings. Since 2026-10-17 the held-out seasons are the newest
two, each scored walk-forward on the seasons before it, and each must
come out ahead on its own: the newest season alone (a part season) could
never reach MIN_LISTED. Until then the page shows both numbers as readings
and nothing on the board — the hold, a projection, a tier — reads them.

Standard library only.
"""

from __future__ import annotations

import json
import math

PRACTICE = {"did not participate in practice": "DNP", "did not practice": "DNP", "dnp": "DNP",
            "limited participation in practice": "Limited", "limited": "Limited",
            "full participation in practice": "Full", "full": "Full"}
DESIGNATIONS = ("Questionable", "Doubtful", "Out")
#: Shrink a club's questionable rate toward the league's by this many listings.
PRIOR_N = 20
#: A snap ratio needs this many games before the one listed.
MIN_PRIOR_GAMES = 2
#: The bar.
MIN_T = 2.0
MIN_LISTED = 300
STORE = "practice_fit.json"


def practice_of(raw) -> str:
    return PRACTICE.get(str(raw or "").strip().lower(), "None")


def designation_of(raw) -> str:
    r = str(raw or "").strip().lower()
    for d in DESIGNATIONS:
        if r == d.lower():
            return d
    return ""


def _norm(name):
    from .backtest import _norm as n
    return n(name)


def listings(injury_rows, snaps: dict) -> list:
    """``injury_rows``: nflverse injury report rows (any seasons).
    ``snaps``: {(norm name, season, week): snap share 0-1} from the logs.
    → [(season, team, designation, practice, played, snap_ratio|None)]."""
    out = []
    for r in injury_rows:
        d = designation_of(r.get("report_status"))
        if not d:
            continue
        try:
            season, week = int(r.get("season")), int(r.get("week"))
        except (TypeError, ValueError):
            continue
        name = _norm(r.get("full_name") or r.get("player_name") or "")
        if not name:
            continue
        share = snaps.get((name, season, week))
        prior = [snaps.get((name, season, w)) for w in range(week - 4, week)]
        prior = [p for p in prior if p]
        if share is None and not prior:
            continue                         # no snap history at all: not a player the logs follow
        played = bool(share and share > 0)
        ratio = (share / (sum(prior) / len(prior))) if played and len(prior) >= MIN_PRIOR_GAMES else None
        out.append((season, str(r.get("team") or ""), d, practice_of(r.get("practice_status")), played, ratio))
    return out


def table(rows) -> dict:
    """``{"designation|practice": {"n", "played", "ratio"}}`` and the league
    questionable rate."""
    acc: dict = {}
    for _s, _t, d, p, played, ratio in rows:
        for key in (f"{d}|{p}", f"{d}|*"):
            a = acc.setdefault(key, [0, 0, 0.0, 0])
            a[0] += 1
            a[1] += int(played)
            if ratio is not None:
                a[2] += ratio
                a[3] += 1
    return {k: {"n": a[0], "played": round(a[1] / a[0], 4), "ratio": round(a[2] / a[3], 3) if a[3] else None}
            for k, a in acc.items()}


def clubs(rows, league_q: float) -> dict:
    """``{"TEAM|season": {"n", "raw", "played"}}`` for the questionable
    designation, shrunk toward the league by PRIOR_N listings."""
    acc: dict = {}
    for season, team, d, _p, played, _r in rows:
        if d != "Questionable" or not team:
            continue
        a = acc.setdefault(f"{team}|{season}", [0, 0])
        a[0] += 1
        a[1] += int(played)
    return {k: {"n": n, "raw": round(k_ / n, 4),
                "played": round((k_ + PRIOR_N * league_q) / (n + PRIOR_N), 4)}
            for k, (n, k_) in acc.items()}


def chance(fit: dict, team: str, season: int, designation: str, practice: str) -> dict | None:
    """The chance he plays, league-wide for his designation and practice,
    and with his club's honesty folded in (questionable only): the club's
    shrunk rate over the league's questionable rate, times the league's
    rate for his practice status. None when the table has no such row."""
    tab = (fit or {}).get("table") or {}
    row = tab.get(f"{designation}|{practice}") or tab.get(f"{designation}|*")
    if not row:
        return None
    out = {"league": row["played"], "n": row["n"], "ratio": row.get("ratio"), "club": None, "club_n": 0}
    if designation == "Questionable":
        q = (tab.get("Questionable|*") or {}).get("played")
        c = ((fit or {}).get("clubs") or {}).get(f"{team}|{season}") or ((fit or {}).get("clubs") or {}).get(f"{team}|{season - 1}")
        if q and c:
            out["club"] = round(min(0.995, row["played"] * c["played"] / q), 4)
            out["club_n"] = c["n"]
    return out


def _ll(p, y):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(math.log(p) if y else math.log(1 - p))


def held_out(rows) -> dict:
    """Walk-forward over the held-out seasons (the newest two once there
    are three — engine/bookmenu.held_seasons): each one's questionable
    listings scored with a fit on every season before it, league-and-
    practice chance against club-folded chance, by log loss, paired and
    pooled. Scored on the newest season alone, a part season held 66
    questionable listings against a bar of 300 (box run, 2026-10-17); and
    a club's honesty is read from its season or the one before, so each
    season has to see the seasons before it."""
    from .bookmenu import held_seasons
    test = held_seasons({r[0] for r in rows})
    if not test:
        return {"n": 0, "gain": None, "t": None, "holds": False}
    diffs: list = []
    by: dict = {}
    for season_out in sorted(test):
        train = [r for r in rows if r[0] < season_out]
        if not train:
            continue
        fit = {"table": table(train)}
        fit["clubs"] = clubs(train, (fit["table"].get("Questionable|*") or {}).get("played") or 0.5)
        for season, team, d, p, played, _r in (r for r in rows if r[0] == season_out):
            if d != "Questionable":
                continue
            c = chance(fit, team, season, d, p)
            if not c or c["club"] is None:
                continue
            x = _ll(c["league"], played) - _ll(c["club"], played)
            diffs.append(x)
            by.setdefault(str(season_out), []).append(x)
    label = "+".join(str(y) for y in sorted(test))
    n = len(diffs)
    if n < 2:
        return {"n": n, "gain": None, "t": None, "holds": False, "season": label}
    m = sum(diffs) / n
    var = sum((x - m) ** 2 for x in diffs) / (n - 1)
    t = m / math.sqrt(var / n) if var > 0 else None
    per = {k: round(sum(v) / len(v), 5) for k, v in sorted(by.items())}
    return {"n": n, "gain": round(m, 5), "t": None if t is None else round(t, 2), "season": label,
            "by_season": per,
            "holds": bool(n >= MIN_LISTED and m > 0 and (t or 0) >= MIN_T and all(v > 0 for v in per.values()))}


# ---- the box: every season's reports against every season's snaps ------------

def snap_index(conn, sport: str = "nfl") -> dict:
    """``{(norm name, season, week): snap share}`` from the stored logs."""
    out = {}
    for r in conn.execute("SELECT season, period, player, value FROM player_game_logs "
                          "WHERE sport=? AND market='snap_pct' AND value IS NOT NULL", (sport,)):
        try:
            out[(_norm(r[2]), int(r[0]), int(r[1]))] = float(r[3])
        except (TypeError, ValueError):
            continue
    return out


def load_reports(seasons) -> list:
    """Every season's injury report rows (the box's own cached download)."""
    from .sources.injuries import load_injuries
    rows = []
    for s in seasons:
        try:
            rows += [{**r, "season": r.get("season") or s} for r in load_injuries(s)]
        except Exception as exc:                              # noqa: BLE001
            print(f"  ⚠️  {s} injury reports unavailable: {exc}")
    return rows


def measure(conn, seasons, sport: str = "nfl") -> dict:
    rows = listings(load_reports(seasons), snap_index(conn, sport))
    tab = table(rows)
    q = (tab.get("Questionable|*") or {}).get("played") or 0.5
    return {"sport": sport, "listings": len(rows), "seasons": sorted({r[0] for r in rows}),
            "table": tab, "clubs": clubs(rows, q), "held_out": held_out(rows)}


def save(res: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    try:
        with open(p) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    d[res["sport"]] = {k: res[k] for k in ("table", "clubs", "held_out", "seasons")}
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=1)
    return p


def load(sport: str = "nfl") -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh).get(sport) or {}
    except (OSError, ValueError):
        return {}


def report_lines(res: dict) -> list:
    out = [f"Practice reports — {res['sport'].upper()}: {res['listings']} listed player-weeks, seasons {res['seasons']}"]
    out.append("  designation × practice: played (n) · snap share vs his last four when he played")
    for k in sorted(res["table"], key=lambda k: (DESIGNATIONS.index(k.split("|")[0]), k)):
        v = res["table"][k]
        out.append(f"    {k:24s} {v['played']:.0%} ({v['n']}) · {v['ratio'] if v['ratio'] is not None else '—'}")
    cl = sorted(res["clubs"].items(), key=lambda kv: kv[1]["played"])
    if cl:
        out.append("  questionable, by club and season (shrunk): fewest played …")
        out += [f"    {k:10s} {v['played']:.0%} (raw {v['raw']:.0%}, n {v['n']})" for k, v in cl[:5]]
        out.append("  … most played")
        out += [f"    {k:10s} {v['played']:.0%} (raw {v['raw']:.0%}, n {v['n']})" for k, v in cl[-5:]]
    h = res["held_out"]
    out.append(f"  held out {h.get('season')}: club-folded vs league log loss gain {h['gain']} (t {h['t']}, n {h['n']}) — "
               f"{'HOLDS' if h['holds'] else 'does not hold'}")
    out.append(f"  THE BAR: the club-folded chance beats the league's by log loss, t ≥ {MIN_T}, ≥ {MIN_LISTED} questionable listings")
    return out


# ---- the ideas file -----------------------------------------------------------------

def _week_rows(season: int, week: int) -> list:
    from .sources.injuries import load_injuries
    return [r for r in load_injuries(season) if str(r.get("week") or "") == str(week)]


def _season_week(board) -> tuple | None:
    import re
    m = re.match(r"^(\d{4})-W(\d{1,2})$", str((board or {}).get("date") or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def ideas_section(props, games, board, sport):
    if sport != "nfl":
        return None
    sw = _season_week(board)
    if not sw:
        return None
    fit = load(sport)
    listed = {}
    for r in _week_rows(*sw):
        d = designation_of(r.get("report_status"))
        name = r.get("full_name") or r.get("player_name") or ""
        if not d or not name:
            continue
        team, p = str(r.get("team") or ""), practice_of(r.get("practice_status"))
        c = chance(fit, team, sw[0], d, p) if fit else None
        listed[_norm(name)] = {"player": name, "team": team, "designation": d, "practice": p,
                               "injury": r.get("report_primary_injury") or "", **(c or {})}
    return {"listed": listed, "measured": bool(fit), "held_out": (fit or {}).get("held_out") or {}}


def pick_view(sec, player, market, side="", line=None):
    r = (sec.get("listed") or {}).get(_norm(player))
    if not r:
        return None
    return {**r, "measured": sec.get("measured"), "held_out": sec.get("held_out") or {}}


def game_view(sec, home, away):
    rows = [r for r in (sec.get("listed") or {}).values() if r["team"] in (home, away)
            and r["designation"] != "Out"]
    if not rows:
        return None
    return {"rows": sorted(rows, key=lambda r: (r["team"], r["designation"], r["player"])),
            "measured": sec.get("measured"), "held_out": sec.get("held_out") or {}}


def main(argv=None) -> int:
    import argparse
    import datetime as _dt
    ap = argparse.ArgumentParser(description="Practice reports and club honesty, measured on every stored report")
    ap.add_argument("--seasons", type=int, nargs="*", help="seasons to read (default: the last five)")
    ap.add_argument("--save", action="store_true", help="keep the table where the pick page reads it")
    a = ap.parse_args(argv)
    year = _dt.date.today().year
    seasons = a.seasons or list(range(year - 5, year + 1))
    from . import db as _db
    conn = _db.connect()
    try:
        res = measure(conn, seasons)
    finally:
        conn.close()
    print("\n".join(report_lines(res)))
    if a.save:
        print(f"  saved → {save(res)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
