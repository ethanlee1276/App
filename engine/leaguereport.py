"""The game report for MLB, the NHL, the NBA and the WNBA.

Ethan, 2026-10-20 ("I want you too do all of it besides D"): the report
written for every NFL and college game (engine/gamereport), for the other
leagues' games. The same shape — sections of paragraphs, headings, lists,
tables and player cards, drawn by js/report.js unchanged — built from what
each league's board holds:

  MLB   the pitching matchup (each starter's hand, expected ERA, strikeout
        rate and slugging allowed to each side; each lineup against
        tonight's hand; the pens), the park, the weather and the plate
        umpire, and a read on every hitter and starter (engine/mlb/scan:
        the board's `mlb_tape` and `scan_reads`)
  NHL   the tale of the tape (goals, shots and 5-on-5 chances for and
        against, with ranks; tonight's expected goals), the goalies (who
        starts, whether it is confirmed, his save rate and goals saved
        above expected), the injury report and pulled props, and a read on
        every key skater and starter (engine/nhl/scan: `nhl_tape`,
        `scan_reads`)
  NBA   the schedule spots (rest, the trip, the clock, altitude, the
        blowout watch — the board's `schedule_spots`); the tale of the tape
        — each side's offence and defence per 100 possessions, pace,
        shooting, the threes, the glass and the turnovers, with ranks — and
        the key matchups (engine/nba/scan: `nba_tape`); the breakout watch
        and who could shine or struggle (`scan_reads`); the injury report,
        who carries each team over his last ten games, and where each
        defence gives up the most and the least a game (engine/hoopsdvp) —
        the last three what the build knows and the board does not carry,
        handed in as ``meta``
  WNBA  the NBA's report

Every league's report carries the market (gamereport.sec_market: the
line, the moneyline's chance with the cut out, the opener, the prediction
markets and their money), the short version, and what changed since it
was first written (engine/reportlog).

WHAT IT IS NOT, as the NFL's: no prop pick. No line, price or probability
on any player — a read says why a player sets up well or badly, never
what to bet. The run line and the puck line are a run or a goal and a
half wide whoever is favored, so no team totals are read off them.

IT IS PAID, under the same `game_reports` key (engine/gate.PAID_KEYS).

Standard library only. Never raises out of ``attach``.
"""
from __future__ import annotations

from .gamereport import (KEY, Ctx, _f, _h, _join, _list, _num, _ord, _p, _pct, _section,
                         _sentence, a_pct, absent_sentence, cap, finish, kickoff_words, line_words,
                         log_changes, market_sentence, ml_chances, named, player_clause, sec_market,
                         shine_lines, summary, team_be, team_np, team_owner)

#: The leagues this module writes.
SPORTS = ("mlb", "nhl", "nba", "wnba")

#: Nicknames two words long (the rest are the full name's last word).
TWO_WORD = {"Red Sox", "White Sox", "Blue Jays", "Maple Leafs", "Golden Knights", "Blue Jackets",
            "Red Wings", "Trail Blazers"}

#: How many players each list names.
SHINE_N, STRUGGLE_N, CARRY_N = 6, 4, 5

#: A bullpen that threw this many relief innings in the last two days is
#: tired (engine/mlb/scan's own bar).
PEN_TIRED = 6.0
#: A lineup this far off its average against tonight's hand is named.
HAND_EDGE = 0.03


def team_names(sport: str) -> dict:
    """{code: nickname} off the odds feed's full names ("Philadelphia
    Phillies" → "Phillies")."""
    try:
        from .sources import oddsapi as O
        table = {"mlb": O.MLB_TEAM_ABBR, "nhl": O.NHL_TEAM_ABBR, "nba": O.NBA_TEAM_ABBR,
                 "wnba": O.WNBA_TEAM_ABBR}.get(sport) or {}
    except Exception:                                        # noqa: BLE001
        return {}
    out: dict = {}
    for full, code in table.items():
        words = str(full).split()
        two = " ".join(words[-2:])
        nick = two if two in TWO_WORD else ("Utah" if two == "Hockey Club" else words[-1])
        out.setdefault(code, nick)
    return out


def _slg(x) -> str:
    v = _f(x)
    return f".{round(v * 1000):03d}" if v is not None and v < 1 else ("—" if v is None else f"{v:.3f}")


def _hand(h) -> str:
    return {"R": "right-handed", "L": "left-handed"}.get(str(h or "").upper(), "")


def _reads(c: Ctx, *, pos=None, not_pos=None) -> list:
    return [r for r in c.reads if (pos is None or str(r.get("pos") or "").upper() in pos)
            and (not_pos is None or str(r.get("pos") or "").upper() not in not_pos)]


def _lower_first(x: str) -> str:
    """A reason as the middle of a sentence: its first letter small, unless
    the first word is a code or a name in capitals ("PHI rarely ...")."""
    return x[0].lower() + x[1:] if len(x) > 1 and x[1].islower() else x


def _verdict(r: dict, tone: str | None = None, both: bool = False) -> dict:
    """A read as a player card: his reasons for (shine) or against
    (struggle), or both (a starter)."""
    tone = tone or {"breakout": "up", "good": "up", "tough": "down", "avoid": "down"}.get(r.get("read"), "")
    pro = [str(x) for x in r.get("pro") or [] if x]
    con = [str(x) for x in r.get("con") or [] if x]
    if both:
        why = pro[:3] + [f"Against: {_lower_first(x)}" for x in con[:2]]
    else:
        why = (pro if tone == "up" else con)[:3]
    notes = [str(x) for x in r.get("notes") or [] if x][:1]
    return {"title": r.get("player"), "player": r.get("player"), "team": r.get("team"),
            "pos": r.get("pos") or "", "label": r.get("label") or "", "verdict": tone,
            "headshot": r.get("headshot") or "", "why": [_sentence(w) for w in why + notes]}


def shine_struggle(c: Ctx, reads: list) -> list:
    """Could shine (breakout first) and could struggle, as player cards."""
    shine = sorted((r for r in reads if r.get("read") in ("breakout", "good")),
                   key=lambda r: (r.get("read") != "breakout", -len(r.get("pro") or [])))
    struggle = sorted((r for r in reads if r.get("read") in ("tough", "avoid")),
                      key=lambda r: (r.get("read") != "avoid", -len(r.get("con") or [])))
    blocks = []
    if shine:
        blocks += [_h("Could shine"), {"type": "verdicts", "items": [_verdict(r, "up") for r in shine[:SHINE_N]]}]
    if struggle:
        blocks += [_h("Could struggle"),
                   {"type": "verdicts", "items": [_verdict(r, "down") for r in struggle[:STRUGGLE_N]]}]
    if reads and not shine:
        blocks.append(_p("No one in this game reads as a breakout candidate or a good matchup"))
    return blocks


def _names(rows, n) -> str:
    return _join(f"{r.get('player')} ({r.get('team')})" for r in rows[:n])


def _short_common(c: Ctx) -> list:
    """The line, said as a sentence (gamereport.market_sentence)."""
    s = market_sentence(c)
    return [s] if s else []


def _shine_short(c: Ctx, reads: list) -> list:
    """Who could have a big day and a hard one, each with his reason."""
    return shine_lines(c, reads)


def _facts_head(c: Ctx, word: str) -> list:
    items = []
    when = kickoff_words(c.g.get("date") or "", c.g.get("kickoff") or "")
    if when:
        items.append(f"{word}: {when}")
    items.append(f"{c.name(c.away)} ({c.away}) at {c.name(c.home)} ({c.home})")
    return items


def _stale(c: Ctx) -> list:
    return (["The game lines on this page are older than the build — check the price before you "
             "trust the market section"] if c.g.get("price_stale") else [])


# ═══ MLB ═════════════════════════════════════════════════════════════════════════════
def _tape(c: Ctx) -> dict:
    return c.g.get("mlb_tape") or c.g.get("nhl_tape") or c.g.get("nba_tape") or {}


def _sides(c: Ctx) -> dict:
    return _tape(c).get("sides") or {}


def _starter(c: Ctx, t: str) -> dict:
    sp = (_sides(c).get(t) or {}).get("starter")
    if isinstance(sp, dict) and sp.get("name"):
        return sp
    p = (c.g.get("pitchers") or {}).get("home" if t == c.home else "away")
    return p if isinstance(p, dict) and p.get("name") else {}


def _sp_words(c: Ctx, t: str) -> str:
    sp = _starter(c, t)
    if not sp:
        return f"{t}: to be announced"
    bits = [b for b in (str(sp.get("throws") or "").upper()[:1],
                        _f(sp.get("xera")) is not None and f"{float(sp['xera']):.2f} xERA",
                        _f(sp.get("k_rate")) is not None and f"{_pct(sp['k_rate'])} K") if b]
    return f"{sp['name']} ({t}{', ' + ', '.join(bits) if bits else ''})"


def mlb_facts(c: Ctx) -> dict | None:
    g = c.g
    items = _facts_head(c, "First pitch")
    if g.get("doubleheader"):
        items[-1] += f" — game {int(g.get('game_number') or 1)} of a doubleheader"
    park = g.get("park") if isinstance(g.get("park"), dict) else {}
    name = park.get("name") or g.get("park_name") or ""
    if name:
        roof = {"open": "open air", "retractable": "a retractable roof", "dome": "a fixed dome",
                "closed": "roof closed"}.get(str(park.get("roof") or g.get("roof") or "").lower(), "")
        surface = str(park.get("surface") or g.get("surface") or "").replace("_", " ")
        alt = _f(park.get("altitude_ft") if park.get("altitude_ft") is not None else g.get("altitude_ft"))
        dims = [f"{int(park[k])} to {w}" for k, w in (("lf_ft", "left"), ("cf_ft", "center"), ("rf_ft", "right"))
                if _f(park.get(k)) is not None]
        if dims:
            dims[0] = dims[0].replace(" to ", " feet to ", 1)
        bits = [b for b in (roof, surface and f"{surface}", alt and alt >= 1000 and f"{int(alt):,} feet up") if b]
        items.append(f"Ballpark: {name}" + (f" — {', '.join(bits)}" if bits else "")
                     + (f"; {', '.join(dims)}" if dims else ""))
    if g.get("lineups_confirmed") is True:
        items.append("Lineups: both confirmed")
    elif g.get("lineups_confirmed") is False:
        items.append("Lineups: not out yet")
    if g.get("plate_umpire"):
        items.append(f"Plate umpire: {g['plate_umpire']}")
    return _section("facts", "Game facts", [_list(items)])


def mlb_pitching(c: Ctx) -> dict | None:
    t_a, t_h = c.away, c.home
    sa, sh = _starter(c, t_a), _starter(c, t_h)
    blocks = []
    if sa or sh:
        def cell(sp, k, how):
            v = sp.get(k) if sp else None
            if v is None or v == "":
                return "—"
            return how(v)
        rows = [["Throws", cell(sa, "throws", lambda v: str(v).upper()[:1] or "—"),
                 cell(sh, "throws", lambda v: str(v).upper()[:1] or "—")],
                ["Expected ERA", cell(sa, "xera", lambda v: f"{float(v):.2f}"),
                 cell(sh, "xera", lambda v: f"{float(v):.2f}")],
                ["Strikeout rate", cell(sa, "k_rate", _pct), cell(sh, "k_rate", _pct)],
                ["SLG allowed, lefties", cell(sa, "slg_vs_l", _slg), cell(sh, "slg_vs_l", _slg)],
                ["SLG allowed, righties", cell(sa, "slg_vs_r", _slg), cell(sh, "slg_vs_r", _slg)]]
        rows = [r for r in rows if r[1] != "—" or r[2] != "—"]
        note = "Expected ERA is what the contact he allowed should have cost, not what it did"
        if any(r[0].startswith("SLG") for r in rows):
            note += "; SLG allowed is the slugging percentage he allows to each side of the plate"
        blocks.append({"type": "table", "title": "The starters",
                       "head": ["", f"{sa.get('name') or 'TBA'} ({t_a})", f"{sh.get('name') or 'TBA'} ({t_h})"],
                       "rows": rows, "note": _sentence(note)})
    items = []
    league = (_tape(c).get("league") or {})
    for t in (t_a, t_h):
        s = _sides(c).get(t) or {}
        if s.get("mix"):
            items.append(f"{c.poss(t)} starter throws {s['mix']}")
        vh = s.get("vs_hand") or {}
        if _f(vh.get("factor")) is not None and vh.get("hand"):
            f = float(vh["factor"]) - 1
            how = (f"{_pct(abs(f))} {'better' if f > 0 else 'worse'} than its average"
                   if abs(f) >= HAND_EDGE else "about its average")
            items.append(f"{t}'s lineup hits {_hand(vh['hand'])} pitching {how} "
                         f"({vh.get('hitters')} hitters measured)")
        if _f(s.get("k_rate")) is not None:
            items.append(f"{t} strikes out {_pct(s['k_rate'], 1)} of the time"
                         + (f" (league {_pct(league['k_rate'])})" if _f(league.get("k_rate")) is not None else ""))
    pens = []
    for t in (t_a, t_h):
        s = _sides(c).get(t) or {}
        bits = []
        if s.get("pen_rank"):
            bits.append(f"ranks {_ord(int(s['pen_rank']))}")
        fat = _f(s.get("pen_fatigue"))
        if fat is not None and fat >= PEN_TIRED:
            bits.append(f"threw {_num(fat)} relief innings the last two days — tired")
        if bits:
            pens.append(f"{c.poss(t)} bullpen {' and '.join(bits)}")
    if pens:
        items.append("The pens: " + "; ".join(pens))
    blocks.append(_list(items))
    starters = _reads(c, pos={"SP", "P"})
    if starters:
        blocks += [_h("How each starter sets up"),
                   {"type": "verdicts", "items": [_verdict(r, both=True) for r in starters]}]
    return _section("pitching", "The pitching matchup", blocks)


def mlb_park(c: Ctx) -> dict | None:
    g = c.g
    blocks = []
    park = g.get("park") if isinstance(g.get("park"), dict) else {}
    if park.get("plays"):
        blocks.append(_p(park["plays"]))
    tp = _tape(c).get("park") or {}
    fac = []
    for k, w in (("hr", "home runs"), ("runs", "runs"), ("k", "strikeouts")):
        v = _f(tp.get(k))
        if v is not None:
            d = round((v - 1) * 100)
            fac.append(f"{'+' if d > 0 else '−' if d < 0 else '±'}{abs(d)}% {w}")
    items = []
    if fac:
        items.append(f"{tp.get('name') or park.get('name') or 'The park'} plays {', '.join(fac)} "
                     "against an average park")
    w = g.get("weather") or {}
    if w.get("dome") or str(g.get("roof") or "").lower() in ("dome", "closed"):
        items.append("Under a roof: no weather in play")
    elif w:
        bits = []
        if _f(w.get("temp_f")) is not None:
            bits.append(f"{round(float(w['temp_f']))}°F")
        if _f(w.get("wind_mph")) is not None:
            bits.append(f"wind {round(float(w['wind_mph']))} mph"
                        + (f" blowing {w['wind_dir']}" if w.get("wind_dir") in ("in", "out") else
                           f" {w['wind_dir']}" if w.get("wind_dir") else ""))
        if w.get("rain"):
            bits.append("rain in the forecast")
        if bits:
            items.append("Weather: " + ", ".join(bits))
    for why in ((g.get("conditions") or {}).get("why") or [])[:3]:
        items.append(str(why))
    ump = _tape(c).get("umpire") or {}
    if ump.get("name"):
        bits = []
        for k, word in (("k", "strikeouts"), ("runs", "runs")):
            v = _f(ump.get(k))
            if v is not None and abs(v - 1) >= 0.02:
                bits.append(f"{'+' if v > 1 else '−'}{round(abs(v - 1) * 100)}% {word}")
        items.append(f"Plate umpire {ump['name']}" + (f": {', '.join(bits)} in his games" if bits else
                                                      ": calls an average zone"))
    blocks.append(_list(items))
    return _section("weather", "The park and the weather", blocks)


def mlb_watch(c: Ctx) -> dict | None:
    return _section("watch", "Players to watch", shine_struggle(c, _reads(c, not_pos={"SP", "P", "RP"})))


def mlb_injuries(c: Ctx) -> dict | None:
    team_of = {}
    for r in c.result.get("recommendations") or []:
        if isinstance(r, dict) and r.get("player") and r.get("team"):
            team_of.setdefault(r["player"], r["team"])
    il = [p for p in c.result.get("injured_list") or [] if team_of.get(p) in c.teams]
    if not il:
        return None
    return _section("injuries", "Injuries", [_p("On the injured list: " + _join(
        f"{p} ({team_of[p]})" for p in sorted(il)))])


def mlb_before(c: Ctx) -> dict | None:
    lines = []
    if c.g.get("lineups_confirmed") is not True:
        lines.append("Lineups post two to four hours before first pitch; a hitter left out has no "
                     "at-bats, and every read of him is moot")
    lines.append("A probable starter can be scratched up to first pitch — the line moves when he is")
    w = c.g.get("weather") or {}
    if w and not w.get("dome") and (w.get("rain") or (_f(w.get("wind_mph")) or 0) >= 10):
        lines.append("Check the wind and the rain again close to first pitch: they move run scoring "
                     "more here than anywhere else in the report")
    lines += _stale(c)
    return _section("before", "Before first pitch", [_list(lines)])


def _sp_clause(c: Ctx, t: str) -> str:
    """"the Phillies start right-hander Zack Wheeler (a 3.05 expected ERA,
    striking out 29% of the batters he faces)"."""
    sp = _starter(c, t)
    if not sp:
        return f"{team_np(c, t)} {team_be(c, t, 'have', 'has')} not named a starter"
    hand = {"R": "right-hander", "L": "left-hander"}.get(str(sp.get("throws") or "").upper()[:1], "")
    bits = []
    if _f(sp.get("xera")) is not None:
        x = f"{float(sp['xera']):.2f}"
        bits.append(f"{'an' if x.startswith('8') or x.startswith('11.') else 'a'} {x} expected ERA")
    if _f(sp.get("k_rate")) is not None:
        bits.append(f"striking out {_pct(sp['k_rate'])} of the batters he faces")
    who = f"{hand} {sp['name']}" if hand else sp["name"]
    return (f"{team_np(c, t)} {team_be(c, t, 'start', 'starts')} {who}"
            + (f" ({', '.join(bits)})" if bits else ""))


#: The home-run model's weather notes (engine/mlb/homeruns), said as
#: sentences for the short version; any other note passes through.
_WEATHER_SAID = (
    (r"^Wind blowing OUT at (\d+) mph — \+(\d+)% to home-run probability$",
     r"The wind is blowing out at \1 mph, which adds about \2% to the chance of a home run"),
    (r"^Wind blowing IN at (\d+) mph — knocks balls down$",
     r"The wind is blowing in at \1 mph, which knocks fly balls down"),
    (r"^(\d+)°F — warm, thin air helps carry$", r"It's \1°F, and warm air helps the ball carry"),
    (r"^(\d+)°F — cold, heavy air kills carry$", r"It's \1°F, and cold, heavy air keeps the ball in the park"),
)


def _weather_said(text: str) -> str:
    import re
    t = str(text or "").strip()
    for pat, repl in _WEATHER_SAID:
        if re.match(pat, t):
            return _sentence(re.sub(pat, repl, t))
    return _sentence(cap(t))


def mlb_short(c: Ctx, built: dict) -> dict | None:
    """The short version, in sentences (gamereport's note above
    `POS_WORDS`: Ethan, 2026-10-22, "It's very blunt")."""
    items = _short_common(c)
    if _starter(c, c.away) or _starter(c, c.home):
        items.append(_sentence(f"On the mound, {_sp_clause(c, c.away)}, and {_sp_clause(c, c.home)}"))
    why = (c.g.get("conditions") or {}).get("why") or []
    if why:
        items.append(_weather_said(why[0]))
    for t in c.teams:
        tired = _f((_sides(c).get(t) or {}).get("pen_fatigue"))
        if tired is not None and tired >= PEN_TIRED:
            items.append(_sentence(f"{cap(team_owner(c, t))} bullpen is tired: it threw {_num(tired)} relief "
                                   "innings over the last two days"))
    items += _shine_short(c, _reads(c, not_pos={"SP", "P", "RP"}))
    if c.g.get("lineups_confirmed") is False:
        items.append("The lineups are not out yet; they post two to four hours before first pitch.")
    return _section("short", "The short version", [_list(items)])


MLB = ((mlb_facts, sec_market, mlb_pitching, mlb_watch, mlb_park, mlb_injuries, mlb_before), mlb_short)


def mlb_more(g: dict, result: dict) -> dict:
    """What MLB adds to the change log's snapshot (engine/reportlog): the
    probable starters, the weather and whether the lineups are out."""
    out: dict = {"starter_word": "starting pitcher"}
    c_teams = (g.get("away"), g.get("home"))
    sides = ((g.get("mlb_tape") or {}).get("sides") or {})
    st = {}
    for t, side in zip(c_teams, ("away", "home")):
        sp = (sides.get(t) or {}).get("starter") or (g.get("pitchers") or {}).get(side) or {}
        if isinstance(sp, dict) and sp.get("name"):
            st[t] = sp["name"]
    if st:
        out["starters"] = st
    w = g.get("weather") or {}
    if w and not w.get("dome") and str(g.get("roof") or "").lower() not in ("dome", "closed"):
        out["weather"] = {k: w.get(k) for k in ("temp_f", "wind_mph", "wind_dir", "rain") if w.get(k) is not None}
    if isinstance(g.get("lineups_confirmed"), bool):
        out["lineups"] = g["lineups_confirmed"]
    return out


# ═══ NHL ═════════════════════════════════════════════════════════════════════════════
def _goalie(c: Ctx, t: str) -> dict:
    return _sides(c).get(t) or {}


def nhl_facts(c: Ctx) -> dict | None:
    items = _facts_head(c, "Puck drop")
    for t in c.teams:
        s = _goalie(c, t)
        if s.get("b2b"):
            items.append(f"{c.name(t)}: the second night of a back-to-back")
        gp, wt = s.get("gp_season"), _f(s.get("season_weight"))
        if gp is not None and wt is not None and wt < 0.95:
            items.append(f"{t} has played {int(gp)} game{'s' if gp != 1 else ''} this season, so last "
                         f"season still carries {_pct(1 - wt)} of its numbers")
    return _section("facts", "Game facts", [_list(items)])


NHL_ROWS = (("gf", "Goals for a game", 2), ("ga", "Goals against a game", 2),
            ("sog_for", "Shots for a game", 1), ("sog_against", "Shots against a game", 1),
            ("xgf_ev", "5-on-5 xG for", 2), ("xga_ev", "5-on-5 xG against", 2))


def nhl_tape(c: Ctx) -> dict | None:
    sides = _sides(c)
    a, h = sides.get(c.away) or {}, sides.get(c.home) or {}
    if not a and not h:
        return None
    n = _tape(c).get("teams") or 32

    def cell(s, k, nd):
        v = _f(s.get(k))
        if v is None:
            return "—"
        rk = (s.get("ranks") or {}).get(k)
        return f"{v:.{nd}f}" + (f" ({_ord(int(rk))})" if rk else "")
    rows = [[label, cell(a, k, nd), cell(h, k, nd)] for k, label, nd in NHL_ROWS]
    rows = [r for r in rows if r[1] != "—" or r[2] != "—"]
    if _f(a.get("xg")) is not None or _f(h.get("xg")) is not None:
        rows.append(["Expected goals tonight",
                     _num(a.get("xg"), 2) if _f(a.get("xg")) is not None else "—",
                     _num(h.get("xg"), 2) if _f(h.get("xg")) is not None else "—"])
    blocks = [{"type": "table", "title": "Tale of the tape", "head": ["", c.away, c.home], "rows": rows,
               "note": f"Ranks out of {n}; 1st is the best — the most for, the fewest against. xG is "
                       "expected goals, the quality of the chances, from our own shot model; tonight's "
                       "figure is the game model's, goalies and rest included."}]
    items = []
    for t in c.teams:
        mine, them = sides.get(t) or {}, sides.get(c.opp[t]) or {}
        r_for, r_against = (mine.get("ranks") or {}).get("sog_for"), (them.get("ranks") or {}).get("sog_against")
        if r_for and r_against and r_for <= 8 and r_against >= n - 7:
            items.append(f"{t} shoots the {_ord(int(r_for))}-most, and {c.opp[t]} allows the "
                         f"{_ord(n - int(r_against) + 1)}-most shots — a busy night for {c.opp[t]}'s goalie")
    blocks.append(_list(items))
    return _section("tape", "The matchup", blocks)


def nhl_goalies(c: Ctx) -> dict | None:
    items = []
    for t in c.teams:
        s = _goalie(c, t)
        if not s.get("starter"):
            items.append(f"{t}: no starter named yet")
            continue
        bits = ["confirmed" if s.get("starter_sure") else "probable, not confirmed"]
        if _f(s.get("starter_sv")) is not None:
            bits.append(f".{round(float(s['starter_sv']) * 1000):03d} save rate")
        if _f(s.get("starter_gsax")) is not None:
            bits.append(f"{float(s['starter_gsax']):+.1f}".replace("-", "\u2212")
                        + " goals saved above expected lately")
        if _f(s.get("starter_share")) is not None:
            bits.append(f"started {_pct(s['starter_share'])} of {c.poss(t)} recent games")
        items.append(f"{s['starter']} for {t} — {'; '.join(bits)}")
    blocks = [_list(items)]
    goalies = _reads(c, pos={"G"})
    if goalies:
        blocks += [_h("How each goalie sets up"),
                   {"type": "verdicts", "items": [_verdict(r, both=True) for r in goalies]}]
    return _section("goalies", "In net", blocks)


def nhl_watch(c: Ctx) -> dict | None:
    return _section("watch", "Players to watch", shine_struggle(c, _reads(c, not_pos={"G"})))


def nhl_injuries(c: Ctx) -> dict | None:
    items = []
    for t in c.teams:
        for i in (_goalie(c, t).get("injuries") or []):
            if isinstance(i, dict) and i.get("player"):
                items.append(f"{i['player']} ({t}) — {str(i.get('status') or '').lower()}"
                             + (f", {str(i['injury']).lower()}" if i.get("injury") else ""))
    pulled = [p for p in _tape(c).get("pulled") or [] if p]
    blocks = [_list(items)]
    if pulled:
        blocks.append(_p(f"Every book took {_join(pulled)}'s props down before puck drop — treated as "
                         "out until the lineup or the books say otherwise"))
    return _section("injuries", "Injuries", blocks)


def nhl_before(c: Ctx) -> dict | None:
    lines = []
    unsure = [t for t in c.teams if _goalie(c, t).get("starter") and not _goalie(c, t).get("starter_sure")]
    if unsure:
        lines.append("Starting goalies are confirmed after the morning skate; not yet for "
                     + _join(unsure) + " — a backup in net moves the line and every shooter's read")
    if any(_goalie(c, t).get("b2b") for t in c.teams):
        lines.append("On a back-to-back the second night's goalie is often the backup")
    lines.append("Line combinations change at the morning skate; a skater moved off the top six or "
                 "the first power-play unit loses ice time")
    lines += _stale(c)
    return _section("before", "Before puck drop", [_list(lines)])


def nhl_short(c: Ctx, built: dict) -> dict | None:
    """The short version, in sentences (see mlb_short)."""
    items = _short_common(c)
    gl = []
    for t in c.teams:
        s = _goalie(c, t)
        if s.get("starter"):
            gl.append(f"{s['starter']} for {team_np(c, t)}"
                      + (" (confirmed)" if s.get("starter_sure") else " (expected, not confirmed yet)"))
    if gl:
        items.append(_sentence("In net: " + " against ".join(gl)))
    xg = [(t, _f(_goalie(c, t).get("xg"))) for t in c.teams]
    if all(v is not None for _t, v in xg):
        (ta, va), (tb, vb) = xg
        items.append(_sentence(f"Our game model expects about {va:.1f} goals from {team_np(c, ta)} and "
                               f"{vb:.1f} from {team_np(c, tb)}"))
    for t in c.teams:
        if _goalie(c, t).get("b2b"):
            items.append(_sentence(f"{cap(team_np(c, t))} {team_be(c, t)} on the second night of a "
                                   "back-to-back, when the starting goalie often sits for the backup"))
    items += _shine_short(c, _reads(c, not_pos={"G"}))
    outs = [{"player": i["player"], "team": t, "status": "OUT", "position": ""}
            for t in c.teams for i in _goalie(c, t).get("injuries") or []
            if isinstance(i, dict) and i.get("player")
            and str(i.get("status") or "").lower() not in ("day-to-day", "questionable", "")]
    gone = absent_sentence(c, outs)
    if gone:
        items.append(gone)
    return _section("short", "The short version", [_list(items)])


NHL = ((nhl_facts, sec_market, nhl_tape, nhl_goalies, nhl_watch, nhl_injuries, nhl_before), nhl_short)


def nhl_more(g: dict, result: dict) -> dict:
    """What the NHL adds to the change log's snapshot: the starting
    goalies, whether each is confirmed, and the injury report."""
    sides = ((g.get("nhl_tape") or {}).get("sides") or {})
    if not sides:
        return {}
    out: dict = {"starter_word": "starting goalie",
                 "starters": {t: s.get("starter") for t, s in sides.items() if s.get("starter")},
                 "confirmed": {t: bool(s.get("starter_sure")) for t, s in sides.items() if s.get("starter")},
                 "injuries": {}, "who": {}}
    for t, s in sides.items():
        for i in s.get("injuries") or []:
            if isinstance(i, dict) and i.get("player"):
                out["injuries"][str(i["player"])] = str(i.get("status") or "").lower()
                out["who"][str(i["player"])] = t
    out["pulled"] = sorted(str(p) for p in (g.get("nhl_tape") or {}).get("pulled") or [] if p)
    return out


# ═══ NBA and WNBA ════════════════════════════════════════════════════════════════════
REST_SHORT = {"b2b_home": "on the second night of a back-to-back", "3in4": "playing a third game in four nights",
              "4in6_road": "playing a fourth game in six nights", "2plus": "rested", "1day": "on one day off"}

#: The defence stats the report names, in order, with how each reads.
DEF_STATS = (("pts", "points"), ("reb", "rebounds"), ("ast", "assists"), ("fg3m", "threes"))


def _spots(c: Ctx) -> dict:
    for r in c.result.get("schedule_spots") or []:
        if isinstance(r, dict) and r.get("home") == c.home and r.get("away") == c.away:
            return r
    return {}


def _spot(c: Ctx, t: str) -> dict:
    return ((_spots(c).get("teams") or {}).get("home" if t == c.home else "away")) or {}


def nba_facts(c: Ctx) -> dict | None:
    items = _facts_head(c, "Tip-off")
    sp = _spots(c)
    if sp.get("arena"):
        feet = _f(sp.get("feet"))
        items.append(f"Arena: {sp['arena']}" + (f" — {int(feet):,} feet up" if feet and feet >= 4000 else ""))
    for t in c.teams:
        s = _spot(c, t)
        bits = []
        if s.get("rest") in REST_SHORT:
            bits.append(REST_SHORT[s["rest"]])
        if _f(s.get("miles")) and s.get("from") and s.get("from") != c.home:
            trip = f"{int(s['miles']):,} miles from {s['from']}"
            if s.get("days_since"):
                trip += f" ({_plural_days(s['days_since'])} ago)"
            bits.append(trip)
        tz = _f(s.get("tz_shift"))
        if tz:
            bits.append(f"the clock {'moved ahead' if tz > 0 else 'moved back'} "
                        f"{int(abs(tz))} hour{'s' if abs(tz) != 1 else ''}")
        if "altitude" in (s.get("flags") or []):
            bits.append("up from near sea level to altitude")
        if bits:
            items.append(f"{c.name(t)}: {'; '.join(bits)}")
    if any("blowout" in (_spot(c, t).get("flags") or []) for t in c.teams):
        items.append("Blowout watch: a spread of 10 or more — starters' minutes are the first thing a "
                     "coach takes back in a lopsided game")
    return _section("facts", "Game facts", [_list(items)])


def _plural_days(n) -> str:
    n = int(n)
    return "a day" if n == 1 else f"{n} days"


def nba_carry(c: Ctx) -> dict | None:
    carry = c.meta.get("carry") or {}
    blocks = []
    for t in c.teams:
        rows = [r for r in carry.get(t) or [] if isinstance(r, dict) and r.get("player")]
        if not rows:
            continue
        items = []
        for r in rows[:CARRY_N]:
            bits = [f"{_num(r[k])} {w}" for k, w in (("min", "minutes"), ("pts", "points"), ("reb", "rebounds"),
                                                     ("ast", "assists"), ("fg3m", "threes"))
                    if _f(r.get(k)) is not None]
            items.append({"player": r["player"], "team": t, "pos": r.get("pos") or "",
                          "label": "Starter" if r.get("starter") else "", "tone": "",
                          "text": (f"{', '.join(bits)} a game over his last {r.get('games')}"
                                   if bits else "")})
        blocks += [_h(f"{c.name(t)}"), {"type": "players", "items": items}]
    if not blocks:
        return None
    return _section("carry", "Who carries each team", blocks)


def nba_defense(c: Ctx) -> dict | None:
    dvp = c.meta.get("dvp") or {}
    items = []
    for t in c.teams:
        d = dvp.get(t) or {}
        soft, hard = [], []
        for k, word in DEF_STATS:
            r = d.get(k) or {}
            rank, of = r.get("rank"), r.get("of")
            if not rank or not of or _f(r.get("pg")) is None:
                continue
            if rank <= 5:
                soft.append(f"{word} ({_num(r['pg'])} a game, {_ord(int(rank))}-most; league {_num(r.get('league'))})")
            elif rank > of - 5:
                hard.append(f"{word} ({_num(r['pg'])} a game, {_ord(int(of - rank + 1))}-fewest; "
                            f"league {_num(r.get('league'))})")
        if soft:
            items.append(f"{t}'s defence gives up the most {_join(soft)}")
        if hard:
            items.append(f"{t}'s defence gives up the fewest {_join(hard)}")
    if not items:
        return None
    note = ("Per game, not per possession: a fast team's defence reads a little worse than it is"
            + ("; last season's numbers, this one is too young to rank" if c.meta.get("dvp_last") else ""))
    return _section("defense", "Where each defence gives", [_list(items), {"type": "note", "text": _sentence(note)}])


def nba_tape(c: Ctx) -> dict | None:
    """The tale of the tape (engine/nba/scan formats the rows) and the key
    matchups — where one side's offence meets the other's defence at the far
    ends of the league."""
    t = c.g.get("nba_tape") or {}
    rows = [r for r in t.get("rows") or [] if isinstance(r, dict) and r.get("label")]
    if not rows:
        return None

    def cell(v, rk):
        return str(v or "—") + (f" ({_ord(int(rk))})" if rk and v not in (None, "—") else "")
    table = [[r["label"], cell(r.get("a"), r.get("ar")), cell(r.get("h"), r.get("hr"))] for r in rows]
    note = " ".join(x for x in (t.get("basis"), t.get("note")) if x)
    blocks = [{"type": "table", "title": "Tale of the tape", "head": ["", c.away, c.home], "rows": table,
               "note": _sentence(note) if note else ""}]
    edges = [e.get("text") for e in t.get("edges") or [] if isinstance(e, dict) and e.get("text")]
    if edges:
        blocks += [_h("Key matchups"), _list(edges)]
    return _section("tape", "The matchup", blocks)


def nba_watch(c: Ctx) -> dict | None:
    """The breakout watch, then who could shine and who could struggle."""
    reads = c.reads
    brk = sorted((r for r in reads if r.get("read") == "breakout"), key=lambda r: -len(r.get("pro") or []))
    good = sorted((r for r in reads if r.get("read") == "good"), key=lambda r: -len(r.get("pro") or []))
    bad = sorted((r for r in reads if r.get("read") in ("tough", "avoid")),
                 key=lambda r: (r.get("read") != "avoid", -len(r.get("con") or [])))
    blocks = []
    if brk:
        blocks += [_h("Breakout watch"), {"type": "verdicts", "items": [_verdict(r, "up") for r in brk[:SHINE_N]]}]
    if good:
        blocks += [_h("Could shine"), {"type": "verdicts", "items": [_verdict(r, "up") for r in good[:SHINE_N]]}]
    if bad:
        blocks += [_h("Could struggle"),
                   {"type": "verdicts", "items": [_verdict(r, "down") for r in bad[:STRUGGLE_N]]}]
    if reads and not brk and not good:
        blocks.append(_p("No one in this game reads as a breakout spot or a good matchup"))
    return _section("watch", "Players to watch", blocks)


def nba_injuries(c: Ctx) -> dict | None:
    inj = [i for i in c.meta.get("injuries") or [] if isinstance(i, dict) and i.get("player")
           and i.get("team") in c.teams]
    if not inj:
        return None
    items = [f"{i['player']} ({i['team']}) — {str(i.get('status') or '').lower()}"
             + (f", {str(i['injury']).lower()}" if i.get("injury") else "") for i in inj]
    return _section("injuries", "Injuries", [_list(items)])


def nba_before(c: Ctx) -> dict | None:
    lines = ["The injury report updates through the day; starting lineups come about half an hour "
             "before tip-off"]
    q = [i for i in c.meta.get("injuries") or [] if isinstance(i, dict) and i.get("team") in c.teams
         and str(i.get("status") or "").lower() in ("questionable", "doubtful", "probable", "day-to-day", "game time decision")]
    if q:
        lines.append("Still to be decided: " + _join(f"{i['player']} ({i['team']}, {str(i['status']).lower()})"
                                                     for i in q))
    lines += _stale(c)
    return _section("before", "Before tip-off", [_list(lines)])


def nba_short(c: Ctx, built: dict) -> dict | None:
    """The short version, in sentences (see mlb_short)."""
    items = _short_common(c)
    for t in c.teams:
        s = _spot(c, t)
        if s.get("rest") in ("b2b_home", "3in4", "4in6_road"):
            items.append(_sentence(f"{cap(team_np(c, t))} {team_be(c, t)} {REST_SHORT[s['rest']]}"))
    outs = [{"player": i["player"], "team": i["team"], "status": "OUT", "position": ""}
            for i in c.meta.get("injuries") or [] if isinstance(i, dict) and i.get("team") in c.teams
            and str(i.get("status") or "").lower() == "out"]
    gone = absent_sentence(c, outs, per_team=6)
    if gone:
        items.append(gone)
    carry = c.meta.get("carry") or {}
    leads = []
    for t in c.teams:
        rows = [r for r in carry.get(t) or [] if isinstance(r, dict) and _f(r.get("pts")) is not None]
        if rows:
            r = rows[0]
            n = int(r.get("games") or 0)
            leads.append(f"{r['player']} for {team_np(c, t)} ({_num(r['pts'])} points a game"
                         + (f" over his last {n}" if n else "") + ")")
    if leads:
        items.append(_sentence("Leading the scoring lately: " + _join(leads)))
    edges = [e for e in (c.g.get("nba_tape") or {}).get("edges") or [] if isinstance(e, dict) and e.get("text")]
    if edges:
        e = edges[0]
        items.append(_sentence(f"The key matchup: {named(c, e.get('matchup') or e['text'])}"
                               + (f", an edge for {team_np(c, e['team'])}" if e.get("team") and e.get("matchup")
                                  else "")))
    brk = [r for r in c.reads if r.get("read") == "breakout"]
    if brk:
        items.append(_sentence("On breakout watch: " + ". ".join(player_clause(c, r, "up", tag=False)
                                                                  for r in brk[:3])))
    items += _shine_short(c, [r for r in c.reads if r.get("read") != "breakout"])
    if any("blowout" in (_spot(c, t).get("flags") or []) for t in c.teams):
        items.append("Blowout watch: with a spread of 10 or more, the starters' minutes are the first thing "
                     "a coach takes back if it turns lopsided.")
    return _section("short", "The short version", [_list(items)])


NBA = ((nba_facts, sec_market, nba_tape, nba_watch, nba_carry, nba_defense, nba_injuries, nba_before), nba_short)


def nba_more(g: dict, meta: dict | None) -> dict:
    """What basketball adds to the change log's snapshot: the injury report."""
    inj = [i for i in (meta or {}).get("injuries") or [] if isinstance(i, dict) and i.get("player")]
    if not (meta or {}).get("injuries_read"):
        return {}
    return {"injuries": {str(i["player"]): str(i.get("status") or "").lower() for i in inj},
            "who": {str(i["player"]): str(i.get("team") or "") for i in inj}}


def nba_meta(games: list, hist: dict, listed: dict, dvp: dict | None = None, dvp_last: bool = False,
             injuries_read: bool = True) -> dict:
    """{"AWAY@HOME": what the NBA build knows that the board does not carry}:
    who carries each team over his last ten (minutes, points, rebounds,
    assists, threes — off the build's own `player_history`), the injury
    report's names on the two teams, and the defence ratings."""
    out: dict = {}
    hurt = {p for p, i in (listed or {}).items()
            if str((i or {}).get("status") or "").strip().lower() == "out"}
    for g in games or []:
        h, a = g.get("home"), g.get("away")
        if not h or not a:
            continue
        carry = {}
        for t in (a, h):
            rows = []
            for p, x in (hist or {}).items():
                if x.get("team") != t or p in hurt:
                    continue
                mins = [float(v) for v in (x.get("minutes") or [])[:10] if v is not None]
                if len(mins) < 3:
                    continue
                row = {"player": p, "games": len(mins), "min": round(sum(mins) / len(mins), 1),
                       "starter": bool(x.get("starter"))}
                for k in ("pts", "reb", "ast", "fg3m"):
                    vs = [float(v) for v in (x.get(k) or [])[:10] if v is not None]
                    if vs:
                        row[k] = round(sum(vs) / len(vs), 1)
                rows.append(row)
            rows.sort(key=lambda r: -r["min"])
            carry[t] = rows[:CARRY_N]
        inj = [{"player": (i or {}).get("player") or p, "team": (hist.get(p) or {}).get("team"),
                "status": (i or {}).get("status") or "", "injury": (i or {}).get("injury") or ""}
               for p, i in (listed or {}).items() if (hist.get(p) or {}).get("team") in (a, h)]
        out[f"{a}@{h}"] = {"carry": carry, "injuries": sorted(inj, key=lambda i: (i["team"], i["player"])),
                           "injuries_read": bool(injuries_read),
                           "dvp": {t: (dvp or {}).get(t) or {} for t in (a, h)}, "dvp_last": bool(dvp_last)}
    return out


# ═══ THE HOOK ════════════════════════════════════════════════════════════════════════
BUILDERS = {"mlb": MLB, "nhl": NHL, "nba": NBA, "wnba": NBA}


def build(g: dict, result: dict, *, sport: str, names: dict | None = None, meta: dict | None = None,
          changes: dict | None = None) -> dict | None:
    """One game's report, or None for a row with no teams or a league this
    module does not write."""
    if not isinstance(g, dict) or not g.get("away") or not g.get("home") or sport not in BUILDERS:
        return None
    c = Ctx(g, result, names=names if names is not None else team_names(sport), sport=sport,
            meta=meta, changes=changes)
    fns, short = BUILDERS[sport]
    return finish(c, fns, short)


def attach(result: dict, sport: str, *, meta: dict | None = None, out=None, at: str | None = None) -> str:
    """``result["game_reports"]`` for every game on an MLB, NHL, NBA or WNBA
    board. ``meta`` is {"AWAY@HOME": what the build knows of a game and the
    board leaves off} (basketball's: nba_meta). ``out`` is the board's
    public path; what changed is kept beside its private copy, stamped
    ``at``. One line for the build log; never raises."""
    try:
        names = team_names(sport)
        prepared = []
        for g in result.get("games") or []:
            if not isinstance(g, dict) or not g.get("home") or not g.get("away"):
                continue
            m = (meta or {}).get(f"{g['away']}@{g['home']}") or {}
            more = (mlb_more(g, result) if sport == "mlb" else nhl_more(g, result) if sport == "nhl"
                    else nba_more(g, m))
            prepared.append((g, m, more))
        logged = log_changes(result, [(g, {}, more) for g, _m, more in prepared], sport, out, at)
        reports = []
        for g, m, _more in prepared:
            r = build(g, result, sport=sport, names=names, meta=m,
                      changes=logged.get(f"{g['away']}@{g['home']}|{str(g.get('date') or '')[:10]}"))
            if r:
                reports.append(r)
        result[KEY] = reports
        if not reports:
            return "Game reports: no games on the board"
        return summary(reports, logged, out)
    except Exception as exc:                                 # noqa: BLE001
        result.pop(KEY, None)
        return f"⚠️  Game reports skipped ({type(exc).__name__}: {exc})"
