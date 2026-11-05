"""MLB travel and rest, measured before anything is built (docs/MLB_MODEL.md §7).

Ethan, 2026-11-05: "Go through nfl and CFB and nba and mlb ... make sure we
have all the tools and data we can be using." The MLB spec's Travel /
Fatigue Engine (day games after night games, cross-country trips, time
zones, getaway days, long stretches without an off day, doubleheaders) was
written in the spec and never in the code. The house rule is that a piece
of data is shown first, measured second, and only then allowed to move a
number. This is the measurement.

READ-ONLY. It reads MLB's own schedule (statsapi.mlb.com, the source the
nightly already reads: one request per season, nothing cached, nothing
written) and, for the market part, the closing totals the box already
stored (the history file opened read-only). It changes nothing.

THE BASELINE. Each season's runs are fitted as one multiplicative model:
runs = league level × his club's offence × the opponent's defence × the
park × home field (iterative proportional fitting over every final regular
season game). A situation is then judged on what is left: the runs a club
scored against what that model expected (`runs scored`), the runs it
allowed against the opponent's expectation (`runs allowed`), and its wins
against the expected chance from both (Pythagenpat). The standard errors
read the runs' own overdispersion.

THE SITUATIONS, each from the club's own schedule:

  * a day game the day after a night game;
  * two or more time zones east since the last game, with no day off (and
    west, the same);
  * 1,500 miles or more since the last park, with no day off;
  * the 13th day or more in a row with a game;
  * the first game after a day off (the rested side, for contrast);
  * a getaway day: the next game is tomorrow in another park, and the same
    as a day game;
  * the second game of a doubleheader;
  * the first home game after a road trip of six games or more.

THE BAR is the NFL's (the one college's lineup step waits on): two
standard errors on the seasons pooled, and the same side in at least three
of the seasons. A situation that clears it is worth building; one that
does not is left alone, said so, and the reason kept.

THE MARKET PART. Where the box stored a closing total (the `games` table's
MLB rows), the games carrying a situation are compared with the close: if
the runs move and the close moved with them, the market already prices it.

THE FIRST READ (2026-11-05, off the box): five seasons of Retrosheet game
logs (2018, 2019, 2021-2023; Chadwick Bureau's copy on GitHub) through this
same check, 12,031 games. Nothing cleared the bar. The closest: 1,500+ miles
without a day off scored 5.8% fewer runs (z -1.7, all five seasons), and the
first home game after a long road trip allowed 3.0% more (z +1.6, all five).
The second game of a doubleheader cleared it only while 2021's seven-inning
doubleheaders were in (0.80 that season); a game scheduled short of nine
innings is skipped now. A day game after a night game: -1.0%, z -1.1.

Run on the box: ``python3 mlbtravelcheck.py`` (default: 2018 to the latest
season, 2020's sixty games left out). ``--files a.json b.json`` reads saved
schedule payloads instead.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sqlite3
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SCHEDULE = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&season={season}&gameType=R"

#: Hours from UTC in summer (the season is nearly all daylight time). Arizona
#: keeps standard time, so in summer it sits with the Pacific parks.
PARK_TZ = {
    "yankee": -4, "fenway": -4, "citi": -4, "cbp": -4, "nationals": -4, "camden": -4,
    "pnc": -4, "progressive": -4, "comerica": -4, "gabp": -4, "truist": -4,
    "loandepot": -4, "tropicana": -4, "rogers": -4, "steinbrenner": -4,
    "wrigley": -5, "rate": -5, "amfam": -5, "busch": -5, "kauffman": -5, "target": -5,
    "daikin": -5, "globelife": -5,
    "coors": -6,
    "chase": -7, "oracle": -7, "petco": -7, "dodger": -7, "angel": -7, "tmobile": -7,
    "sutter": -7, "coliseum": -7,
}
#: Parks the weather table does not carry, from the seasons measured here.
EXTRA_VENUES = {"steinbrenner": "steinbrenner", "oakland": "coliseum", "coliseum": "coliseum",
                "ring central": "coliseum"}
EXTRA_COORDS = {"steinbrenner": (27.980, -82.507), "coliseum": (37.751, -122.200)}

SITUATIONS = (
    ("day_after_night", "a day game after a night game"),
    ("east2", "2+ time zones east, no day off"),
    ("west2", "2+ time zones west, no day off"),
    ("long_trip", "1,500+ miles since the last park, no day off"),
    ("streak13", "the 13th+ day in a row with a game"),
    ("after_off", "the first game after a day off"),
    ("getaway", "a getaway day (tomorrow in another park)"),
    ("getaway_day", "a getaway day game"),
    ("dh2", "the second game of a doubleheader"),
    ("home_after_trip", "the first home game after a 6+ game road trip"),
)
Z_BAR = 2.0
SEASONS_BAR = 3


# --- the schedule ----------------------------------------------------------------
def _park(venue: str):
    from engine.mlb.sources.mlbstats import VENUE_PARK
    v = (venue or "").lower()
    for frag, key in list(VENUE_PARK.items()) + list(EXTRA_VENUES.items()):
        if frag in v:
            return key
    return None


def _coords(park):
    from engine.mlb.sources.mlbstats import PARK_COORDS
    return PARK_COORDS.get(park) or EXTRA_COORDS.get(park)


def miles(a, b) -> float | None:
    if not a or not b:
        return None
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def games_from(payload: dict) -> list[dict]:
    """Every final regular-season game in a schedule payload."""
    from engine.mlb.sources.mlbstats import TEAM_ID_ABBR
    out = []
    for day in (payload or {}).get("dates") or []:
        for g in day.get("games") or []:
            st = g.get("status") or {}
            if st.get("abstractGameState") != "Final" or (st.get("codedGameState") or "") in ("D", "C"):
                continue
            # A game scheduled short of nine innings (2020-21's seven-inning
            # doubleheaders) is not the same game: it would read as fewer runs
            # in whatever situation it falls in (the second game of a
            # doubleheader read 0.80 in 2021 for that reason alone).
            if int(g.get("scheduledInnings") or 9) != 9:
                continue
            t = g.get("teams") or {}
            h, a = t.get("home") or {}, t.get("away") or {}
            hid, aid = (h.get("team") or {}).get("id"), (a.get("team") or {}).get("id")
            if hid is None or aid is None or h.get("score") is None or a.get("score") is None:
                continue
            venue = str((g.get("venue") or {}).get("name") or "")
            out.append({"pk": int(g.get("gamePk") or 0), "date": str(g.get("officialDate") or day.get("date"))[:10],
                        "start": str(g.get("gameDate") or ""), "day": (g.get("dayNight") or "night") == "day",
                        "dh2": int(g.get("gameNumber") or 1) == 2,
                        "home": TEAM_ID_ABBR.get(hid, str(hid)), "away": TEAM_ID_ABBR.get(aid, str(aid)),
                        "hr": int(h["score"]), "ar": int(a["score"]), "park": _park(venue), "venue": venue})
    out.sort(key=lambda g: (g["start"], g["pk"]))
    return out


def team_rows(games: list[dict]) -> list[dict]:
    """One row per club per game, with its situations from its own schedule."""
    by_team: dict = defaultdict(list)
    for g in games:
        by_team[g["home"]].append((g, True))
        by_team[g["away"]].append((g, False))
    rows = []
    for team, seq in by_team.items():
        seq.sort(key=lambda x: (x[0]["start"], x[0]["pk"]))
        streak, road = 0, 0
        for i, (g, home) in enumerate(seq):
            prev = seq[i - 1][0] if i else None
            nxt = seq[i + 1][0] if i + 1 < len(seq) else None
            d = _dt.date.fromisoformat(g["date"])
            rest = (d - _dt.date.fromisoformat(prev["date"])).days - 1 if prev else None
            if prev is None or rest is None or rest >= 1:
                streak = 1
            elif rest == 0:
                streak += 1
            # the same day (a doubleheader) leaves the streak where it was
            tz_now, tz_prev = PARK_TZ.get(g["park"]), PARK_TZ.get(prev["park"]) if prev else None
            shift = (tz_now - tz_prev) if tz_now is not None and tz_prev is not None else None
            dist = miles(_coords(g["park"]), _coords(prev["park"])) if prev else None
            nd = (_dt.date.fromisoformat(nxt["date"]) - d).days if nxt else None
            away_streak = road
            road = 0 if home else road + 1
            flags = {
                "day_after_night": bool(prev and rest == 0 and g["day"] and not prev["day"]),
                "east2": bool(prev and rest == 0 and shift is not None and shift >= 2),
                "west2": bool(prev and rest == 0 and shift is not None and shift <= -2),
                "long_trip": bool(prev and rest == 0 and dist is not None and dist >= 1500),
                "streak13": streak >= 13,
                "after_off": bool(prev and rest is not None and rest >= 1),
                "getaway": bool(nxt and nd == 1 and nxt["park"] != g["park"]),
                "dh2": g["dh2"],
                "home_after_trip": bool(home and prev and away_streak >= 6),
            }
            flags["getaway_day"] = flags["getaway"] and g["day"]
            rows.append({"team": team, "opp": g["away"] if home else g["home"], "home": home,
                         "park": g["park"] or g["venue"], "date": g["date"], "pk": g["pk"],
                         "runs": g["hr"] if home else g["ar"], "allowed": g["ar"] if home else g["hr"],
                         "won": (g["hr"] > g["ar"]) == home, "flags": flags})
    return rows


# --- the baseline -------------------------------------------------------------
def fit(rows: list[dict], rounds: int = 25) -> None:
    """Writes each row's expected runs ``e`` and allowed ``e_opp`` from one
    season's multiplicative model (offence, defence, park, home)."""
    off: dict = defaultdict(lambda: 1.0)
    dfn: dict = defaultdict(lambda: 1.0)
    park: dict = defaultdict(lambda: 1.0)
    h = 1.0
    mu = sum(r["runs"] for r in rows) / max(1, len(rows))

    def base(r):
        return mu * off[r["team"]] * dfn[r["opp"]] * park[r["park"]] * (h if r["home"] else 1.0)

    for _ in range(rounds):
        for table, pick in ((off, lambda r: r["team"]), (dfn, lambda r: r["opp"]),
                            (park, lambda r: r["park"])):
            num, den = defaultdict(float), defaultdict(float)
            for r in rows:
                k = pick(r)
                num[k] += r["runs"]
                den[k] += base(r) / table[k]
            for k in num:
                table[k] = num[k] / den[k] if den[k] > 0 else 1.0
        hn = sum(r["runs"] for r in rows if r["home"])
        hd = sum(base(r) / h for r in rows if r["home"])
        h = hn / hd if hd > 0 else 1.0
        mu *= sum(r["runs"] for r in rows) / max(1e-9, sum(base(r) for r in rows))
    for r in rows:
        r["e"] = base(r)
    by_game = defaultdict(list)
    for r in rows:
        by_game[(r["pk"], r["date"])].append(r)
    for pair in by_game.values():
        if len(pair) == 2:
            a, b = pair
            a["e_opp"], b["e_opp"] = b["e"], a["e"]
    for r in rows:
        eo = r.get("e_opp")
        if eo:
            x = (r["e"] + eo) ** 0.287
            r["p"] = r["e"] ** x / (r["e"] ** x + eo ** x)


def measure(rows: list[dict], flag: str, phi: float) -> dict:
    """``{n, scored, allowed, wins}``: each ``(ratio or per-100, se)``."""
    got = [r for r in rows if r["flags"].get(flag) and "e_opp" in r]
    n = len(got)
    if not n:
        return {"n": 0}
    se_ = sum(r["e"] for r in got)
    sa_ = sum(r["e_opp"] for r in got)
    out = {"n": n,
           "scored": (sum(r["runs"] for r in got) / se_, math.sqrt(phi * se_) / se_),
           "allowed": (sum(r["allowed"] for r in got) / sa_, math.sqrt(phi * sa_) / sa_)}
    exp_w = sum(r["p"] for r in got)
    var_w = sum(r["p"] * (1 - r["p"]) for r in got)
    out["wins"] = (100.0 * (sum(1 for r in got if r["won"]) - exp_w) / n, 100.0 * math.sqrt(var_w) / n)
    return out


def overdispersion(rows: list[dict]) -> float:
    e = sum(r["e"] for r in rows)
    return sum((r["runs"] - r["e"]) ** 2 for r in rows) / e if e else 1.0


def verdict(pooled: dict, by_season: list[dict]) -> tuple[bool, str]:
    """The bar on runs scored and runs allowed: (holds, why)."""
    best = None
    for part in ("scored", "allowed"):
        if part not in pooled:
            continue
        v, se = pooled[part]
        z = (v - 1.0) / se if se else 0.0
        side = [s[part][0] - 1.0 for s in by_season if s.get("n") and part in s]
        same = sum(1 for d in side if (d > 0) == (v > 1.0) and d != 0)
        ok = abs(z) >= Z_BAR and same >= SEASONS_BAR
        cand = (ok, abs(z), part, v, z, same, len(side))
        if best is None or cand[:2] > best[:2]:
            best = cand
    if best is None:
        return False, "nothing to measure"
    ok, _az, part, v, z, same, k = best
    word = "runs scored" if part == "scored" else "runs allowed"
    return ok, f"{word} {v - 1.0:+.1%} (z {z:+.1f}), the same side in {same} of {k} seasons"


# --- the market part -----------------------------------------------------------
def closes(db_path: str) -> dict:
    """``{(date, home): closing total}`` off the box's games table, read-only."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        got = {}
        for date, period, home, total in conn.execute(
                "SELECT date, period, home, total FROM games WHERE sport='mlb' AND total IS NOT NULL"):
            got[(str(date or period)[:10], str(home or "").upper())] = float(total)
        return got
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


# --- the run --------------------------------------------------------------------
def fetch(season: int) -> dict:
    from engine.sources.fetch import USER_AGENT
    req = urllib.request.Request(SCHEDULE.format(season=season), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run(payloads: dict, db_path: str | None = None, say=print) -> dict:
    """``payloads``: {season: schedule payload}. Prints the read; returns
    {situation: (holds, why)}."""
    seasons, all_rows, games_n = [], [], 0
    by_season_rows = {}
    for season in sorted(payloads):
        games = games_from(payloads[season])
        if not games:
            continue
        rows = team_rows(games)
        fit(rows)
        for r in rows:
            r["season"] = season
        by_season_rows[season] = rows
        all_rows += rows
        games_n += len(games)
        seasons.append(season)
    if not all_rows:
        say("No final MLB games read: nothing to measure.")
        return {}
    phi = overdispersion(all_rows)
    say(f"MLB travel and rest, {seasons[0]}-{seasons[-1]}: {games_n:,} games, {len(all_rows):,} club-games "
        f"(runs model per season: each club's offence and defence, each park, home field; "
        f"runs overdispersion {phi:.2f})")
    unknown = sum(1 for r in all_rows if r["park"] not in PARK_TZ)
    if unknown:
        say(f"  {unknown} club-games at a park with no time zone here (neutral sites): no trip read for them")
    say("")
    out = {}
    for flag, label in SITUATIONS:
        pooled = measure(all_rows, flag, phi)
        if not pooled.get("n"):
            say(f"  {label:48s} none")
            out[flag] = (False, "none")
            continue
        per = [measure(by_season_rows[s], flag, overdispersion(by_season_rows[s])) for s in seasons]
        sc, al, wi = pooled["scored"], pooled["allowed"], pooled["wins"]
        say(f"  {label:48s} n={pooled['n']:>6,}  runs scored {sc[0]:.3f} ±{sc[1]:.3f}  "
            f"runs allowed {al[0]:.3f} ±{al[1]:.3f}  wins {wi[0]:+.1f} per 100 ±{wi[1]:.1f}")
        say(f"  {'':48s} scored by season: " + " ".join(f"{p['scored'][0]:.3f}" if p.get('n') else "—" for p in per)
            + "   allowed: " + " ".join(f"{p['allowed'][0]:.3f}" if p.get('n') else "—" for p in per))
        out[flag] = verdict(pooled, per)
    if db_path:
        got = closes(db_path)
        joined = [r for r in all_rows if r["home"] and (r["date"], r["team"].upper()) in got]
        say("")
        if not joined:
            say("The market: no stored MLB closing total joined these games.")
        else:
            for r in joined:
                r["close"] = got[(r["date"], r["team"].upper())]
            pair_flags = defaultdict(list)
            opp = {(r["pk"], r["date"]): r for r in all_rows if not r["home"]}
            base = [r["runs"] + r["allowed"] - r["close"] for r in joined]
            say(f"The market: {len(joined):,} games with a stored closing total; all of them landed "
                f"{sum(base) / len(base):+.2f} runs from the close on average")
            for r in joined:
                o = opp.get((r["pk"], r["date"]))
                for flag, _label in SITUATIONS:
                    if r["flags"].get(flag) or (o and o["flags"].get(flag)):
                        pair_flags[flag].append(r["runs"] + r["allowed"] - r["close"])
            for flag, label in SITUATIONS:
                xs = pair_flags.get(flag) or []
                if len(xs) >= 30:
                    m = sum(xs) / len(xs)
                    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
                    say(f"  games with {label}: {len(xs):,}, {m:+.2f} runs from the close ±{sd / math.sqrt(len(xs)):.2f}")
    say("")
    say(f"Verdicts (the NFL's bar: {Z_BAR:.0f} standard errors pooled, the same side in {SEASONS_BAR}+ seasons):")
    for flag, label in SITUATIONS:
        ok, why = out.get(flag, (False, "none"))
        say(f"  {label}: {'holds — worth building' if ok else 'too small to use'} ({why})")
    return out


def default_seasons(last: int) -> list[int]:
    """2018 to ``last``, 2020 left out: sixty games, no crowds, a schedule
    built to avoid travel, so it measures none of this."""
    return [s for s in range(2018, last + 1) if s != 2020]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seasons", type=int, nargs="*", default=None,
                    help="regular seasons to read (default: 2018 to the latest finished one, "
                         "2020 left out)")
    ap.add_argument("--files", nargs="*", default=None, help="saved schedule payloads, one per season")
    ap.add_argument("--db", default=str(ROOT / "data" / "history.db"),
                    help="the history file, opened read-only, for the closing totals")
    args = ap.parse_args(argv)
    payloads = {}
    if args.files:
        for i, f in enumerate(args.files):
            payload = json.loads(Path(f).read_text(encoding="utf-8"))
            first = ((payload.get("dates") or [{}])[0].get("date") or "")[:4]
            payloads[int(first) if first.isdigit() else i] = payload
    else:
        today = _dt.date.today()
        last = today.year if today.month >= 10 else today.year - 1
        for season in (args.seasons or default_seasons(last)):
            try:
                payloads[season] = fetch(season)
            except Exception as exc:                                  # noqa: BLE001
                print(f"  {season}: the schedule did not answer ({type(exc).__name__}: {exc}); left out")
    db = args.db if args.db and Path(args.db).exists() else None
    return 0 if run(payloads, db) else 1


if __name__ == "__main__":
    sys.exit(main())
