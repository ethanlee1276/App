#!/usr/bin/env python3
"""Does each published parlay ticket actually hold together?

    python3 parlaycheck.py                 # every sport that built a board
    python3 parlaycheck.py mlb             # one sport
    python3 parlaycheck.py --quiet         # exit code only, for CI

WHY

The Parlay Zone publishes a ticket with a correlation and a mechanism
sentence, and the mechanism is chosen from the legs' own `team` and
`opponent` fields. Those fields come from roster data, and roster data
goes stale — a deadline trade is the ordinary case, not the exotic one.

That matters more here than anywhere else on the site, because the sign of
the correlation depends on it. An MLB pitcher's strikeout over next to a
moneyline is +0.275 when the moneyline is HIS team ("managers leave
winners in", §5.1) and a hard kill when it is the opponent's. Get the team
wrong on one traded pitcher and the same pair walks through Gate 3 with a
positive rho, gets priced as a correlated construction, and is published
as a ticket that bets both ways at once. Nothing downstream would notice:
the joint is arithmetically fine, the card renders, and only the roster
was wrong.

So this re-derives, from the published ticket alone, the two facts the
mechanism assumed — that a Type A ticket's legs really do share one game,
and that no pair carries a positive rho while sitting on opposite sides of
it — and says so out loud.

WHAT IT WILL NOT DO

Check rosters. It has no opinion on which team a player is really on; it
only reports the attribution the build used, so a person who knows the
answer can look at one line instead of reading JSON. A ticket it passes is
a ticket that is internally consistent, which is not the same as correct.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Where each sport's builder writes its board.
#
# IMPORTED, NOT RETYPED. This was a fourth hand-copy of the same map and
# four of its six entries named files that have never existed —
# cfb_recommendations.json and friends, where the real boards are
# cfb.json, nba.json, wnba.json and ufc.json. `main` skips a board it
# cannot open, so this script has been auditing NFL and MLB tickets only
# and printing "every published ticket is internally consistent" about
# four sports it never opened. A check that reassures without looking is
# worse than no check.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.parlayledger import BOARD_FILES as BOARDS       # noqa: E402


def matchup(leg: dict) -> tuple:
    """The game a leg belongs to, from its own two team fields."""
    return tuple(sorted(((leg.get("team") or "").upper(),
                         (leg.get("opponent") or "").upper())))


def audit_ticket(t: dict) -> list[str]:
    """Problems with one published ticket. Empty list = internally sound."""
    bad = []
    legs = t.get("legs") or []
    keys = {matchup(l) for l in legs}
    kind = t.get("parlay_type")

    # A Type A ticket claims a shared game — that claim is what every
    # same-game correlation prior is resting on.
    if kind == "A" and len(keys) != 1:
        bad.append(f"published as Type A (same game) but its legs sit in "
                   f"{len(keys)} different matchups: "
                   + " / ".join("@".join(k) for k in sorted(keys)))
    if kind == "B" and len(keys) == 1:
        bad.append("published as Type B (cross-game) but both legs share one "
                   "matchup — the correlation tax was never applied")

    # A positive rho between legs on opposite sides of one game is the
    # stale-roster signature: the pair was priced as if it were one story.
    for p in t.get("pairs") or []:
        rho = float(p.get("rho") or 0.0)
        if rho <= 0:
            continue
        a = next((l for l in legs if l.get("player") == p.get("a")), None)
        b = next((l for l in legs if l.get("player") == p.get("b")), None)
        if not a or not b:
            continue
        ta, tb = (a.get("team") or "").upper(), (b.get("team") or "").upper()
        oa = (a.get("opponent") or "").upper()
        if ta and tb and ta != tb and tb == oa:
            bad.append(
                f"{p.get('a')} ({ta}) and {p.get('b')} ({tb}) are on OPPOSITE "
                f"sides of one game, yet the pair carries rho {rho:+.2f} — "
                f"a positive prior between opponents is the signature of a "
                f"stale team on one of them. Mechanism claimed: "
                f"{p.get('mechanism')}")
    return bad


def audit_board(sport: str, path: Path, quiet: bool = False) -> int:
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        if not quiet:
            print(f"  {sport}: could not read {path} — {exc}")
        return 0                       # not built is not a failure
    pz = d.get("parlays") or {}
    tickets = pz.get("tickets") or []
    if not quiet:
        print(f"\n{sport.upper()} — {path}")
        print(f"  {pz.get('verdict', '(no verdict)')}")
        if pz.get("structural"):
            print(f"  why: {pz['structural'][:160]}")
    problems = 0
    for t in tickets:
        bad = audit_ticket(t)
        problems += len(bad)
        if quiet:
            continue
        head = (f"  #{t.get('rank')} Type {t.get('parlay_type')} · "
                f"{t.get('grade')} · qualified={t.get('qualified')}")
        print(("❌" if bad else "✅") + head)
        for l in t.get("legs") or []:
            print(f"       {str(l.get('player')):<24} "
                  f"team={str(l.get('team') or '?'):<5} "
                  f"opp={str(l.get('opponent') or '?'):<5} "
                  f"{l.get('side')} {l.get('line')} {l.get('market')} "
                  f"{l.get('odds'):+}")
        for p in t.get("pairs") or []:
            print(f"       rho {float(p.get('rho') or 0):+.2f} → priced "
                  f"{float(p.get('rho_priced') or 0):+.3f}  "
                  f"measured={p.get('rho_measured')}")
            print(f"       {p.get('mechanism')}")
        for b in bad:
            print(f"       ⚠️  {b}")
    return problems


def main(argv: list) -> int:
    quiet = "--quiet" in argv
    want = [a.lower() for a in argv if not a.startswith("-")]
    total = 0
    seen = 0
    for sport, rel in BOARDS.items():
        if want and sport not in want:
            continue
        # The PRIVATE copy where there is one: `parlays` is a paid key,
        # so on a box with QB_PAYWALL=1 the public file has an empty
        # parlay zone and this audit would pass every sport by finding
        # no tickets in any of them.
        from engine import gate
        p = gate.board_source(Path(rel))
        if not p.is_file():
            continue
        seen += 1
        total += audit_board(sport, p, quiet)
    if not seen:
        print("No built board found. Run `python3 launch.py` first.")
        return 0
    if total == 0:
        if not quiet:
            print("\n✅ every published ticket is internally consistent — its "
                  "legs sit where its correlation says they do.")
            print("   This does NOT verify rosters. Read the team= fields "
                  "above against who is actually on those clubs.")
        return 0
    print(f"\n❌ {total} problem(s). A correlation prior is chosen from the "
          f"legs' team fields, so a stale roster does not produce a wrong "
          f"number — it produces a ticket betting both ways with a "
          f"confident sentence attached.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
