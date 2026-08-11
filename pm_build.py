#!/usr/bin/env python3
"""Build the Prediction Market Intelligence page's data.

    python3 pm_build.py --out web/data/predmarkets.json

Pulls Polymarket's top markets (Gamma API) and the public trade tape
(Data API) — both free, keyless — records everything into the history DB
(the tape cannot be backfilled, so recording runs before any analysis),
then scores the large flow and writes the page's JSON.
"""

from __future__ import annotations

import argparse
import datetime
import json
import time
from pathlib import Path

from engine import predmarket as pm
from engine.db import connect
from engine.sources.fetch import DataUnavailable

#: Where each sport's built slate lives — the games and moneyline
#: probabilities the Kalshi board compares against. Read from disk rather
#: than recomputed: pm builds AFTER the sport refreshes in launch.py's
#: cycle, so these are minutes old at worst, and rebuilding engines here
#: would double every build for a comparison column.
SLATE_FILES = {"nfl": "recommendations.json",
               "mlb": "mlb_recommendations.json",
               "nba": "nba.json", "wnba": "wnba.json", "cfb": "cfb.json"}


def _names_by_abbr(sport: str) -> dict:
    try:
        from engine.sources.oddsapi import SPORT_CONFIG
        teams = (SPORT_CONFIG.get(sport) or {}).get("teams") or {}
        return {ab: nm for nm, ab in teams.items()}
    except Exception:                              # noqa: BLE001
        return {}


def _tonights_games_and_probs(data_dir: Path):
    """(games_by_sport, model_probs) from the already-built slates.

    model_probs is {(sport, "AWY@HOM"): P(home wins)} — converted from each
    moneyline's pick-relative win_prob, because the Kalshi matcher needs one
    fixed convention and "probability of the pick" flips team every game.
    """
    games_by_sport, model_probs = {}, {}
    for sport, fname in SLATE_FILES.items():
        try:
            d = json.loads((data_dir / fname).read_text())
        except Exception:                          # noqa: BLE001
            continue
        names = _names_by_abbr(sport)
        rows = []
        for g in d.get("games", []) or []:
            rows.append({"home": g.get("home", ""), "away": g.get("away", ""),
                         "home_name": names.get(g.get("home", ""), ""),
                         "away_name": names.get(g.get("away", ""), "")})
        if rows:
            games_by_sport[sport] = rows
        for b in d.get("game_bets", []) or []:
            if b.get("bet_type") != "moneyline" or b.get("win_prob") is None:
                continue
            key = f"{b.get('away', '')}@{b.get('home', '')}"
            p = float(b["win_prob"])
            model_probs[(sport, key)] = p if b.get("pick_is_home") else 1 - p
    return games_by_sport, model_probs


def build_kalshi(out_path: Path, data_dir: Path) -> None:
    """The second venue, in its own failure domain.

    Kalshi being down must not cost the Polymarket build and vice versa —
    they are different hosts with different outages. When the feed is
    unreachable and a previous board exists, the previous board stands
    (same "keep last data" contract as the Polymarket path); with no
    previous board the page gets an honest note instead of silence.
    """
    from engine import kalshiweather as kw
    from engine import ledger
    from engine.sources import kalshi as kx
    try:
        markets = kx.parse_markets(kx.fetch_markets())
    except DataUnavailable as exc:
        if out_path.exists():
            print(f"⚠️  Kalshi unreachable — keeping last board.\n   {exc}")
            return
        out_path.write_text(json.dumps({
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "venue": "kalshi", "rows": [], "n_markets": 0, "n_matched": 0,
            "n_modeled": 0, "n_rec": 0, "sports_seen": [], "weather": [],
            # The exception's own words, so "unreachable" stops being a
            # diagnosis-free shrug — Ethan has only ever seen this note,
            # never a recommendation, and the WHY is the fixable part.
            "note": f"Kalshi feed unreachable from this machine — {exc}"},
            indent=2))
        return
    conn = connect()
    kx.store_snapshot(conn, markets)
    games_by_sport, model_probs = _tonights_games_and_probs(data_dir)
    out = kx.board(markets, games_by_sport, model_probs)

    # THE WEATHER DESK — NWS forecast priced against the daily-high
    # brackets. Its own failure domain: a dead forecast API costs the
    # weather rows, never the sports board.
    weather_rows = []
    try:
        by_series = kw.fetch_weather_markets(kx.parse_markets)
        today = datetime.date.today().isoformat()
        highs = {}
        for series, meta in kw.CITIES.items():
            if series not in by_series:
                continue
            for lead in range(kw.MAX_LEAD_DAYS + 1):
                d = (datetime.date.today()
                     + datetime.timedelta(days=lead)).isoformat()
                mu = kw.nws_high(meta["lat"], meta["lon"], d)
                if mu is not None:
                    highs[(series, d)] = mu
        weather_rows = kw.weather_board(by_series, highs, today=today)
        kw.log_forecasts(conn, weather_rows)
    except Exception as exc:                       # noqa: BLE001
        print(f"⚠️  weather desk skipped: {exc}")
    out["weather"] = weather_rows[:20]

    # Journal what cleared the gates (flat paper stakes), then grade
    # whatever the exchange has since settled.
    recs = ([dict(r, desk="kalshi_ml") for r in out["rows"] if r.get("rec")]
            + [dict(r, sport="weather", desk="kalshi_wx")
               for r in weather_rows if r.get("rec")])
    logged = ledger.log_predmarket(conn, recs)
    settled = 0
    try:
        open_tk = ledger.open_predmarket_tickers(conn)
        results = {}
        for m in kx.fetch_markets_by_tickers(open_tk):
            res = (m.get("result") or "").lower()
            if res in ("yes", "no"):
                results[m.get("ticker", "")] = res
        settled = ledger.resolve_predmarket(conn, results)
    except Exception as exc:                       # noqa: BLE001
        print(f"⚠️  desk settlement skipped: {exc}")
    out["desk"] = {"logged_today": logged, "settled_now": settled,
                   "paper": {k: ledger.predmarket_report(conn).get(k)
                             for k in ("settled", "wins", "losses",
                                       "net_units", "roi")}}

    stored = conn.execute(
        "SELECT COUNT(*) FROM kalshi_snapshots").fetchone()[0]
    out["tape"] = {"stored_total": stored}
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Kalshi: {out['n_markets']} sports market(s), "
          f"{out['n_matched']} matched to tonight, "
          f"{out['n_modeled']} with a model number, "
          f"{out.get('n_rec', 0)} recommended · weather rows "
          f"{len(weather_rows)} · desk +{logged} logged, {settled} settled "
          f"· tape {stored:,}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/predmarkets.json")
    args = ap.parse_args()

    out_dir = Path(args.out).parent
    build_kalshi(out_dir / "kalshi.json", out_dir)

    try:
        markets = pm.parse_markets(pm.fetch_markets())
        trades = pm.parse_trades(pm.fetch_trades())
    except DataUnavailable as exc:
        print(f"⚠️  Polymarket unreachable — keeping last data.\n   {exc}")
        raise SystemExit(2)
    # Dedicated big-trade pull: the general feed is nearly all retail-sized
    # fills, so without this a 500-row slice can contain zero whales.
    try:
        trades += pm.parse_trades(pm.fetch_big_trades())
    except DataUnavailable:
        pass

    conn = connect()
    new_trades = pm.store_trades(conn, trades)
    pm.store_snapshot(conn, markets)
    history = pm.wallet_history(conn)
    names = pm.wallet_names(conn)
    total_trades = conn.execute("SELECT COUNT(*) FROM pm_trades").fetchone()[0]

    # Score the last 24h of RECORDED tape, not just this pull's thin slice —
    # big trades are a few per hour, and the tape accumulates them.
    feed = pm.build_flow_feed(pm.recent_tape(conn), markets, history)
    for f in feed:
        f["name"] = names.get(f["wallet"], "")

    # Validation loop: persist every flag, settle the ones whose markets
    # resolved, and publish the report card. An ungraded flag is decoration.
    new_flags = pm.store_flags(conn, feed)
    try:
        settled = pm.resolve_flags(conn)
    except Exception:
        settled = 0
    validation = pm.flag_report(conn)
    for w in validation.get("wallets", []):
        w["name"] = names.get(w["wallet"], "")
    for r in validation.get("recent", []):
        r["name"] = names.get(r["wallet"], "")
    conn.close()

    # Top traders by realized P&L (Polymarket's own leaderboard), each with
    # their latest trades. Falls back to our tape's most-active wallets if
    # the leaderboard endpoint is unreachable.
    top_traders, traders_note = [], ""
    try:
        leaders, window_label = [], ""
        for window, label in pm.LEADERBOARD_WINDOWS:
            try:
                leaders = pm.parse_leaderboard(pm.fetch_leaderboard(window))[:10]
            except (DataUnavailable, ValueError):
                continue
            if leaders:
                window_label = label
                break
        if not leaders:
            raise DataUnavailable("no leaderboard window answered")
        by_wallet, pnl_by_wallet = {}, {}
        for ld in leaders:
            try:
                by_wallet[ld["wallet"]] = pm.parse_trades(
                    pm.fetch_wallet_trades(ld["wallet"]))
            except DataUnavailable:
                by_wallet[ld["wallet"]] = []
            try:
                # One-month cumulative P&L curve, straight from the same
                # endpoint Polymarket's own profile chart uses.
                pnl_by_wallet[ld["wallet"]] = pm.parse_pnl_series(
                    pm.fetch_pnl_series(ld["wallet"]))
            except (DataUnavailable, ValueError):
                pnl_by_wallet[ld["wallet"]] = []
        top_traders = pm.build_top_traders(leaders, by_wallet, pnl_by_wallet)
        traders_note = (f"ranked by realized profit over {window_label} "
                        f"(Polymarket leaderboard)")
    except (DataUnavailable, ValueError) as exc:
        ranked = sorted(history.items(), key=lambda kv: -kv[1]["usd"])[:10]
        top_traders = pm.build_top_traders(
            [{"wallet": w, "name": names.get(w, ""), "pnl": 0.0}
             for w, _ in ranked], {})
        traders_note = (f"leaderboard unreachable ({exc}) — showing our "
                        f"tape's most-active wallets instead")

    # Display board: live prices only — a settled market pinned at 0/100¢
    # (finished esports series etc.) is clutter, not information.
    display_markets = [m for m in markets if 0.02 <= m["yes"] <= 0.98]

    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "venue": "polymarket",
        "markets": display_markets[:50],
        "flow": feed,
        "validation": validation,
        "top_traders": top_traders,
        "traders_note": traders_note,
        "tape": {"stored_total": total_trades, "new_this_pull": new_trades,
                 "wallets_seen": len(history)},
    }
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print(f"Polymarket: {len(markets)} markets, {new_trades} new trade(s) "
          f"recorded ({total_trades:,} on tape, {len(history):,} wallets), "
          f"{len(feed)} flow flag(s) ≥ ${pm.FEED_FLOOR_USD:,}; "
          f"{new_flags} flag(s) stored, {settled} settled, "
          f"{validation.get('graded', 0)} graded all-time. Wrote {args.out}")


if __name__ == "__main__":
    main()
