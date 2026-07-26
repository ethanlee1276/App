"""Fantasy football engine — volume is predictive, efficiency is noise.

Points are the OUTPUT: a lagging indicator contaminated by touchdown luck
and one 60-yard catch. The INPUT is opportunity — targets, carries, and
their share of the team's work — and that's what carries into next week.
Every view here is a different read of the same stored usage rows:

* **usage board** — each player's share of team targets/carries, framed as
  the spec demands: last week vs 4-week average vs season. The DELTA is
  where the money is; a riser at 42% beats a flat 60%.
* **buy-low / sell-high** — expected points from pure volume (league-wide
  value per target and per carry, fit from our own data each season)
  against actual PPR scoring. Big overshoot = likely to cool; big
  undershoot = usage says production is coming. Sustainable-band caveat
  applied: good players legitimately beat volume, so small gaps are noise.
* **game scripts** — Vegas is the input: implied team totals from
  spread/total, the four archetypes, and confidence that SCALES with
  spread size (7+ favorites win ~79%; a 2-point spread predicts nothing).

Data: the nflverse usage rows ingested alongside player logs. Offseason
shows the last completed season, labeled as such.
"""

from __future__ import annotations

from .statmath import clamp

USAGE_MIN_WEEKS = 4
BOARD_LIMIT = 60
SUSTAINABLE_PPG = 1.5          # gap within this band is skill/noise, not signal
SCRIPT_ARCHETYPES = {
    ("high", "close"): ("Everyone eats", "High total, close spread — the best "
                        "environment in fantasy. Prime stacking."),
    ("high", "big"): ("Favorite runs, dog throws", "High total, big spread — "
                      "favorite's RB gets clock-killing volume; underdog WRs "
                      "get garbage-time targets. Underdog RB nearly unstartable."),
    ("low", "big"): ("Floor, no ceiling", "Low total, big spread — favorite's "
                     "RB is a floor play; fade the underdog backfield entirely."),
    ("low", "close"): ("Nobody's good", "Low total, close spread — downgrade "
                       "across the board."),
}


def latest_season(conn) -> int | None:
    row = conn.execute(
        "SELECT MAX(season) FROM player_game_logs WHERE sport='nfl' "
        "AND market='targets'").fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _weekly(conn, season: int) -> dict:
    """{player: {"team", "position", "weeks": {wk: {market: value}}}} plus
    {(team, wk): {market: team total}} in one pass."""
    players: dict[str, dict] = {}
    teams: dict[tuple, dict] = {}
    for r in conn.execute(
            "SELECT player, team, opponent, position, period, market, value "
            "FROM player_game_logs WHERE sport='nfl' AND season=? AND market "
            "IN ('targets','carries','receptions','air_yards','fp_ppr')",
            (season,)):
        wk = r["period"]
        p = players.setdefault(r["player"], {"team": r["team"],
                                             "position": r["position"],
                                             "weeks": {}})
        p["team"] = r["team"] or p["team"]
        p["weeks"].setdefault(wk, {})[r["market"]] = float(r["value"])
        t = teams.setdefault((r["team"], wk), {})
        t[r["market"]] = t.get(r["market"], 0.0) + float(r["value"])
    return {"players": players, "teams": teams}


def _share(part: float, whole: float) -> float | None:
    return part / whole if whole > 0 else None


def _short_key(name: str, team: str) -> tuple:
    """Join key across name styles: pbp says "P.Mahomes", weekly stats say
    "Patrick Mahomes" — (first initial, last name, team) matches both."""
    parts = [p for p in str(name).replace(".", " ").lower().split() if p]
    if not parts:
        return ("", "", team)
    return (parts[0][0], parts[-1], team)


def _pbp_weekly(conn, season: int) -> dict:
    """{short_key: {week: {"xfp"|"rz_tgt"|"i5_car": value}}} from ingested
    play-by-play aggregates (empty dict when pbp was never ingested)."""
    out: dict = {}
    for r in conn.execute(
            "SELECT player, team, period, market, value FROM player_game_logs "
            "WHERE sport='nfl' AND season=? AND market IN "
            "('xfp','rz_tgt','i5_car')", (season,)):
        key = _short_key(r["player"], r["team"])
        out.setdefault(key, {}).setdefault(r["period"], {})[r["market"]] = \
            float(r["value"])
    return out


def usage_board(conn, season: int, limit: int = BOARD_LIMIT) -> list[dict]:
    """Target/carry shares with the trend framing: last week vs 4-week
    average vs season, sorted so the biggest movers surface first."""
    data = _weekly(conn, season)
    pbp = _pbp_weekly(conn, season)
    out = []
    for player, p in data["players"].items():
        weeks = sorted(p["weeks"])
        if len(weeks) < USAGE_MIN_WEEKS:
            continue
        share_key = "carries" if p["position"] == "RB" else "targets"

        def wk_share(wk):
            mine = p["weeks"][wk].get(share_key, 0.0)
            team = data["teams"].get((p["team"], wk), {}).get(share_key, 0.0)
            return _share(mine, team)

        shares = [s for s in (wk_share(w) for w in weeks) if s is not None]
        if not shares:
            continue
        last = wk_share(weeks[-1])
        prior4 = [s for s in (wk_share(w) for w in weeks[-5:-1]) if s is not None]
        l4 = sum(prior4) / len(prior4) if prior4 else None
        season_avg = sum(shares) / len(shares)
        delta = (last - l4) if (last is not None and l4 is not None) else 0.0
        fp = [p["weeks"][w].get("fp_ppr", 0.0) for w in weeks]
        # TD equity from play-by-play: inside-5 carries for RBs, red-zone
        # targets for pass-catchers, per game.
        pw = pbp.get(_short_key(player, p["team"]), {})
        rz_key = "i5_car" if share_key == "carries" else "rz_tgt"
        rz_vals = [m.get(rz_key, 0.0) for m in pw.values()]
        out.append({
            "player": player, "team": p["team"], "position": p["position"],
            "metric": "carry share" if share_key == "carries" else "target share",
            "season": round(season_avg, 3),
            "l4": round(l4, 3) if l4 is not None else None,
            "last": round(last, 3) if last is not None else None,
            "delta": round(delta, 3),
            "fp_pg": round(sum(fp) / len(fp), 1),
            "rz_pg": round(sum(rz_vals) / len(rz_vals), 1) if rz_vals else None,
            "rz_label": "i5 car/g" if rz_key == "i5_car" else "RZ tgt/g",
            "weeks": len(weeks),
        })
    # Real usage first, biggest movement on top of it.
    out.sort(key=lambda r: (-abs(r["delta"]), -r["season"]))
    return out[:limit]


def league_rates(conn, season: int,
                 min_rows: int = 50) -> dict[str, tuple[float, float]]:
    """Per-position PPR value of one target and one carry, fit from our own
    season data (least squares on player-weeks). Self-derived — no magic
    constants to go stale."""
    data = _weekly(conn, season)
    by_pos: dict[str, list[tuple[float, float, float]]] = {}
    for p in data["players"].values():
        for wk, m in p["weeks"].items():
            by_pos.setdefault(p["position"], []).append(
                (m.get("targets", 0.0), m.get("carries", 0.0),
                 m.get("fp_ppr", 0.0)))
    rates: dict[str, tuple[float, float]] = {}
    for pos, rows in by_pos.items():
        if len(rows) < min_rows:
            continue
        # Normal equations for fp ≈ a*targets + b*carries (no intercept).
        # Degenerate samples (a position with no carries, or no targets)
        # collapse to the single-regressor fit instead of vanishing.
        stt = sum(t * t for t, c, f in rows)
        scc = sum(c * c for t, c, f in rows)
        stc = sum(t * c for t, c, f in rows)
        stf = sum(t * f for t, c, f in rows)
        scf = sum(c * f for t, c, f in rows)
        if stt < 1e-9 and scc < 1e-9:
            continue
        if stt < 1e-9:
            a, b = 0.0, scf / scc
        elif scc < 1e-9:
            a, b = stf / stt, 0.0
        else:
            det = stt * scc - stc * stc
            if abs(det) < 1e-9:
                continue
            a = (stf * scc - scf * stc) / det
            b = (scf * stt - stf * stc) / det
        rates[pos] = (round(clamp(a, 0.0, 5.0), 3), round(clamp(b, 0.0, 3.0), 3))
    return rates


def buy_sell_board(conn, season: int, limit: int = 12,
                   min_fit_rows: int = 50) -> dict:
    """Rank the gap between volume-expected and actual points per game.

    Positive gap = producing above what the opportunity supports (sell-high
    / regression risk); negative = the usage says production is coming
    (buy-low). Gaps inside the sustainable band are excluded — good players
    legitimately beat volume by ~1.5 PPG, and calling that luck is wrong."""
    data = _weekly(conn, season)
    rates = league_rates(conn, season, min_rows=min_fit_rows)
    pbp = _pbp_weekly(conn, season)
    rows = []
    for player, p in data["players"].items():
        rate = rates.get(p["position"])
        weeks = sorted(p["weeks"])
        if not rate or len(weeks) < USAGE_MIN_WEEKS:
            continue
        n = len(weeks)
        tgt = sum(m.get("targets", 0.0) for m in p["weeks"].values()) / n
        car = sum(m.get("carries", 0.0) for m in p["weeks"].values()) / n
        if tgt + car < 5:                 # bench noise — not a decision anyone faces
            continue
        actual = sum(m.get("fp_ppr", 0.0) for m in p["weeks"].values()) / n
        # Real xFP when play-by-play was ingested: each opportunity valued
        # by WHERE it happened, not just that it happened. Falls back to
        # the flat volume fit otherwise.
        xfp_vals = [m["xfp"] for m in pbp.get(_short_key(player, p["team"]),
                                              {}).values() if "xfp" in m]
        if len(xfp_vals) >= USAGE_MIN_WEEKS:
            expected = sum(xfp_vals) / len(xfp_vals)
            basis = "xfp"
        else:
            expected = rate[0] * tgt + rate[1] * car
            basis = "volume"
        gap = actual - expected
        if abs(gap) <= SUSTAINABLE_PPG:
            continue
        rows.append({"player": player, "team": p["team"],
                     "position": p["position"],
                     "actual_ppg": round(actual, 1),
                     "expected_ppg": round(expected, 1),
                     "gap": round(gap, 1), "basis": basis,
                     "targets_pg": round(tgt, 1), "carries_pg": round(car, 1)})
    rows.sort(key=lambda r: r["gap"])
    return {"buy_low": rows[:limit],
            "sell_high": list(reversed(rows[-limit:])),
            "band": SUSTAINABLE_PPG}


def team_proe(conn) -> dict[str, float]:
    """Season-average pass rate over expectation per team, from the latest
    ingested play-by-play season. Intent, not circumstance — the stable
    half of predicting how a team will actually call the game."""
    row = conn.execute("SELECT MAX(season) FROM team_weeks "
                       "WHERE sport='nfl'").fetchone()
    if not row or row[0] is None:
        return {}
    sums: dict[str, list] = {}
    for r in conn.execute(
            "SELECT team, proe FROM team_weeks WHERE sport='nfl' AND season=? "
            "AND proe IS NOT NULL", (int(row[0]),)):
        s = sums.setdefault(r["team"], [0.0, 0])
        s[0] += float(r["proe"])
        s[1] += 1
    return {t: round(v / n, 4) for t, (v, n) in sums.items() if n >= 4}


def game_scripts(conn) -> list[dict]:
    """Implied team totals + archetype for every NFL game carrying a real
    spread and total, newest season/week first. Confidence scales with the
    spread — a 7+ favorite is a genuine script prediction, a 2-point spread
    is a coin flip and says so."""
    out = []
    proe = team_proe(conn)
    for g in conn.execute(
            "SELECT season, period, home, away, spread, total FROM games "
            "WHERE sport='nfl' AND total IS NOT NULL AND spread IS NOT NULL "
            "AND home_score IS NULL "
            "ORDER BY season DESC, period ASC LIMIT 32"):
        total, spread = float(g["total"]), float(g["spread"])
        if total <= 0:
            continue
        home_imp = total / 2.0 - spread / 2.0     # spread<0 = home favored
        away_imp = total - home_imp
        size = abs(spread)
        conf = ("high — favorites this size win ~79%" if size >= 7
                else "moderate" if size >= 3
                else "coin flip — don't project a script off this")
        key = ("high" if total >= 47 else "low",
               "big" if size >= 6.5 else "close")
        name, desc = SCRIPT_ARCHETYPES[key]
        out.append({
            "season": g["season"], "week": g["period"],
            "home": g["home"], "away": g["away"],
            "total": total, "spread": spread,
            "home_implied": round(home_imp, 1),
            "away_implied": round(away_imp, 1),
            "home_proe": proe.get(g["home"]),
            "away_proe": proe.get(g["away"]),
            "favorite": g["home"] if spread < 0 else g["away"],
            "confidence": conf, "archetype": name, "read": desc,
        })
    return out
