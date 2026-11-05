"""Which feed shows a score first: ESPN's scoreboard or BALLDONTLIE's (RS6).

ASLEEP UNTIL THERE IS A KEY. launch.py starts `watch_once` on its own
thread only when engine/sources/balldontlie has ``BALLDONTLIE_API_KEY``;
without one nothing here runs and nothing is written.

WHAT IT DOES, while an NBA or NFL game is on in ESPN's scoreboard: each
tick it reads that scoreboard the way the score loop does (the same
cached copy, so ESPN is asked no more often than it is now) and
BALLDONTLIE's games for the same dates, one request a league. For each
game both feeds carry, the first time each shows a new score is written
down: data/cache/feedlatency/YYYY-MM-DD.jsonl, one line a sighting, kept
KEEP_DAYS. ESPN's time is when its copy was fetched (the shared cache
file's time); BALLDONTLIE's is when its answer came.

WHAT IT MEASURES (`report`): a score both feeds showed, and which showed
it first. A feed only learns a score when it is next read, so each
sighting also carries how long since that feed was last read (``iv``);
the change happened somewhere in that gap, and the fair comparison is of
the gaps' middles, so a feed read more often is not credited with being
faster. The rule (docs/DATA_SOURCES.md): a league moves to the licensed
feed only where it is as fast or faster, the middle of the differences
at or past zero over at least MIN_PAIRS score changes.

``python3 -m engine.feedlatency`` prints the report, read-only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "cache" / "feedlatency"
#: ESPN's leagues BALLDONTLIE also covers. MLB's live scores come from
#: MLB's own feed, not ESPN's, and its season is over; it waits.
LEAGUES = ("nba", "nfl")
#: The tick while a game is on: about the score loop's own pass, so both
#: feeds are read about as often. A plan with few requests a minute sets
#: QB_FEEDLATENCY_EVERY_S higher; the middles keep the comparison fair.
FAST_S = 8
IDLE_S = 180
KEEP_DAYS = 60
MIN_PAIRS = 200
#: After a 429, BALLDONTLIE is left alone this long.
BACKOFF_S = 60

_LAST: dict = {}        # (feed, game) -> (score, t)
_SEEN_AT: dict = {}     # (feed, sport) -> the last time that feed was read
_PAUSE = [0.0]
_OFF = [False]          # a refused key: asleep for the life of the process
_PRUNED = [""]
_SEEDED: set = set()


def every_s() -> float:
    try:
        return max(5.0, float(os.environ.get("QB_FEEDLATENCY_EVERY_S") or FAST_S))
    except ValueError:
        return float(FAST_S)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


#: Codes that differ between ESPN's board vocabulary and BALLDONTLIE's.
ALIASES = {"nfl": {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"},
           "nba": {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA",
                   "WSH": "WAS", "PHO": "PHX", "BRK": "BKN", "CHO": "CHA"}}


def _code(sport: str, code: str) -> str:
    c = str(code or "").upper()
    return ALIASES.get(sport, {}).get(c, c)


def _et_date(iso: str) -> str:
    try:
        t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:                                          # noqa: BLE001
        return ""


def match(sport: str, espn_row: dict, bdl_games: list):
    """The BALLDONTLIE game that is this ESPN game: the same two sides, by
    code or by full name."""
    eh, ea = _code(sport, espn_row.get("home")), _code(sport, espn_row.get("away"))
    nh, na = _norm(espn_row.get("home_name")), _norm(espn_row.get("away_name"))
    for g in bdl_games:
        if (_code(sport, g.get("home")) == eh and _code(sport, g.get("away")) == ea) or \
                (nh and na and _norm(g.get("home_name")) == nh and _norm(g.get("away_name")) == na):
            return g
    return None


def _path(day: str, root: Path | None = None) -> Path:
    return Path(root or DIR) / f"{day}.jsonl"


def _seed(day: str, root: Path | None = None) -> None:
    """The last score each feed showed for each game today, so a restart
    does not write the same sighting again."""
    if day in _SEEDED:
        return
    _SEEDED.add(day)
    for rec in read_day(day, root):
        _LAST[(rec["feed"], rec["game"])] = (tuple(rec["score"]), rec["t"])


def read_day(day: str, root: Path | None = None) -> list:
    out = []
    try:
        with open(_path(day, root), encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _sight(feed: str, sport: str, game: str, score: tuple, t: float, iv,
           period, clock, root: Path | None = None) -> bool:
    """Write a sighting when this feed's score for this game is new."""
    if score[0] is None or score[1] is None or (score[0] + score[1]) == 0:
        return False                           # before the first score: nothing to time
    last = _LAST.get((feed, game))
    if last and last[0] == score:
        return False
    _LAST[(feed, game)] = (score, t)
    day = game.split(":", 1)[0]
    p = _path(day, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": round(t, 2), "iv": None if iv is None else round(iv, 2), "feed": feed,
           "sport": sport, "game": game, "score": list(score), "per": period, "clk": clock}
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
    return True


def _espn_rows(sport: str):
    """ESPN's rows and when they were fetched (the shared cache's time)."""
    from .sources import fetch as F
    from .sources.livescores import fetch_rows
    rows = fetch_rows(sport, ttl=int(every_s()))
    try:
        t = F._cache_path(f"espn_{sport}_scoreboard.json").stat().st_mtime
    except OSError:
        t = time.time()
    return rows, t


def _bdl_games(sport: str, dates: list):
    from .sources import balldontlie as B
    g = B.games(sport, dates)
    return g, time.time()


def prune(today: str, root: Path | None = None) -> int:
    """Drop the days past KEEP_DAYS, once a day."""
    if _PRUNED[0] == today:
        return 0
    _PRUNED[0] = today
    cut = (_dt.date.fromisoformat(today) - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    n = 0
    for f in Path(root or DIR).glob("*.jsonl"):
        if f.stem < cut:
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def watch_once(espn=None, bdl=None, now=None, root: Path | None = None, log=print) -> float:
    """One tick. Returns the wait before the next: `every_s()` while either
    league has a live game in ESPN's scoreboard, IDLE_S otherwise.
    ``espn(sport) -> (rows, fetched_at)`` and ``bdl(sport, dates) ->
    (games, answered_at)`` are for tests."""
    from .sources import balldontlie as B
    espn = espn or _espn_rows
    bdl = bdl or _bdl_games
    clock = now or time.time
    if _OFF[0]:
        return IDLE_S
    live_any = False
    for sport in LEAGUES:
        try:
            rows, te = espn(sport)
        except Exception:                                      # noqa: BLE001
            continue
        live = [r for r in rows if getattr(r.get("live"), "state", "") == "live"]
        if not live:
            # Nothing on: the next game's first reading has no gap to
            # split, rather than one hours long.
            _SEEN_AT.pop(("espn", sport), None)
            _SEEN_AT.pop(("bdl", sport), None)
            continue
        live_any = True
        if clock() < _PAUSE[0]:
            continue
        dates = sorted({d for d in (_et_date(getattr(r["live"], "start_time", "")) for r in live) if d})
        if not dates:
            continue
        try:
            games, tb = bdl(sport, dates)
        except B.BDLRateLimited:
            _PAUSE[0] = clock() + BACKOFF_S
            continue
        except B.BDLUnavailable as exc:
            if "refused the key" in str(exc):
                _OFF[0] = True
                log(f"  feed latency: {exc} Asleep until the next restart.")
                return IDLE_S
            continue
        prev_e, prev_b = _SEEN_AT.get(("espn", sport)), _SEEN_AT.get(("bdl", sport))
        iv_e = None if prev_e is None or te <= prev_e else te - prev_e
        iv_b = None if prev_b is None else tb - prev_b
        stale = 6 * every_s()          # a gap this long is a pause, not a reading's rhythm
        fresh_e = prev_e is None or te > prev_e
        iv_e = None if iv_e is not None and iv_e > stale else iv_e
        iv_b = None if iv_b is not None and iv_b > stale else iv_b
        _SEEN_AT[("bdl", sport)] = tb
        if fresh_e:
            _SEEN_AT[("espn", sport)] = te
        for r in live:
            lv = r["live"]
            day = _et_date(getattr(lv, "start_time", ""))
            if not day:
                continue
            _seed(day, root)
            prune(day, root)
            game = f"{day}:{r.get('away')}@{r.get('home')}"
            if fresh_e:                    # a copy already read cannot show anything new
                _sight("espn", sport, game, (lv.away_score, lv.home_score), te, iv_e,
                       getattr(lv, "period", ""), getattr(lv, "clock", ""), root)
            g = match(sport, r, games)
            if g is not None:
                _sight("bdl", sport, game, (g.get("away_score"), g.get("home_score")), tb, iv_b,
                       g.get("period"), g.get("clock"), root)
    return every_s() if live_any else IDLE_S


def _mid(rec: dict) -> float:
    return rec["t"] - (rec["iv"] or 0.0) / 2.0


def pairs(records: list) -> dict:
    """``{sport: {"pairs": [(raw, mid)], "only_espn", "only_bdl", "games"}}``:
    each score both feeds showed, ESPN's time less BALLDONTLIE's (positive
    when BALLDONTLIE showed it first), from each feed's first sighting."""
    first: dict = {}
    for rec in records:
        k = (rec["sport"], rec["game"], tuple(rec["score"]), rec["feed"])
        if k not in first or rec["t"] < first[k]["t"]:
            first[k] = rec
    out: dict = {}
    seen = {(s, g, sc) for s, g, sc, _f in first}
    for s, g, sc in seen:
        d = out.setdefault(s, {"pairs": [], "only_espn": 0, "only_bdl": 0, "games": set()})
        d["games"].add(g)
        e, b = first.get((s, g, sc, "espn")), first.get((s, g, sc, "bdl"))
        if e and b:
            d["pairs"].append((e["t"] - b["t"], _mid(e) - _mid(b)))
        elif e:
            d["only_espn"] += 1
        else:
            d["only_bdl"] += 1
    return out


def report(days: int = 14, today: str | None = None, root: Path | None = None) -> dict:
    """Per league: how many score changes both feeds showed, who showed
    them first and by how much (the middles), and the verdict."""
    t = _dt.date.fromisoformat(today) if today else _dt.date.today()
    recs = []
    for i in range(days):
        recs += read_day((t - _dt.timedelta(days=i)).isoformat(), root)
    out = {}
    for sport, d in sorted(pairs(recs).items()):
        mids = [m for _r, m in d["pairs"]]
        raws = [r for r, _m in d["pairs"]]
        n = len(mids)
        row = {"n": n, "games": len(d["games"]), "only_espn": d["only_espn"], "only_bdl": d["only_bdl"],
               "bdl_first": sum(1 for m in mids if m > 0.5), "espn_first": sum(1 for m in mids if m < -0.5),
               "median_s": round(statistics.median(mids), 1) if mids else None,
               "median_raw_s": round(statistics.median(raws), 1) if raws else None}
        if n < MIN_PAIRS:
            row["verdict"] = f"collecting ({n} of {MIN_PAIRS} score changes)"
        elif row["median_s"] >= 0:
            row["verdict"] = (f"BALLDONTLIE as fast or faster (by {row['median_s']:.1f} s at the middle) "
                              f"— a switch candidate")
        else:
            row["verdict"] = f"ESPN faster by {-row['median_s']:.1f} s at the middle — keep ESPN"
        out[sport] = row
    return out


def report_lines(rep: dict, enabled: bool) -> list:
    if not rep:
        return ["  feed latency: nothing recorded yet"
                + ("" if enabled else " (no BALLDONTLIE key on this box, so the watcher is asleep)")]
    lines = []
    for sport, r in rep.items():
        lines.append(f"  {sport}: {r['n']} score change(s) both feeds showed, over {r['games']} game(s); "
                     f"BALLDONTLIE first {r['bdl_first']}, ESPN first {r['espn_first']}; "
                     f"only ESPN {r['only_espn']}, only BALLDONTLIE {r['only_bdl']}")
        if r["median_s"] is not None:
            lines.append(f"  {'':{len(sport)}}  middle difference {r['median_s']:+.1f} s "
                         f"(raw {r['median_raw_s']:+.1f} s; + means BALLDONTLIE sooner)")
        lines.append(f"  {'':{len(sport)}}  → {r['verdict']}")
    return lines


def main(argv=None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    days = 14
    if "--days" in argv:
        try:
            days = int(argv[argv.index("--days") + 1])
        except (IndexError, ValueError):
            pass
    from .sources import balldontlie as B
    for line in report_lines(report(days), B.enabled()):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
