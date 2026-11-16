"""Was the data right? What a finished game's report said before it, checked (2026-11-16).

Ethan, 2026-11-16: "think about what users would want to see after the game's
over. Like, they'd probably want to see if the data we were giving them were
correct or not, and the read we had was correct or not, and all that stuff. So
we need to fact check ourselves after the game's over and see if we were
correct or not."

engine/reportgrade grades the reads, a player's or an offense's night against
its own average. This module checks the rest of what the report gave before the
game, each against the final score and the box score (the same box
engine/reportgrade reads):

  * THE NUMBERS ON THE CALL (gamereport.sec_verdict's winner block): the
    lines as the report read them (`expect`, else the report's own `line`
    words, all a report written before this kept) against the final — the
    margin and the total, who covered and which side of the total it fell;
    our team ratings' own pick (`ratings`, shown as unproven); the
    simulation's own pick (`sim`), and in football which of the four scripts
    the game turned out to be, with the share of the simulated games that did.
  * HOW THE GAME WOULD GO (a `claim` on a line or a paragraph): football's
    script by the lines, high- or low-scoring and close or a clear favorite at
    engine/gamescript's own cuts; basketball's pace on the night against the
    league's, its points against the league's average game, the close game
    and the blowout watch, on the final margin.
  * THE INJURY REPORT: each man it listed, whether he played (a basketball
    box's minutes, a hockey box's time on ice; a football box keeps only the
    men with a stat, so a man without one is said as that); and, in basketball
    and hockey, the regulars who sat and were never on it.
  * TOUCHDOWN CHANCES: whether each man we gave one scored, against how many
    our chances added up to.
  * WHY A READ MISSED: his minutes (time on ice; a back's carries, a
    receiver's catches, a passer's throws) against his own, beside his grade
    when they were far off it.
  * THE BEST CALLS AND THE BIGGEST MISSES among the graded reads.

Nothing here moves a number or a pick. Standard library only; every function
returns None (or nothing) on what it cannot read, never raises past
engine/reportgrade.grade.
"""
from __future__ import annotations

import re

HOOPS = ("nba", "wnba", "cbb")
#: A basketball game decided by this many points or fewer was close; by
#: BLOWOUT_BY or more, a blowout.
CLOSE_BY, BLOWOUT_BY = 10, 15
#: What a player's night is measured in beside his grade: (stat, one, many,
#: how it is said), by league; football's by his position.
VOLUME = {"nba": ("min", "minute", "minutes", "In"), "wnba": ("min", "minute", "minutes", "In"),
          "cbb": ("min", "minute", "minutes", "In"), "nhl": ("toi", "minute on the ice", "minutes on the ice", "In")}
FOOT_VOLUME = {"QB": ("pass_att", "pass", "passes", "On"), "RB": ("rush_att", "carry", "carries", "On"),
               "FB": ("rush_att", "carry", "carries", "On"), "WR": ("receptions", "catch", "catches", "On"),
               "TE": ("receptions", "catch", "catches", "On")}
#: His volume is said beside his grade when it was this far off his own: a
#: share of his average, and at least this much.
VOLUME_GAP = 0.25
VOLUME_FLOOR = {"min": 5.0, "toi": 3.0, "pass_att": 8.0, "rush_att": 4.0, "receptions": 2.0}
#: A regular: in REGULAR_IN of his club's last REGULAR_OF games, at
#: REGULAR_VOLUME a game when he played.
REGULAR_OF, REGULAR_IN = 4, 3
REGULAR_VOLUME = {"min": 20.0, "toi": 12.0}
#: Every football stat a box keeps for a man who had one: what says he had a line.
FOOT_LINES = ("pass_att", "rush_att", "receptions", "rec_yds", "rush_yds", "pass_yds", "anytime_td")
#: The four scripts (gamereport.SCRIPT_KEYS), as a finished game says which one it was.
SCRIPT_SAID = {"A": "the favorite by 8 to 14", "B": "the underdog won", "C": "the favorite by 1 to 7",
               "D": "the favorite by 15 or more"}
#: The sections whose words say who is out, for a regular who sat.
LISTED_IN = ("injuries", "absences", "before", "changes")


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _num(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def _pct(p) -> str:
    return f"{round(float(p) * 100)}%"


def _norm(name) -> str:
    from .gameresults import norm
    return norm(name)


def own(name: str) -> str:
    """A club's name as an owner: "Celtics’", "Heat’s"."""
    name = str(name or "")
    return f"{name}’" if name.endswith("s") else f"{name}’s"


def final(g: dict) -> tuple | None:
    """(away's score, home's score) of a finished game, or None."""
    lv = (g or {}).get("live") or {}
    if str(lv.get("state") or "") != "final":
        return None
    a, h = _f(lv.get("away_score")), _f(lv.get("home_score"))
    return None if a is None or h is None else (a, h)


def names_of(report: dict, g: dict) -> dict:
    """{club: its name as the report says it}, from its call."""
    out = {x: x for x in ((g or {}).get("home"), (g or {}).get("away"), (report or {}).get("home"),
                          (report or {}).get("away")) if x}
    w = winner_block(report)
    if w:
        if w.get("team") and w.get("name"):
            out[w["team"]] = w["name"]
        if w.get("other") and w.get("other_name"):
            out[w["other"]] = w["other_name"]
    return out


def winner_block(report: dict) -> dict | None:
    for s in (report or {}).get("sections") or []:
        if s.get("key") == "verdict":
            for b in s.get("blocks") or []:
                if isinstance(b, dict) and b.get("type") == "winner":
                    return b
    return None


# --- the lines, the ratings and the simulation ----------------------------------------------------
_LINE_FAV = re.compile(r"^(?P<fav>\S+) by (?P<m>\d+(?:\.\d+)?)")
_LINE_FIXED = re.compile(r"^(?P<fav>\S+) [−-](?P<m>\d+(?:\.\d+)?) on the ")
_LINE_TOTAL = re.compile(r"total (?P<t>\d+(?:\.\d+)?)")


def parse_line(text: str, home: str, away: str) -> dict | None:
    """The lines a report wrote in words (gamereport.line_words: "BOS by 6.5
    at home, total 227.5", "PHI −1.5 on the run line, total 9.5") as numbers:
    {"spread": the home number, "total", "fixed": 1 for a run or puck line}."""
    t = str(text or "").strip()
    out: dict = {}
    m = _LINE_FAV.match(t)
    fixed = _LINE_FIXED.match(t)
    if m and m.group("fav") in (home, away):
        v = float(m.group("m"))
        out["spread"] = -v if m.group("fav") == home else v
    elif fixed and fixed.group("fav") in (home, away):
        v = float(fixed.group("m"))
        out["spread"] = -v if fixed.group("fav") == home else v
        out["fixed"] = 1
    elif t.lower().startswith(("a pick'em", "a pick’em")):
        out["spread"] = 0.0
    m = _LINE_TOTAL.search(t)
    if m:
        out["total"] = float(m.group("t"))
    return out or None


def expect_of(report: dict) -> dict | None:
    """The lines the report read: its call's own (`expect`), else its `line`
    words — all a report written before 2026-11-16 kept of them."""
    w = winner_block(report) or {}
    e = w.get("expect")
    if isinstance(e, dict) and (_f(e.get("spread")) is not None or _f(e.get("total")) is not None):
        return e
    return parse_line((report or {}).get("line"), (report or {}).get("home"), (report or {}).get("away"))


def score_check(report: dict, g: dict, sport: str = "") -> dict | None:
    """The final against the lines the report read: the margin and the total,
    who covered, which side of the total; information, never right or wrong
    (the lines are the market's, not our call)."""
    fin = final(g)
    e = expect_of(report)
    if not fin or not e:
        return None
    a, h = fin
    home, away = (report or {}).get("home") or g.get("home"), (report or {}).get("away") or g.get("away")
    nm = names_of(report, g)
    sp, tot = _f(e.get("spread")), _f(e.get("total"))
    margin, total = h - a, h + a
    out: dict = {"status": "info", "final": {"away": a, "home": h}}
    said, after = [], []
    if sp is not None:
        if sp == 0:
            said.append("a pick’em")
        else:
            fav, dog = (home, away) if sp < 0 else (away, home)
            line = abs(sp)
            fm = margin if fav == home else -margin
            word = "" if not e.get("fixed") else (" on the puck line" if sport == "nhl" else " on the run line")
            said.append(f"{nm.get(fav, fav)} by {_num(line)}" if not e.get("fixed")
                        else f"{nm.get(fav, fav)} −{_num(line)}{word}")
            if fm > line:
                out["cover"] = fav
                after.append(f"{nm.get(fav, fav)} covered")
            elif fm == line:
                out["cover"] = ""
                after.append("a push on the spread")
            else:
                out["cover"] = dog
                after.append(f"{nm.get(dog, dog)} covered" + (", and won outright" if fm < 0 else ""))
            if not e.get("fixed"):
                out["margin_miss"] = round(abs(margin + sp), 1)
                if tot is not None:
                    out["expected"] = {"home": round((tot - sp) / 2.0, 1), "away": round((tot + sp) / 2.0, 1)}
    if tot is not None:
        said.append(f"{_num(tot)} points" if sport not in ("mlb", "nhl") else
                    f"{_num(tot)} {'goals' if sport == 'nhl' else 'runs'}")
        out["total_miss"] = round(abs(total - tot), 1)
        out["side"] = "over" if total > tot else "under" if total < tot else "push"
        after.append({"over": "it went over", "under": "it went under", "push": "a push on the total"}[out["side"]])
    if not said:
        return None
    unit = "goals" if sport == "nhl" else "runs" if sport == "mlb" else "points"
    if margin == 0:
        was = f"a tie, {_num(total)} {unit}"
    else:
        won = home if margin > 0 else away
        was = f"{nm.get(won, won)} by {_num(abs(margin))}, {_num(total)} {unit}"
    out["words"] = f"the lines had {' and '.join(said)}; it was {was}" + (f" — {' and '.join(after)}" if after else "")
    return out


def _won(g: dict) -> str | None:
    fin = final(g)
    if not fin or fin[0] == fin[1]:
        return None
    return g.get("home") if fin[1] > fin[0] else g.get("away")


def ratings_check(report: dict, g: dict) -> dict | None:
    """Our team ratings' own pick (shown beside the call, unproven): right or
    wrong on who won."""
    r = (winner_block(report) or {}).get("ratings")
    won = _won(g)
    if not isinstance(r, dict) or r.get("even") or not r.get("team") or not won:
        return None
    right = r["team"] == won
    name = r.get("name") or r["team"]
    chance = _f(r.get("chance"))
    return {"status": "right" if right else "wrong", "team": r["team"], "same": bool(r.get("same")),
            "words": f"{'right' if right else 'wrong'} — they had {name}"
                     + (f" ({_pct(chance)})" if chance is not None else "")
                     + ("" if r.get("same", True) else ", the other side from the price")}


def script_of(fav_margin: float) -> str | None:
    """Which of the four scripts a final was, by the favorite's margin."""
    if fav_margin == 0:
        return None
    if fav_margin < 0:
        return "B"
    return "C" if fav_margin <= 7 else "A" if fav_margin <= 14 else "D"


def sim_check(report: dict, g: dict) -> dict | None:
    """The simulation's own pick, right or wrong on who won; with its margins,
    which script the game turned out to be and how many of its games did."""
    s = (winner_block(report) or {}).get("sim")
    won = _won(g)
    fin = final(g)
    if not isinstance(s, dict) or not s.get("team") or not won or not fin:
        return None
    nm = names_of(report, g)
    right = s["team"] == won
    chance = _f(s.get("chance"))
    out = {"status": "right" if right else "wrong", "team": s["team"],
           "words": f"{'right' if right else 'wrong'} — it had {nm.get(s['team'], s['team'])} winning"
                    + (f" {_pct(chance)} of its games" if chance is not None else "")}
    hist = s.get("hist") or []
    if len(hist) == 6 and all(_f(x) is not None for x in hist):
        home = g.get("home")
        f, d = ("home", "away") if s["team"] == home else ("away", "home")
        by = dict(zip((("home", 15), ("home", 8), ("home", 1), ("away", 1), ("away", 8), ("away", 15)),
                      (float(x) for x in hist)))
        share = {"A": by[(f, 8)], "B": by[(d, 1)] + by[(d, 8)] + by[(d, 15)], "C": by[(f, 1)], "D": by[(f, 15)]}
        a, h = fin
        k = script_of((h - a) if f == "home" else (a - h))
        if k:
            out["script"] = k
            out["share"] = round(share[k], 4)
            out["words"] += f"; the game went Script {k}, {SCRIPT_SAID[k]}, as {_pct(share[k])} of them did"
    return out


# --- a claim on a line or a paragraph ---------------------------------------------------------
GAME_KINDS = ("script", "scoring", "close", "blowout", "pace")


def claim_grade(sport: str, claim: dict, bx, g: dict, report: dict) -> dict | None:
    """One claim's check, by its kind: how the game would go (GAME_KINDS), a
    touchdown chance ("td") or an injury line ("injury"). None where it
    cannot be read."""
    kind = (claim or {}).get("kind")
    if kind == "td":
        return td_check(claim, bx)
    if kind == "injury":
        return injury_check(sport, claim, bx)
    if kind not in GAME_KINDS:
        return None
    fin = final(g)
    if not fin:
        return None
    a, h = fin
    margin, total = h - a, h + a
    nm = names_of(report, g)
    if kind == "script":
        return _script(claim, a, h, g, nm)
    if kind == "scoring":
        avg, read = _f(claim.get("avg")), claim.get("read")
        if avg is None:
            return None
        diff = f"{_num(abs(total - avg))} {'over' if total > avg else 'under'} the average game ({_num(avg)})" \
            if total != avg else f"the average game exactly ({_num(avg)})"
        if read in ("high", "low"):
            ok = total > avg if read == "high" else total < avg
            return {"status": "right" if ok else "wrong", "actual": total, "avg": avg,
                    "words": f"{'Right' if ok else 'Wrong'}: {_num(total)} points, {diff}."}
        return {"status": "info", "actual": total, "avg": avg, "words": f"It finished at {_num(total)} points, {diff}."}
    if kind == "close":
        m = abs(margin)
        ok = m <= CLOSE_BY
        return {"status": "right" if ok else "wrong", "actual": m,
                "words": f"{'Right' if ok else 'Wrong'}: decided by {_num(m)}"
                         + (", a blowout" if m >= BLOWOUT_BY else "") + "."}
    if kind == "blowout":
        m = abs(margin)
        ok = m >= BLOWOUT_BY
        return {"status": "right" if ok else "wrong", "actual": m,
                "words": f"Right: a blowout, decided by {_num(m)}." if ok
                else f"Wrong: not a blowout, decided by {_num(m)}."}
    return _pace(claim, bx, g, nm)


def _script(claim: dict, a: float, h: float, g: dict, nm: dict) -> dict | None:
    """Football's script by the lines (gamereport.script_claim): its two
    halves, each right or wrong."""
    cut, big = _f(claim.get("cut")), _f(claim.get("big"))
    scoring, shape = claim.get("scoring"), claim.get("shape")
    if cut is None or big is None or scoring not in ("high", "low") or shape not in ("big", "close"):
        return None
    total, margin = a + h, h - a
    rights, said = 0, []
    ok = total >= cut if scoring == "high" else total < cut
    rights += ok
    said.append(f"{_num(total)} points, {scoring}-scoring as read" if ok else
                f"{_num(total)} points, not the {scoring}-scoring game read "
                f"({_num(cut)} or more)" if scoring == "high" else
                f"{_num(total)} points, not the {scoring}-scoring game read (under {_num(cut)})")
    fav = claim.get("fav") or ""
    if shape == "big":
        if fav not in (g.get("home"), g.get("away")):
            return None
        fm = margin if fav == g.get("home") else -margin
        ok = fm >= big
        name = nm.get(fav, fav)
        said.append(f"{name} won by {_num(fm)}, the clear favorite as read" if ok else
                    f"{name} won by only {_num(fm)}, closer than read" if fm > 0 else
                    "a tie, not the clear favorite read" if fm == 0 else
                    f"{name} lost, not the clear favorite read")
    else:
        ok = abs(margin) < big
        said.append(f"decided by {_num(abs(margin))}, close as read" if ok else
                    f"decided by {_num(abs(margin))}, not the close game read")
    rights += ok
    st = "right" if rights == 2 else "wrong" if rights == 0 else "split"
    head = {"right": "Right", "wrong": "Wrong", "split": "Half right"}[st]
    return {"status": st, "right": rights, "of": 2, "words": f"{head}: {said[0]}; {said[1]}."}


def _pace(claim: dict, bx, g: dict, nm: dict) -> dict | None:
    """Basketball's pace on the night (engine/nba/teams.season_profiles, the
    report's own arithmetic) against the league's, or, in a tug of war, whose."""
    lp = _f(claim.get("league"))
    home, away = g.get("home"), g.get("away")
    if lp is None or bx is None or not (bx.has(home) and bx.has(away)):
        return None
    from .nba import teams as T
    day = str((g or {}).get("date") or "")[:10] or "night"
    night = {(home, day): dict(bx.teams.get(home) or {}, opp=away), (away, day): dict(bx.teams.get(away) or {}, opp=home)}
    pace = _f((T.season_profiles(night, min_games=1).get(home) or {}).get("pace"))
    if pace is None:
        return None
    read = claim.get("read")
    said = f"{pace:.1f} possessions per 48 minutes"
    if read in ("fast", "slow"):
        ok = pace > lp if read == "fast" else pace < lp
        return {"status": "right" if ok else "wrong", "actual": round(pace, 1), "avg": lp,
                "words": f"{'Right' if ok else 'Wrong'}: {said}, {'over' if pace > lp else 'under'} the league’s "
                         f"{lp:.1f}."}
    if read == "split":
        mine = {t: _f(v) for t, v in claim.get("pace") or [] if _f(v) is not None}
        if len(mine) == 2:
            near = min(mine, key=lambda t: abs(mine[t] - pace))
            far = next(t for t in mine if t != near)
            return {"status": "info", "actual": round(pace, 1),
                    "words": f"{nm.get(near, near)} won the tug of war: {said}, nearer its {mine[near]:.1f} than "
                             f"{own(nm.get(far, far))} {mine[far]:.1f}."}
    return {"status": "info", "actual": round(pace, 1), "words": f"It played at {said} (the league’s is {lp:.1f})."}


# --- touchdowns and the injury report ------------------------------------------------------------
def td_check(claim: dict, bx) -> dict | None:
    """Whether a man we gave a touchdown chance scored: "hit" or "miss", never
    right or wrong (a chance is not a call)."""
    p = _f(claim.get("p"))
    if bx is None or not bx.teams:
        return {"status": "pending", "p": p, "words": "Waiting on the box score."}
    mine = bx.players.get(_norm(claim.get("player")))
    if mine is None and not bx.has(claim.get("team") or ""):
        return {"status": "pending", "p": p, "words": "Waiting on the box score."}
    n = _f((mine or {}).get("stats", {}).get("anytime_td")) or 0.0
    if n >= 1:
        return {"status": "hit", "p": p, "actual": n, "words": "Scored." if n == 1 else f"Scored {_num(n)}."}
    return {"status": "miss", "p": p, "actual": 0.0, "words": "No touchdown."}


def _says(status: str) -> str:
    """What an injury status says of the game: "sits", "plays" or "maybe"."""
    s = str(status or "").strip().lower()
    if s.startswith(("out", "doubtful", "suspen", "injured reserve", "inactive", "not with")) or s in ("ir", "o", "d"):
        return "sits"
    if s.startswith(("probable", "available", "active")):
        return "plays"
    return "maybe"


def played(sport: str, mine: dict | None, pos: str = "") -> tuple:
    """(True, his line) when the box says he played, (False, "") when it says
    he did not, (None, "") when it cannot say (a football box keeps only the
    men with a stat)."""
    if sport in ("nfl", "cfb"):
        if mine is None:
            return None, ""
        return True, foot_line(mine.get("stats") or {}, pos)
    if mine is None:
        return False, ""
    st = mine.get("stats") or {}
    if sport in HOOPS:
        mins = _f(st.get("min"))
        if mins is not None and mins <= 0:
            return False, ""
        pts = _f(st.get("pts"))
        return True, ", ".join(x for x in ((f"{round(mins)} minutes" if mins is not None else ""),
                                          (f"{_num(pts)} points" if pts is not None else "")) if x)
    if sport == "nhl":
        toi = _f(st.get("toi"))
        if toi is not None and toi <= 0:
            return False, ""
        if _f(st.get("saves")) is not None:
            return True, f"{_num(st['saves'])} saves"
        pts = _f(st.get("points"))
        return True, ", ".join(x for x in ((f"{round(toi)} minutes on the ice" if toi is not None else ""),
                                          (f"{_num(pts)} points" if pts is not None else "")) if x)
    return True, ""


def foot_line(st: dict, pos: str = "") -> str:
    pos = str(pos or "").upper()
    bits = []
    if pos == "QB" or (not pos and _f(st.get("pass_att"))):
        if _f(st.get("pass_yds")) is not None:
            bits.append(f"{_num(st['pass_yds'])} passing yards")
    if _f(st.get("rush_att")):
        bits.append(f"{_num(st['rush_att'])} carries for {_num(_f(st.get('rush_yds')) or 0)} yards")
    if _f(st.get("receptions")):
        bits.append(f"{_num(st['receptions'])} catches for {_num(_f(st.get('rec_yds')) or 0)} yards")
    return ", ".join(bits) or "a line in the box score"


def injury_check(sport: str, claim: dict, bx) -> dict | None:
    """One injury line against the box: a man listed out right when he sat, a
    probable one when he played; a questionable one says what happened."""
    team = claim.get("team") or ""
    if bx is None or not bx.teams or not bx.has(team):
        return {"status": "pending", "words": "Waiting on the box score."}
    says = _says(claim.get("status"))
    did, line = played(sport, bx.players.get(_norm(claim.get("player"))), claim.get("pos") or "")
    if did is None:
        return {"status": "right" if says == "sits" else "info", "says": says, "played": None,
                "words": "No stats in the box score" + (", as listed." if says == "sits" else ".")}
    if says == "sits":
        return ({"status": "wrong", "says": says, "played": True, "words": f"Wrong: he played — {line}."} if did else
                {"status": "right", "says": says, "played": False, "words": "Right: he sat."})
    if says == "plays":
        return ({"status": "right", "says": says, "played": True, "words": f"Right: he played — {line}."} if did else
                {"status": "wrong", "says": says, "played": False, "words": "Wrong: he sat."})
    return ({"status": "played", "says": says, "played": True, "words": f"He played — {line}."} if did else
            {"status": "sat", "says": says, "played": False, "words": "He sat."})


def _listed_text(report: dict) -> str:
    """Every word of the sections that say who is out, folded for a search."""
    out = []

    def walk(x):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, dict):
            for k, v in x.items():
                if k not in ("grade", "grades", "graded"):
                    walk(v)
    for s in (report or {}).get("sections") or []:
        if s.get("key") in LISTED_IN:
            walk(s.get("blocks"))
    return _norm(" ".join(out))


def missed(sport: str, report: dict, bx, conn, g: dict, label: str, listed: set) -> list:
    """The regulars who sat and were never on the report (basketball and
    hockey, whose box keeps every man who dressed): in REGULAR_IN of his club's
    last REGULAR_OF games at REGULAR_VOLUME a game, no minutes tonight, and
    still his club's man (his last game before this one was for it)."""
    if sport not in VOLUME or bx is None or not bx.teams or conn is None:
        return []
    from .reportgrade import _before_clause
    where = _before_clause(sport, g, label)
    if where is None:
        return []
    clause, args = where
    stat = VOLUME[sport][0]
    clubs = [t for t in (g.get("home"), g.get("away")) if t and bx.has(t)]
    if not clubs:
        return []
    q = (f"SELECT player, team, season, period, value FROM player_game_logs WHERE {clause} AND market=? "
         f"AND team IN ({','.join('?' * len(clubs))})")
    nights: dict = {}
    per: dict = {}
    for player, team, season, period, value in conn.execute(q, (*args, stat, *clubs)).fetchall():
        key = (season, str(period))
        nights.setdefault(team, set()).add(key)
        per.setdefault((team, player), {})[key] = _f(value)
    text = _listed_text(report)
    out = []
    for team in clubs:
        last = sorted(nights.get(team) or (), reverse=True)[:REGULAR_OF]
        if len(last) < REGULAR_OF:
            continue
        for (t, player), games in per.items():
            if t != team:
                continue
            apps = [games[k] for k in last if (games.get(k) or 0) > 0]
            if len(apps) < REGULAR_IN or sum(apps) / len(apps) < REGULAR_VOLUME[stat]:
                continue
            did, _line = played(sport, bx.players.get(_norm(player)))
            if did:
                continue
            key = _norm(player)
            if key in listed or (key and key in text):
                continue
            if _moved(conn, sport, clause, args, player, stat, team):
                continue
            out.append({"player": player, "team": team, "avg": round(sum(apps) / len(apps), 1), "n": len(apps),
                        "of": len(last)})
    out.sort(key=lambda x: -x["avg"])
    return out


def _moved(conn, sport: str, clause: str, args: list, player: str, stat: str, team: str) -> bool:
    """Whether his last game before this one was for another club (a trade)."""
    row = conn.execute(f"SELECT team FROM player_game_logs WHERE {clause} AND market=? AND player=? "
                       f"ORDER BY season DESC, period DESC LIMIT 1", (*args, stat, player)).fetchone()
    return bool(row) and row[0] != team


def missed_words(m: dict, sport: str, names: dict) -> str:
    unit = "minutes on the ice" if sport == "nhl" else "minutes"
    club = names.get(m["team"], m["team"])
    return (f"Not on our injury report: {m['player']} ({club}) didn’t play — {round(m['avg'])} {unit} a game in "
            f"{m['n']} of {own(club)} last {m['of']}.")


# --- why a read missed, and the standouts -------------------------------------------------------
def volume_stat(sport: str, item: dict) -> tuple | None:
    """(stat, one, many, how it is said) a man's night is measured in."""
    if sport in VOLUME:
        return VOLUME[sport]
    if sport in ("nfl", "cfb"):
        return FOOT_VOLUME.get(str((item or {}).get("pos") or "").upper())
    return None


def volume_note(sport: str, item: dict, mine: dict, past: list) -> dict | None:
    """His night's volume against his own, when it was far off it: {"stat",
    "actual", "avg", "words"} — "In 19 minutes (he averages 31).", "On 6
    carries (he averages 15)."."""
    vs = volume_stat(sport, item)
    if not vs or not mine:
        return None
    stat, one, many, how = vs
    v = _f((mine.get("stats") or {}).get(stat))
    past = [x for x in past or [] if _f(x) is not None]
    if v is None or len(past) < 2:
        return None
    avg = sum(past) / len(past)
    if abs(v - avg) < max(VOLUME_GAP * avg, VOLUME_FLOOR.get(stat, 0.0)):
        return None
    shown = round(v) if stat in ("min", "toi") else v
    return {"stat": stat, "actual": round(v, 1), "avg": round(avg, 1),
            "words": f"{how} {_num(shown)} {one if shown == 1 else many} (he averages {round(avg)})."}


#: How each group's read is said beside a name, by the card's verdict.
LABEL = {"matchups": {"favorable": "a favorable matchup", "unfavorable": "a tough matchup"},
         "candidates": {"": "a breakout candidate"}, "fades": {"": "a fade"},
         "starters": {"favorable": "a favorable start", "unfavorable": "a tough start"},
         "angles": {"": "an angle"}}
#: How many of each the summary lists.
STANDOUTS = 3


def standout(group: str, item: dict | None, gr: dict, way: str | None) -> tuple | None:
    """(how far it went the read's way, its words) for a graded read with a
    number and an average, else None."""
    if not gr or gr.get("status") not in ("right", "wrong") or way not in ("more", "less"):
        return None
    actual, avg = _f(gr.get("actual")), _f(gr.get("avg"))
    if actual is None or avg is None:
        return None
    # How far, as a share of his own number (a rate's own scale; a count near
    # nothing as much as one), so a 38-point night against 24 and a 61% night
    # against 52% weigh alike; capped, so one freak night is not the list.
    rate = abs(avg) < 1 and abs(actual) < 1.5
    rel = (actual - avg) / (max(abs(avg), 0.05) if rate else max(abs(avg), 1.0))
    rel = max(-3.0, min(3.0, rel)) * (1 if way == "more" else -1)
    words = str(gr.get("words") or "")
    words = re.sub(r"^(Right|Wrong|Even): ", "", words)
    if item and item.get("player"):
        lab = LABEL.get(group) or {}
        label = lab.get(str(item.get("verdict") or "").lower()) or lab.get("") or ""
        words = f"{item['player']}{', ' + label if label else ''}: {words[:1].lower()}{words[1:]}"
    return rel, words


def standouts(rows: list) -> tuple:
    """(the best calls, the biggest misses): each a list of words."""
    good = sorted((r for r in rows if r and r[0] > 0), key=lambda r: -r[0])
    bad = sorted((r for r in rows if r and r[0] < 0), key=lambda r: r[0])
    return [w for _r, w in good[:STANDOUTS]], [w for _r, w in bad[:STANDOUTS]]
