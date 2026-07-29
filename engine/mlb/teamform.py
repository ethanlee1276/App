"""Team form tracking — hot & cold MLB teams from our own ingested results.

Three jobs, in the discipline order the specs demand (docs/MLB_MODEL.md §11 —
track, measure, and only then adjust):

1. TRACK: rolling per-team form over the last N days from the ``games``
   table the nightly ingest already fills — record, run diff vs the team's
   own season baseline, and the current streak.
2. MEASURE: ``audit()`` walks the whole season and asks the only question
   that matters — did the hotter team actually win the next game more often
   than baseline? Streaks are the most public stat in sports, so the
   default assumption is the market prices them; the audit exists to check,
   not to assume in either direction.
3. LEARN FORWARD: the form sampler (engine.ledger.log_form_picks) journals
   the hot side's moneyline at the REAL book price, flat 0.1u, in its own
   quarantined bucket. The Record page grades it like the stale-line
   sampler; the fixed promotion bar (100+ graded, z ≥ 2, positive ROI)
   decides if form ever becomes a recommendation input.

Standard library only; reads the history DB the site already maintains.
"""

from __future__ import annotations

import datetime as _dt


def _mlb_games(hist_conn):
    """Every scored MLB game, date-ordered: (date, home, away, hs, as)."""
    return hist_conn.execute(
        "SELECT period AS date, home, away, home_score, away_score "
        "FROM games WHERE sport='mlb' AND home_score IS NOT NULL "
        "AND away_score IS NOT NULL AND period IS NOT NULL "
        "ORDER BY period").fetchall()


def team_form(hist_conn, on_date: str, window_days: int = 7,
              min_games: int = 3, _rows=None) -> dict[str, dict]:
    """{team: form} strictly BEFORE ``on_date`` — never leaks the day's own
    result into the day's form.

    ``delta_diff`` is the headline number: run differential per game over
    the window minus the team's season run differential per game. A +2.1
    means the team has been two runs a game better than its own normal —
    "hot" relative to itself, not to the league.
    """
    cutoff = (_dt.date.fromisoformat(on_date)
              - _dt.timedelta(days=window_days)).isoformat()
    season: dict[str, list] = {}     # team -> [w, l, rd_sum, n]
    window: dict[str, list] = {}
    streaks: dict[str, list] = {}    # team -> ordered W/L chars
    for g in (_rows if _rows is not None else _mlb_games(hist_conn)):
        if g["date"] >= on_date:
            break
        for team, mine, theirs in ((g["home"], g["home_score"], g["away_score"]),
                                   (g["away"], g["away_score"], g["home_score"])):
            won = mine > theirs
            s = season.setdefault(team, [0, 0, 0.0, 0])
            s[0 if won else 1] += 1
            s[2] += float(mine) - float(theirs)
            s[3] += 1
            streaks.setdefault(team, []).append("W" if won else "L")
            if g["date"] >= cutoff:
                w = window.setdefault(team, [0, 0, 0.0, 0])
                w[0 if won else 1] += 1
                w[2] += float(mine) - float(theirs)
                w[3] += 1

    out: dict[str, dict] = {}
    for team, (w, l, rd, n) in window.items():
        s = season.get(team)
        if n < min_games or not s or not s[3]:
            continue
        season_diff = s[2] / s[3]
        run = streaks.get(team) or []
        streak, ch = 0, (run[-1] if run else "")
        for c in reversed(run):
            if c != ch:
                break
            streak += 1
        out[team] = {
            "w": w, "l": l, "games": n,
            "diff_pg": round(rd / n, 2),
            "season_diff_pg": round(season_diff, 2),
            "delta_diff": round(rd / n - season_diff, 2),
            "streak": (streak if ch == "W" else -streak),
        }
    return out


def form_score(f: dict) -> float:
    """One number for "how hot": window win% above .500 plus the run-diff
    delta (runs carry the information; win% carries the narrative)."""
    n = max(1, f["games"])
    return round((f["w"] / n - 0.5) * 2.0 + f["delta_diff"] / 3.0, 3)


def hot_cold(form: dict[str, dict], top: int = 6) -> tuple[list, list]:
    """(hot, cold) team lists, strongest first, each row site-ready."""
    rows = [{"team": t, "score": form_score(f), **f} for t, f in form.items()]
    rows.sort(key=lambda r: -r["score"])
    hot = [r for r in rows[:top] if r["score"] > 0]
    cold = [r for r in rows[::-1][:top] if r["score"] < 0]
    return hot, cold


# A matchup only enters the audit/sampler when the form gap is real.
FORM_GAP_BAR = 0.60


def audit(hist_conn, window_days: int = 7, min_games: int = 4) -> dict:
    """Did the hotter team win the NEXT game more often than the base rate?

    Walks every scored game in the DB; for each one where both teams have a
    windowed sample and the form gap clears the bar, records whether the
    hotter side won. Baseline is 50% (form gap ignores venue on purpose —
    a raw predictiveness check, not a price check). IMPORTANT caveat,
    printed with the verdict: winning more than 50% is NOT the same as
    beating the moneyline PRICE on hot teams — the forward sampler, which
    journals real prices, is the only judge of that.
    """
    import math
    rows = _mlb_games(hist_conn)
    by_date: dict[str, list] = {}
    for g in rows:
        by_date.setdefault(g["date"], []).append(g)

    n = hot_wins = 0
    for date in sorted(by_date):
        form = team_form(hist_conn, date, window_days, min_games, _rows=rows)
        for g in by_date[date]:
            fh, fa = form.get(g["home"]), form.get(g["away"])
            if not fh or not fa:
                continue
            sh, sa = form_score(fh), form_score(fa)
            if abs(sh - sa) < FORM_GAP_BAR:
                continue
            hot_home = sh > sa
            hot_won = (g["home_score"] > g["away_score"]) == hot_home
            n += 1
            hot_wins += 1 if hot_won else 0

    if not n:
        return {"n": 0, "verdict": "not enough scored games in the DB yet — "
                                   "accrues nightly from the results ingest"}
    rate = hot_wins / n
    z = (hot_wins - n * 0.5) / math.sqrt(n * 0.25)
    if n < 60 or abs(z) < 2:
        verdict = (f"no measurable form edge yet ({rate:.1%} over {n} "
                   f"matchups, z {z:+.2f}) — streaks look priced in; the "
                   f"sampler keeps testing at real prices")
    elif z >= 2:
        verdict = (f"hot teams DID win more ({rate:.1%} over {n}, z {z:+.2f}) "
                   f"— but only the sampler's record at real prices can say "
                   f"whether the market underpays them")
    else:
        verdict = (f"hot teams actually UNDERperformed ({rate:.1%} over {n}, "
                   f"z {z:+.2f}) — a fade signal worth watching, same bar")
    return {"n": n, "hot_win_rate": round(rate, 4), "z": round(z, 2),
            "window_days": window_days, "verdict": verdict}
