"""The Most Likely board learns from its own record, every sport, by itself.

Ethan, 2026-10-03, after pasting the NFL audit by hand: "we shouldn't have
to constantly run tests for every sport like this to make it better and see
where it's winning and losing, our models and the site should automatically
be able to do this by itself with its own data."

Until now the board's two record-driven corrections were commands someone
had to type on the box:

  * engine/likelycal: pull each pick toward its price by as much as picks
    from the same maker (the list, the matchup picks, the scenarios, the
    bold picks) on the same side have earned;
  * engine/likelyctx (NFL): the same for the scout's football flags,
    stacked on likelycal.

Both were built to be safe to automate: they fit on the RAW claim the
journal keeps (so a refit never learns its own correction), they score
themselves on games they never saw, and they are saved only if the
held-out log loss improves at the bottom of its 95% interval. This module
runs them on every settle pass that graded a new Most Likely pick, for
every league with a board. It adds no new bar.

THE LATEST FIT DECIDES. A fit that passes replaces the league's entry; a
fit that no longer passes REMOVES it, and the board goes back to its own
numbers until the record proves a correction again. The store always holds
what the record supports today, not what it once supported.

WHERE IT WINS AND LOSES. Each run also writes the league's record, sliced
the ways a reader would ask about it: by maker and side, by market and
side, and by the chance we claimed. Each slice is graded against its own
claim (z = wins minus claimed wins, over its spread), so a slice of long
shots that hit 35% where we said 33% reads as holding up, not as losing.
The NFL also gets the scout's flags. The Record page shows all of it under
"What it learned", so nobody has to paste anything to see it.

Standard library only. Never raises into the settle pass.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from collections import defaultdict
from pathlib import Path

from . import modelstate

#: Every league with a Most Likely board.
SPORTS = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl")
#: The fewest picks a slice needs before it is graded on the page.
MIN_SLICE = 15
#: |z| at which a slice is called over-claiming or beating its claim. The
#: same bar nflaudit and losspatterns' raw test read.
Z_BAR = 2.0


def _path() -> Path:
    return Path(modelstate.path("board_learning.json"))


def report(path=None) -> dict:
    """The last run's findings, for the export. {} before the first run."""
    try:
        return json.loads(Path(path or _path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(rep: dict, path=None) -> None:
    p = Path(path or _path())
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)


# --- where it wins and loses ------------------------------------------------
def grade(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    w = sum(1 for r in rows if r["won"])
    claim = sum(r["p"] for r in rows)
    var = sum(r["p"] * (1 - r["p"]) for r in rows)
    z = (w - claim) / math.sqrt(var) if var > 0 else 0.0
    verdict = ("over-claims" if z <= -Z_BAR else "beats its claim" if z >= Z_BAR else "holds up")
    return {"n": n, "won": w, "hit": round(w / n, 4), "said": round(claim / n, 4), "z": round(z, 2),
            "verdict": verdict}


def _band(p: float) -> str:
    for edge, label in ((0.4, "under 40%"), (0.55, "40-54%"), (0.65, "55-64%"), (0.75, "65-74%")):
        if p < edge:
            return label
    return "75% and up"


MAKER_WORDS = {"list": "Most Likely list", "bold": "bolder than the books", "matchup": "matchup picks",
               "scenario": "touchdown scenarios"}


def slices(rows: list[dict]) -> dict:
    """{cut: [slice, ...]} — each slice graded against its own claim,
    worst first, only slices of MIN_SLICE or more."""
    from .likelyctx import maker
    cuts = {
        "maker": lambda r: f"{MAKER_WORDS[maker(r['sources'])]} · {_side(r)}",
        "market": lambda r: f"{r['market']} · {_side(r)}",
        "claimed": lambda r: _band(r["p"]),
    }
    out = {}
    for name, key in cuts.items():
        grp = defaultdict(list)
        for r in rows:
            grp[key(r)].append(r)
        graded = [{"key": k, **grade(v)} for k, v in grp.items() if len(v) >= MIN_SLICE]
        out[name] = sorted(graded, key=lambda s: s["z"])
    return out


def _side(r) -> str:
    s = str(r.get("side") or "").lower()
    return "under" if s in ("under", "no") else "over"


# --- the refit ----------------------------------------------------------------
def _drop(module, sport: str) -> bool:
    """Remove a league's entry from a correction store; True if it had one."""
    store = module.load()
    if sport not in store:
        return False
    del store[sport]
    p = module._store()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=1), encoding="utf-8")
    tmp.replace(p)
    return True


def _verdict(res: dict) -> dict:
    ho = res.get("held_out") or {}
    return {"passed": bool(res.get("passed")), "n": res.get("n", 0),
            "held_out": {k: ho.get(k) for k in ("n", "games", "raw", "corrected", "gain", "lo", "hi")}}


def held_record(lconn, sport: str) -> dict:
    """The picks the board HELD BACK (likelyboard.held_reason), graded at
    the chance they carried. If they hit about as often as we claimed,
    holding them cost us picks that were fine, and the page says so."""
    rows = [{"won": r["status"] == "won", "p": float(r["p"])} for r in lconn.execute(
        "SELECT status, COALESCE(raw_prob, hit_prob) p FROM bets WHERE LOWER(sport)=? AND category='held' "
        "AND status IN ('won','lost') AND COALESCE(raw_prob, hit_prob) IS NOT NULL", (sport,))]
    return grade(rows)


def learn_sport(lconn, hconn, sport: str, log=print) -> dict:
    """Refit one league's corrections and grade its record. Returns the
    report entry."""
    from . import likelycal, likelyctx
    rows = likelyctx.journal(lconn, sport)
    entry = {"sport": sport, "settled": len(rows), "record": grade(rows), "slices": slices(rows),
             "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}
    entry["held"] = held_record(lconn, sport)
    cal = likelycal.fit(lconn, sport)
    if cal["passed"]:
        likelycal.save(cal)
        log(f"  board learning ({sport}): record correction adopted — "
            f"{sum(1 for g in cal['groups'].values() if g['k'] < 1)} group(s) pulled toward the price")
    elif _drop(likelycal, sport):
        log(f"  board learning ({sport}): the record no longer proves its correction — removed")
    entry["calibration"] = {**_verdict(cal), "groups": cal.get("groups") or {}}
    if sport in likelyctx.SPORTS and hconn is not None:
        flagged = likelyctx.flagged_journal(lconn, hconn, sport)
        ctx = likelyctx.fit(lconn, hconn, sport, flagged=flagged)
        if ctx["passed"]:
            likelyctx.save(ctx)
            log(f"  board learning ({sport}): scout correction adopted on "
                f"{sum(1 for f in ctx['flags'].values() if f['k'] < 1)} flag(s)")
        elif _drop(likelyctx, sport):
            log(f"  board learning ({sport}): the scout's correction no longer holds — removed")
        found = [r for r in flagged if r.get("ctx")]
        # BY POSITION, which only the football join knows (the journal
        # keeps no position). The 2026-10-03 audit found tight ends
        # over-claiming on BOTH sides — a spread too narrow, not a lean —
        # and that is the kind of thing this has to keep watching.
        pos = defaultdict(list)
        for r in found:
            if r["ctx"].get("position"):
                pos[f"{r['ctx']['position']} · {_side(r)}"].append(r)
        # TOUCHDOWN PICKS BY THEIR TEAM'S EXPECTED POINTS — the cut that
        # sent engine/tdscale looking (1-for-12 at 18-22 points, 13-for-21
        # at 26+), kept on the page so it keeps answering.
        tdb = defaultdict(list)
        for r in found:
            imp = r["ctx"].get("implied")
            if r.get("market") == "anytime_td" and imp is not None:
                tdb["under 21 points" if imp < 21 else "21-25.9 points" if imp < 26 else "26+ points"].append(r)
        entry["slices"]["td_team_total"] = sorted(({"key": k, **grade(v)} for k, v in tdb.items()
                                                   if len(v) >= MIN_SLICE), key=lambda s: s["z"])
        entry["slices"]["position"] = sorted(({"key": k, **grade(v)} for k, v in pos.items() if len(v) >= MIN_SLICE),
                                             key=lambda s: s["z"])
        by_flag = defaultdict(list)
        for r in found:
            for f in r["flags"]:
                by_flag[f].append(r)
        from . import scout
        entry["scout"] = {**_verdict(ctx), "matched": len(found), "too_common": ctx.get("too_common") or [],
                          "flags": sorted(({"key": f, "note": scout.note(f, sport), **grade(v)}
                                           for f, v in by_flag.items() if len(v) >= MIN_SLICE),
                                          key=lambda s: s["z"]),
                          "fitted": ctx.get("flags") or {}}
    return entry


def refresh(lconn, hconn=None, log=print, sports=SPORTS, force: bool = False, path=None) -> dict:
    """Run every league whose graded Most Likely picks changed since its
    last run (or all of them, ``force``). Returns {sport: entry} for the
    leagues it ran. One league's failure is that league's."""
    from . import likelyctx
    rep = report(path)
    ran = {}
    for sport in sports:
        try:
            n = len(likelyctx.journal(lconn, sport))
            if not n or (not force and (rep.get(sport) or {}).get("settled") == n):
                continue
            ran[sport] = rep[sport] = learn_sport(lconn, hconn, sport, log=log)
        except Exception as exc:                        # noqa: BLE001
            log(f"  ⚠️  board learning ({sport}) skipped: {exc}")
    if ran:
        _write(rep, path)
    return ran


def main(argv=None) -> int:
    """`python3 -m engine.boardlearn [--sport nfl]` — run it now and print
    what it found (the settle pass does this by itself)."""
    import argparse
    from . import db, ledger
    ap = argparse.ArgumentParser(prog="python3 -m engine.boardlearn")
    ap.add_argument("--sport", default="", help="one league (default: every league with a board)")
    ap.add_argument("--auto", action="store_true",
                    help="the settle loop's run: only leagues with new graded picks, short output")
    a = ap.parse_args(argv)
    sports = (a.sport.lower(),) if a.sport else SPORTS
    ran = refresh(ledger.connect(), db.connect(), sports=sports, force=not a.auto)
    if a.auto:
        print(f"board learning: refitted {', '.join(ran) or 'nothing (no new graded picks)'}")
        return 0
    for sport, e in ran.items():
        r = e["record"]
        print(f"\n=== {sport.upper()}: {r.get('won', 0)}-{r.get('n', 0) - r.get('won', 0)} on {r.get('n', 0)} graded "
              f"Most Likely picks, hit {r.get('hit', 0):.0%} where we said {r.get('said', 0):.0%}")
        for cut, rows in e["slices"].items():
            for s in rows:
                print(f"    {cut:8} {s['key']:38} n {s['n']:4}  hit {s['hit']:.0%}  said {s['said']:.0%}  {s['verdict']}")
        c = e["calibration"]
        print(f"    record correction: {'ADOPTED' if c['passed'] else 'not proven'}")
        if "scout" in e:
            print(f"    scout correction:  {'ADOPTED' if e['scout']['passed'] else 'not proven'} "
                  f"({e['scout']['matched']} picks matched to their game)")
    if not ran:
        print("no graded Most Likely picks yet")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
