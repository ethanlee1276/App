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
}
#: Steps that only speak when something happens: flat on a quiet night is
#: normal, so these are reported, never flagged.
SITUATIONAL = {"injury", "cap", "rare", "learned"}
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
    lines.append("")
    if flagged:
        lines.append("  LOOK AT THESE:")
        lines += [f"    {x}" for x in flagged]
    else:
        lines.append("  nothing dead: every step that should move a number moved some")
    return lines
