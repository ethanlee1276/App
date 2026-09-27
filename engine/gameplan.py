"""The game plan: one game read the way a bettor reads it, in order.

Ethan, 2026-09-27, with two more of the other AI's reports (Jets @ Lions,
Chargers @ Bills): "I'm trying to get you to focus on the way the ai
thinks and finds its bets and its thought process and the steps it goes
through … this is the way we need to be thinking on the site."

The steps it goes through, every game, in the same order:

  1. THE LINE AND THE SCRIPT. Spread, total, implied points; who is
     expected to lead and run, who is expected to trail and throw.
  2. WHO IS OUT, AND WHERE THE WORK GOES. Each absence as targets or
     carries to share out, and the men it lifts.
  3. THE MATCHUP. The units that decide it, the soft spot in coverage,
     the pass rush, the scheme.
  4. PLAYS THAT FIT. Volume first — catches and touchdowns are bets on
     a role, yardage is a bet on a role AND a big play — then yardage,
     each with the reason the script and the matchup give it.
  5. PLAYS TO AVOID. The popular side that fights the defence's
     strength, the number chasing last week, the yardage market our
     own record says we cannot price.
  6. WHAT CHANGES THE READ. The questionable players whose call moves
     our numbers, the weather when it is not in yet.
  7. WHERE WE DISAGREE WITH THE MARKET. The other AI's strongest calls
     are the ones furthest from the books (Sadiq 2.5+ catches, Hampton
     2+ catches); ours refuses anything past MAX_CREDIBLE_EDGE as our
     own error. Both cannot be right. These rows are named here, never
     staked, and journaled on paper under ``plan_gap`` so the record —
     not an argument — says whether big disagreements pay.

Nothing here moves a number. Every line is built from what the build
already measured: the game script (engine/gamescript), the matchup scan
and its reads (engine/gamescan), the projections and their reasons
(engine/projection, engine/betting), the one Most Likely board
(engine/likelyboard). The plan is the order those are read in, and the
sentence each step produces — which is the part the site never said.

Standard library only.
"""
from __future__ import annotations

from .betting import (IMPLAUSIBLE_EDGE_REASON, MAX_CREDIBLE_EDGE,
                      MODEL_OFF_MARKET_REASON, UNRELIABLE_CALIBRATION_REASON)

#: Our chance on a side before it is a play that fits.
FIT_MIN_PROB = 0.55
#: Plays that fit, per game; volume markets are listed before yardage.
FIT_PER_GAME = 6
#: The volume markets: bets on a role, not on a big play.
VOLUME_MARKETS = ("receptions", "anytime_td", "pass_td", "pass_att", "pass_cmp", "rush_att")
#: Yardage markets the record says the model orders no better than a coin
#: (calibrate.SHUT_MARKETS names them for the Edge board): a play here is
#: shown as the read's, never as a number the model vouches for.
YARDAGE_MARKETS = ("rec_yds", "rush_yds", "pass_yds")
#: A last-3 swing this far above form, in the market's own units, reads as
#: chasing last week (receptions / yards).
CHASE_RECEPTIONS = 1.5
CHASE_YARDS = 25.0
#: Raw disagreement with the market past this is a `plan_gap` row.
GAP_MIN = MAX_CREDIBLE_EDGE
#: The heaviest price a plan row is quoted at.
MAX_JUICE = -250
#: "Who scores": the scorers per game, likeliest first — the other model's
#: six-candidate table (Ethan, 2026-09-27).
WHO_SCORES = 6
#: The Most Likely board's heaviest price (likely.HEAVIEST_PRICE) and its
#: floor (likely.MIN_PROB), said on a scorer the board does not carry.
from .likely import HEAVIEST_PRICE as _CAP, MIN_PROB as _FLOOR   # noqa: E402

#: A questionable player whose absence moves a projection this much is
#: a pregame watch item.
WATCH_MOVE = 0.08

_MARKET_WORD = {"receptions": "catches", "rec_yds": "receiving yards", "rush_yds": "rushing yards",
                "pass_yds": "passing yards", "pass_td": "passing touchdowns", "anytime_td": "a touchdown",
                "pass_att": "pass attempts", "pass_cmp": "completions", "rush_att": "carries"}

REFUSALS = (IMPLAUSIBLE_EDGE_REASON, UNRELIABLE_CALIBRATION_REASON,
            MODEL_OFF_MARKET_REASON.split(" (")[0])


def _key(g) -> str:
    return f"{g.get('away')}@{g.get('home')}"


def _refused(r: dict) -> str:
    for why in r.get("reasons") or []:
        s = str(why)
        if s.startswith(REFUSALS[2]) or s in REFUSALS[:2]:
            return s
    return ""


def _ord(n) -> str:
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _juice_ok(odds) -> bool:
    try:
        return odds is not None and float(odds) >= MAX_JUICE
    except (TypeError, ValueError):
        return False


# ═══ 1. THE LINE AND THE SCRIPT ═══════════════════════════════════════════

def script_lines(g: dict) -> tuple[dict, list]:
    """The game script from the posted number, and the sentences it gives
    the plan: who leads and runs, who trails and throws."""
    from .gamescript import describe, for_team
    home, away = g.get("home"), g.get("away")
    d = describe(g.get("spread"), g.get("total"), home, away)
    if not d:
        return {}, ["No posted line yet — the script is unread until there is one."]
    fav = d.get("favorite")
    lines = []
    if fav:
        dog = away if fav == home else home
        size = abs(float(d["spread"]))
        lines.append(f"{fav} by {size:g} at {float(d['total']):g}: the lines expect {fav} to score about "
                     f"{d['home_implied'] if fav == home else d['away_implied']:g}, {dog} about "
                     f"{d['away_implied'] if fav == home else d['home_implied']:g} ({d['confidence']}).")
        ft, dt = for_team(g["spread"], g["total"], home, away, fav), for_team(g["spread"], g["total"], home, away, dog)
        if ft and dt:
            lines.append(f"{fav} {ft['lean']}; {dog} {dt['lean']}.")
    else:
        lines.append(f"Pick'em at {float(d['total']):g}: the number says nothing about who leads — "
                     f"both offences stay in it, volume props over script props.")
    return d, lines


# ═══ 2. WHO IS OUT ═══════════════════════════════════════════════════════

def absences(scan: dict) -> list:
    """[{player, team, position, status, opens}] — the ruled-out first,
    the questionable after, each with what it opens."""
    rows = [dict(i) for i in (scan.get("injuries") or []) if isinstance(i, dict) and i.get("opens")]
    rows.sort(key=lambda i: (str(i.get("status", "")).upper() == "QUESTIONABLE", i.get("team") or ""))
    return [{k: i.get(k) for k in ("player", "team", "position", "status", "opens", "headshot")} for i in rows]


# ═══ 3. THE MATCHUP ══════════════════════════════════════════════════════

def matchup_lines(scan: dict, home: str, away: str) -> list:
    """The units that decide it, the soft spot, the rush — from the scan."""
    out = []
    n = int((scan.get("method") or {}).get("teams") or 32)
    for e in (scan.get("edges") or [])[:3]:
        if not isinstance(e, dict):
            continue
        better = e.get("off") if (e.get("gap") or 0) > 0 else e.get("def")
        out.append(f"{e.get('off')}'s {e.get('unit')} offence ({_ord(e.get('off_rank') or 0)} of {n}) against "
                   f"{e.get('def')}'s {e.get('unit')} defence ({_ord(e.get('def_rank') or 0)}) — edge {better}.")
    for team in (away, home):
        room = (scan.get("coverage") or {}).get(team) or {}
        soft = room.get("weakest")
        if soft:
            c = next((x for x in room.get("corners") or [] if x.get("name") == soft), None)
            if c and c.get("rating") is not None:
                out.append(f"{team}'s soft spot: {soft} ({c.get('spot')}) has allowed a {c['rating']:.0f} passer "
                           f"rating on {c.get('targets')} targets.")
        for m in room.get("missing") or []:
            out.append(f"{team}'s starting {m.get('spot')} {m.get('name')} is {str(m.get('status', '')).lower()} — "
                       f"the next man up is the one to throw at.")
        sch = (scan.get("scheme") or {}).get(team)
        if isinstance(sch, dict) and sch.get("zone") is not None:
            look = "zone" if (sch.get("zone") or 0) >= 0.65 else "man" if (sch.get("man") or 0) >= 0.35 else ""
            if look:
                out.append(f"{team} plays {look} {sch[look]:.0%} of the time"
                           + (f", blitzes {sch['blitz']:.0%}" if sch.get("blitz") is not None else "") + ".")
        rush = [d for d in (scan.get("rush") or {}).get(team) or [] if isinstance(d, dict)]
        if rush and (rush[0].get("pressures") or 0) >= 8:
            out.append(f"{team}'s rush runs through {rush[0]['name']} ({rush[0]['pressures']} pressures, "
                       f"{rush[0].get('sacks') or 0:g} sacks).")
    return out


# ═══ 4. PLAYS THAT FIT / 5. PLAYS TO AVOID / 7. THE GAP ═════════════════

def _in_game(r: dict, g: dict) -> bool:
    pair = {g.get("home"), g.get("away")}
    return (isinstance(r, dict) and r.get("team") in pair and r.get("opponent") in pair
            and r.get("team") != r.get("opponent") and not r.get("live") and not r.get("started"))


def _fit_reason(r: dict) -> list:
    """Why this play fits: the read's own lines, the script, and whether
    it is a bet on a role or on a big play."""
    why = list(r.get("matchup_lines") or [])[:2]
    gs = r.get("game_script") or {}
    if isinstance(gs, dict) and gs.get("lean"):
        why.append(f"Script: {gs['lean']}.")
    if r.get("market") in VOLUME_MARKETS:
        why.append("A volume market — a bet on his role, not on a big play.")
    elif r.get("market") in YARDAGE_MARKETS:
        why.append("Yardage — a bet on his role AND a big play; the catches or the score is the steadier way in.")
    return why[:4]


def sort_plays(rows: list) -> list:
    """Volume markets first, then yardage; within each by our chance."""
    return sorted(rows, key=lambda r: (r["market"] not in VOLUME_MARKETS, -(r.get("model_prob") or 0)))


def fits(g: dict, matchup: dict | None, props: list, board_rows: list) -> list:
    """PLAYS THAT FIT: this game's matchup picks (engine/matchpicks — the
    read's side where our number agrees at 55% or better, at a real
    price), volume first, each saying whether the one Most Likely board
    carries it and at which tier."""
    key = _key(g)
    on_board = {(r.get("player"), r.get("market"), str(r.get("side") or "").lower()): r
                for r in board_rows or [] if r.get("game") == key}
    by_rec = {(r.get("player"), r.get("market")): r for r in props or [] if _in_game(r, g)}
    out = []
    for r in ((matchup or {}).get("td") or []) + ((matchup or {}).get("props") or []):
        if not isinstance(r, dict) or r.get("model_prob") is None or float(r["model_prob"]) < FIT_MIN_PROB:
            continue
        rec = by_rec.get((r.get("player"), r.get("market"))) or {}
        b = on_board.get((r.get("player"), r.get("market"), str(r.get("side") or "").lower()))
        out.append({**{k: r.get(k) for k in ("kind", "player", "team", "opponent", "position", "headshot",
                                               "market", "market_label", "side", "line", "odds", "book",
                                               "model_prob", "projection", "read", "label")},
                    "game": key, "why": _fit_reason(dict(r, game_script=rec.get("game_script"))),
                    "on_board": bool(b), "tier": (b or {}).get("tier"), "tier_label": (b or {}).get("tier_label"),
                    "volume": r.get("market") in VOLUME_MARKETS})
    return sort_plays(out)[:FIT_PER_GAME]


def avoids(g: dict, reads: list, props: list) -> list:
    """PLAYS TO AVOID: the over on a player whose read says he could
    struggle (the popular side fights the defence), and the over on a
    number that has chased his last three games up."""
    from .matchpicks import _side_price
    by_read = {(x.get("team"), x.get("player")): x for x in reads or []}
    out = []
    for r in props or []:
        if not _in_game(r, g) or r.get("hit_prob") is None or r.get("line") is None:
            continue
        market = r.get("market") or ""
        if market == "anytime_td":
            continue
        read = by_read.get((r.get("team"), r.get("player"))) or {}
        hp = float(r["hit_prob"])
        p_over = hp if str(r.get("side") or "").upper() == "OVER" else 1.0 - hp
        why = ""
        if read.get("read") in ("tough", "avoid") and market in (read.get("lean") or []):
            con = (read.get("con") or [""])[0]
            why = f"The over fights the matchup — {con.rstrip('.') if con else 'the read says he could struggle'}."
        else:
            td = r.get("trend_delta")
            chase = CHASE_RECEPTIONS if market in ("receptions", "pass_td") else CHASE_YARDS
            if td is not None and float(td) >= chase:
                why = (f"Chasing last week — his last three sit {float(td):+g} {_MARKET_WORD.get(market, market)} "
                       f"above his form, and the number is priced off them.")
        if not why:
            continue
        odds, book = _side_price(r, "over")
        out.append({"kind": "prop", "player": r.get("player"), "team": r.get("team"), "opponent": r.get("opponent"),
                    "position": r.get("position"), "headshot": r.get("headshot"), "market": market,
                    "market_label": r.get("market_label") or market, "side": "OVER", "line": r.get("line"),
                    "odds": odds or r.get("odds"), "book": book or r.get("book"), "model_prob": round(p_over, 4),
                    "projection": r.get("projection"), "game": _key(g), "read": read.get("read"), "why": why})
    out.sort(key=lambda r: (r["market"] not in VOLUME_MARKETS, r["model_prob"]))
    return out[:4]


def gaps(g: dict, props: list) -> list:
    """WHERE WE DISAGREE WITH THE MARKET: rows our raw number puts more
    than GAP_MIN from the market's — named, never staked, on paper."""
    out = []
    for r in props or []:
        if not _in_game(r, g):
            continue
        raw, fair, side = r.get("raw_prob"), r.get("fair_prob"), str(r.get("side") or "").upper()
        if raw is None or fair is None or side not in ("OVER", "UNDER", "YES") or not _juice_ok(r.get("odds")):
            continue
        gap = float(raw) - float(fair)
        if abs(gap) <= GAP_MIN:
            continue
        from .boldcheck import check as _check
        try:
            v = _check(r, side, r.get("line"), r.get("hit_prob"), fair, raw) or {}
        except Exception:                                    # noqa: BLE001
            v = {}
        out.append({"kind": "prop", "player": r.get("player"), "team": r.get("team"), "opponent": r.get("opponent"),
                    "position": r.get("position"), "headshot": r.get("headshot"), "market": r.get("market"),
                    "market_label": r.get("market_label") or r.get("market"), "side": side, "line": r.get("line"),
                    # The pill shows the RAW chance — the claim on paper.
                    "odds": r.get("odds"), "book": r.get("book"), "model_prob": round(float(raw), 4),
                    "shown_prob": round(float(r.get("hit_prob") or raw), 4), "raw_prob": round(float(raw), 4), "fair_prob": round(float(fair), 4), "gap": round(gap, 4),
                    "projection": r.get("projection"), "game": _key(g),
                    "verdict": v.get("verdict") or "unexplained", "verdict_label": v.get("label") or "",
                    "why": (f"Our raw number says {float(raw):.0%} on the {side.lower()}; the market says "
                            f"{float(fair):.0%}. "
                            + (f"{v['label']} — {' '.join(v.get('why') or [])} "
                               if v.get("label") else "")
                            + ("Shown on Most Likely; the site stakes nothing on it and grades it on paper."
                               if v.get("verdict") == "found" else
                               "Kept off the board; the site stakes nothing and grades it on paper so the "
                               "record can say whether it was."))})
    out.sort(key=lambda r: -abs(r["gap"]))
    return out[:4]


# ═══ WHO SCORES ══════════════════════════════════════════════════════════

def who_scores(g: dict, field: list, board_rows: list, matchup: dict | None) -> list:
    """Every quoted scorer in the game, likeliest first, WHO_SCORES of
    them: our chance, his goal-line work, and his seat — on the Most
    Likely board (its tier), or why not (the price past the board's cap:
    "likely, priced out"; under the floor: "a real chance, not a likely
    one"). Ethan's other model's Gibbs, 2026-09-27: "the most likely TD
    on the board — but the price kills it"."""
    key = _key(g)
    on_board = {r.get("player"): r for r in board_rows or []
                if r.get("game") == key and r.get("market") == "anytime_td"}
    matched = {r.get("player"): r for r in (matchup or {}).get("td") or []}
    rows = [r for r in field or [] if isinstance(r, dict) and _in_game(r, g)
            and r.get("model_prob") is not None and not str(r.get("injury_status") or "").strip()]
    rows.sort(key=lambda r: -float(r["model_prob"]))
    out = []
    for r in rows[:WHO_SCORES]:
        p = float(r["model_prob"])
        b = on_board.get(r.get("player"))
        try:
            odds = int(r.get("odds") or 0)
        except (TypeError, ValueError):
            odds = 0
        if b:
            seat = f"On the Most Likely board — {b.get('tier_label') or 'posted'}."
        elif odds and odds < _CAP:
            seat = (f"Likely — but {odds:+d} is past the board's {_CAP} cap, so it is priced out, "
                    f"not doubted.")
        elif p < _FLOOR:
            seat = f"A real chance, not a likely one — under the board's {_FLOOR:.0%} bar."
        else:
            seat = "Clears the bar; the board's seats went to likelier picks."
        why = [x for x in (r.get("goal_line_text"),) if x]
        m = matched.get(r.get("player"))
        if m:
            why += [x for x in (m.get("matchup_lines") or []) if x and x != r.get("goal_line_text")][:2]
        elif r.get("implied_total") is not None:
            why.append(f"{r.get('team')} expected to score {float(r['implied_total']):.1f} by the lines")
        why.append(seat)
        out.append({"kind": "td", "player": r.get("player"), "team": r.get("team"),
                    "opponent": r.get("opponent"), "position": r.get("position"), "headshot": r.get("headshot"),
                    "market": "anytime_td", "market_label": "Anytime TD", "side": "YES", "line": 0.5,
                    "odds": r.get("odds"), "book": r.get("book"), "model_prob": round(p, 4),
                    "game": key, "goal_line": r.get("goal_line"), "on_board": bool(b),
                    "tier": (b or {}).get("tier"), "tier_label": (b or {}).get("tier_label"), "why": why})
    return out


# ═══ 6. WHAT CHANGES THE READ ════════════════════════════════════════════

def watch_items(g: dict, scan: dict, props: list) -> list:
    """The questionable players whose call moves our numbers, and the
    weather when the forecast is not in."""
    out = []
    maybe = [i for i in scan.get("injuries") or []
             if isinstance(i, dict) and str(i.get("status", "")).upper() in ("QUESTIONABLE", "GTD")]
    for i in maybe:
        moves = []
        for r in props or []:
            if not _in_game(r, g) or r.get("team") != i.get("team"):
                continue
            sits = (r.get("mate_card") or {}).get("if_sits") or {}
            if not any(str(o).lower() == str(i.get("player")).lower() for o in sits.get("who") or []):
                continue
            base = float((r.get("mate_card") or {}).get("applied") or 1.0)
            d = float(sits.get("mult") or 1.0) / base - 1.0
            if abs(d) >= WATCH_MOVE:
                moves.append(f"{r.get('player')} {d:+.0%} {_MARKET_WORD.get(r.get('market'), r.get('market'))}")
        # Only a call that moves a number is a watch item; the rest
        # already sit under "who is out".
        if moves:
            out.append({"player": i.get("player"), "team": i.get("team"), "position": i.get("position"),
                        "status": i.get("status"), "headshot": i.get("headshot"),
                        "text": f"If he sits: {', '.join(sorted(set(moves)))}."})
    w = g.get("weather") if isinstance(g.get("weather"), dict) else {}
    if w and not w.get("dome") and w.get("forecast") is False and str(g.get("roof") or "outdoors") in ("outdoors", "open"):
        out.append({"player": "", "team": "", "status": "weather",
                    "text": "Outdoors and no game-time forecast pulled yet — wind past 15 mph would lower the passing numbers."})
    elif w and (w.get("wind_mph") or 0) >= 15 and not w.get("dome"):
        out.append({"player": "", "team": "", "status": "weather",
                    "text": f"Wind {w['wind_mph']:.0f} mph at kickoff — already in the passing numbers."})
    return out


# ═══ THE PLAN ════════════════════════════════════════════════════════════

def yardage_note(sport: str = "nfl") -> str:
    """What the record says about yardage markets, from the calibration
    that shut them (calibrate.SHUT_MARKETS) — said once on the plan."""
    try:
        from .calibrate import SHUT_MARKETS
    except Exception:                                        # noqa: BLE001
        return ""
    shut = sorted(m for (s, m) in SHUT_MARKETS if s == sport and m in YARDAGE_MARKETS)
    if not shut:
        return ""
    words = " and ".join(_MARKET_WORD.get(m, m) for m in shut)
    return (f"{words[0].upper() + words[1:]} are read-only on this site: against real closing lines the model "
            f"orders them no better than a coin, so a yardage play here is the read's, not a number we vouch for. "
            f"Catches and touchdowns are where the number counts.")


def plan_for(g: dict, reads: dict, props: list, board_rows: list, matchup: dict | None,
             sport: str = "nfl", field: list | None = None) -> dict | None:
    scan = g.get("scan") if isinstance(g.get("scan"), dict) else None
    if not scan:
        return None
    script, s_lines = script_lines(g)
    players = (reads or {}).get("players") or []
    fit_rows = fits(g, matchup, props, board_rows)
    out = {"game": _key(g), "home": g.get("home"), "away": g.get("away"),
           "date": g.get("date"), "kickoff": g.get("kickoff"),
           "script": {k: script.get(k) for k in ("archetype", "read", "favorite", "confidence",
                                                  "home_implied", "away_implied", "spread", "total")} if script else {},
           "steps": [
               {"key": "line", "title": "The line and the script", "lines": s_lines},
               {"key": "out", "title": "Who is out, and where the work goes", "rows": absences(scan)},
               {"key": "matchup", "title": "The matchup", "lines": matchup_lines(scan, g.get("home"), g.get("away"))},
               {"key": "who", "title": "Who scores", "rows": who_scores(g, field, board_rows, matchup)},
               {"key": "fits", "title": "Plays that fit", "rows": fit_rows,
                "note": yardage_note(sport) if any(not r["volume"] for r in fit_rows) else ""},
               {"key": "avoid", "title": "Plays to avoid", "rows": avoids(g, players, props)},
               {"key": "watch", "title": "What changes the read", "rows": watch_items(g, scan, props)},
               {"key": "gap", "title": "Where we disagree with the market", "rows": gaps(g, props)},
           ]}
    return out


def build(result: dict, sport: str = "nfl") -> list:
    """A plan for every game with a scan, in the board's game order."""
    reads_all = result.get("scan_reads") or {}
    props = result.get("recommendations") or []
    board = ((result.get("likely_board") or {}).get("rows")) or []
    matchups = {m.get("game"): m for m in result.get("matchup_picks") or [] if isinstance(m, dict)}
    out = []
    for g in result.get("games") or []:
        if not isinstance(g, dict):
            continue
        p = plan_for(g, reads_all.get(_key(g)) or {}, props, board, matchups.get(_key(g)), sport,
                     field=result.get("td_field") or result.get("longshot_watch") or [])
        if p:
            out.append(p)
    return out


def attach(result: dict, sport: str = "nfl") -> str:
    """``result["game_plans"]`` and the line for the build log. Never
    raises — a plan that fails leaves the page on the scan alone."""
    try:
        plans = build(result, sport)
        result["game_plans"] = plans
        n_fit = sum(len(next(s for s in p["steps"] if s["key"] == "fits")["rows"]) for p in plans)
        n_gap = sum(len(next(s for s in p["steps"] if s["key"] == "gap")["rows"]) for p in plans)
        return f"Game plans: {len(plans)} game(s), {n_fit} play(s) that fit, {n_gap} market gap(s) on paper"
    except Exception as exc:                                 # noqa: BLE001
        return f"⚠️  game plans skipped: {exc}"


def journal_rows(plans: list) -> list:
    """The gap rows of every plan, flat, for the ledger's paper book —
    `model_prob` is our RAW chance, the claim being tested."""
    rows = []
    for p in plans or []:
        for s in p.get("steps") or []:
            if s.get("key") != "gap":
                continue
            for r in s.get("rows") or []:
                rows.append(dict(r, model_prob=r.get("raw_prob"), kind="prop"))
    return rows


def _main(argv: list) -> int:
    """``python3 -m engine.gameplan nfl LAC@BUF`` — one game's plan from
    the box's own built board (gate.full_board), read-only."""
    import json
    from .gate import full_board
    sport = argv[0] if argv else "nfl"
    want = argv[1].upper() if len(argv) > 1 else ""
    board = full_board(f"{sport}.json") or full_board("recommendations.json" if sport == "nfl" else f"{sport}.json")
    if not board:
        print(f"No built {sport} board to read.")
        return 1
    plans = board.get("game_plans") or build(board, sport)
    for p in plans:
        if want and p.get("game", "").upper() != want:
            continue
        print(f"\n== {p['game']}  {p.get('date') or ''} {p.get('kickoff') or ''}  {(p.get('script') or {}).get('archetype') or ''}")
        for s in p.get("steps") or []:
            print(f"-- {s['title']}")
            for t in s.get("lines") or []:
                print(f"   {t}")
            for r in s.get("rows") or []:
                if r.get("market"):
                    why = r.get("why")
                    print(f"   {r.get('player')} {r.get('side')} {r.get('line')} {r.get('market_label') or r.get('market')} "
                          f"{r.get('odds')} {r.get('book') or ''} · {float(r.get('model_prob') or 0):.0%}"
                          + (f" · {r.get('tier_label')}" if r.get("tier_label") else ""))
                    for w in ([why] if isinstance(why, str) else why or []):
                        print(f"      · {w}")
                else:
                    print(f"   {r.get('player') or 'Weather'} {str(r.get('status') or '').lower()}: {r.get('opens') or r.get('text') or ''}")
            if s.get("note"):
                print(f"   ({s['note']})")
    if not plans:
        print(json.dumps({"games": len(board.get("games") or []), "plans": 0}))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
