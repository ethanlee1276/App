"""Does the usage ripple carry information the close does not?

Ethan, 2026-09-14: "RB2 Isiah Pacheco is now out till October 11th so
RB1 Jahmyr Gibbs should be seeing a lot more usage ... I wanna make sure
we are adjusting if needed." Two sizes were offered and he took both.
The safe one is on the card (engine.redistribute.ripples_for_props): the
measured share a beneficiary absorbed when this teammate sat. This is
the other one — whether that number should MOVE the projection — and
it is answered the only way a pricing change is answered here: against
closing lines, not argued (docs/THE_INFORMATION_TEST.md).

THE QUESTION, EXACTLY. On a week where a same-position teammate did not
play, the book hung a number on the beneficiary. Did he beat it by more
than the book allowed, and by an amount the ripple predicted from
strictly earlier weeks? If the close already carries the absence — and
a book that reads the Friday injury report has every chance to — the
residual (actual − close) is noise around zero and the predicted extra
yards do not order it. Then the card's note stays a note.

WHAT IS MEASURED, per market:
  * every beneficiary-week with a stored close on which a same-group
    teammate was absent (absence read from the stats: he had a real
    share of the team's carries or targets earlier this season and no
    usage this week — the same reading `redistribute` uses);
  * the residual actual − close over those rows, with its standard
    error: is the market missing the absence at all?
  * on the rows where the ripple could be measured from earlier weeks
    (three or more missed games behind it), the predicted extra
    production — share delta × the team's volume × his yards per touch
    — regressed on the residual: does the SIZE of the ripple predict
    the size of the miss? Fitted on the earlier season(s), judged on
    the latest, never the same games (`engine.nflfit` set that rule);
  * and a bet rule on the judged season: over the close wherever the
    predicted extra clears a floor, settled at the stored over price.
    A coefficient that cannot pay the vig is a finding, not a model.

A market CLEARS when, on the judged season alone, the residual on the
measured rows sits two standard errors above zero (the close missed the
absence) and the bet rule pays at the close. The slope is reported
beside the verdict, not in it.

THE VERDICT is per market and stored (`ripplefit.json` in the models
directory) so a pricing hook can read it — and there is deliberately no
pricing hook yet. If a market clears, adding one is a small change made
on a measurement; if none does, nothing was built on a guess.

Runs inside the weekly Lab (engine.lab), so the answer lands on the
site's Lab page without anyone running anything. `python3 -m
engine.ripplefit` prints the same table on demand. Standard library.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from . import redistribute as _rd

#: A teammate counts as absent only if he had a real role: at least this
#: share of the team's usage, averaged over EVERY team week since he
#: first appeared — zeros included. Averaged over his active weeks
#: alone, the third back who carries the ball only when the starter is
#: hurt reads as a 25% player who is then "absent" every healthy week,
#: and the first cut of this counted 180 absences where there were 72.
MIN_SHARE = 0.15
#: ... measured over at least this many earlier weeks with usage.
MIN_PRIOR_WEEKS = 2
#: Fewer absence rows than this for a market and the verdict is "not
#: enough" rather than a coefficient nobody should read.
MIN_ROWS = 40
#: The bet rule needs this many settled bets on the judged season.
MIN_BETS = 30
#: Slope must be this many standard errors from zero on the judged
#: season.
MIN_T = 2.0
#: When only one season carries closes: fitted on weeks before this,
#: judged on weeks from it.
SPLIT_WEEK = 10
#: The predicted extra production at which the bet rule fires.
BET_FLOOR = {"rush_yds": 5.0, "rec_yds": 5.0, "receptions": 0.5}
STORE = "ripplefit.json"

KINDS = {
    "carries": {"markets": ("rush_yds",), "group": frozenset({"RB", "FB"})},
    "targets": {"markets": ("rec_yds", "receptions"),
                "group": frozenset({"WR", "TE"})},
}
MARKETS = tuple(m for k in KINDS.values() for m in k["markets"])
USAGE_MARKETS = ("targets", "carries") + MARKETS


def load_logs(conn, seasons=None) -> dict:
    """``{(season, week, team): {player: {"pos", market: value}}}`` from
    the ingested NFL logs — usage and production on one row per player."""
    sql = ("SELECT season, period, player, team, position, market, value "
           "FROM player_game_logs WHERE sport='nfl' AND market IN (%s) "
           % ",".join("?" * len(USAGE_MARKETS)))
    args: list = list(USAGE_MARKETS)
    if seasons:
        sql += "AND season IN (%s) " % ",".join("?" * len(seasons))
        args.extend(int(s) for s in seasons)
    out: dict = {}
    for r in conn.execute(sql, args):
        try:
            week = int(r["period"])
        except (TypeError, ValueError):
            continue
        if r["value"] is None or not r["team"]:
            continue
        key = (int(r["season"]), week, str(r["team"]).upper())
        d = out.setdefault(key, {}).setdefault(r["player"], {})
        d[r["market"]] = float(r["value"])
        if r["position"]:
            d["pos"] = str(r["position"]).upper()
    return out


def _stat_rows(logs, season: int, team: str, upto_week=None) -> list:
    """The nflverse-shaped rows `redistribute` reads, for one team-season."""
    rows = []
    for (s, w, t), players in logs.items():
        if s != season or t != team or (upto_week is not None and w > upto_week):
            continue
        for p, d in players.items():
            rows.append({"season": s, "week": w, "player_display_name": p,
                         "recent_team": t, "position": d.get("pos", ""),
                         "targets": d.get("targets", 0.0),
                         "carries": d.get("carries", 0.0)})
    return rows


def absent_this_week(logs, season: int, week: int, team: str, kind: str,
                     group) -> list:
    """Group players with a real role earlier this season who have no
    usage this week, on a week the team played."""
    this = logs.get((season, week, team))
    if not this:
        return []
    shares: dict = {}          # player -> [share per team week since first seen]
    active: dict = {}          # player -> weeks with usage
    for w in range(1, week):
        wk = logs.get((season, w, team))
        if not wk:
            continue
        tot = sum(d.get(kind, 0.0) for d in wk.values())
        if tot <= 0:
            continue
        for p in shares:
            shares[p].append((wk.get(p) or {}).get(kind, 0.0) / tot)
        for p, d in wk.items():
            if d.get("pos") in group and d.get(kind, 0.0) > 0:
                if p not in shares:
                    shares[p] = [d[kind] / tot]
                active[p] = active.get(p, 0) + 1
    out = []
    for p, ss in shares.items():
        if active.get(p, 0) < MIN_PRIOR_WEEKS or sum(ss) / len(ss) < MIN_SHARE:
            continue
        # NO ROW AT ALL, not zero usage. nflverse writes a row for every
        # player who dressed, carries or not; a man who did not play has
        # none. Zero usage is a healthy scratch or an unused backup —
        # the third back three weeks after his run of work — and reading
        # him as absent counted 36 healthy weeks as absences.
        if p not in this:
            out.append(p)
    return sorted(out)


def predicted_extra(logs, season: int, week: int, team: str, absent: str,
                    beneficiary: str, kind: str, market: str):
    """Extra production the ripple predicts for `beneficiary` this week,
    from strictly earlier weeks: share delta × team volume × his rate.
    None when the absence sample is under the floor or he cannot be
    compared."""
    stats = _stat_rows(logs, season, team, week - 1)
    prior = _stat_rows(logs, season - 1, team)
    rows = _rd.absence_rows(stats, prior, team, absent, kind, season, week)
    if not rows:
        return None
    res = _rd.redistribution(rows, team, absent, kind)
    b = res["beneficiaries"].get(beneficiary)
    if not res["enough"] or not b:
        return None
    vols = [sum(d.get(kind, 0.0) for d in logs[(season, w, team)].values())
            for w in range(1, week) if (season, w, team) in logs]
    if len(vols) < MIN_PRIOR_WEEKS:
        vols = [sum(d.get(kind, 0.0) for d in players.values())
                for (s, w, t), players in logs.items()
                if s == season - 1 and t == team]
    vols = [v for v in vols if v > 0]
    if not vols:
        return None
    volume = sum(vols) / len(vols)
    num = den = 0.0
    for s in (season, season - 1):
        for (ss, w, t), players in logs.items():
            if ss != s or t != team or (s == season and w >= week):
                continue
            d = players.get(beneficiary)
            if d:
                den += d.get(kind, 0.0)
                num += d.get(market, 0.0)
        if den >= 10:
            break
    if den <= 0:
        return None
    return float(b["delta"]) * volume * (num / den)


@dataclass
class Row:
    season: int
    week: int
    team: str
    player: str
    market: str
    kind: str
    absent: str
    x: float | None          # predicted extra production, None if unmeasurable
    line: float
    over_odds: int
    under_odds: int
    actual: float

    @property
    def resid(self) -> float:
        return self.actual - self.line


def _norm(name: str) -> str:
    from .backtest import _norm as _n
    return _n(name)


def build_rows(conn, seasons=None, dates: dict | None = None,
               closes: dict | None = None) -> list:
    """Every beneficiary-week with a close on which a same-group teammate
    was absent. ``dates`` is ``{(season, week, team): 'YYYY-MM-DD'}``
    (the schedule); ``closes`` is ``{market: closing_odds_by_date}``.
    Both injectable so the suite never reads the box or the network."""
    from . import db as _db
    if closes is None:
        closes = {m: _db.closing_odds_by_date(conn, "nfl", m) for m in MARKETS}
    closes = {m: {(_norm(p), d): q for (p, d), q in (closes.get(m) or {}).items()}
              for m in MARKETS}
    close_seasons = set()
    if dates is None:
        from .formbook import game_dates
        dates = game_dates(seasons)
    have_dates = set(d for d in dates.values() if d)
    for m in MARKETS:
        for (_p, d) in closes[m]:
            if d in have_dates:
                close_seasons.update(s for (s, _w, _t), dd in dates.items() if dd == d)
    if seasons:
        close_seasons = set(int(s) for s in seasons)
    if not close_seasons:
        return []
    want = sorted(close_seasons)
    logs = load_logs(conn, seasons=sorted(set(want) | {s - 1 for s in want}))
    rows: list = []
    for (season, week, team) in sorted(k for k in logs if k[0] in close_seasons):
        players = logs[(season, week, team)]
        date = dates.get((season, week, team))
        if not date:
            continue
        for kind, spec in KINDS.items():
            absent = absent_this_week(logs, season, week, team, kind, spec["group"])
            if not absent:
                continue
            for player, d in players.items():
                if d.get("pos") not in spec["group"] or player in absent:
                    continue
                for market in spec["markets"]:
                    q = closes[market].get((_norm(player), date))
                    actual = d.get(market)
                    if not q or q.get("line") is None or actual is None:
                        continue
                    xs = [predicted_extra(logs, season, week, team, a, player,
                                          kind, market) for a in absent]
                    xs = [x for x in xs if x is not None]
                    rows.append(Row(season, week, team, player, market, kind,
                                    ", ".join(absent), sum(xs) if xs else None,
                                    float(q["line"]), int(q.get("over_odds") or -110),
                                    int(q.get("under_odds") or -110), float(actual)))
    return rows


def _payout(odds: int) -> float:
    return odds / 100.0 if odds > 0 else 100.0 / abs(odds)


def _split(rows: list) -> tuple:
    seasons = sorted({r.season for r in rows})
    if len(seasons) >= 2:
        test = seasons[-1]
        return ([r for r in rows if r.season != test],
                [r for r in rows if r.season == test],
                f"fitted on {', '.join(str(s) for s in seasons[:-1])}, judged on {test}")
    return ([r for r in rows if r.week < SPLIT_WEEK],
            [r for r in rows if r.week >= SPLIT_WEEK],
            f"one season of closes: fitted on weeks 1–{SPLIT_WEEK - 1}, "
            f"judged on weeks {SPLIT_WEEK}+")


def _mean_se(vals: list) -> tuple:
    n = len(vals)
    if n < 2:
        return (vals[0] if vals else 0.0), float("nan")
    m = sum(vals) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    return m, sd / math.sqrt(n)


def fit(rows: list) -> dict:
    """The table, per market, and a verdict each."""
    from .nflinfo import fit_ols
    out: dict = {"markets": {}, "n_rows": len(rows)}
    for market in MARKETS:
        mr = [r for r in rows if r.market == market]
        m: dict = {"n": len(mr), "verdict": "not enough", "n_measured": 0}
        out["markets"][market] = m
        if not mr:
            continue
        mean, se = _mean_se([r.resid for r in mr])
        m["resid_mean"], m["resid_se"] = round(mean, 3), (round(se, 3) if se == se else None)
        measured = [r for r in mr if r.x is not None]
        m["n_measured"] = len(measured)
        if len(mr) < MIN_ROWS:
            m["reason"] = f"{len(mr)} absence rows, floor {MIN_ROWS}"
            continue
        train, test, how = _split(measured)
        m["split"] = how
        for label, part in (("train", train), ("test", test)):
            f = fit_ols([((r.x,), r.resid) for r in part]) if len(part) >= 3 else None
            if f:
                (_a, b), (_sa, sb) = f
                m[f"{label}_slope"], m[f"{label}_slope_se"] = round(b, 4), round(sb, 4)
                m[f"{label}_n"] = len(part)
        floor = BET_FLOOR.get(market, 0.0)
        bets = [r for r in test if r.x >= floor]
        net = sum((_payout(r.over_odds) if r.actual > r.line else
                   (0.0 if r.actual == r.line else -1.0)) for r in bets)
        m["bets"], m["roi"] = len(bets), (round(net / len(bets), 4) if bets else None)
        m["wins"] = sum(1 for r in bets if r.actual > r.line)
        # THE GATE, on the judged season only: the market MISSED the
        # absence (the residual on the measured rows sits MIN_T standard
        # errors above zero) AND the bet rule pays at the close. The
        # slope — does the SIZE of the ripple order the miss — is
        # reported beside it and is not the gate: a pricing hook adds the
        # measured delta, and the money question is whether rows with a
        # measured delta beat the number, not whether bigger beats more.
        jm, jse = _mean_se([r.resid for r in test]) if len(test) >= 2 \
            else (0.0, float("nan"))
        m["judged_resid_mean"] = round(jm, 3)
        m["judged_resid_se"] = round(jse, 3) if jse == jse else None
        missed = bool(jse == jse and jse > 0 and jm / jse >= MIN_T)
        pays = len(bets) >= MIN_BETS and (m["roi"] or 0) > 0
        if missed and pays:
            m["verdict"] = "clears"
        else:
            m["verdict"] = "declined"
            why = []
            if not test:
                why.append("no measurable rows on the judged season")
            elif not missed:
                why.append(f"judged-season residual {jm:+.2f} ± "
                           f"{(jse if jse == jse else 0):.2f} — the close "
                           f"already carries the absence")
            if len(bets) < MIN_BETS:
                why.append(f"{len(bets)} bets, floor {MIN_BETS}")
            elif (m["roi"] or 0) <= 0:
                why.append(f"ROI {m['roi']:+.1%} at the close")
            m["reason"] = "; ".join(why)
    out["adopt"] = {k: v["verdict"] == "clears" for k, v in out["markets"].items()}
    return out


def store_path(models_dir=None) -> Path:
    from . import modelstate
    base = models_dir or modelstate.directory()
    return Path(base) / STORE


def save(out: dict, models_dir=None) -> Path:
    p = store_path(models_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(out, indent=2, sort_keys=True))
    os.replace(tmp, p)
    return p


def load(models_dir=None) -> dict:
    try:
        return json.loads(store_path(models_dir).read_text())
    except (OSError, ValueError):
        return {}


def run(conn, seasons=None, dates=None, closes=None, models_dir=None,
        log=print) -> dict:
    """Measure, store, return. The Lab's entry point."""
    import datetime as _dt
    rows = build_rows(conn, seasons=seasons, dates=dates, closes=closes)
    out = fit(rows)
    out["measured_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    save(out, models_dir)
    for line in report_lines(out):
        log(line)
    return out


def report_lines(out: dict) -> list:
    lines = ["", "  USAGE RIPPLE AGAINST THE CLOSE — does a teammate's absence "
                 "carry information the book missed?",
             f"  {out.get('n_rows', 0)} beneficiary-weeks with a same-position "
             f"teammate absent and a stored close"]
    for market, m in (out.get("markets") or {}).items():
        lines.append(f"  {market:<11} n={m['n']:<5} measured={m['n_measured']:<5} "
                     f"resid {m.get('resid_mean', 0):+.2f} ± {m.get('resid_se') or 0:.2f}   "
                     f"→ {m['verdict'].upper()}"
                     + (f" — {m['reason']}" if m.get("reason") else ""))
        if m.get("test_slope") is not None:
            lines.append(f"  {'':<11} {m.get('split', '')}: slope "
                         f"{m['test_slope']:+.3f} ± {m['test_slope_se']:.3f} "
                         f"(train {m.get('train_slope', float('nan')):+.3f}), "
                         f"bets {m['bets']} won {m['wins']}"
                         + (f" ROI {m['roi']:+.1%}" if m.get("roi") is not None else ""))
    lines.append("  A residual near zero means the close already carries the "
                 "absence; the card's note stays a note.")
    return lines


def main(argv=None) -> int:
    import argparse
    from . import db as _db
    ap = argparse.ArgumentParser(description="The usage ripple against the close.")
    ap.add_argument("--season", type=int, action="append",
                    help="Season(s) with closes to use (default: every season "
                         "that has a stored close)")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable output instead of the report")
    args = ap.parse_args(argv)
    conn = _db.connect()
    out = run(conn, seasons=args.season, log=(lambda *_: None) if args.json else print)
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":                                # pragma: no cover
    raise SystemExit(main())
