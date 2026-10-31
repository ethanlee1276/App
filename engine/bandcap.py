"""Near even money, the one board's Top and Strong labels: proven wrong, or not?

Ethan's loss audit and bandcheck, 2026-10-04. Every settled one-board pick
graded correctly (0 of 1,276 over/unders disagree with their own stat),
and still, at a price between +120 and −149, the board's tiers ran
backwards: Top pick 18-40, Strong 38-52, Worth a look 158-176. The label
that should mean "most trustworthy" was the worst bet on the board at
that price. Heavier favourites on the same board landed on their claim.

THE RULE, WRITTEN BEFORE ITS FIRST RUN. In the band, the board's Top pick
and Strong picks ("high") have their label capped at Worth a look only if
all four hold:
  1. high picks hit below the price (needed) with z ≤ −2, on MIN_N or more;
  2. high picks hit below the price in BOTH halves of the dates — the
     later half is the test the first half did not see;
  3. high picks do no better against the price than the band's Worth a
     look picks (the label adds nothing here);
  4. at −150 to −300, high picks hit within OUTSIDE_SLACK of the price or
     better — the tiers still work there, so the cap is about this price
     and not about the tiers.

What the cap does: the pick stays on the board and in the journal, with
"Worth a look" and a line saying why. Nothing is removed. The verdict is
saved by `bandcheck.py --save` and read by engine/likelyboard; with no
saved verdict, or one that does not hold, the board is unchanged.
Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

from . import modelstate

BAND = (0.454, 0.600)            # +120 (45.45%) in, +121 out; −149 in, −150 out
OUTSIDE = (0.600, 0.750)         # −150 to −300
HIGH = ("Top pick", "Strong")
LOOK = "Worth a look"
MIN_N = 60
OUTSIDE_SLACK = 0.03
STORE = "band_tiercap.json"


def implied(o) -> float | None:
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (100.0 - o)


def in_band(odds) -> bool:
    p = implied(odds)
    return p is not None and BAND[0] <= p < BAND[1]


def load_rows(conn) -> list[dict]:
    """The one board's settled picks: day, price, grade, won."""
    out = []
    for day, odds, grade, status in conn.execute(
            "SELECT COALESCE(game_day, date), odds, grade, status FROM bets WHERE category='board' "
            "AND status IN ('won','lost') ORDER BY 1"):
        p = implied(odds)
        if p is not None:
            out.append({"day": str(day or ""), "need": p, "grade": str(grade or ""), "won": status == "won"})
    return out


def _score(rs: list[dict]) -> dict:
    n = len(rs)
    if not n:
        return {"n": 0, "w": 0, "hit": None, "need": None, "z": None, "edge": None}
    w = sum(r["won"] for r in rs)
    hit, need = w / n, sum(r["need"] for r in rs) / n
    se = math.sqrt(max(need * (1 - need), 1e-9) / n)
    return {"n": n, "w": w, "hit": round(hit, 4), "need": round(need, 4),
            "z": round((hit - need) / se, 2), "edge": round(hit - need, 4)}


def judge(rows: list[dict]) -> dict:
    band = [r for r in rows if BAND[0] <= r["need"] < BAND[1]]
    high = [r for r in band if r["grade"] in HIGH]
    look = [r for r in band if r["grade"] == LOOK]
    outside = [r for r in rows if OUTSIDE[0] <= r["need"] < OUTSIDE[1] and r["grade"] in HIGH]
    days = sorted({r["day"] for r in high})
    cut = days[len(days) // 2] if days else ""
    s_high, s_look, s_out = _score(high), _score(look), _score(outside)
    halves = {"earlier": _score([r for r in high if r["day"] < cut]),
              "later": _score([r for r in high if r["day"] >= cut])}
    c1 = s_high["n"] >= MIN_N and s_high["z"] <= -2.0
    c2 = all(h["n"] and h["edge"] < 0 for h in halves.values())
    c3 = s_look["n"] > 0 and s_high["n"] > 0 and s_high["edge"] <= s_look["edge"]
    c4 = s_out["n"] > 0 and s_out["edge"] >= -OUTSIDE_SLACK
    return {"high": s_high, "look": s_look, "outside": s_out, "halves": halves, "cut": cut,
            "checks": [c1, c2, c3, c4], "holds": bool(c1 and c2 and c3 and c4)}


def save(res: dict, path=None) -> None:
    p = Path(path or modelstate.path(STORE))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({**res, "band": list(BAND),
                             "at": _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                             .isoformat(timespec="seconds")}, indent=1), encoding="utf-8")


def verdict(path=None) -> dict | None:
    try:
        return json.loads(Path(path or modelstate.path(STORE)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cap_note(v: dict | None, odds) -> str | None:
    """The line a capped pick carries, or None when no cap applies."""
    if not v or not v.get("holds") or not in_band(odds):
        return None
    h = v.get("high") or {}
    return (f"Near even money our Top and Strong picks have gone {h.get('w', 0)}-"
            f"{h.get('n', 0) - h.get('w', 0)}, so this one is marked Worth a look")
