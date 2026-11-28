"""The posted picks against the matchup reads, every league, in one read.

    python3 -m engine.pickaudit                 # every league's board
    python3 -m engine.pickaudit --sport cfb     # one league

Ethan, 2026-11-14: "Duke's running back has 17 touchdowns, and yet we're
marking him as a bad matchup ... audit all of that for every sport ...
audit all the picks and all that shit and remove and add anything we need
to." The matchup reads now count each factor once, never call a featured
player one to avoid, and say when a tough draw is still the go-to scorer's
(engine/readlogic). This reads what the boards POST after that, so the
next fix is a rule, never a hand-edited pick:

  1. the self-check's count, by kind (engine/contradictions): a pick the
     read argues against, a play to avoid another board posts, two chances
     for one bet;
  2. every could-struggle read (tough or avoid) on a key player — a
     quarterback, his team's go-to scorer, a featured share of the work —
     with the reasons on each side, so a read like the Duke back's is seen
     at once, go-to scorers first;
  3. every go-to scorer with no touchdown pick on any board, with his
     chance, his price and why he is not posted when the board says
     (the injury report, the -250 cap) — the picks to add, if a rule says.

Reads the private board copy (gate.board_source), as the self-check does:
the public copy has the reads and the picks taken out. Read-only.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import contradictions as C

ROOT = Path(__file__).resolve().parents[1]

#: Every league whose board carries matchup reads: the self-check's, and
#: the NHL's (nhl_build writes scan_reads too).
FILES = {**C.FILES, "nhl": "nhl.json"}
#: Football: a featured share of the work (engine/tdscenarios' "ok" bars).
KEY_TGT_SHARE = 0.18
KEY_CARRY_SHARE = 0.40
#: Basketball: a starter's minutes or a featured usage (engine/nba/scan).
KEY_MPG = 28.0
KEY_USG = 0.25
#: Hockey: a top-six forward's or a top-pair defenceman's ice time.
KEY_TOI = 17.0
#: The Most Likely board's price cap (likely.HEAVIEST_PRICE).
PRICE_CAP = -250
#: Reads a "could struggle" list holds.
STRUGGLE = ("tough", "avoid")
#: Where a posted touchdown pick can sit on a board.
TD_MARKETS = ("anytime_td", "anytime")


def _f(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def is_key(x: dict) -> bool:
    """A quarterback, a go-to scorer, or a featured share of the work."""
    if ((x.get("scoring") or {}).get("go_to")):
        return True
    pos = str(x.get("pos") or "").upper()
    u = x.get("usage") or {}
    if pos == "QB":
        return True
    if pos in ("WR", "TE") and (_f(u.get("tgt_share")) or 0) >= KEY_TGT_SHARE:
        return True
    if pos in ("RB", "FB") and (_f(u.get("carry_share")) or 0) >= KEY_CARRY_SHARE:
        return True
    if (_f(u.get("mpg")) or 0) >= KEY_MPG or (_f(u.get("usg")) or 0) >= KEY_USG:
        return True
    if (_f(u.get("toi")) or 0) >= KEY_TOI:
        return True
    return False


def role_words(x: dict) -> str:
    u = x.get("usage") or {}
    bits = []
    if _f(u.get("carry_share")) is not None:
        bits.append(f"{float(u['carry_share']):.0%} of the carries")
    if _f(u.get("tgt_share")) is not None and float(u["tgt_share"]) > 0:
        bits.append(f"{float(u['tgt_share']):.0%} of the {u.get('share_of') or 'targets'}")
    if _f(u.get("mpg")) is not None:
        bits.append(f"{float(u['mpg']):.0f} min")
    if _f(u.get("usg")) is not None:
        bits.append(f"{float(u['usg']):.0%} usage")
    if _f(u.get("toi")) is not None:
        bits.append(f"{float(u['toi']):.1f} min of ice")
    return ", ".join(bits)


def td_posted(d: dict) -> set:
    """Every player a touchdown pick of whom sits on any board."""
    out = {e["player"] for e in C.entries(d) if str(e.get("market") or "") in TD_MARKETS}
    for key in ("td_scenarios", "long_shots"):
        for r in d.get(key) or []:
            if isinstance(r, dict) and r.get("player"):
                out.add(r["player"])
    for g in ((d.get("game_parlays") or {}).get("games")) or []:
        for t in (g.get("scorers") or []) + (g.get("threes") or []) + (g.get("twos") or []):
            for leg in t.get("legs") or []:
                if str(leg.get("market") or "") in TD_MARKETS and leg.get("player"):
                    out.add(leg["player"])
    return out


def why_not(x: dict) -> str:
    td = x.get("td") or {}
    if td.get("injury_status"):
        return f"on the injury report ({td['injury_status']})"
    odds = td.get("odds")
    try:
        if odds is not None and int(odds) < PRICE_CAP:
            return f"past the {PRICE_CAP} cap"
    except (TypeError, ValueError):
        pass
    if not td:
        return "no touchdown price on the board"
    return "priced, under every board's bar"


#: Rows of each contradiction kind the audit prints (2026-11-14: the counts
#: alone named 92 college contradictions and none of the picks behind them).
EXAMPLES = 6


def built_utc(d: dict):
    """When the board was built, in UTC, or None. A stamp without a zone is
    the box's own clock (`datetime.now()` where it was written)."""
    import datetime as _dt
    s = str(d.get("built_at") or d.get("generated_at") or "")
    try:
        t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(_dt.timezone.utc)


def audit(d: dict) -> dict:
    """{"contradictions": Counter, "found": [...], "reads": Counter, "struggle": [...], "unposted": [...]}.

    THE BOARD'S OWN CLOCK (2026-11-14). The self-check asks whether a pick's
    game has started as of now, so Ethan's run at 7:32pm ET counted 43
    college picks STARTED — every 7:30 kickoff since the 7:19 build. As of the
    build, a pick on a game under way is a real fault; as of the read, it is
    the clock."""
    found = C.scan(d, now=built_utc(d))
    reads = C.reads(d)
    struggle = [x for x in reads if x.get("read") in STRUGGLE and is_key(x) and not x.get("own_status")]
    struggle.sort(key=lambda x: (not (x.get("scoring") or {}).get("go_to"), x.get("read") != "avoid",
                                 str(x.get("team") or ""), str(x.get("player") or "")))
    posted = td_posted(d)
    unposted = [x for x in reads if (x.get("scoring") or {}).get("go_to") and x.get("player") not in posted]
    unposted.sort(key=lambda x: -float(((x.get("scoring") or {}).get("prob")) or 0))
    return {"contradictions": Counter(f["kind"] for f in found), "found": found,
            "reads": Counter(str(x.get("read") or "?") for x in reads),
            "struggle": struggle, "unposted": unposted}


def report(sport: str, d: dict, limit: int = 40) -> list[str]:
    a = audit(d)
    out = [f"{sport.upper()} board built {d.get('built_at') or d.get('generated_at') or '?'}"]
    c = a["contradictions"]
    if c:
        said = (f"  Self-check: {sum(c.values())} contradiction(s) — "
                + ", ".join(f"{k} {n}" for k, n in c.most_common()))
        if sport in C.FILES:
            said += f"  (every row: python3 -m engine.contradictions --sport {sport} --all)"
        out.append(said)
        # THE ROWS BEHIND EACH COUNT, a few of each kind, so a fix can land on
        # the rule that made them.
        for kind, _n in c.most_common():
            rows = [f for f in a["found"] if f["kind"] == kind]
            for f in rows[:EXAMPLES]:
                out.append(f"    {kind}: {f['player']} — {f['text']}")
            if len(rows) > EXAMPLES:
                out.append(f"    {kind}: … {len(rows) - EXAMPLES} more")
    else:
        out.append("  Self-check: no contradictions")
    r = a["reads"]
    if not r:
        out.append("  Reads: none on this board")
        return out
    order = ("breakout", "good", "neutral", "tough", "avoid")
    out.append(f"  Reads: {sum(r.values())} — " + " · ".join(f"{k} {r[k]}" for k in order if r.get(k)))
    s = a["struggle"]
    out.append(f"  Could struggle, key players: {len(s)}" + (" (go-to scorers first)" if s else ""))
    for x in s[:limit]:
        role = role_words(x)
        out.append(f"    {x.get('player')} ({x.get('team')} vs {x.get('opp')}, {x.get('pos') or '-'}): "
                   f"\"{x.get('label')}\"" + (f" · {role}" if role else ""))
        sc = x.get("scoring") or {}
        if sc.get("go_to"):
            out.append(f"        go-to scorer: {float(sc.get('prob') or 0):.0%} to score"
                       + (f", the team expected to score {float(sc['implied']):.1f}" if _f(sc.get("implied")) else ""))
        if x.get("con"):
            out.append("        against: " + " | ".join(str(t) for t in x["con"]))
        if x.get("pro"):
            out.append("        for: " + " | ".join(str(t) for t in x["pro"]))
    if len(s) > limit:
        out.append(f"    … {len(s) - limit} more")
    # THE TOUCHDOWN PAIRS' RESEARCH (engine/gameparlays.research_scorers):
    # how many priced scorers carried a case, and why the rest did not.
    gp = d.get("game_parlays") or {}
    if gp.get("research_census") is not None:
        cnt = gp.get("counts") or {}
        out.append(f"  Touchdown pairs: {cnt.get('scorers', 0)} across {cnt.get('games', 0)} game(s); "
                   f"{gp.get('scorers_researched', 0)} of {gp.get('scorers_priced', 0)} priced scorers carry a "
                   f"research case")
        for why, n in (gp.get("research_census") or {}).items():
            out.append(f"    turned away: {why} — {n}")
    u = a["unposted"]
    out.append(f"  Go-to scorers with no touchdown pick on any board: {len(u)}")
    for x in u[:limit]:
        td = x.get("td") or {}
        sc = x.get("scoring") or {}
        price = f" at {int(td['odds']):+d} {td.get('book') or ''}".rstrip() if td.get("odds") else ""
        out.append(f"    {x.get('player')} ({x.get('team')}, {x.get('pos') or '-'}): "
                   f"{float(sc.get('prob') or 0):.0%}{price} — {why_not(x)}")
    return out


def _load(sport: str, file: str | None) -> dict:
    path = Path(file) if file else ROOT / "web" / "data" / FILES[sport]
    if not file:
        from . import gate
        path = Path(gate.board_source(path))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The posted picks against the matchup reads")
    ap.add_argument("--sport", default=None, choices=sorted(FILES))
    ap.add_argument("--file", default=None)
    ap.add_argument("--all", action="store_true", help="every row, not forty a list")
    a = ap.parse_args(argv)
    sports = [a.sport] if a.sport else sorted(FILES)
    for sport in sports:
        try:
            d = _load(sport, a.file)
        except (OSError, ValueError) as exc:
            print(f"{sport.upper()}: no board to read ({exc})")
            print()
            continue
        for ln in report(sport, d, limit=10 ** 6 if a.all else 40):
            print(ln)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
