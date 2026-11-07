"""A UFC leg in the parlay checker, read off the UFC card's own model.

Ethan, 2026-10-14, "do 1-11", to the call "UFC in the parlay checker? A
fight leg reads 'not on our board' today (step 38b)": yes.

The UFC build (ufc_build.py → ufc.json) runs every bout on the card through
the model and keeps a row for each, in its picks or its pass list. A bout
the model priced carries how it thinks the fight ends — ``method``, each
corner's share of wins by KO, submission and decision, summing to one — the
board's own chance for the side it judged (``p_final``, the model's number
held toward the market by the humility clamp), and every market those
imply on ``market_board``, the round prices among them where enough
finishes are on file (engine/ufc/rounds).

ONE FIGHT, ONE SET OF OUTCOMES. Every leg on a bout is read off the same
outcomes: who wins, held to the board's own chance; how, in the model's own
split of each corner's wins; and when a finish lands, in the shape the
round prices already assume (one shape for every finish, whoever lands it
and however — engine/ufc/rounds). A leg's chance is the share of outcomes it
wins on, so two legs on one bout are priced together, exactly, never as if
they were separate games: "A wins" and "A by decision" are one event and a
piece of it, and "A wins" with "B wins", or "goes the distance" with "A by
KO", cannot both happen.

HOW AND WHEN ARE FAIR NUMBERS. The board stakes the moneyline and the
markets its grade passes; the method, distance and round numbers on its
market board are fair numbers it shows to shop and never stakes. A leg on
one says so.

NO NUMBER WITHOUT ONE. A bout the board passed on before pricing — no
dossier, no fight-by-fight data, no two-sided price, the clamp's refusal —
gets no number, with the board's own reason. A round leg on a bout with no
round prices gets none either.

THE FIGHT, AS IT HAPPENS. `live_state` reads the live fight feed
(ufc_live_build.py → ufc_live.json): pre, in the round, or final, and a
leg's result once the feed names a winner and — for a leg that asks how or
when — how and when it ended. A final with no winner named (a draw, a no
contest, a feed still filling in) settles nothing; the book settles those.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

#: The checker's fight markets besides the moneyline, by the key the slip
#: reader returns (engine/slipgrade.MARKETS).
MARKETS = ("fight_distance", "fight_rounds", "fight_round", "win_ko", "win_sub", "win_dec", "win_finish")
#: The ones naming a fighter. A fighter's moneyline names one too.
FIGHTER_MARKETS = ("win_ko", "win_sub", "win_dec", "win_finish")
#: The ones on the whole bout.
BOUT_MARKETS = ("fight_distance", "fight_rounds", "fight_round")
#: How each is said.
WORDS = {"fight_distance": "goes the distance", "fight_rounds": "rounds", "fight_round": "ends in round",
         "win_ko": "by KO/TKO", "win_sub": "by submission", "win_dec": "by decision",
         "win_finish": "inside the distance"}
#: Each method leg's ways of winning, in the model's own keys.
METHODS = {"win_ko": ("ko",), "win_sub": ("sub",), "win_dec": ("dec",), "win_finish": ("ko", "sub")}
#: The feed's methods, in the same keys (engine/sources/espnmma.method_from_status).
FEED_METHOD = {"KO/TKO": "ko", "SUB": "sub", "DEC": "dec"}
#: The board's reasons for passing on a bout before any number exists.
NO_NUMBER = ("no_dossier", "no_data", "no_price", "clamp_kill")
#: The live fight feed, beside the other live files (engine/sliplive.FAST_DIR).
LIVE_FILE = "ufc_live.json"
#: A round, in seconds.
ROUND_S = 300.0


# ---- names --------------------------------------------------------------------------
def _key(name) -> str:
    from .teammates import _norm
    return _norm(str(name or ""))


def _words(text) -> set:
    return set(_key(text).split())


def corners(row: dict) -> tuple[str, str]:
    """(fighter a, fighter b) as the bout's label names them — the odds
    feed's names, the ones a slip prints and the model's keys use."""
    a, sep, b = str((row or {}).get("fight") or "").partition(" vs ")
    return (a.strip(), b.strip()) if sep and a.strip() and b.strip() else ("", "")


def _names(row: dict) -> list[set]:
    """Each corner's names: the label's and the dossier's."""
    a, b = corners(row)
    out = [{_key(a)}, {_key(b)}]
    for i, f in enumerate([f for f in (row or {}).get("fighters") or [] if isinstance(f, dict)][:2]):
        if f.get("name"):
            out[i].add(_key(f["name"]))
    return [{k for k in s if k} for s in out]


def which(names: list[set], name) -> int | None:
    """0 or 1, the corner ``name`` is: his full name, or — for a slip that
    prints "Jones" or "J. Jones" — the one corner whose surname (and
    initial) it is. None for neither or both."""
    want = _key(name)
    if not want:
        return None
    hits = [i for i in (0, 1) if want in names[i]]
    if len(hits) == 1:
        return hits[0]
    words = want.split()
    if len(words) > 1 and len(words[0]) > 1:
        return None                      # a full first name that matched nobody is somebody else
    initial = words[0] if len(words) > 1 else ""
    hits = [i for i in (0, 1) if any(k.split()[-1] == words[-1] and k.split()[0].startswith(initial)
                                     for k in names[i] if k)]
    return hits[0] if len(hits) == 1 else None


def _names_bout(names: list[set], text) -> bool:
    """The slip's words name this bout: a corner's full name, or both
    corners' surnames."""
    t = f" {_key(text)} "
    words = set(t.split())
    if any(f" {k} " in t for s in names for k in s):
        return True
    return all(any(k.split()[-1] in words for k in s if k) for s in names)


def fighter_of(leg: dict) -> str:
    return str(leg.get("team") or leg.get("player") or "")


# ---- the bout -----------------------------------------------------------------------
def bouts(board: dict | None) -> list[dict]:
    """Every bout on the card: its picks and its pass list."""
    b = board or {}
    return [r for r in list(b.get("picks") or []) + list(b.get("pass_list") or [])
            if isinstance(r, dict) and all(corners(r))]


def find(board: dict | None, leg: dict) -> tuple[dict, int | None] | None:
    """(the bout, the corner the leg backs — None for a leg on the whole
    bout), or None when the card has no such bout, or two fit."""
    rows = bouts(board)
    if leg.get("market") == "moneyline" or leg.get("market") in FIGHTER_MARKETS:
        hits = [(r, which(_names(r), fighter_of(leg))) for r in rows]
        hits = [(r, i) for r, i in hits if i is not None]
        return hits[0] if len(hits) == 1 else None
    text = " ".join(str(leg.get(k) or "") for k in ("game", "team", "player", "text"))
    hits = [r for r in rows if _names_bout(_names(r), text)]
    return (hits[0], None) if len(hits) == 1 else None


def timing(row: dict) -> tuple[list, list] | None:
    """When a finish lands, as the round prices assume it: the bout's
    stretches in rounds [(from, to), …] and each one's share of the
    finishes. Read back off the round prices on the market board (each
    "Under x.5" and "Ends in round r" over the chance it ends inside the
    distance). None for a bout with none."""
    rounds = 5 if int(row.get("scheduled_rounds") or 3) == 5 else 3
    inside = 1.0 - float(row.get("p_distance") or 0.0)
    if inside <= 0.0:
        return None
    unders: dict = {}
    exact: dict = {}
    for c in row.get("market_board") or []:
        if not isinstance(c, dict) or not isinstance(c.get("p_model"), (int, float)):
            continue
        sel = str(c.get("selection") or "")
        try:
            if c.get("market") == "round" and sel.startswith("Under "):
                unders[float(sel.split()[1])] = float(c["p_model"]) / inside
            elif c.get("market") == "exact_round" and sel.startswith("Ends in round "):
                exact[int(sel.rsplit(" ", 1)[1])] = float(c["p_model"]) / inside
        except (ValueError, IndexError):
            continue
    if not unders and not exact:
        return None
    cdf = dict(unders)
    if set(exact) == set(range(1, rounds + 1)):
        run = 0.0
        for r in range(1, rounds + 1):
            run += exact[r]
            cdf[float(r)] = run
    cdf[float(rounds)] = 1.0
    points = sorted(x for x in cdf if 0.0 < x <= rounds)
    out, shares, last, at = [], [], 0.0, 0.0
    for x in points:
        f = min(1.0, max(last, cdf[x]))
        out.append((at, x))
        shares.append(f - last)
        last, at = f, x
    total = sum(shares)
    if total <= 0.0:
        return None
    return out, [s / total for s in shares]


def outcomes(row: dict) -> list[tuple] | None:
    """Every way the bout can end, with its chance: [((corner, method,
    stretch), p)], the stretch None for a decision or where the bout has
    no round prices. Who wins is the board's own chance (p_final, for the
    side it judged); how, the model's own split of each corner's wins; when,
    `timing`. None for a bout the board has no number on."""
    if (row.get("reason_code") in NO_NUMBER or row.get("p_final") is None
            or not isinstance(row.get("method"), dict)):
        return None
    m = row["method"]
    keys = ("a_ko", "a_sub", "a_dec", "b_ko", "b_sub", "b_dec")
    if any(not isinstance(m.get(k), (int, float)) for k in keys):
        return None
    a = corners(row)[0]
    raw = {"a": m["a_ko"] + m["a_sub"] + m["a_dec"], "b": m["b_ko"] + m["b_sub"] + m["b_dec"]}
    if raw["a"] <= 0.0 or raw["b"] <= 0.0:
        return None
    p_a = float(row["p_final"]) if str(row.get("pick") or "") == a else 1.0 - float(row["p_final"])
    scale = {"a": p_a / raw["a"], "b": (1.0 - p_a) / raw["b"]}
    when = timing(row)
    out = []
    for c in ("a", "b"):
        for meth in ("ko", "sub"):
            p = m[f"{c}_{meth}"] * scale[c]
            if when:
                out += [((c, meth, seg), p * w) for seg, w in zip(*when)]
            else:
                out.append(((c, meth, None), p))
        out.append(((c, "dec", None), m[f"{c}_dec"] * scale[c]))
    return out


def wins_on(leg: dict, corner: int | None, outs: list[tuple], rounds: int):
    """The outcomes ``leg`` wins on, as indexes into ``outs`` — or None
    where its chance cannot be read off them (a round leg on a bout with
    no round prices, or at a number between the stretches)."""
    market, side = leg.get("market"), str(leg.get("side") or "").lower()
    me = "ab"[corner] if corner is not None else None
    line = float(leg.get("line") or 0.0)
    timed = all(o[0][2] is not None for o in outs if o[0][1] != "dec")
    edges = {seg[1] for (_c, _m, seg), _p in outs if seg} | {seg[0] for (_c, _m, seg), _p in outs if seg}
    if market in ("fight_rounds", "fight_round") and (not timed or not edges):
        return None
    if market == "fight_rounds" and line not in edges:
        return None
    if market == "fight_round" and not ({line - 1.0, line} <= edges and 1 <= line <= rounds):
        return None
    got = []
    for i, ((c, meth, seg), _p) in enumerate(outs):
        if market == "moneyline":
            ok = c == me
        elif market in METHODS:
            ok = c == me and meth in METHODS[market]
        elif market == "fight_distance":
            ok = (meth == "dec") == (side == "yes")
        elif market == "fight_rounds":
            past = meth == "dec" or seg[0] >= line
            ok = past if side == "over" else not past
        else:                                       # fight_round
            ok = meth != "dec" and seg[0] >= line - 1.0 and seg[1] <= line
        if ok:
            got.append(i)
    return got


# ---- the leg ------------------------------------------------------------------------
def _pct(p) -> str:
    return f"{round(float(p) * 100)}%"


def name(leg: dict) -> str:
    """The leg in words, as the card names it."""
    market, side = leg.get("market"), str(leg.get("side") or "").lower()
    who = fighter_of(leg)
    bout = str(leg.get("game") or "") or who or "the fight"
    if market == "fight_distance":
        return f"{bout} {'goes' if side != 'no' else 'does not go'} the distance"
    if market == "fight_rounds":
        return f"{bout} {side} {float(leg.get('line') or 0):g} rounds"
    if market == "fight_round":
        return f"{bout} ends in round {int(float(leg.get('line') or 0))}"
    return f"{who} {WORDS.get(market, market)}"


def price(board: dict | None, leg: dict) -> dict | None:
    """{"prob", "row"} for one fight leg off the card, or None when the card
    has no such bout. ``prob`` is None, with the reason among the row's
    facts, where the board has no number on it."""
    got = find(board, leg)
    if got is None:
        return None
    bout, corner = got
    a, b = corners(bout)
    rounds = 5 if int(bout.get("scheduled_rounds") or 3) == 5 else 3
    who = (a, b)[corner] if corner is not None else ""
    other = (b, a)[corner] if corner is not None else ""
    row = {"league": "ufc", "fight": f"{a} vs {b}", "home": a, "away": b, "team": who, "opponent": other,
           "event_date": str((board or {}).get("event_date") or ""), "facts": [], "fair_only": False}
    if leg.get("market") == "moneyline" and who and str(bout.get("pick") or "") == who and bout.get("odds"):
        row["odds"] = bout["odds"]              # the book's price the card read for his side
    outs = outcomes(bout)
    if outs is None:
        why = str(bout.get("why") or "the model put no number on it")
        row["refused"] = why
        row["facts"].append(("Our model", f"No number on this fight: {why}"))
        return {"prob": None, "row": row}
    wins = wins_on(leg, corner, outs, rounds)
    if wins is None:
        row["refused"] = "no round prices on this fight"
        row["facts"].append(("Our model", "No number on this bet: the card has no round prices on this "
                                          "fight (too few stored finishes at its length)"))
        _bout_facts(row, bout, outs, leg, corner)
        return {"prob": None, "row": row}
    p = sum(outs[i][1] for i in wins)
    row.update(outcomes=[o[1] for o in outs], wins=wins, fair_only=leg.get("market") != "moneyline")
    row["facts"].append(("Our model", _head(leg, bout, outs, corner, p)))
    _bout_facts(row, bout, outs, leg, corner)
    return {"prob": max(0.0, min(1.0, p)), "row": row}


def _won_by(outs, corner: str, meths) -> float:
    return sum(p for (c, meth, _s), p in outs if c == corner and meth in meths)


def _head(leg: dict, bout: dict, outs, corner, p: float) -> str:
    market = leg.get("market")
    a, b = corners(bout)
    if corner is not None:
        me = "ab"[corner]
        mine = _won_by(outs, me, ("ko", "sub", "dec"))
        who = (a, b)[corner]
        if market == "moneyline":
            pick_a = str(bout.get("pick") or "") == a
            mkt = bout.get("p_market")
            theirs = None if mkt is None else (float(mkt) if (corner == 0) == pick_a else 1.0 - float(mkt))
            return (f"{who} wins {_pct(p)} by our model, held toward the market the way every UFC price on "
                    f"the board is" + (f" (the books, margin out: {_pct(theirs)})" if theirs is not None else ""))
        share = p / mine if mine > 0 else 0.0
        return (f"{who} {WORDS[market]} {_pct(p)}: {_pct(share)} of his wins go that way in our model, on "
                f"the board's own {_pct(mine)} that he wins")
    if market == "fight_distance":
        return (f"Ends inside the distance {_pct(p)} by our model" if leg.get("side") == "no" else
                f"Goes the distance {_pct(p)} by our model")
    return f"{name(dict(leg, game=f'{a} vs {b}'))}: {_pct(p)} by our model"


def _bout_facts(row: dict, bout: dict, outs, leg: dict, corner) -> None:
    facts = row["facts"]
    a, b = corners(bout)
    split = []
    for c, who in (("a", a), ("b", b)):
        won = _won_by(outs, c, ("ko", "sub", "dec"))
        split.append(f"{who} {_pct(won)} (KO {_pct(_won_by(outs, c, ('ko',)))}, submission "
                     f"{_pct(_won_by(outs, c, ('sub',)))}, decision {_pct(_won_by(outs, c, ('dec',)))})")
    facts.append(("How it ends", "; ".join(split)))
    if leg.get("market") in BOUT_MARKETS:
        rr = bout.get("round_read") or {}
        if rr.get("note"):
            facts.append(("Rounds", str(rr["note"])))
    if leg.get("market") != "moneyline":
        facts.append(("Fair number", "the UFC board shows this number to shop and never stakes it"))
    if bout.get("kind") == "pick":
        label = str(bout.get("grade_label") or "")
        facts.append(("The board", f"Our pick on this fight: {bout.get('selection') or bout.get('pick')}"
                                   + (f" ({label}, grade {bout.get('grade_score')})" if label else "")))
    elif bout.get("why"):
        facts.append(("The board", f"We pass on this fight: {bout['why']}"))
    notes = [str(n) for n in bout.get("style_notes") or [] if n]
    if notes:
        facts.append(("Style", notes[0]))
    if bout.get("line_note"):
        facts.append(("Line", str(bout["line_note"])))
    briefs = [f for f in bout.get("fighters") or [] if isinstance(f, dict)][:2]
    for i, f in enumerate(briefs):
        if corner is not None and i != corner:
            continue
        for flag in (f.get("red_flags") or [])[:2]:
            facts.append(("Watch", f"{(a, b)[i]}: {flag}"))


def together(legs: list[dict]) -> float | None:
    """Our chance every leg in ``legs`` — all on one bout, each priced by
    `price` — wins: the share of the bout's outcomes all of them win on.
    None when any leg carries no outcomes."""
    rows = [l.get("row") or {} for l in legs]
    if not rows or any("wins" not in r or "outcomes" not in r for r in rows):
        return None
    common = set(rows[0]["wins"])
    for r in rows[1:]:
        common &= set(r["wins"])
    return max(0.0, min(1.0, sum(rows[0]["outcomes"][i] for i in common)))


def bout_of(leg: dict) -> str:
    """The bout a priced fight leg is on, or "" for any other leg."""
    r = leg.get("row") or {}
    return str(r.get("fight") or "") if r.get("league") == "ufc" and "wins" in r else ""


# ---- the fight, as it happens --------------------------------------------------------
def _clock_s(clock) -> float | None:
    a, sep, b = str(clock or "").strip().partition(":")
    if not sep or not a.isdigit() or not b.isdigit():
        return None
    return int(a) * 60.0 + int(b)


def result(leg: dict, corner: int | None, winner: int | None, method: str | None,
           rnd, clock) -> str | None:
    """"won" or "lost" for a leg on a finished bout, or None where the feed
    has not said enough: who won (any leg), how (a method or distance leg,
    a finished round leg) and when (a round leg on a finish)."""
    if winner is None:
        return None
    market, side = leg.get("market"), str(leg.get("side") or "").lower()
    meth = FEED_METHOD.get(str(method or ""))
    if market == "moneyline":
        return "won" if winner == corner else "lost"
    if market in METHODS:
        if winner != corner:
            return "lost"
        if meth is None:
            return None
        return "won" if meth in METHODS[market] else "lost"
    if meth is None:
        return None
    if market == "fight_distance":
        return "won" if (meth == "dec") == (side != "no") else "lost"
    line = float(leg.get("line") or 0.0)
    if meth == "dec":
        return ("won" if side == "over" else "lost") if market == "fight_rounds" else "lost"
    try:
        r = int(rnd)
    except (TypeError, ValueError):
        return None
    if market == "fight_round":
        return "won" if r == int(line) else "lost"
    secs = _clock_s(clock)
    if secs is None or r < 1:
        return None
    at = (r - 1) + min(secs, ROUND_S) / ROUND_S
    return ("won" if at > line else "lost") if side == "over" else ("won" if at < line else "lost")


def live_state(leg: dict, fast_dir=None, now: float | None = None) -> dict | None:
    """Where the leg's bout stands on the live fight feed, in the shape the
    checker's other leagues give (engine/sliplive.live_state): "pre",
    "live" with the round and the clock, or "final" and the leg's result.
    None when the feed is old (the refresher has stopped) or the bout is
    not on it."""
    from .sliplive import FAST_DIR, FAST_FRESH_S
    path = Path(fast_dir or FAST_DIR) / LIVE_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        age = (time.time() if now is None else now) - os.stat(path).st_mtime
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or age > FAST_FRESH_S:
        return None
    market = leg.get("market")
    hit = None
    for bout in doc.get("bouts") or []:
        fighters = [f for f in bout.get("fighters") or [] if isinstance(f, dict)][:2]
        if len(fighters) != 2:
            continue
        names = [{_key(f.get("name"))} - {""} for f in fighters]
        if market == "moneyline" or market in FIGHTER_MARKETS:
            c = which(names, fighter_of(leg))
            if c is None:
                continue
        else:
            text = " ".join(str(leg.get(k) or "") for k in ("game", "team", "player", "text"))
            if not _names_bout(names, text):
                continue
            c = None
        if hit is not None:
            return None                       # two bouts fit: a guess is not graded
        hit = (bout, fighters, c)
    if hit is None:
        return None
    bout, fighters, corner = hit
    st = bout.get("status") or {}
    state = {"pre": "pre", "in": "live", "post": "final"}.get(str(st.get("state") or ""), "")
    out = {"state": state, "home": str(fighters[0].get("name") or ""), "away": str(fighters[1].get("name") or "")}
    if state == "live":
        out["clock"] = " ".join(x for x in (f"R{st['round']}" if st.get("round") else "",
                                            str(st.get("clock") or "")) if x)
    if state != "final":
        return out
    won = [i for i, f in enumerate(fighters) if f.get("winner")]
    winner = won[0] if len(won) == 1 else None
    out["clock"] = " ".join(x for x in (str(st.get("method") or ""),
                                        f"R{st['round']} {st.get('clock') or ''}".strip() if st.get("round") else "")
                            if x)
    res = result(leg, corner, winner, st.get("method"), st.get("round"), st.get("clock"))
    if res is not None:
        out["result"] = res
    elif winner is None:
        out["note"] = "no winner named on the feed: a draw or no contest is settled by your book"
    else:
        out["note"] = "the feed has not said how or when it ended"
    return out
