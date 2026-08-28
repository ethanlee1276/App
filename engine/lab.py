"""The Lab — every walk-forward harness, run on a cadence and published.

The measured-evidence loop has always existed: half a dozen backtests
replay the PRODUCTION pricer over stored history and report whether the
model actually forecasts better than guessing. All of it printed to a
terminal and vanished. You could not see any of it from a phone, and a
measurement nobody reads is not a measurement.

This module runs what each sport's stored data actually supports,
normalizes every harness into one shape, and writes
``web/data/backtest.json`` for the site's Lab page. It runs weekly from
the maintenance pass — never a command anyone has to remember.

What each sport supports, and why the gaps are gaps:

* **Player props** — MLB replays its own ingested game logs and, where
  a closing price was harvested, prices against *the number a bettor
  could actually have taken*. NFL's harness needs a weekly-stats CSV
  the release feed gates. NBA / WNBA / CFB have no prop harness at all:
  their projections ship, but nothing replays them, and saying so is
  the point of the coverage matrix.
* **Game lines** — spreads and totals replay through the production
  pricer for every sport with harvested closes.

Two honesty rules the page inherits from the harnesses:

* **Basis.** A prop priced against a naive baseline line measures
  predictive skill, NOT an edge over the market. Only the book-priced
  subset speaks to beating a book, so basis travels with every number
  and the page refuses to headline a naive ROI.
* **Skill, not Brier.** "Brier 0.2417" reads like a score out of
  something; it is not. The bar is what you would score predicting the
  base rate every time, and the sharpness figure catches the other
  failure — a model that hedges toward the base rate is perfectly
  calibrated and perfectly useless.

Standard library only; reads the databases the ingests already fill.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

#: Absolute, because the launcher and the maintenance pass do not run from
#: the repo root — a relative default would quietly write the page's data
#: into whatever directory happened to be current.
LAB_PATH = Path(__file__).resolve().parents[1] / "web" / "data" / "backtest.json"

#: Backtests are CPU-heavy and their inputs move slowly — a week's fresh
#: results change a season-long walk-forward by very little. Weekly keeps
#: the page current without spending an evening's compute every launch.
LAB_EVERY_DAYS = 7

#: MLB prop markets worth replaying. Home runs have their own dedicated
#: harness (hr_backtest.py) because a rare event needs different bars.
MLB_MARKETS = ("total_bases", "hits", "strikeouts")

#: Game-line markets, and the sports whose closes can carry them.
GAME_MARKETS = ("total", "spread")
GAME_SPORTS = ("nfl", "mlb", "cfb", "nba", "wnba")

#: A walk-forward needs a real history before its numbers mean anything.
MIN_HISTORY = 8

#: Sports with no player-prop harness, and the honest reason. Absence
#: rendered as an explicit row beats a sport quietly missing from a page.
NO_PROP_HARNESS = {
    "nba": "no walk-forward prop harness yet — projections ship unreplayed",
    "wnba": "no walk-forward prop harness yet — projections ship unreplayed",
    "cfb": "no walk-forward prop harness yet — game lines only",
    "ufc": "fight picks are graded forward in the journal, not backtested",
}


def _round(x, n=4):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


def report_to_dict(report, market: str = "", label: str = "") -> dict:
    """One :class:`engine.backtest.BacktestReport` as plain JSON.

    ``basis`` is the headline honesty flag: "book" means every number
    below was priced against a harvested closing line, "naive" means the
    baseline, "mixed" means both and the segments carry the split.
    """
    used, total = report.used_real_lines, report.total_priced
    basis = "naive"
    if used and used >= total:
        basis = "book"
    elif used:
        basis = "mixed"
    out = {
        "market": market,
        "label": label or market,
        "n": report.n,
        "mae": _round(report.mae, 3),
        "rmse": _round(report.rmse, 3),
        "brier": _round(report.brier),
        "ece": _round(report.ece, 3),
        "skill": None,
        "bins": [{"lo": _round(b.lo, 2), "hi": _round(b.hi, 2), "n": b.n,
                  "mean_pred": _round(b.mean_pred, 3),
                  "hit_rate": _round(b.hit_rate, 3)}
                 for b in report.bins if b.n],
        "n_bets": report.n_bets,
        "wins": report.wins,
        "win_rate": _round(report.win_rate, 3),
        "roi": _round(report.roi, 4),
        "net_units": _round(report.net_units, 2),
        "units_staked": _round(report.units_staked, 2),
        "used_real_lines": used,
        "total_priced": total,
        "basis": basis,
        "segments": {},
    }
    sk = report.skill()
    if sk:
        out["skill"] = {"n": sk["n"], "base_rate": _round(sk["base_rate"], 4),
                        "base_brier": _round(sk["base_brier"]),
                        "skill": _round(sk["skill"], 4),
                        "hedged": _round(sk["hedged"], 3)}
    for name, g in (report.segments or {}).items():
        out["segments"][name] = {
            "n_bets": g.get("n_bets", 0), "wins": g.get("wins", 0),
            "win_rate": _round(g.get("win_rate"), 3),
            "roi": _round(g.get("roi"), 4), "net": _round(g.get("net"), 2),
            # THE GRADE LADDER, PER BASIS. `evaluate` has bucketed each
            # segment by grade all along and this dropped the buckets on
            # the way out, so the page could show that A and B+ disagree
            # and never which pricing produced the disagreement. The
            # whole question — does the top band earn its billing against
            # a real book — is a per-grade record inside the "book"
            # segment, and it was the one number not carried across.
            # THE SIDE SPLIT, for the same reason the grades are here.
            # `evaluate` has bucketed it all along and this dropped it.
            # Measured on 2025 NFL props: a naive-basis segment reading
            # "256 bets, 57.1%, +8.7%" is 129 overs at 44.2% (-8.5%) and
            # 127 unders at 66.1% (+26.1%). Those are not one number, and
            # the blended one describes neither side of the board.
            "sides": {side: {
                "n_bets": s.get("n_bets", 0), "wins": s.get("wins", 0),
                "win_rate": _round((s["wins"] / s["n_bets"])
                                   if s.get("n_bets") else None, 3),
                "roi": _round(s.get("roi"), 4),
                "net": _round(s.get("net"), 2)}
                for side, s in (g.get("sides") or {}).items()},
            "grades": {grade: {
                "n_bets": b.get("n_bets", 0), "wins": b.get("wins", 0),
                "win_rate": _round((b["wins"] / b["n_bets"])
                                   if b.get("n_bets") else None, 3),
                "roi": _round(b.get("roi"), 4),
                "net": _round(b.get("net"), 2)}
                for grade, b in (g.get("grades") or {}).items()},
        }
    return out


# --- player props ------------------------------------------------------------
def mlb_props(conn, markets=MLB_MARKETS, min_history: int = MIN_HISTORY,
              log=print) -> list[dict]:
    """Replay MLB props over ingested logs, priced against harvested closes
    wherever one exists (see engine.mlb.backtest.settled_props_from_logs)."""
    from . import db as _db
    from .mlb.backtest import backtest_from_logs
    from .mlb.models import MARKET_LABELS

    out = []
    for market in markets:
        try:
            entries = _db.entries_for_market(conn, "mlb", market,
                                             min_games=min_history + 1)
            if not entries:
                continue
            real = _db.closing_odds_by_date(conn, "mlb", market)
            rep = backtest_from_logs(entries, market,
                                     min_history=min_history,
                                     real_lines=real or {})
            if rep.n:
                out.append(report_to_dict(
                    rep, market, MARKET_LABELS.get(market, market)))
        except Exception as exc:                   # noqa: BLE001
            log(f"  lab: mlb {market} skipped — {exc}")
    return out


#: The NFL prop markets a harvested close can be joined to. The four
#: `SPORT_CONFIG["nfl"]["markets"]` buys, plus the scorer market — stored
#: under the same names `harvest_odds.py` writes.
#:
#: `anytime_td` matters more than the others here. A scorer prop is built
#: with NO proxy line on purpose (nflverse.build_slate: "a scorer market
#: priced against a made-up -110 would put fake edges on a longshot
#: board"), so the touchdown board is the one market that CANNOT be
#: replayed at all without a purchased price. Every other market has a
#: baseline to fall back on; this one has silence.
NFL_MARKETS = ("receptions", "rec_yds", "rush_yds", "pass_yds", "anytime_td")


def _seasons_to_try(season: int | None) -> list:
    """The season asked for, or the current one and the one before it.

    An explicit season is honoured exactly — a caller naming 2023 means
    2023 and must not silently get 2022.
    """
    from .pipeline import nfl_season_of
    if season:
        return [int(season)]
    current = nfl_season_of(None)
    return [current, current - 1]


def nfl_real_lines(conn, markets=NFL_MARKETS) -> dict:
    """``{(normalized player, market, date): close}`` for the NFL props.

    `closing_odds_by_date` answers one market at a time and drops the
    market from its key; the backtest needs it back, because a player has
    a receptions close and a receiving-yards close on the same day and
    they are different bets.
    """
    from . import db as _db
    out: dict = {}
    for market in markets:
        try:
            for (player, date), quote in _db.closing_odds_by_date(
                    conn, "nfl", market).items():
                out[(player, market, date)] = quote
        except Exception as exc:                   # noqa: BLE001
            raise RuntimeError(f"nfl {market} closes unreadable — {exc}")
    return out


def nfl_replay(season: int | None, weeks: list, real: dict, log=print):
    """``(report, season, tried)`` — the newest season that produced one.

    ONE implementation, because the second one was wrong. The `--bets`
    path reimplemented this loop and left out the `DataUnavailable`
    arm, so it crashed on an unplayed 2026 instead of falling back to
    2025 — the exact failure the fallback exists to prevent, in a copy of
    the fallback.
    """
    from .backtest import backtest_from_stats
    from .sources.fetch import DataUnavailable
    tried: list = []
    for candidate in _seasons_to_try(season):
        try:
            rep = backtest_from_stats(candidate, weeks, real_lines=real)
        except DataUnavailable as exc:
            tried.append(f"{candidate}: {str(exc).split(chr(10))[0]}")
            continue
        except Exception as exc:                   # noqa: BLE001
            log(f"  lab: nfl props {candidate} skipped — {exc}")
            tried.append(f"{candidate}: {exc}")
            continue
        if rep.n:
            return rep, candidate, tried
        tried.append(f"{candidate}: no settled props in weeks "
                     f"{weeks[0]}–{weeks[-1]}")
    return None, _seasons_to_try(season)[0], tried


def nfl_props(season: int | None = None, weeks=None, log=print,
              conn=None) -> dict:
    """Replay NFL props walk-forward. The weekly-stats feed is release-gated,
    so "no CSV on this machine" is the normal state and reported as such.

    Priced against harvested closes wherever one exists — `conn` is the
    history DB, and without it every prop falls back to the recent-form
    proxy the way this always did.
    """
    from .backtest import backtest_from_stats
    from .sources.fetch import DataUnavailable

    weeks = list(weeks or range(6, 18))
    real: dict = {}
    if conn is not None:
        try:
            real = nfl_real_lines(conn)
        except Exception as exc:                   # noqa: BLE001
            log(f"  lab: nfl closes unavailable — {exc}")

    # THE SEASON WITH GAMES IN IT, not the one the calendar is in.
    # `nfl_season_of` is right about what it answers — on 2026-08-27 the
    # 2026 season IS the current one — and wrong as a backtest default,
    # because that season has not been played. A lab run in August was
    # therefore guaranteed to replay an empty season and report
    # "unavailable" while four thousand credits of 2025 closing prices
    # sat in the database unread.
    #
    # One step back is enough and no further: an offseason run wants last
    # season, and a run in week 2 wants last season too (six weeks of
    # priors do not exist yet). Both are "the current season produced
    # nothing", so both are the same fallback.
    rep, season, tried = nfl_replay(season, weeks, real, log=log)
    if rep is None:
        return {"unavailable": "; ".join(tried) or "nothing to replay",
                "season": season}
    d = report_to_dict(rep, "all", "All prop markets")
    d["season"] = season
    d["weeks"] = [weeks[0], weeks[-1]]
    markets = [d]
    # THE TOUCHDOWN BOARD, REPORTED APART. A +450 scorer market and a
    # -110 yardage market do not share a meaningful win rate, and one
    # blended row would describe neither — so it gets its own entry the
    # way it gets its own report.
    if rep.longshots is not None and rep.longshots.n:
        td = report_to_dict(rep.longshots, "anytime_td", "Anytime touchdown")
        td["season"] = season
        td["weeks"] = [weeks[0], weeks[-1]]
        markets.append(td)
    return {"markets": markets, "season": season}


# --- game lines --------------------------------------------------------------
def game_lines(conn, sport: str, log=print) -> dict:
    """Spreads and totals through the production pricer, graded on real
    closing numbers.

    ``engine.gamebets`` refuses to price a sport whose scoring baseline
    and variances were never registered, rather than quietly borrowing
    another league's — so a refusal is reported as the honest gap it is.
    CFB registers its own at import, which is what every real build
    relies on; NBA and WNBA have none, so their game lines genuinely
    cannot be replayed yet.
    """
    from .gamebacktest import backtest_game_lines
    if sport == "cfb":
        from .cfb import ratings as _cfb_ratings      # noqa: F401  (installs)

    out, refusal = [], None
    for market in GAME_MARKETS:
        try:
            r = backtest_game_lines(conn, sport, market=market)
        except ValueError as exc:
            refusal = str(exc).split(" — ")[0]
            continue
        except Exception as exc:                   # noqa: BLE001
            log(f"  lab: {sport} {market} skipped — {exc}")
            continue
        # `games_quoted`, and the field name is the whole bug. This read
        # `games_priced`, which `GameLineBacktest` has never had, through
        # a `getattr(..., 0)` that turned the mistake into a silent zero
        # — so EVERY game-line market was skipped, for every sport, on
        # every run, and the Lab reported "no harvested closing lines
        # stored for this sport" on a database holding 17,457 MLB closes
        # and 899 replayable NFL games. An AttributeError would have been
        # loud on the first run; the default made it invisible for the
        # life of the feature. Attribute access, deliberately, so the
        # next rename fails instead of lying.
        if not r.games_quoted:
            continue
        out.append({
            "market": market,
            "games_seen": r.games_seen,
            "games_quoted": r.games_quoted,
            # Games whose stored close carries a LINE but no price. They
            # measure the projection and can never be bet, so they are
            # counted apart rather than folded into either number.
            "unpriced": r.unpriced,
            "n_bets": r.n_bets,
            "wins": r.wins,
            "win_rate": _round(r.wins / r.n_bets, 3) if r.n_bets else None,
            "roi": _round(r.roi, 4),
            "net": _round(r.net, 2),
            "mae": _round(r.mae, 3),
            "refused": r.refused,
            "source": r.source,
        })
    if out:
        return {"markets": out}
    if refusal:
        return {"unavailable": refusal}
    return {"unavailable": "no harvested closing lines stored for this sport"}


# --- the whole lab -----------------------------------------------------------
def build(conn=None, hconn=None, log=print, nfl: bool = True) -> dict:
    """Run every harness this machine's data supports and return the page's
    JSON. Each sport reports what it HAS and, where it has nothing, why."""
    from . import db as _db

    close = False
    if hconn is None:
        hconn = _db.connect()
        close = True
    try:
        sports: dict = {}
        props = mlb_props(hconn, log=log)
        sports["mlb"] = {"props": {"markets": props} if props else
                         {"unavailable": "no ingested game logs deep enough "
                                         "to replay yet"},
                         "game_lines": game_lines(hconn, "mlb", log=log)}
        sports["nfl"] = {"props": nfl_props(log=log, conn=hconn) if nfl else
                         {"unavailable": "skipped"},
                         "game_lines": game_lines(hconn, "nfl", log=log)}
        for sp in ("cfb", "nba", "wnba"):
            sports[sp] = {"props": {"unavailable": NO_PROP_HARNESS[sp]},
                          "game_lines": game_lines(hconn, sp, log=log)}
        sports["ufc"] = {
            "props": {"unavailable": NO_PROP_HARNESS["ufc"]},
            "game_lines": {"unavailable": "a fight has no spread or total to "
                                          "replay — the moneyline is the market"}}
        return {
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "sports": sports,
            "min_history": MIN_HISTORY,
            "every_days": LAB_EVERY_DAYS,
            # The caveat that must never be dropped in rendering: a naive
            # basis measures skill against a trailing average, not an edge
            # over a book, and the two get confused constantly.
            "basis_note": ("A prop priced against a NAIVE baseline line "
                           "measures predictive skill, not an edge over the "
                           "market. Only book-priced rows speak to beating "
                           "a sportsbook."),
        }
    finally:
        if close:
            hconn.close()


def _due(path: Path, today: _dt.date) -> bool:
    try:
        prev = json.loads(path.read_text()).get("generated_at") or ""
        last = _dt.date.fromisoformat(prev[:10])
    except (OSError, ValueError, AttributeError):
        return True
    return (today - last).days >= LAB_EVERY_DAYS


def run_if_due(hconn=None, log=print, path: Path | str | None = None,
               force: bool = False, today: _dt.date | None = None,
               nfl: bool = True) -> str:
    """The automatic lane. Returns a status word rather than raising — the
    settle pass must never fail because a backtest did."""
    p = Path(path if path is not None else LAB_PATH)
    today = today or _dt.date.today()
    if not force and not _due(p, today):
        return "already"
    try:
        out = build(hconn=hconn, log=log, nfl=nfl)
    except Exception as exc:                       # noqa: BLE001
        log(f"  lab: skipped — {exc}")
        return "failed"
    # THROUGH THE GATE. backtest.json is in gate.PAID_FILES — sealed in
    # its entirety on the public path — and this wrote the whole thing
    # there directly, so every weekly Lab run put the backtests back on
    # the open web until the next `--seal`. It also never wrote the
    # private copy, so `/api/board/backtest.json` had nothing to serve a
    # subscriber: the Lab page only worked at all because the file was
    # leaking. Third builder found doing this, after memes and fantasy.
    from . import gate
    gate.publish(out, p, p.name)
    ran = sum(1 for s in out["sports"].values()
              if (s["props"].get("markets")
                  or s["game_lines"].get("markets")))
    log(f"  lab: replayed {ran} sport(s) → {p}")
    return "ok"


# --- the command line --------------------------------------------------------
def _pct(x):
    return "—" if x is None else f"{x:.1%}"


def _print_market(m, indent="    ") -> None:
    """One market's replay, with the pricing basis it was measured on.

    The basis leads because it decides what every number under it means:
    "book" is a claim about beating a market, "naive" is a claim about the
    projection and nothing else.
    """
    # THE SEASON IS PART OF THE HEADLINE, because the replay silently
    # falls back one when the current season has not produced enough
    # games yet — so all through an offseason and the first weeks of a
    # new one, these numbers are LAST season's, and a reader with no year
    # in front of them has no way to know that.
    season = m.get("season")
    head = f"{indent}{m.get('label') or m.get('market')}"
    if season:
        head += f" [{season}]"
    n, basis = m.get("n") or 0, m.get("basis") or "naive"
    used, total = m.get("used_real_lines") or 0, m.get("total_priced") or 0
    share = f" ({used}/{total} priced on real closes)" if total else ""
    print(f"{head}: {n} settled · basis {basis}{share}")
    if m.get("n_bets"):
        print(f"{indent}  all bets   {m['n_bets']:>4}  "
              f"win {_pct(m.get('win_rate'))}  roi {_pct(m.get('roi'))}")
    for name in ("book", "naive"):
        seg = (m.get("segments") or {}).get(name)
        if not seg or not seg.get("n_bets"):
            continue
        label = "vs the book" if name == "book" else "vs a proxy"
        print(f"{indent}  {label:<10} {seg['n_bets']:>4}  "
              f"win {_pct(seg.get('win_rate'))}  roi {_pct(seg.get('roi'))}")
        # The two sides, because a segment's blended number can hide a
        # board that is winning on one and losing on the other.
        sides = seg.get("sides") or {}
        if len(sides) > 1:
            for side in ("OVER", "UNDER"):
                sd = sides.get(side)
                if sd and sd.get("n_bets"):
                    print(f"{indent}      {side:<5} {sd['n_bets']:>4}  "
                          f"win {_pct(sd.get('win_rate'))}  "
                          f"roi {_pct(sd.get('roi'))}")
        # The grade ladder, inside this basis. The question the harvest
        # was bought to answer lives here and nowhere else.
        for grade in ("A+", "A", "B+"):
            g = (seg.get("grades") or {}).get(grade)
            if g and g.get("n_bets"):
                print(f"{indent}      {grade:<3} {g['n_bets']:>4}  "
                      f"win {_pct(g.get('win_rate'))}  "
                      f"roi {_pct(g.get('roi'))}")


def _implied(odds) -> float | None:
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return (-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)


def dump_bets(report, limit: int = 0, indent: str = "  ") -> None:
    """Every settled BET behind a report, and the price band it sat in.

    THE QUESTION THE AGGREGATES CANNOT ANSWER. The touchdown board's
    first book-priced result was 7-for-40 at -48.9% ROI. At n=40 a 17.5%
    hit rate is statistically ordinary — the SE is 6 points — while that
    ROI implies an average winning payout near +92, which is not a
    longshot price at all. Those two readings point in different
    directions and only the rows can settle it: a board quietly taking
    -150s and calling them longshots looks exactly like a board with a
    broken model, until you print the prices.
    """
    bets = [s for s in (getattr(report, "settled", None) or [])
            if s.recommended]
    if not bets:
        print(f"{indent}(no settled bets)")
        return
    bands = {"-300 and shorter": 0, "-299..-150": 0, "-149..+150": 0,
             "+151..+350": 0, "+351..+700": 0, "longer than +700": 0}
    won = dict.fromkeys(bands, 0)
    staked = dict.fromkeys(bands, 0.0)
    net = dict.fromkeys(bands, 0.0)

    def band_of(o):
        if o <= -300:
            return "-300 and shorter"
        if o <= -150:
            return "-299..-150"
        if o <= 150:
            return "-149..+150"
        if o <= 350:
            return "+151..+350"
        if o <= 700:
            return "+351..+700"
        return "longer than +700"

    from .odds import american_to_decimal
    for s in bets:
        b = band_of(int(s.odds))
        bands[b] += 1
        stake = s.stake_units if s.stake_units > 0 else 1.0
        if s.outcome is None:                 # a push stakes nothing
            continue
        staked[b] += stake
        if s.outcome == 1:
            won[b] += 1
            net[b] += (american_to_decimal(s.odds) - 1.0) * stake
        else:
            net[b] -= stake

    print(f"{indent}by price band")
    print(f"{indent}  {'band':<18}{'bets':>5}{'won':>5}{'win%':>8}{'roi':>9}")
    for b, n in bands.items():
        if not n:
            continue
        wr = f"{won[b] / n:.1%}" if n else "—"
        roi = f"{net[b] / staked[b]:+.1%}" if staked[b] else "—"
        print(f"{indent}  {b:<18}{n:>5}{won[b]:>5}{wr:>8}{roi:>9}")

    rows = sorted(bets, key=lambda s: int(s.odds))
    if limit:
        rows = rows[:limit]
    print(f"{indent}\n{indent}every bet, shortest price first")
    print(f"{indent}  {'player':<24}{'price':>7}{'model':>8}"
          f"{'implied':>9}{'grade':>7}  result")
    for s in rows:
        imp = _implied(s.odds)
        print(f"{indent}  {str(s.player)[:24]:<24}{int(s.odds):>+7}"
              f"{s.hit_prob:>8.1%}{(f'{imp:.1%}' if imp else '—'):>9}"
              f"{(s.grade or '—'):>7}  "
              f"{'WON' if s.outcome == 1 else 'push' if s.outcome is None else 'lost'}")


def main(argv=None) -> int:
    """Replay every harness this machine's data supports and print it.

        python3 -m engine.lab
        python3 -m engine.lab --sport nfl
        python3 -m engine.lab --season 2025

    It existed only as a nightly side effect that wrote JSON — running the
    module directly printed nothing at all, twice, while its numbers were
    the whole point of a four-thousand-credit harvest.
    """
    import argparse
    from . import db as _db
    ap = argparse.ArgumentParser(description="Replay the models and report.")
    ap.add_argument("--sport", default="", help="Only this sport")
    ap.add_argument("--season", type=int, default=0,
                    help="NFL season to replay (default: the newest with games)")
    ap.add_argument("--json", action="store_true", help="Dump the raw JSON")
    ap.add_argument("--bets", action="store_true",
                    help="Print every settled NFL bet with its price and "
                         "result, plus a per-price-band summary")
    args = ap.parse_args(argv)

    hconn = _db.connect()
    if args.bets:
        # ITS OWN PATH, and NFL only. The bet rows live on the
        # BacktestReport, which `build()` has already flattened to JSON by
        # the time it returns — and re-running the walk-forward a second
        # time just to recover them would double the slowest thing here.
        weeks = list(range(6, 18))
        rep, season, tried = nfl_replay(args.season or None, weeks,
                                        nfl_real_lines(hconn))
        if rep is None:
            print("nothing to replay — " + ("; ".join(tried) or "no reason given"))
            return 0
        print(f"\nNFL {season} · all prop markets")
        dump_bets(rep)
        print(f"\nNFL {season} · anytime touchdown")
        if rep.longshots is not None and rep.longshots.n:
            dump_bets(rep.longshots)
        else:
            # NOT the same as "measured, found nothing". A scorer prop is
            # built with no line at all, so with no harvested touchdown
            # closes there is nothing for the board to price.
            print("  (no scorer prop carried a harvested price — nothing to "
                  "settle. `harvest_odds.py nfl --markets anytime_td`)")
        return 0
    if args.season:
        # An explicit season only reaches the NFL prop harness, which is
        # the only one that takes one.
        out = {"sports": {"nfl": {
            "props": nfl_props(season=args.season, conn=hconn),
            "game_lines": game_lines(hconn, "nfl")}}}
    else:
        out = build(hconn=hconn)
    if args.json:
        import json as _json
        print(_json.dumps(out, indent=2, sort_keys=True))
        return 0

    print("\nModel replay — every number is priced, and says what against\n")
    for sport, blob in (out.get("sports") or {}).items():
        if args.sport and sport != args.sport:
            continue
        print(f"{sport.upper()}")
        props = blob.get("props") or {}
        if props.get("unavailable"):
            print(f"    props: {props['unavailable']}")
        for m in props.get("markets") or []:
            _print_market(m)
        gl = blob.get("game_lines") or {}
        if gl.get("unavailable"):
            print(f"    game lines: {gl['unavailable']}")
        for m in gl.get("markets") or []:
            quoted, unpriced = m.get("games_quoted", 0), m.get("unpriced", 0)
            note = f", {unpriced} with no price" if unpriced else ""
            print(f"    {m['market']}: {quoted} game(s) quoted{note}  "
                  f"line MAE {m.get('mae')}  ({m.get('source', '')})")
            if m.get("n_bets"):
                print(f"      {m['n_bets']} bet(s)  "
                      f"win {_pct(m.get('win_rate'))}  roi {_pct(m.get('roi'))}")
            else:
                print(f"      no bet cleared the bar "
                      f"({m.get('refused', 0)} refused as not credible)")
        print()
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
