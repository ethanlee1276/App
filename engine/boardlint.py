"""Read a published board the way a sceptical bettor reads it.

Ethan, 2026-09-02: "dive deep into making sure the nfl bets for edge
bets and most likely bets are perfect and following everything we have
and make sense ... Some of them seem weird so I wanna make sure.
Especially the most likely bets."

The boards are built on the droplet from feeds this sandbox cannot
reach, so the only way to audit the rows a reader actually sees is to
audit the payload on the box that built it. This prints every row on
the three NFL boards — Most Likely, Recommended props, game bets — with
the numbers behind it, and beside each row every check the doctrine
implies that the row fails:

    Most Likely
      HELD        listed Questionable / Doubtful / Out (the injury hold)
      CHALK       heavier than the -250 cap
      GAP         shown probability more than MAX_CREDIBLE_EDGE from the
                  book's de-vigged number
      RAW GAP     the engine's PRE-SHRINK claim more than MAX_CREDIBLE_EDGE
                  from it — the check GAP cannot make, because the shrink
                  caps the shown gap (see likely.engine_credible)
      PROJ<LINE   an over whose projection sits below the line
      PROJ>LINE   an under whose projection sits above it (unders are
                  admitted since 2026-09-02 — the cap answers the chalk)
      HISTORY     fewer than a third of his recent games cleared the line
                  while the board says 60%+ (the reader will ask)
      SCRIPT      the game script tilts against the side
      ROLE        a market that does not fit the position
      REPEAT      the same player on the board more than once (a game row
                  repeats only within its own matchup — "Over 43" in two
                  games is two bets)
      RANK-ONLY   a market that ranks but cannot be bet (shown, not a defect)
      LEAN        a game row from a market measured below the ranking floor
                  (shown with its figure, by Ethan's call — not a defect)
      FLIP        a game row built for the other side of the edge card,
                  because the card backed the short end on price (info)
      STARTED     the game has kicked off
    Recommended props
      HELD, GAP, PROJ vs SIDE, SCRIPT, REPEAT as above, plus
      WARNED      recommended with a live warning on it
      REFUSED     a refusal sentence in its reasons
      BAR         edge under its tier's bar
      GRADE       grade and quality disagree, or quality under the floor
      LADDER      stake above what the PRICE allows (engine/staking) —
                  the rule that actually sets a size since 2026-08-12
      EV          non-positive EV
      PROXY       no real book price
      BOTH SIDES  the same player recommended over AND under
    Game bets
      CREDIBLE    recommended with `credible` False
      QUALITY     a game-bet quality above the ceiling a NEUTRAL context allows
      GRADE / LADDER / EV / STARTED as above

Nothing here re-prices anything. It reads the payload and the injuries
page and says what it sees; a flag is a question for a human, not a
verdict. READ-ONLY.

    python3 -m engine.boardlint                       # web/data/recommendations.json
    python3 -m engine.boardlint --sport cfb           # web/data/cfb.json
    python3 -m engine.boardlint --file some.json
    python3 -m engine.boardlint --all                 # every row, flagged or not

Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

from .betting import MAX_CREDIBLE_EDGE, REFUSAL_REASONS
from .quality import GRADE_BANDS, MARKET_TIER, TIER_MIN_EDGE
from .staking import units_for_price
from .quality import NEUTRAL as _NEUTRAL
from .likely import HEAVIEST_PRICE, MIN_PROB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {"nfl": "recommendations.json", "cfb": "cfb.json",
         "mlb": "mlb_recommendations.json"}

#: Markets a position should not be carrying. A quarterback on a
#: receptions line, a kicker on a rushing line — a mis-keyed menu, not a
#: pick.
ROLE_MISFIT = {
    "QB": {"receptions", "rec_yds", "anytime_td"},
    "K": {"receptions", "rec_yds", "rush_yds", "pass_yds", "anytime_td"},
    "DEF": {"receptions", "rec_yds", "rush_yds", "pass_yds"},
}

#: Above this shown probability, a history in which fewer than
#: HISTORY_MIN_SHARE of recent games cleared the line is a question the
#: reader will ask.
HISTORY_PROB = 0.60
HISTORY_MIN_SHARE = 1.0 / 3.0

#: The most a game bet can score: the edge component plus the neutral
#: context every game bet is given (engine/quality.game_bet_score).
GAME_BET_QUALITY_MAX = 40.0 + sum(_NEUTRAL.values())


def _grade_floor() -> float:
    return min(f for _, f in GRADE_BANDS)


def _letter(score) -> str:
    try:
        x = float(score)
    except (TypeError, ValueError):
        return "?"
    for name, floor in GRADE_BANDS:
        if x >= floor:
            return name
    return "Pass"


def _norm(name: str) -> str:
    return " ".join(str(name or "").lower().replace(".", "").split())


def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# --- the injuries page, by player -------------------------------------------
def injury_index(path: str | None = None, sport: str = "nfl") -> dict:
    """``{normalised player: status}`` for anyone not Active, from the
    injuries page the site publishes. Missing file → empty index."""
    path = path or os.path.join(ROOT, "web", "data", "injuries.json")
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    rows = ((d.get("sports") or {}).get(sport) or []) if isinstance(d, dict) else []
    out: dict = {}
    for r in rows:
        status = str(r.get("status") or "").strip()
        if status and status.lower() not in ("active", "healthy", ""):
            out[_norm(r.get("player"))] = status
    return out


# --- per-row checks ----------------------------------------------------------
def _script_against(row: dict, side: str) -> bool:
    gs = row.get("game_script") or {}
    if not isinstance(gs, dict):
        return False
    tilt = _f(gs.get("tilt"))
    if tilt is None:
        return False
    up = side in ("over", "yes", "")
    return (tilt < 0.97) if up else (tilt > 1.03)


def _history_share(row: dict) -> float | None:
    vals = [v for v in (row.get("recent_values") or []) if v is not None]
    line = _f(row.get("line"))
    if line is None or len(vals) < 3:
        return None
    return sum(1 for v in vals if _f(v, 0.0) > line) / len(vals)


def _ladder_flags(stake, odds) -> list:
    """Is this stake bigger than the rule that sets stakes allows?

    THE CHECK THAT WAS AUDITING A RETIRED RULE. This compared every
    stake against `quality.STAKE_CAP_U`, the per-grade ceiling — and
    that ceiling stopped deciding sizes on 2026-08-12, when the price
    ladder replaced Kelly-times-grade for every board (see
    engine/staking.py for the three measurements that retired it).
    Nothing in production has enforced it since; the lint was the last
    place it was alive, so it flagged CORRECT rows. A "+190 at 0.66u"
    card is the ladder's own answer, and a check that calls the shipped
    rule a defect teaches a reader to ignore the flags.

    Re-measured 2026-09-02 on 1,050 settled NFL game bets before this
    was changed, because "the cap is retired" is not the same claim as
    "the cap does no good": ROI -2.76% on the ladder, -2.53% with the
    grade cap on top, -2.14% flat, -3.44% at quarter Kelly. Every gap
    sits inside a 95% band of about six points, so nothing here
    separates. What the cap demonstrably DOES is halve the money
    staked (1,007u to 522u) while leaving ROI where it was — which is
    Ethan's point, 2026-09-02: "i dont care about what grade it allowed
    how much money."

    WHAT IS CHECKED INSTEAD is the rule that runs: the price ladder is
    the ceiling for a given price, and every caller-side adjustment is
    a DOWNWEIGHT (the NBA's minutes multiplier, the correlation pass's
    trims), so a stake ABOVE the ladder cannot come from any path that
    exists and is worth a human's attention. Under it is legitimate and
    silent.
    """
    if stake is None or odds is None:
        return []
    try:
        allowed = units_for_price(int(odds))
    except (TypeError, ValueError):
        return []
    if allowed > 0 and stake > allowed + 1e-9:
        return [f"LADDER {stake:g}u over the {allowed:g}u this price allows"]
    return []


def _started(row: dict, now: _dt.datetime | None) -> bool:
    if row.get("live"):
        return True
    if now is None:
        return False
    k = str(row.get("kickoff") or row.get("game_kickoff") or "")
    try:
        t = _dt.datetime.fromisoformat(k.replace("Z", "+00:00"))
    except ValueError:
        return False
    if t.tzinfo is None:
        return False
    return t <= now


def _who(r: dict) -> str:
    """The identity REPEAT counts on. A player row is the player; a game
    row is its pick label WITHIN its matchup, since "Over 43" can be the
    honest pick in two different games on one Sunday."""
    key = _norm(r.get("player"))
    if r.get("kind") == "game":
        key += "|" + _norm(r.get("matchup"))
    return key


def lint_likely(rows: list[dict], injuries: dict, now=None) -> list[dict]:
    seen: dict = {}
    for r in rows:
        seen[_who(r)] = seen.get(_who(r), 0) + 1
    out = []
    for r in rows:
        flags = []
        side = str(r.get("side") or "").lower()
        status = str(r.get("injury_status") or "")
        listed = injuries.get(_norm(r.get("player")))
        if status:
            flags.append(f"HELD listed {status}")
        elif listed:
            flags.append(f"HELD injuries page says {listed}")
        odds = _f(r.get("odds"))
        if odds is not None and odds < HEAVIEST_PRICE:
            flags.append(f"CHALK {int(odds):+d}")
        prob, fair = _f(r.get("model_prob")), _f(r.get("implied_prob"))
        if prob is not None and prob < MIN_PROB:
            flags.append(f"UNDER-FLOOR {prob:.0%}")
        if prob is not None and fair is not None and abs(prob - fair) > MAX_CREDIBLE_EDGE:
            flags.append(f"GAP {prob:.0%} vs book {fair:.0%}")
        # The same question of the number the ENGINE judged. Ethan's
        # Gelof card, 2026-09-02: shown 73% against a 63% book, which
        # passes GAP, while the claim underneath it was 96%.
        eraw = _f(r.get("engine_raw_prob"))
        efair = _f(r.get("fair_prob"))
        if eraw is not None and efair is not None and abs(eraw - efair) > MAX_CREDIBLE_EDGE:
            flags.append(f"RAW GAP model {eraw:.0%} vs book {efair:.0%} "
                         f"before the shrink")
        proj, line = _f(r.get("projection")), _f(r.get("line"))
        if proj is not None and line is not None and side != "under" and proj < line:
            flags.append(f"PROJ<LINE {proj:.1f} < {line:g}")
        if proj is not None and line is not None and side == "under" and proj > line:
            flags.append(f"PROJ>LINE {proj:.1f} > {line:g} on an under")
        share = _history_share(r)
        if (share is not None and prob is not None and prob >= HISTORY_PROB
                and share < HISTORY_MIN_SHARE and side != "under"):
            flags.append(f"HISTORY {share:.0%} of recent games cleared {line:g}")
        if _script_against(r, side):
            flags.append("SCRIPT against the side")
        pos = str(r.get("position") or "").upper()
        if r.get("market") in ROLE_MISFIT.get(pos, set()):
            flags.append(f"ROLE {pos} on {r.get('market')}")
        if seen.get(_who(r), 0) > 1:
            flags.append(f"REPEAT x{seen[_who(r)]}")
        if r.get("bettable") is False:
            flags.append("RANK-ONLY")
        if r.get("kind") == "game":
            # The game rows' own facts, printed so the audit reads what
            # the page says: a lean is labelled, a flipped side names
            # the card it came from, and a game row must carry the id
            # parts the page opens it by.
            if r.get("ranked") is False:
                auc = _f(r.get("rank_auc"))
                flags.append(f"LEAN measured {auc:.2f}" if auc is not None else "LEAN")
                if not r.get("rank_note"):
                    flags.append("LEAN without its note")
            if r.get("flipped"):
                flags.append("FLIP")
            if not (r.get("home") and r.get("away") and (r.get("market") or r.get("bet_type"))):
                flags.append("NO DOOR (home/away/market missing)")
        if _started(r, now):
            flags.append("STARTED")
        out.append({"row": r, "flags": flags})
    return out


def lint_props(rows: list[dict], injuries: dict, now=None) -> list[dict]:
    recs = [r for r in rows if r.get("recommended")]
    sides: dict = {}
    for r in recs:
        sides.setdefault(_norm(r.get("player")), set()).add(str(r.get("side") or "").lower())
    out = []
    for r in recs:
        flags = []
        side = str(r.get("side") or "").lower()
        status = str(r.get("injury_status") or "")
        listed = injuries.get(_norm(r.get("player")))
        if status:
            flags.append(f"HELD listed {status}")
        elif listed:
            flags.append(f"HELD injuries page says {listed}")
        if r.get("warnings"):
            flags.append(f"WARNED {str(r['warnings'][0])[:60]}")
        for reason in r.get("reasons") or []:
            if any(str(reason).startswith(x[:40]) for x in REFUSAL_REASONS):
                flags.append("REFUSED " + str(reason)[:50])
                break
        market = str(r.get("market") or "")
        tier = MARKET_TIER.get(market, 2)
        edge = _f(r.get("edge"))
        if edge is not None and edge < TIER_MIN_EDGE.get(tier, 0.03):
            flags.append(f"BAR edge {edge:+.1%} under tier {tier} {TIER_MIN_EDGE.get(tier, 0.03):.1%}")
        q, grade = _f(r.get("quality")), str(r.get("grade") or "")
        if q is not None:
            if q < _grade_floor():
                flags.append(f"GRADE quality {q:.0f} under the {_grade_floor():.0f} floor")
            elif _letter(q) != grade:
                flags.append(f"GRADE {grade} on quality {q:.0f} (bands say {_letter(q)})")
        stake = _f(r.get("stake_units"), 0.0)
        for _flag in _ladder_flags(stake, r.get("odds")):
            flags.append(_flag)
        ev = _f(r.get("ev_per_unit"))
        if ev is not None and ev <= 0:
            flags.append(f"EV {ev:+.3f}")
        if str(r.get("book") or "").lower() == "proxy" or r.get("has_market") is False:
            flags.append("PROXY no real price")
        prob, fair = _f(r.get("hit_prob")), _f(r.get("fair_prob"))
        if prob is not None and fair is not None and abs(prob - fair) > MAX_CREDIBLE_EDGE:
            flags.append(f"GAP {prob:.0%} vs book {fair:.0%}")
        proj, line = _f(r.get("projection")), _f(r.get("line"))
        if proj is not None and line is not None:
            if side == "over" and proj < line:
                flags.append(f"PROJ<LINE {proj:.1f} < {line:g} on an over")
            if side == "under" and proj > line:
                flags.append(f"PROJ>LINE {proj:.1f} > {line:g} on an under")
        if _script_against(r, side):
            flags.append("SCRIPT against the side")
        if len(sides.get(_norm(r.get("player")), ())) > 1:
            flags.append("BOTH SIDES recommended")
        if _started(r, now):
            flags.append("STARTED")
        out.append({"row": r, "flags": flags})
    return out


def lint_game_bets(rows: list[dict], now=None) -> list[dict]:
    out = []
    for r in rows:
        if not r.get("recommended"):
            continue
        flags = []
        if r.get("credible") is False:
            flags.append("CREDIBLE recommended on a price the layer called not credible")
        q, grade = _f(r.get("quality")), str(r.get("grade") or "")
        if q is not None:
            if q > GAME_BET_QUALITY_MAX + 1e-9:
                flags.append(f"QUALITY {q:.0f} above the {GAME_BET_QUALITY_MAX:.0f} a game bet can score")
            if q < _grade_floor():
                flags.append(f"GRADE quality {q:.0f} under the floor")
            elif _letter(q) != grade:
                flags.append(f"GRADE {grade} on quality {q:.0f} (bands say {_letter(q)})")
        stake = _f(r.get("stake_units"), 0.0)
        for _flag in _ladder_flags(stake, r.get("odds")):
            flags.append(_flag)
        ev = _f(r.get("ev_per_unit"))
        if ev is not None and ev <= 0:
            flags.append(f"EV {ev:+.3f}")
        if r.get("has_market") is False:
            flags.append("PROXY no real price")
        if r.get("warnings"):
            flags.append(f"WARNED {str(r['warnings'][0])[:60]}")
        if _started(r, now):
            flags.append("STARTED")
        out.append({"row": r, "flags": flags})
    return out


# --- text --------------------------------------------------------------------
def _pct(x):
    v = _f(x)
    return "—" if v is None else f"{v:.0%}"


def _likely_line(r: dict) -> str:
    gs = r.get("game_script") or {}
    arch = gs.get("archetype", "") if isinstance(gs, dict) else ""
    vals = [v for v in (r.get("recent_values") or [])[:6] if v is not None]
    hist = "/".join(f"{_f(v, 0):g}" for v in vals)
    return (f"{r.get('player', '?'):<22} {r.get('team', ''):<4} v {r.get('opponent', ''):<4} "
            f"{str(r.get('side') or '').lower():<5} {str(r.get('line') if r.get('line') is not None else ''):>5} "
            f"{r.get('market', ''):<12} {str(r.get('odds') or ''):>5} {str(r.get('book') or ''):<10} "
            f"shown {_pct(r.get('model_prob'))} ({r.get('prob_source', '?')}, raw {_pct(r.get('raw_prob'))}) "
            f"book {_pct(r.get('implied_prob'))} proj {r.get('projection') if r.get('projection') is not None else '—'} "
            f"hist {hist or '—'} role {r.get('usage_role') or r.get('position') or '?'}"
            + (f" script {arch}" if arch else ""))


def _prop_line(r: dict) -> str:
    return (f"{r.get('player', '?'):<22} {r.get('team', ''):<4} v {r.get('opponent', ''):<4} "
            f"{str(r.get('side') or '').lower():<5} {str(r.get('line') if r.get('line') is not None else ''):>5} "
            f"{r.get('market', ''):<12} {str(r.get('odds') or ''):>5} {str(r.get('book') or ''):<10} "
            f"hit {_pct(r.get('hit_prob'))} fair {_pct(r.get('fair_prob'))} edge {_pct(r.get('edge'))} "
            f"q {r.get('quality')} {r.get('grade')} {r.get('stake_units')}u ev {r.get('ev_per_unit')} "
            f"proj {r.get('projection')}")


def _gb_line(r: dict) -> str:
    return (f"{r.get('matchup', '?'):<12} {r.get('bet_type', ''):<10} {r.get('pick_label', r.get('pick', '')):<18} "
            f"{str(r.get('line') if r.get('line') is not None else ''):>6} {str(r.get('odds') or ''):>5} "
            f"win {_pct(r.get('win_prob'))} fair {_pct(r.get('fair_prob'))} edge {_pct(r.get('edge'))} "
            f"q {r.get('quality')} {r.get('grade')} {r.get('stake_units')}u ev {r.get('ev_per_unit')}")


def render(report: dict, show_all: bool = False) -> str:
    lines = [f"Board lint — {report['sport']} · {report['file']} · built {report.get('built_at') or '?'}",
             f"injuries page: {report['injury_rows']} listed not-active"]
    for title, key, fmt in (("MOST LIKELY", "likely", _likely_line),
                            ("RECOMMENDED PROPS", "props", _prop_line),
                            ("GAME BETS", "game_bets", _gb_line)):
        items = report[key]
        flagged = [x for x in items if x["flags"]]
        lines += ["", f"{title}: {len(items)} rows, {len(flagged)} flagged"]
        for x in items:
            if not x["flags"] and not show_all:
                continue
            lines.append("  " + fmt(x["row"]))
            for f in x["flags"]:
                lines.append(f"      ! {f}")
    c = report.get("likely_census") or {}
    if c:
        lines += ["", "likely board refused: " + ", ".join(f"{v} {k}" for k, v in sorted(c.items()))]
    lines += ["", "A flag is a question, not a verdict — the row and its numbers are printed so the question can be answered."]
    return "\n".join(lines)


def lint_payload(d: dict, sport: str, file: str = "", injuries: dict | None = None,
                 now: _dt.datetime | None = None) -> dict:
    injuries = injuries if injuries is not None else {}
    return {
        "sport": sport, "file": file, "built_at": d.get("built_at"),
        "injury_rows": len(injuries),
        "likely": lint_likely(d.get("most_likely") or [], injuries, now),
        "props": lint_props(d.get("recommendations") or [], injuries, now),
        "game_bets": lint_game_bets(d.get("game_bets") or [], now),
        "likely_census": d.get("likely_census") or {},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read a published board sceptically")
    ap.add_argument("--sport", default="nfl", choices=sorted(FILES))
    ap.add_argument("--file", default=None)
    ap.add_argument("--injuries", default=None, help="injuries.json path")
    ap.add_argument("--all", action="store_true", help="print unflagged rows too")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    path = a.file or os.path.join(ROOT, "web", "data", FILES[a.sport])
    if not os.path.exists(path):
        print(f"no board at {path}", file=sys.stderr)
        return 2
    # THE PRIVATE COPY, AND THIS TOOL IS THE FIFTH TO LEARN IT.
    #
    # `gate.publish` writes the full board to data/built/ and a REDACTED
    # copy to web/data/ — `recommendations`, `most_likely`,
    # `board_shelves` and `game_bets` are all paid keys and all stripped.
    # This linted the public path, so with the paywall on it read a board
    # with no rows in it, found nothing wrong, and said so.
    #
    # A lint that reports CLEAN because it was handed an empty board is
    # worse than no lint: it is the one tool whose whole job is to say a
    # board is wrong, and it was answering about a different file. Every
    # sport in FILES — nfl, cfb, mlb — was affected, which is exactly the
    # question Ethan asked (2026-09-03: "make sure that redaction doesnt
    # affect any other sports too").
    #
    # ONLY FOR A PATH ACTUALLY IN A web/data TREE, and that scoping is
    # not fussiness. `board_source` resolves by FILE NAME, not by
    # location: hand it /tmp/cfbprobe.json and it returns
    # data/built/cfb.json, because the name matches. So an unscoped
    # resolve would silently lint a different file than the one asked
    # for — worst of all for `--file`, which exists precisely to point
    # this at a board somewhere else. `show_boards` learned the same
    # thing the same way (launch.py, 2026-09-03).
    note = ""
    parts = Path(path).resolve().parts
    in_web_data = len(parts) >= 2 and parts[-3:-1] == ("web", "data")
    if in_web_data:
        try:
            from . import gate
            src = gate.board_source(Path(path))
            if str(src) != str(path):
                note = " (via gate.board_source, not the stripped public copy)"
                path = str(src)
        except Exception:                                    # noqa: BLE001
            pass      # a gate hiccup must not stop the lint reading SOMETHING
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    # AND SAY SO IF THE ROWS ARE STILL MISSING. A locked board with no
    # private copy behind it carries no priced rows at all and would lint
    # as a clean empty board — the same false all-clear, arriving by a
    # different route (engine/devigcheck.py reached this conclusion first).
    if d.get("locked") and not any(d.get(k) for k in
                                   ("recommendations", "most_likely", "game_bets")):
        print(f"⚠️  {path} is the LOCKED public copy and no private board was "
              f"found beside it — every priced row has been stripped, so a "
              f"clean result here means nothing. Run against "
              f"data/built/{os.path.basename(path)}.", file=sys.stderr)
        return 2
    if note:
        print(f"reading {os.path.relpath(path, ROOT)}{note}")
    inj = injury_index(a.injuries, a.sport)
    now = _dt.datetime.now(_dt.timezone.utc)
    rep = lint_payload(d, a.sport, os.path.relpath(path, ROOT), inj, now)
    if a.json:
        print(json.dumps({k: (v if k not in ("likely", "props", "game_bets") else
                              [{"player": x["row"].get("player") or x["row"].get("matchup"),
                                "market": x["row"].get("market"), "flags": x["flags"]}
                               for x in v]) for k, v in rep.items()}, indent=1))
    else:
        print(render(rep, a.all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
