"""Does the board contradict itself? — every NFL board read across all its parts.

    python3 -m engine.contradictions                 # the published NFL board
    python3 -m engine.contradictions --sport cfb
    python3 -m engine.contradictions --file path/to/board.json

Ethan, 2026-10-06: "I feel like we have a lot of contradictions in our
picks and the data and what we are saying so we need to check all of
that now."

One board is several makers: the Edge picks, the Most Likely list, the one
board, each game's plan (plays that fit, plays to avoid), the matchup
picks and the player reads. Each is checked on its own elsewhere
(engine/boardlint). Nothing checked them AGAINST EACH OTHER, which is
where a reader sees a contradiction: an over on one board and an under on
another, a play listed to avoid that another board posts, one prop with
two different chances, a reason printed under a pick that argues the
other way.

Every check is a question a reader would ask, and each finding names the
rows. A finding is not always a bug — an over at one line and an under at
a higher line is a window, not a contradiction, and is not flagged — but
every one is a thing the page says that a reader cannot square.

Reads the private board copy (gate.board_source), as boardlint does: the
public copy has the picks stripped and would read clean.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = {"nfl": "recommendations.json", "cfb": "cfb.json"}

#: Two chances for the same prop, side and line, further apart than this,
#: are two numbers for one bet.
PROB_GAP = 0.05
#: A projection this far off the Edge row's for the same prop is a second
#: number for one player.
PROJ_GAP = 0.05
#: Statuses that mean he is not playing (or not expected to).
OUT = {"OUT", "IR", "DOUBTFUL", "SUSPENDED", "PUP", "NFI"}


def _side(v) -> str:
    s = str(v or "").strip().lower()
    return "over" if s in ("over", "yes") else "under" if s in ("under", "no") else s


def _f(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _p(r: dict):
    return _f(r.get("model_prob") if r.get("model_prob") is not None else r.get("hit_prob"))


def entries(d: dict) -> list[dict]:
    """Every posted player pick on the board, from every maker, in one shape:
    {board, player, team, market, side, line, prob, projection, row}."""
    out = []

    def add(board, r, prob=None):
        if not isinstance(r, dict) or not r.get("player") or r.get("kind") == "game":
            return
        out.append({"board": board, "player": r.get("player"), "team": r.get("team"),
                    "market": r.get("market"), "side": _side(r.get("side")), "line": _f(r.get("line")),
                    "prob": _p(r) if prob is None else prob, "projection": _f(r.get("projection")),
                    "row": r})

    for r in d.get("recommendations") or []:
        if r.get("recommended"):
            add("Edge", r)
    for r in d.get("most_likely") or []:
        add("Most Likely", r)
    for r in ((d.get("likely_board") or {}).get("rows")) or []:
        add("One board", r)
    for m in d.get("matchup_picks") or []:
        for r in (m.get("td") or []) + (m.get("props") or []):
            add("Matchup picks", r)
    for p in d.get("game_plans") or []:
        for st in p.get("steps") or []:
            if st.get("key") == "fits":
                for r in st.get("rows") or []:
                    add("Plays that fit", r)
    return out


def avoid_rows(d: dict) -> list[dict]:
    rows = []
    for p in d.get("game_plans") or []:
        for st in p.get("steps") or []:
            if st.get("key") == "avoid":
                rows += [r for r in st.get("rows") or [] if isinstance(r, dict)]
    return rows


def reads(d: dict) -> list[dict]:
    return [x for g in (d.get("scan_reads") or {}).values() for x in (g or {}).get("players") or []
            if isinstance(x, dict)]


# ─── the sign of a sentence ────────────────────────────────────────────────

def text_sign(t: str, market: str = "") -> int:
    """+1 when a reason argues for the OVER, -1 for the UNDER, 0 neither or
    unknown. Only the phrasings this site prints are read; anything else
    is 0, so the check can miss a contradiction but never invent one. A
    line that already says it is against the pick is 0."""
    s = str(t or "")
    low = s.lower()
    if low.startswith("against it") or "argues the other way" in low:
        return 0
    if low.startswith("script:"):
        from .gameplan import script_sign
        return script_sign(s[len("script:"):], market)
    if "soft matchup" in low or "favorable" in low or "favourable" in low:
        return 1
    if "tough matchup" in low or "tough defensive" in low:
        return -1
    if re.search(r"\b(gives up|forces|allows?) the \d+(st|nd|rd|th)-most\b", low):
        return 1
    if re.search(r"\b(gives up|forces|allows?) the \d+(st|nd|rd|th)-fewest\b", low):
        return -1
    if re.search(r"^only \d+% of the", low):
        return -1
    return 0


def _why_lines(e: dict) -> list[str]:
    r = e["row"]
    if e["board"] == "One board":
        return list(r.get("case_lines") or [])
    if e["board"] == "Plays that fit":
        return list(r.get("why") or [])
    if e["board"] == "Matchup picks":
        return list(r.get("matchup_lines") or [])
    if e["board"] == "Most Likely":
        return list(r.get("bold_why") or [])
    return []


def _desc(e: dict) -> str:
    line = "" if e["line"] is None else f" {e['line']:g}"
    pct = "" if e["prob"] is None else f" ({e['prob']:.0%})"
    return f"{e['board']}: {e['side']}{line} {e['market']}{pct}"


def _started(r: dict, now: _dt.datetime) -> bool:
    k = str(r.get("kickoff") or r.get("game_kickoff") or "")
    if not re.search(r"(Z|[+-]\d{2}:?\d{2})$", k):
        return r.get("live") is True
    try:
        t = _dt.datetime.fromisoformat(k.replace("Z", "+00:00"))
    except ValueError:
        return False
    return t <= now


def scan(d: dict, now: _dt.datetime | None = None) -> list[dict]:
    """[{"kind", "player", "text"}] — every contradiction the board carries."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    found: list[dict] = []

    def flag(kind, player, text):
        found.append({"kind": kind, "player": player or "", "text": text})

    es = entries(d)
    by_prop: dict = defaultdict(list)
    for e in es:
        by_prop[(e["player"], e["market"])].append(e)

    for (player, market), group in by_prop.items():
        overs = [e for e in group if e["side"] == "over"]
        unders = [e for e in group if e["side"] == "under"]
        # 1. AN OVER AND AN UNDER THAT CANNOT BOTH WIN. Over 70.5 with
        #    under 89.5 is a window; over 89.5 with under 70.5 is the
        #    board arguing with itself (and over and under at one line is
        #    the plainest case of it).
        for o in overs:
            for u in unders:
                if o["line"] is None or u["line"] is None or o["line"] >= u["line"]:
                    flag("BOTH WAYS", player, f"{_desc(o)} vs {_desc(u)}")
        # 2. ONE BET, TWO CHANCES.
        same: dict = defaultdict(list)
        for e in group:
            if e["prob"] is not None:
                same[(e["side"], e["line"])].append(e)
        for (_s, _l), xs in same.items():
            boards = {}
            for x in xs:
                boards.setdefault(x["board"], x)
            vals = list(boards.values())
            if len(vals) > 1:
                hi = max(vals, key=lambda x: x["prob"])
                lo = min(vals, key=lambda x: x["prob"])
                if hi["prob"] - lo["prob"] > PROB_GAP:
                    flag("TWO NUMBERS", player, f"{_desc(hi)} vs {_desc(lo)} — one bet, two chances")
        # 3. ONE PLAYER, TWO PROJECTIONS (Edge row against any other).
        edge = next((e for e in group if e["board"] == "Edge" and e["projection"]), None)
        for e in group:
            if edge and e is not edge and e["projection"] and edge["projection"] > 0 and \
                    abs(e["projection"] / edge["projection"] - 1.0) > PROJ_GAP:
                flag("TWO PROJECTIONS", player,
                     f"Edge projects {edge['projection']:.1f}, {e['board']} {e['projection']:.1f} for {market}")

    for e in es:
        p, line, proj = e["prob"], e["line"], e["projection"]
        # 4. A PICK OUR OWN NUMBER SAYS IS LESS LIKELY THAN NOT.
        # A plus-money price is a bet under even by design (the value is
        # the payout), so only a pick laid at minus money is held to it.
        plus = (_f(e["row"].get("odds")) or 0) > 0
        if p is not None and p < 0.5 and e["market"] != "anytime_td" and not plus:
            flag("UNDER 50%", e["player"], f"{_desc(e)} — posted on a side our chance puts under even")
        # 5. THE PROJECTION ON THE OTHER SIDE OF THE LINE FROM THE PICK.
        if proj is not None and line is not None and e["market"] != "anytime_td":
            if e["side"] == "over" and proj < line:
                flag("PROJECTION", e["player"], f"{_desc(e)} with a projection of {proj:.1f}, under the line")
            if e["side"] == "under" and proj > line:
                flag("PROJECTION", e["player"], f"{_desc(e)} with a projection of {proj:.1f}, over the line")
        # 6. A REASON PRINTED UNDER THE PICK THAT ARGUES THE OTHER WAY.
        want = 1 if e["side"] == "over" else -1
        for t in _why_lines(e):
            if text_sign(t, e["market"]) == -want:
                flag("REASON AGAINST", e["player"], f"{_desc(e)} lists “{t}” as a reason")
        # 7. A PICK ON A MAN WHO IS NOT PLAYING, OR A GAME ALREADY GOING.
        st = str(e["row"].get("injury_status") or "").upper()
        if st in OUT:
            flag("NOT PLAYING", e["player"], f"{_desc(e)} — listed {st}")
        if _started(e["row"], now):
            flag("STARTED", e["player"], f"{_desc(e)} — its game has kicked off")

    # 8. A PLAY THE PLAN SAYS TO AVOID, POSTED ELSEWHERE.
    for a in avoid_rows(d):
        k = (a.get("player"), a.get("market"))
        for e in by_prop.get(k, []):
            if e["row"].get("avoid_warning"):
                continue                        # kept, and its card says so (Ethan, 2026-10-06)
            if e["side"] == _side(a.get("side") or "over"):
                flag("AVOID vs PICK", a.get("player"),
                     f"Plays to avoid: {_side(a.get('side') or 'over')} {a.get('market')} — {a.get('why') or ''} "
                     f"| but {_desc(e)}")

    # 9. THE READ AGAINST THE PICKS. A could-shine read with an under on
    #    the same player (or a could-struggle read with an over), on any
    #    board, where the read's card does not already say so.
    lean_side = {"breakout": "over", "good": "over", "tough": "under", "avoid": "under"}
    for x in reads(d):
        want = lean_side.get(x.get("read"))
        if not want:
            continue
        markets = set(x.get("lean") or [])
        for e in es:
            if e["player"] != x.get("player") or e["market"] not in markets or e["market"] == "anytime_td":
                continue
            if e["row"].get("matchup_warning"):
                continue                        # kept, and its card says so (Ethan, 2026-10-06)
            if e["side"] and e["side"] != want:
                flag("READ vs PICK", e["player"],
                     f"read “{x.get('label')}” ({want}s) but {_desc(e)}")
    return found


def report(found: list[dict], limit: int = 12) -> list[str]:
    if not found:
        return ["No contradictions found."]
    by: dict = defaultdict(list)
    for f in found:
        by[f["kind"]].append(f)
    out = [f"{len(found)} contradiction(s) across {len(by)} kind(s)", ""]
    for kind in sorted(by, key=lambda k: -len(by[k])):
        xs = by[kind]
        out.append(f"{kind}  ({len(xs)})")
        seen = set()
        for f in xs:
            key = (f["player"], f["text"])
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > limit:
                out.append(f"    … {len(xs) - limit} more")
                break
            out.append(f"    {f['player']}: {f['text']}")
        out.append("")
    return out


def _load(sport: str, file: str | None) -> dict:
    path = Path(file) if file else ROOT / "web" / "data" / FILES[sport]
    if not file:
        try:
            from . import gate
            path = Path(gate.board_source(path))
        except Exception:                                    # noqa: BLE001
            pass
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read a board for contradictions between its parts")
    ap.add_argument("--sport", default="nfl", choices=sorted(FILES))
    ap.add_argument("--file", default=None)
    ap.add_argument("--all", action="store_true", help="every finding, not twelve a kind")
    a = ap.parse_args(argv)
    try:
        d = _load(a.sport, a.file)
    except (OSError, ValueError) as exc:
        print(f"no board to read: {exc}", file=sys.stderr)
        return 2
    print(f"{a.sport.upper()} board built {d.get('built_at') or d.get('generated_at') or '?'}")
    for ln in report(scan(d), limit=10**6 if a.all else 12):
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
