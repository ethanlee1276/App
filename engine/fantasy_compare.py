"""Start A or B? Two to four players side by side, and the call.

Ethan, 2026-10-27: "I don't know how fantasy works … create more features
and think of more features and invent more things for our fantasy room."
The question every manager asks every week is "who do I start, A or B?"
(docs/FANTASY.md, item 4). The Fantasy room drew each player's week on its
own row and had no way to put two side by side; Ask answered it in words,
for members only. This answers it for anyone, on the numbers the room
already draws, and Ask quotes the same answer (engine/askbot.fantasy_points).

THE CALL is the player with the most points this week at the chance he
plays: each row's `expected`, the number the league desk's lineup is solved
on. With it, HOW OFTEN he outscores each of the others, from the two weeks
as the head-to-head models them (engine/fantasy_h2h): normal around the
projection with the measured spread (`sd`, fantasyweekfit), and a listed
player as a mixture of zero and his week (fantasyweek.week_entry). Under
that model the chance is exact, four cases: both play, only one, neither.
A position with no measured spread (kickers) gets no chance, only points,
and the answer says so rather than inventing one.

THE FLOOR AND THE CEILING are the measured 10th and 90th percentiles of
his week if he plays (`range`): eight weeks in ten land between them. When
the points are close and the call has the lower floor or the lower ceiling,
it says so, because which one you want depends on your matchup: a
favourite wants the floor, an underdog the ceiling. fantasy_h2h's swings
find the same thing from the real margin when a league is linked.

THE CLOCK. A listed player is decided about 90 minutes before his own
kickoff, when his team names its inactives, and every player locks at his
own kickoff. When the listed one plays first, you know before you have to
choose, so the call is the one if he plays. When he plays after the other,
the other is locked before his status is out, so the call is at his chance
to play. Newcomers lose weeks to this; nothing on the page said it.

Standard library only. Pure: rows in, an answer out.
"""
from __future__ import annotations

import datetime as _dt
import math

#: Most players side by side.
MAX_PLAYERS = 4
#: Scorings the week's rows carry points for (fantasyweek: ppr, half, standard).
SCORINGS = {"ppr": "PPR", "half": "half-PPR", "standard": "standard"}
#: A chance inside this of a half is a coin flip, and is said as one.
COIN = 0.05
#: Points this close are close enough for the floor and the ceiling to decide.
CLOSE_POINTS = 2.0
#: A floor or a ceiling has to differ by this much to be worth a sentence.
EDGE_RANGE = 1.0
#: NFL teams name their inactives this long before kickoff.
INACTIVES_MINUTES = 90
#: The 10th to 90th percentile of a normal spans this many spreads.
SPAN_SD = 2.563


def _phi(z: float) -> float:
    """The standard normal CDF, from the stdlib's error function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def scoring_key(scoring) -> str:
    s = str(scoring or "ppr").lower().replace("-", "").replace("_", "").replace(" ", "")
    return {"halfppr": "half", "half": "half", "standard": "standard", "std": "standard",
            "nonppr": "standard"}.get(s, "ppr")


def model(row: dict, scoring: str = "ppr") -> dict:
    """One player's week as the call reads it: points if he plays, the
    chance he plays, the points at that chance, the spread, the floor and
    the ceiling, all under ``scoring``. The spread and the range are
    measured on PPR and scale with his points, first order, as the
    head-to-head scales them (fantasy_h2h.team_total)."""
    key = scoring_key(scoring)
    ppr = row.get("ppr")
    ppr = float(ppr) if ppr is not None else float(row.get("expected") or 0.0)
    pts = row.get(key) if key != "ppr" else None
    if_plays = float(pts) if pts is not None else ppr
    scale = if_plays / ppr if ppr > 0 else 1.0
    play = row.get("play")
    play = 1.0 if play is None else max(0.0, min(1.0, float(play)))
    sd = row.get("sd")
    sd = float(sd) * scale if sd is not None else None
    lo = hi = None
    rg = row.get("range")
    if rg and len(rg) == 2 and rg[0] is not None and rg[1] is not None:
        lo, hi = float(rg[0]) * scale, float(rg[1]) * scale
        if sd is None:
            sd = (hi - lo) / SPAN_SD
        lo, hi = round(lo, 1), round(hi, 1)
    return {"if_plays": if_plays, "play": play, "points": if_plays * play,
            "sd": sd if sd and sd > 0 else None, "lo": lo, "hi": hi}


def beats(a: dict, b: dict, *, if_both_play: bool = False) -> float | None:
    """P(A outscores B) from two `model`s; None without both spreads.

    A listed player is zero or his week: both play (the two normals), A
    alone (a player who plays beats one who does not), B alone, neither (a
    tie, counted half)."""
    sa, sb = a.get("sd"), b.get("sd")
    if not sa or not sb:
        return None
    both = _phi((a["if_plays"] - b["if_plays"]) / math.sqrt(sa * sa + sb * sb))
    if if_both_play:
        return both
    pa, pb = a["play"], b["play"]
    return pa * pb * both + pa * (1 - pb) + (1 - pa) * (1 - pb) * 0.5


# --- the clock -----------------------------------------------------------------------------

def _eastern(when: _dt.datetime) -> _dt.datetime:
    """A UTC time on the Eastern clock: the zone database where the box has
    one, else the US rule (daylight time from the second Sunday of March to
    the first Sunday of November)."""
    try:
        from zoneinfo import ZoneInfo
        return when.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    except Exception:                                         # noqa: BLE001 — no tz database
        y = when.year
        mar = _dt.datetime(y, 3, 8 + (6 - _dt.date(y, 3, 8).weekday()) % 7, 7)
        nov = _dt.datetime(y, 11, 1 + (6 - _dt.date(y, 11, 1).weekday()) % 7, 6)
        naive = when.replace(tzinfo=None)
        return naive - _dt.timedelta(hours=4 if mar <= naive < nov else 5)


def kickoff(game: dict | None) -> _dt.datetime | None:
    """His game's kickoff on the Eastern clock: the board carries nflverse's
    "13:00" (Eastern) beside the date, or an ISO time in UTC."""
    g = game or {}
    k, d = str(g.get("kickoff") or ""), str(g.get("date") or "")[:10]
    try:
        if "T" in k:
            t = _dt.datetime.fromisoformat(k.replace("Z", "+00:00"))
            return _eastern(t) if t.tzinfo else t
        if k and d:
            h, m = (int(x) for x in k.split(":")[:2])
            return _dt.datetime.fromisoformat(d).replace(hour=h, minute=m)
    except ValueError:
        return None
    return None


def clock(t: _dt.datetime | None) -> str:
    """"Sun 1:00 PM ET"."""
    if t is None:
        return ""
    return f"{t.strftime('%a')} {(t.hour % 12) or 12}:{t.minute:02d} {'PM' if t.hour >= 12 else 'AM'} ET"


# --- the answer ----------------------------------------------------------------------------

def _they(row: dict) -> tuple[str, str, str]:
    """A player is "he"; a team defense is "they": (subject, outscores,
    scores)."""
    return ("they", "outscore", "score") if row.get("position") == "DEF" else ("he", "outscores", "scores")


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def _pts(x: float) -> str:
    return f"{x:.1f}"


def _card(row: dict, m: dict) -> dict:
    """What the side-by-side shows for one player: free fields, and a
    member's stat line, touchdown chance and reasons when the row has them
    (a free reader's row does not: fantasyweek.free_view)."""
    g = row.get("game") or {}
    ko = kickoff(g)
    out = {"player": row.get("player"), "team": row.get("team"), "position": row.get("position"),
           "opponent": row.get("opponent"),
           "home": (g.get("home") == row.get("team")) if g.get("home") and row.get("team") else None,
           "points": round(m["points"], 1), "play": round(m["play"], 2),
           "floor": m["lo"], "ceiling": m["hi"],
           "sd": None if m["sd"] is None else round(m["sd"], 2),
           "kickoff": clock(ko) or None}
    if m["play"] < 1.0:
        out["if_plays"] = round(m["if_plays"], 1)
    for k in ("status", "practice", "headshot"):
        if row.get(k):
            out[k] = row[k]
    mu = row.get("matchup") or {}
    if mu.get("grade") or mu.get("text"):
        out["matchup"] = {k: mu.get(k) for k in ("grade", "text") if mu.get(k)}
    if row.get("proj"):
        out["line"] = {k: round(float(v), 2 if k in ("pass_td", "pass_int", "rush_td", "rec_td") else 1)
                       for k, v in row["proj"].items() if isinstance(v, (int, float))}
    if row.get("td_prob") is not None:
        out["td_prob"] = round(float(row["td_prob"]), 3)
    why = [s.get("why") for s in row.get("reasons") or [] if isinstance(s, dict) and s.get("why")]
    if why:
        out["why"] = why[:2]
    if row.get("dst"):
        d = row["dst"]
        out["dst"] = {"sacks": round(float(d.get("sack") or 0), 1),
                      "takeaways": round(float(d.get("int") or 0) + float(d.get("fum_rec") or 0), 1)}
    return out


def _known_first(q: dict, others: list) -> bool:
    """True when ``q``'s inactives are out before any of ``others`` locks:
    his kickoff is no later than every one of theirs, all of them known."""
    kq = kickoff(q.get("game"))
    ks = [kickoff(o.get("game")) for o in others]
    return kq is not None and bool(ks) and all(k is not None and kq <= k for k in ks)


def _clock_note(q: dict, mq: dict, o: dict, mo: dict, start: str) -> str:
    """A listed player against the one he is weighed with, in the order the
    day decides it. ``start`` is the call."""
    name, other = q["player"], o["player"]
    tag = f"{str(q.get('status') or 'listed').lower()}, {_pct(mq['play'])} to play"
    kq, ko = kickoff(q.get("game")), kickoff(o.get("game"))
    p_if = beats(mq, mo, if_both_play=True)
    better_if = (p_if > 0.5) if p_if is not None else mq["if_plays"] > mo["if_plays"]
    if not better_if:
        return f"{name} is {tag}, and even if he plays {other} is the better start."
    if kq is None or ko is None:
        return (f"{name} is {tag}. His team names its inactives about 90 minutes before kickoff: "
                f"if he is active he is the better start; if not, {other}.")
    told = clock(kq - _dt.timedelta(minutes=INACTIVES_MINUTES))
    if kq <= ko:
        return (f"{name} is {tag}: his inactives are out about {told}, before {other}'s game "
                f"({clock(ko)}). Active: start him. Out: start {other}.")
    if start == name:
        return (f"{name} is {tag}, and his game ({clock(kq)}) is after {other}'s ({clock(ko)}): if he "
                f"sits, {other} is already locked, so only a bench player in a game at {clock(kq)} or "
                f"later can replace him. Have one ready.")
    return (f"{name} is {tag}, and his game ({clock(kq)}) is after {other}'s ({clock(ko)}): {other} "
            f"locks before {name}'s inactives are out (about {told}), so this is decided on the "
            f"chance, and on the chance it is {other}. With a bench player in a game at {clock(kq)} "
            f"or later to swap in if he sits, {name} is worth the risk.")


def compare(rows: list, scoring: str = "ppr") -> dict:
    """Two to four of the week's rows side by side, best first, with the
    call, how often the call outscores each of the others, and the notes
    that decide a close one. ``rows`` are the week file's rows (a member's
    or a free reader's).

    THE CALL, two ways. Ordinarily the most points at the chance he plays.
    But when the best start if everyone plays is a listed player whose
    inactives are out before the others lock, nothing has to be decided on
    the chance: the call is his, if he is active, and the next best's if
    he is not."""
    key = scoring_key(scoring)
    got = [r for r in rows or [] if isinstance(r, dict) and r.get("player")][:MAX_PLAYERS]
    if len(got) < 2:
        return {"error": "pick two to four players"}
    ms = {r["player"]: model(r, key) for r in got}
    got.sort(key=lambda r: (-ms[r["player"]]["points"], r["player"]))
    live = [r for r in got if ms[r["player"]]["play"] > 0] or got
    best_if = max(live, key=lambda r: (ms[r["player"]]["if_plays"], -got.index(r)))
    mb = ms[best_if["player"]]
    rest = [r for r in got if r is not best_if]
    conditional = 0 < mb["play"] < 1 and _known_first(best_if, rest)
    if conditional:
        got = [best_if] + rest
    lead, ml = got[0], ms[got[0]["player"]]
    pairs = []
    for r in got[1:]:
        m = ms[r["player"]]
        p = beats(ml, m)
        p_if = beats(ml, m, if_both_play=True)
        pairs.append({"a": lead["player"], "b": r["player"], "edge": round(ml["points"] - m["points"], 1),
                      "p": None if p is None else round(p, 3),
                      "p_if_both_play": None if p_if is None else round(p_if, 3)})
    second, ms2 = got[1], ms[got[1]["player"]]
    top = pairs[0]
    coin = not conditional and top["p"] is not None and abs(top["p"] - 0.5) < COIN
    notes: list = []
    # Who will not play at all.
    for r in got:
        if ms[r["player"]]["play"] <= 0:
            notes.append(f"{r['player']} is {str(r.get('status') or 'out').lower()}: he scores nothing this week.")
    # The clock, for a listed player against the one he is weighed with
    # (the conditional call already says it for its own man).
    for r in got:
        m = ms[r["player"]]
        if 0 < m["play"] < 1 and not (conditional and r is lead):
            o = second if r is lead else lead
            notes.append(_clock_note(r, m, o, ms[o["player"]], lead["player"]))
    # The floor and the ceiling, when the points leave it open. Between two
    # who will play: a listed man's floor is a zero, whatever his range.
    close = coin or (not conditional and top["edge"] <= CLOSE_POINTS)
    sure = ml["play"] >= 1 and ms2["play"] >= 1
    said = False
    if close and sure and ml["lo"] is not None and ms2["lo"] is not None:
        if ms2["lo"] - ml["lo"] >= EDGE_RANGE:
            he, _o, sc = _they(second)
            notes.append(f"{second['player']} is the safer start: eight weeks in ten {he} {sc} at least "
                         f"{_pts(ms2['lo'])}, to {lead['player']}'s {_pts(ml['lo'])}. Favoured this week? "
                         f"The safer start is the better one when the points are this close.")
            said = True
        if ms2["hi"] - ml["hi"] >= EDGE_RANGE:
            he = _they(second)[0]
            notes.append(f"{second['player']} {'have' if he == 'they' else 'has'} the bigger week in "
                         f"{'them' if he == 'they' else 'him'}: one week in ten {he} "
                         f"{'pass' if he == 'they' else 'passes'} {_pts(ms2['hi'])}, to {lead['player']}'s "
                         f"{_pts(ml['hi'])}. The underdog this week? That is the start that can win it.")
            said = True
    if coin and not said:
        notes.append("Too close for the numbers to split them: either is a fine start.")
    unmeasured = sorted({str(r.get("position") or "") for r in got if ms[r["player"]]["sd"] is None})
    if unmeasured:
        what = ", ".join("kickers" if p == "K" else f"{p}s" for p in unmeasured if p) or "these players"
        notes.append(f"No measured spread for {what} yet, so the call is on points alone, with no chance "
                     f"to outscore.")
    if conditional:
        told = clock(kickoff(lead.get("game")) - _dt.timedelta(minutes=INACTIVES_MINUTES))
        p_if = top["p_if_both_play"]
        before = (f"before {second['player']}'s game locks" if len(got) == 2
                  else "before the others' games lock")
        text = (f"Wait on {lead['player']} ({str(lead.get('status') or 'listed').lower()}, {_pct(ml['play'])} "
                f"to play): his inactives are out about {told}, {before}. Active: start him"
                + (f" (he outscores {second['player']} {_pct(p_if)} of the time when he plays)" if p_if is not None
                   else "") + f". Out: start {second['player']}.")
    elif top["p"] is None:
        text = f"Start {lead['player']}: {_pts(top['edge'])} more points this week."
    elif coin:
        he, outs, _s = _they(lead)
        text = (f"A coin flip: {lead['player']} by {_pts(top['edge'])} points, and {he} {outs} "
                f"{second['player']} {_pct(top['p'])} of the time.")
    else:
        out_ = [r["player"] for r in got[1:] if ms[r["player"]]["play"] <= 0]
        beat = ", ".join(f"{pr['b']} {_pct(pr['p'])}" for pr in pairs
                         if pr["p"] is not None and pr["b"] not in out_)
        he, outs, _s = _they(lead)
        text = (f"Start {lead['player']}: {he} {outs} {beat} of the time." if beat
                else f"Start {lead['player']}: {' and '.join(out_)} {'is' if len(out_) == 1 else 'are'} out.")
    if text.endswith(" out."):
        # The call already says who is out; the note would say it twice.
        notes = [n for n in notes if not n.endswith("he scores nothing this week.")]
    return {
        "scoring": SCORINGS[key],
        "players": [_card(r, ms[r["player"]]) for r in got],
        "call": {"start": lead["player"], "order": [r["player"] for r in got], "text": text,
                 "edge": top["edge"], "p": top["p"], "coin": coin, "conditional": conditional,
                 "if_out": second["player"] if conditional else None},
        "pairs": pairs,
        "notes": notes,
    }


def pick(doc: dict, names: list) -> tuple[list, list]:
    """(rows, unknown): the week's rows for ``names`` in the order asked,
    joined on the week's own spellings (fantasyweek.index), team defenses
    by any of their names (dstproj.team_of)."""
    from . import dstproj, fantasyweek
    from .backtest import _norm
    idx = fantasyweek.index(doc or {})
    defs = {r.get("team"): r for r in (doc or {}).get("players") or [] if r.get("position") == "DEF"}
    rows, unknown, seen = [], [], set()
    for n in names or []:
        n = str(n or "").strip()[:80]
        if not n:
            continue
        r = idx.get(_norm(n))
        if r is None:
            club = dstproj.team_of(n)
            r = defs.get(club) if club else None
        if r is None:
            unknown.append(n)
        elif r.get("player") not in seen:
            seen.add(r.get("player"))
            rows.append(r)
    return rows[:MAX_PLAYERS], unknown
