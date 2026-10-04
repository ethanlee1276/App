"""Does every input the models read actually move a number on the live board?

Ethan, 2026-09-23: "do another scan and make sure all the models aren't
being affected by issues where data isn't being used or being pulled or
whatever … we don't want to have any mistakes with our models."

engine/datause asks whether a signal is MENTIONED where it would be read,
and says itself that mention is not production. This asks the published
board: every prop row carries its chain (engine/chain — base × the named
steps that made the projection), so for each league and market it counts
the rows each step actually moved. An input wired in and silently empty
shows up as a step that moved nothing on hundreds of rows — the class of
the NFL's own findings the same day:

  * every receiver carried the role "wr1", so the slot-corner injury rule
    could never fire (a ROLE with one value for a whole position);
  * the odds pull bought markets no position was built for (a market
    PRICED BY PROXY on every row would be the mirror image);
  * passing touchdowns had no matchup at all (a STEP that never moves).

Read-only. `python3 homecheck.py inputs` runs it on the droplet.
"""
from __future__ import annotations

from collections import defaultdict

from .chain import FLAT, STEP_LABELS

#: Steps that are flat on purpose, and why. A dead step not listed here is
#: a finding.
OFF_BY_DESIGN = {
    "trend": "recent form is noted on the card and never applied: shading for it measured worse",
    "context": "team tendency (engine/teamcontext) is not switched on in the builds",
}
#: Steps flat on ONE market for a known reason: printed as known, not flagged.
KNOWN = {
    ("nfl", "pass_td"): {
        "matchup": "measured 2026-09-23: no defence rating predicted passing TDs (engine/defensevs); "
                   "the card shows it, the number does not use it",
        "weather": "the weather model (engine/weather) has no passing-TD coefficient — not yet measured",
    },
    # Flat BY CONSTRUCTION — each of these factors is built without a
    # coefficient for the market, so "moved none" is the code doing what
    # it says. Found on Ethan's box run, 2026-09-24, where they sat under
    # LOOK AT THESE beside the ones that do need a person.
    ("nfl", "rush_yds"): {
        "weather": "wind and rain are measured against passing and receiving only "
                   "(engine/weather.WIND_FORECAST); rushing has no coefficient",
    },
    ("mlb", "hits"): {
        "weather": "the MLB weather table (engine/mlb/weather) moves home runs, total bases "
                   "and strikeouts only",
    },
    ("mlb", "home_runs"): {
        "ump": "the plate umpire moves strikeouts, outs, hits and total bases "
               "(engine/mlb/projection) — never home runs",
    },
    ("mlb", "outs"): {
        "park": "the park table (engine/mlb/parks) carries no outs factor",
        "weather": "the MLB weather table carries no outs factor",
        "statcast": "contact quality has hitter and strikeout branches only (engine/mlb/statcast)",
    },
}


def _memory_on(sport: str, market: str) -> bool:
    """Is per-player memory ADOPTED for this market on this box?
    (engine/playerfit): a market whose memory the record has not earned
    serves 1.0 for everyone, so "moved none" is the fit saying no, not a
    wire that came loose. Unknown answers True, so a broken store is still
    asked about."""
    try:
        from .playerfit import _load
        d = _load().get(f"{sport}:{market}")
    except Exception:                                        # noqa: BLE001
        return True
    return bool(isinstance(d, dict) and d.get("adopted"))
#: Steps that only speak when something happens: flat on a quiet night is
#: normal, so these are reported, never flagged.
SITUATIONAL = {"injury", "cap", "rare", "learned", "lineup"}
#: Fewest rows of a market before "moved nothing" means anything.
MIN_ROWS = 20
#: Positions whose role should say where he ranks (sources/nflverse.role_for).
RANKED = {"WR", "RB"}


def census(rows: list[dict]) -> dict:
    """{market: {"n", "moved": {step: rows it moved}, "seen": {step: rows carrying it},
    "priced", "roles": {position: set}, "cards"}}"""
    out: dict = {}
    for r in rows:
        m = str(r.get("market") or "")
        if not m:
            continue
        c = out.setdefault(m, {"n": 0, "moved": defaultdict(int), "seen": defaultdict(int), "priced": 0,
                               "roles": defaultdict(set), "cards": 0})
        c["n"] += 1
        for s in ((r.get("chain") or {}).get("steps") or []):
            k = s.get("key")
            if not k:
                continue
            c["seen"][k] += 1
            try:
                if abs(float(s.get("mult", 1.0)) - 1.0) >= FLAT:
                    c["moved"][k] += 1
            except (TypeError, ValueError):
                pass
        if r.get("has_market") or str(r.get("book") or "").lower() not in ("", "proxy"):
            c["priced"] += 1
        pos = str(r.get("position") or "").upper()
        if pos:
            c["roles"][pos].add(str(r.get("usage_role") or ""))
        if r.get("matchup_card"):
            c["cards"] += 1
    return out


def findings(sport: str, cen: dict) -> list[str]:
    """The lines that need a person: dead steps, unpriced markets, one-value roles."""
    out = []
    for m, c in sorted(cen.items()):
        if c["n"] < MIN_ROWS:
            continue
        for k, seen in sorted(c["seen"].items()):
            if c["moved"].get(k) or k in OFF_BY_DESIGN or k in SITUATIONAL or seen < MIN_ROWS:
                continue
            if k in KNOWN.get((sport, m), {}):
                continue
            if k == "player" and not _memory_on(sport, m):
                continue
            out.append(f"{sport} {m}: '{STEP_LABELS.get(k, k)}' moved none of {seen} rows — "
                       f"wired in and reading nothing?")
        if c["priced"] == 0:
            out.append(f"{sport} {m}: no row has a real book price ({c['n']} rows, all proxy)")
        for pos, roles in sorted(c["roles"].items()):
            if pos in RANKED and len(roles) == 1 and sport in ("nfl",):
                out.append(f"{sport} {m}: every {pos} carries the role {next(iter(roles))!r} — "
                           f"the depth order is not reaching the model")
    return out


def report(boards: dict) -> list[str]:
    """``boards`` is {sport: board dict}. Returns printable lines."""
    lines = ["INPUTS — does every input the models read move a number on the live board",
             f"  share of rows each step moved (flat = within {FLAT:g}); OFF = off by design"]
    flagged: list[str] = []
    for sport, board in boards.items():
        if not isinstance(board, dict):
            lines.append(f"  {sport}: {board}")
            continue
        rows = board.get("recommendations") or []
        cen = census(rows)
        if not cen:
            lines.append(f"  {sport}: no prop rows on the board")
            continue
        lines.append(f"  {sport}: {len(rows)} rows")
        for m, c in sorted(cen.items()):
            bits = []
            for k in sorted(c["seen"]):
                share = c["moved"].get(k, 0) / c["n"]
                bits.append(f"{k} {'OFF' if k in OFF_BY_DESIGN else f'{100 * share:.0f}%'}")
            extra = f"  priced {100 * c['priced'] / c['n']:.0f}%"
            if c["cards"]:
                extra += f"  matchup card {100 * c['cards'] / c['n']:.0f}%"
            lines.append(f"    {m:<14} n {c['n']:<4} " + " · ".join(bits) + extra)
        flagged += findings(sport, cen)
        for m in sorted(cen):
            for k, why in KNOWN.get((sport, m), {}).items():
                lines.append(f"    known: {m} {STEP_LABELS.get(k, k).lower()} — {why}")
            if cen[m]["seen"].get("player") and not _memory_on(sport, m):
                lines.append(f"    known: {m} player memory — off: the record has not earned it "
                             f"for this market (engine/playerfit)")
        # A bar no read can clear (engine/census.bar_notes). The build has
        # published this since it was written and nothing read it — the
        # site audit, 2026-09-24 (L-7) — so it lands where the operator
        # already looks: the list below.
        flagged += [f"{sport} bar: {x}" for x in board.get("bar_status") or []]
        w = wiring(board)
        if w["checked"]:
            lines.append(f"    wiring: {w['checked']} rows checked — every step and card reaches the number"
                         if not w["bad"] else f"    wiring: {len(w['bad'])} of {w['checked']} rows do not add up")
            flagged += [f"{sport} wiring: {x}" for x in w["bad"][:12]]
    lines.append("")
    if flagged:
        lines.append("  LOOK AT THESE:")
        lines += [f"    {x}" for x in flagged]
    else:
        lines.append("  nothing dead: every step that should move a number moved some")
    return lines


# ---- wiring: does every number on the Most Likely board come from the adjusted projection?
#: Rounding the board writes (projection to 0.1, probabilities to 4 places).
TOL_PROJ = 0.051
TOL_PROB = 0.0015


def _key(r: dict, side_k="side", line_k="line") -> tuple:
    return (str(r.get("player") or ""), str(r.get("market") or ""),
            str(r.get(side_k) or "").lower(), None if r.get(line_k) is None else float(r.get(line_k)))


def wiring(board: dict, fits=None) -> dict:
    """Ethan, 2026-09-23: "make sure everything we pull, all the data we use
    is actually being projected to the pick ... Most Likely is number one."

    For every prop row: base × every step = the projection it shows, and the
    "who plays around him" step equals what its QB and teammate cards say
    was applied. For every Most Likely prop row: its projection is its prop
    row's, and its probability is what that projection gives — the mixture
    recomputed from it, or the prop row's own number. {"checked", "bad": [...]}"""
    from .yardagefit import display_prob
    recs = [r for r in (board or {}).get("recommendations") or [] if isinstance(r, dict)]
    by = {_key(r): r for r in recs}
    bad, n = [], 0
    for r in recs:
        ch = r.get("chain") or {}
        base = (ch.get("base") or {}).get("value")
        if base is None or r.get("projection") is None:
            continue
        n += 1
        prod = float(base)
        for s in ch.get("steps") or []:
            prod *= float(s.get("mult", 1.0))
        if abs(prod - float(r["projection"])) > max(TOL_PROJ, 0.01 * abs(prod)):
            bad.append(f"{r.get('player')} {r.get('market')}: the steps multiply to {prod:.2f}, "
                       f"the row shows {r['projection']}")
        lu = next((s for s in ch.get("steps") or [] if s.get("key") == "lineup"), None)
        want = 1.0
        for c in (r.get("qb_card"), r.get("mate_card")):
            if isinstance(c, dict):
                want *= float(c.get("applied", 1.0))
        got = float(lu["mult"]) if lu else 1.0
        if abs(got - want) > 0.002:
            bad.append(f"{r.get('player')} {r.get('market')}: its cards say ×{want:.3f} was applied, "
                       f"the projection used ×{got:.3f}")
    for m in (board or {}).get("most_likely") or []:
        if not isinstance(m, dict) or m.get("kind") != "prop":
            continue
        n += 1
        src = by.get(_key(m, "main_side", "main_line"))
        if src is None:
            bad.append(f"{m.get('player')} {m.get('market')}: on Most Likely with no prop row behind it")
            continue
        if m.get("projection") != src.get("projection"):
            bad.append(f"{m.get('player')} {m.get('market')}: Most Likely projects {m.get('projection')}, "
                       f"its prop row {src.get('projection')}")
        if m.get("rung") == "main":
            if m.get("prob_source") == "mixture":
                p = display_prob(m["market"], src.get("projection"), m.get("line"),
                                 src.get("recent_values"), fits=fits)
                if p is not None:
                    p = 1.0 - p if str(m.get("side") or "").lower() == "under" else p
                    if abs(p - float(m["model_prob"])) > TOL_PROB:
                        bad.append(f"{m.get('player')} {m.get('market')}: shows {m['model_prob']:.3f}, "
                                   f"its projection gives {p:.3f}")
            else:
                own = src.get("raw_prob") if src.get("sharp_anchored") else src.get("hit_prob")
                if own is not None and abs(float(own) - float(m["model_prob"])) > TOL_PROB:
                    bad.append(f"{m.get('player')} {m.get('market')}: shows {m['model_prob']:.3f}, "
                               f"its prop row says {float(own):.3f}")
    return {"checked": n, "bad": bad}


# ---- weather: did the forecast reach the games, and the numbers?
def weather(boards: dict) -> list[str]:
    """``boards`` is {sport: board dict} (football). Per league: outdoor games
    with a real forecast against those left on the prior, and the prop rows
    whose weather step moved.

    Ethan, 2026-09-23: "it doesn't seem like the model is tracking the
    weather". Until that day it was not — the NFL forecast stopped at the
    console (nflverse.build_slate's ``games``) — and this is the one-line
    check that it now reaches the board.
    """
    lines = ["WEATHER — did the kickoff forecast reach the games and the numbers",
             "  expect every outdoor game forecast inside 16 days of kickoff, and rows moved "
             "wherever a forecast is 7+ mph (8+ for a reading) or rain is 30%+ likely"]
    for sport, board in boards.items():
        if not isinstance(board, dict):
            lines.append(f"  {sport}: {board}")
            continue
        games = board.get("games") or []
        dome = [g for g in games if (g.get("weather") or {}).get("dome")]
        outdoor = [g for g in games if g not in dome]
        read = [g for g in outdoor if (g.get("weather") or {}).get("measured") or g.get("weather_checked")]
        lines.append(f"  {sport}: {len(games)} games — {len(dome)} indoors, {len(outdoor)} outdoors, "
                     f"{len(read)} of them forecast" + ("" if len(read) == len(outdoor)
                                                       else f"  ({len(outdoor) - len(read)} on the prior)"))
        for g in read:
            w = g.get("weather") or {}
            wind, pc = float(w.get("wind_mph") or 0), float(w.get("precip_chance") or 0)
            # College's stamped dicts are forecasts by construction.
            fc = bool(w.get("forecast") or g.get("weather_checked"))
            if wind >= (7 if fc else 8) or pc >= 0.3 or w.get("rain") or w.get("snow"):
                lines.append(f"    {g.get('away')} @ {g.get('home')}: {wind:.0f} mph"
                             + (" forecast" if fc else "")
                             + f", {float(w.get('temp_f') or 0):.0f}°F"
                             + (f", {pc:.0%} precipitation" if pc else ""))
        moved: dict = {}
        for r in board.get("recommendations") or []:
            for s in (r.get("chain") or {}).get("steps") or []:
                if s.get("key") == "weather" and abs(float(s.get("mult") or 1.0) - 1.0) > 1e-4:
                    moved.setdefault(r.get("market"), []).append(float(s["mult"]))
        if moved:
            lines.append("    rows the weather moved: " + " · ".join(
                f"{m} {len(v)} (×{min(v):.2f}–×{max(v):.2f})" for m, v in sorted(moved.items())))
        else:
            lines.append("    no row moved by weather on this board")
    return lines
