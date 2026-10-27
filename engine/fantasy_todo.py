"""Your week, as a to-do list: what to do now, in the order it matters.

Ethan, 2026-10-27: "I don't know how fantasy works … and that the fantasy
room is actually a useful tool and doing what it's supposed to be." The
league desk already held every answer (the best lineup and the swaps, the
head-to-head, the free agents, the trades), each in its own section, and a
manager new to the game could not tell which one mattered today. ESPN's 2025
app answers it with a dashboard that flags actions (docs/FANTASY.md). This is
ours: one list at the top of the desk, each line a thing to do, the points it
is worth, and the section that says more.

THE ORDER is the order a lineup is lost in: a starter who will not play (out,
on a bye) first, then the rest of the lineup's fixes by what each gains, a
starter who may not play (and when his game kicks off, because a manager can
wait on a late game and not an early one), the week's win chance, the best
pickup for this roster, next week's byes among the starters, and a trade that
helps both teams. Nothing is listed that is not worth doing: no fix under half
a point, no pickup the lineup would not start, no trade one side loses.

Standard library only. Pure: every input is the desk's own.
"""
from __future__ import annotations

#: A fix or a pickup smaller than this is not worth a line.
MIN_GAIN = 0.5
#: Shown at most, lineup fixes.
MAX_FIXES = 3


def _pts(x) -> str:
    return f"{float(x):.1f}"


def _week(lineup: dict, name: str) -> dict:
    for s in (lineup or {}).get("starters") or []:
        if s.get("player") == name:
            return s.get("week") or {}
    for s in (lineup or {}).get("bench") or []:
        if s.get("player") == name:
            return s.get("week") or {}
    return {}


#: How a status reads after "is": "is out", "is on IR".
STATUS_WORDS = {"OUT": "out", "IR": "on IR", "PUP": "on the PUP list", "SUSPENDED": "suspended",
                "SUS": "suspended", "NFI": "on the NFI list", "INACTIVE": "inactive"}


def _why_out(wk: dict) -> str:
    if wk.get("bye"):
        return "on a bye"
    st = str(wk.get("status") or "").strip()
    if wk.get("play") == 0 and st:
        return STATUS_WORDS.get(st.upper(), st.lower())
    return ""


def _clock(hhmm: str) -> str:
    """nflverse's "13:00" (Eastern) as "1:00 PM ET"; anything else as given."""
    try:
        h, m = (int(x) for x in str(hhmm).split(":")[:2])
    except ValueError:
        return str(hhmm or "")
    return f"{(h % 12) or 12}:{m:02d} {'PM' if h >= 12 else 'AM'} ET"


def _when(kickoffs: dict | None, team: str | None) -> str:
    k = (kickoffs or {}).get(team or "") or {}
    return " ".join(x for x in (k.get("day"), _clock(k.get("time") or "") if k.get("time") else "") if x)


def build(*, lineup: dict | None = None, h2h: dict | None = None, pickups: dict | None = None,
          trades: list | None = None, next_byes: list | None = None, kickoffs: dict | None = None,
          week: int | None = None) -> list:
    """The list: ``[{kind, tone, title, detail, gain, section}]``.

    ``lineup`` is `fantasy_lineup.lineup` for this roster (with `current`
    when the platform says who is in), ``h2h`` the desk's head-to-head,
    ``pickups`` `fantasy_waivers.for_roster`, ``trades`` the trade finder's,
    ``next_byes`` [(player, team)] of starters off next week, ``kickoffs``
    {team: {day, time}}."""
    out: list = []
    L = lineup or {}
    swaps = [s for s in L.get("swaps") or [] if float(s.get("gain") or 0) >= MIN_GAIN]
    # 1. A starter who will not play, then the other fixes.
    fixes = []
    for s in swaps:
        wk = _week(L, s.get("out")) if s.get("out") else {}
        why = _why_out(wk)
        title = (f"{s['out']} is {why}: start {s['in']}" if s.get("out") and why
                 else f"Start {s['in']} over {s['out']}" if s.get("out")
                 else f"Start {s['in']}")
        fixes.append({"kind": "lineup", "tone": "act" if why else "do",
                      "title": title, "gain": round(float(s["gain"]), 1),
                      "detail": f"+{_pts(s['gain'])} projected points this week", "section": "lineup",
                      "_rank": 0 if why else 1})
    fixes.sort(key=lambda f: (f["_rank"], -f["gain"]))
    for f in fixes[:MAX_FIXES]:
        f.pop("_rank", None)
        out.append(f)
    if L.get("starters") and L.get("current") is None:
        names = [s["player"] for s in L["starters"] if s.get("player")]
        out.append({"kind": "lineup", "tone": "do", "title": "Set this lineup",
                    "detail": ", ".join(names), "gain": None, "section": "lineup"})
    # 2. A starter who may not play.
    for s in L.get("starters") or []:
        wk = s.get("week") or {}
        p = wk.get("play")
        if s.get("player") and p is not None and 0 < float(p) < 1:
            when = _when(kickoffs, wk.get("team"))
            out.append({"kind": "risk", "tone": "warn",
                        "title": f"{s['player']} is {str(wk.get('status') or 'listed').lower()}: "
                                 f"{round(float(p) * 100)}% to play",
                        "detail": (f"His game kicks off {when}; " if when else "")
                        + "have a bench player who plays later ready to swap in.",
                        "gain": None, "section": "lineup"})
    # 3. The week's matchup.
    H = h2h or {}
    if H.get("win_prob") is not None and (H.get("me") or {}).get("points") is not None:
        wp = float(H["win_prob"])
        them = (H.get("them") or {}).get("points")
        opp = H.get("opponent") or "your opponent"
        out.append({"kind": "matchup", "tone": "good" if wp >= 0.55 else "warn" if wp < 0.45 else "info",
                    "title": f"{round(wp * 100)}% to win against {opp}",
                    "detail": (f"Projected {_pts(H['me']['points'])} to {_pts(them)}" if them is not None
                               else f"Projected {_pts(H['me']['points'])}")
                    + (", a coin flip: the swings below decide it" if H.get("coinflip") else ""),
                    "gain": None, "section": "h2h"})
    # 4. The best pickup for this roster.
    P = pickups or {}
    top = (P.get("pickups") or [None])[0]
    if top and float(top.get("gain") or 0) >= MIN_GAIN:
        b = top.get("bid") or {}
        bid_txt = (" Bid $0–1: a one-week stream." if b.get("rule") == "stream" else
                   f" Bid ${b['low']}–${b['high']} of your ${b['of']}." if b.get("high") else "")
        drop = top.get("drop") if "drop" in top else (P.get("drop") or {})
        drop_txt = ""
        if drop and drop.get("player"):
            drop_txt = (f" Drop {drop['player']}." if drop.get("ppg") is None
                        else f" Drop {drop['player']} ({_pts(drop['ppg'])} a game).")
        out.append({"kind": "pickup", "tone": "do",
                    "title": f"Pick up {top['player']} ({'D/ST' if top['position'] == 'DEF' else top['position']})",
                    "detail": (f"+{_pts(top['gain'])} to your best lineup this week"
                               + (f", in for {top['replaces']}" if top.get("replaces") else "") + "."
                               + bid_txt + drop_txt),
                    "gain": round(float(top["gain"]), 1), "section": "pickups"})
    # 5. Next week's byes among the starters.
    if next_byes:
        names = [p for p, _t in next_byes]
        out.append({"kind": "byes", "tone": "info",
                    "title": f"Next week: {len(names)} starter{'s' if len(names) != 1 else ''} on a bye",
                    "detail": ", ".join(names) + ". Line up a replacement on this week's waivers.",
                    "gain": None, "section": "lineup"})
    # 6. A trade that helps both teams.
    good = [t for t in trades or [] if float(t.get("my_gain") or 0) > 0 and float(t.get("their_gain") or 0) > 0]
    if good:
        t = good[0]
        out.append({"kind": "trade", "tone": "info",
                    "title": f"Trade idea with {t.get('with') or 'a rival'}",
                    "detail": (f"Your {', '.join(t.get('give') or [])} for their {', '.join(t.get('get') or [])}: "
                               f"you +{_pts(t['my_gain'])} a week, them +{_pts(t['their_gain'])}."),
                    "gain": round(float(t["my_gain"]), 1), "section": "trades"})
    return out


def kickoffs_from(week_doc: dict | None) -> dict:
    """{team: {day, time}} off the week file's `teams` (date, kickoff), in
    the words the list uses: "Sun 1:00 PM"."""
    import datetime as _dt
    out = {}
    for team, t in ((week_doc or {}).get("teams") or {}).items():
        day = ""
        try:
            day = _dt.date.fromisoformat(str(t.get("date") or "")[:10]).strftime("%a")
        except ValueError:
            day = ""
        out[team] = {"day": day, "time": str(t.get("kickoff") or "")}
    return out
