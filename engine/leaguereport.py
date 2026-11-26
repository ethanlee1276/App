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

from .gamereport import (KEY, Ctx, _claimed_list, _f, _h, _join, _lift_bets, _list, _num, _ord, _p, _pct, _section,
                         _sentence, a_pct, absent_sentence, cap, finish, injury_claim, keep_started, kickoff_words,
                         line_words, newest_word, stamp_track,
                         log_changes, market_sentence, ml_chances, named, parlay_sentence, player_clause,
                         read_pick, sec_market, sec_parlays, shine_lines, summary, team_be, team_np, team_owner)

#: The leagues this module writes.
SPORTS = ("mlb", "nhl", "nba", "wnba", "cbb")

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


#: A reason's first word that is an article, lowered after a colon like any other word ("Against: a lopsided
#: game", never "Against: A lopsided game").
ARTICLES = ("A ", "An ", "The ")


#: A basketball game with a spread of 10 or more, in one sentence wherever a report says it (the facts and the
#: short version said it in two ways, 25 November 2026).
BLOWOUT_WATCH = ("Blowout watch: with a spread of 10 or more, the starters' minutes are the first thing a coach "
                 "takes back if it turns lopsided")


def _lower_first(x: str) -> str:
    """A reason as the middle of a sentence: its first letter small, unless
    the first word is a code or a name in capitals ("PHI rarely ...")."""
    if x.startswith(ARTICLES):
        return x[0].lower() + x[1:]
    return x[0].lower() + x[1:] if len(x) > 1 and x[1].islower() else x


def _verdict(r: dict, tone: str | None = None, both: bool = False) -> dict:
    """A read as a player card: his reasons for (shine) or against
    (struggle), or both (a starter). A starter's or a goalie's card leads
    with the case for its own label (25 November 2026: "Tough matchup" over
    his strengths, the case for it under "Against:"), the other side after."""
    tone = tone or {"breakout": "up", "good": "up", "tough": "down", "avoid": "down"}.get(r.get("read"), "")
    pro = [str(x) for x in r.get("pro") or [] if x]
    con = [str(x) for x in r.get("con") or [] if x]
    if both and tone == "down":
        why = con[:3] + [f"In favor: {_lower_first(x)}" for x in pro[:2]]
    elif both:
        why = pro[:3] + [f"Against: {_lower_first(x)}" for x in con[:2]]
    else:
        why = (pro if tone == "up" else con)[:3]
    notes = [str(x) for x in r.get("notes") or [] if x][:1]
    out = {"title": r.get("player"), "player": r.get("player"), "team": r.get("team"),
           "pos": r.get("pos") or "", "label": r.get("label") or "", "verdict": tone,
           "headshot": r.get("headshot") or "", "why": [_sentence(w) for w in why + notes]}
    # The stats the read leans on: what a finished game grades it by (engine/reportgrade).
    if r.get("lean"):
        out["lean"] = list(r["lean"])
    # MAY SIT (engine/availability, 2026-11-14): the mark, and why, first; the
    # scan's own "listed questionable" note gives way to it.
    if r.get("availability"):
        from .availability import LABELS
        out["status"] = LABELS.get(r["availability"], "")
        out["why"] = [_sentence(r.get("availability_note") or "")] + [
            w for w in out["why"] if "listed questionable" not in w and "is listed" not in w]
    return out


def shine_struggle(c: Ctx, reads: list) -> list:
    """THE RESEARCH'S BREAKOUT CANDIDATES AND FADES (engine/breakouts,
    2026-11-15): each player's case in its measured reasons, his notes, his
    pick on the read's side and the main way it loses, strongest first."""
    from .breakouts import blocks
    return blocks(reads, pick_fn=read_pick, head_fn=_h)


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


def _ours(c: Ctx, e: dict) -> bool:
    """A key matchup between this game's two teams (step AHY): a tape that carried another game's edge would have
    said "LAM's offensive rebounding against RMU's" in Vanderbilt at Ohio State. An edge naming no teams stands."""
    named = [x for x in (e.get("off"), e.get("def"), e.get("team")) if x]
    return all(x in c.teams for x in named)


def _sides(c: Ctx) -> dict:
    return _tape(c).get("sides") or {}


def _starter(c: Ctx, t: str) -> dict:
    sp = (_sides(c).get(t) or {}).get("starter")
    if isinstance(sp, dict) and sp.get("name"):
        return sp
    p = (c.g.get("pitchers") or {}).get("home" if t == c.home else "away")
    return p if isinstance(p, dict) and p.get("name") else {}


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
    # Each club's form (the board's `team_recent`: its newest ten finals this
    # season, engine/teamlogs), said the way the other leagues' reports say it.
    items += form_lines(c, form_from_recent(c.result.get("team_recent"), c.teams))
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
        note = "Expected ERA is what the contact allowed should have cost, not what it did"
        if any(r[0].startswith("SLG") for r in rows):
            note += "; SLG allowed is the slugging percentage allowed to each side of the plate"
        blocks.append({"type": "table", "title": "The starters",
                       "head": ["", f"{sa.get('name') or 'TBA'} ({t_a})", f"{sh.get('name') or 'TBA'} ({t_h})"],
                       "rows": rows, "note": _sentence(note)})
    items = []
    league = (_tape(c).get("league") or {})
    for t in (t_a, t_h):
        s = _sides(c).get(t) or {}
        if s.get("mix"):
            # BY NAME (step AHY): "Phillies' starter's pitch mix" under a table that names him.
            sp = _starter(c, t)
            whose = f"{sp['name']}'s" if sp.get("name") else f"{c.poss(t)} starter's"
            items.append(f"{whose} pitch mix: {s['mix']}")
        vh = s.get("vs_hand") or {}
        if _f(vh.get("factor")) is not None and vh.get("hand"):
            f = float(vh["factor"]) - 1
            how = (f"{_pct(abs(f))} {'better' if f > 0 else 'worse'} than its average"
                   if abs(f) >= HAND_EDGE else "about its average")
            items.append(f"{t}'s lineup hits {_hand(vh['hand'])} pitching {how} "
                         f"({vh.get('hitters')} hitters measured)")
        if _f(s.get("k_rate")) is not None:
            items.append(f"{t} strikes out {_pct(s['k_rate'], 1)} of the time"
                         + (f" (the league average is {_pct(league['k_rate'])})"
                            if _f(league.get("k_rate")) is not None else ""))
    pens = []
    for t in (t_a, t_h):
        s = _sides(c).get(t) or {}
        bits = []
        if s.get("pen_rank"):
            bits.append(f"ranks {_ord(int(s['pen_rank']))}")
        fat = _f(s.get("pen_fatigue"))
        if fat is not None and fat >= PEN_TIRED:
            bits.append(f"is tired after {_num(fat)} relief innings over the last two days")
        if bits:
            pens.append(f"{c.poss(t)} bullpen {' and '.join(bits)}")
    if pens:
        items.append("The bullpens: " + "; ".join(pens))
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
            fac.append(f"{d}% more {w}" if d > 0 else f"{abs(d)}% fewer {w}" if d < 0 else f"the usual {w}")
    items = []
    if fac:
        # "plays +4% home runs, ±0% strikeouts" (2026-11-15): said as more,
        # fewer and the usual.
        items.append(f"Compared with an average park, {tp.get('name') or park.get('name') or 'this park'} "
                     f"sees {_join(fac)}")
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
        items.append(_weather_said(str(why)))
    ump = _tape(c).get("umpire") or {}
    if ump.get("name"):
        bits = []
        for k, word in (("k", "strikeouts"), ("runs", "runs")):
            v = _f(ump.get(k))
            if v is not None and abs(v - 1) >= 0.02:
                bits.append(f"{round(abs(v - 1) * 100)}% {'more' if v > 1 else 'fewer'} {word}")
        items.append(f"Plate umpire {ump['name']}" + (f": games behind this plate umpire have {_join(bits)} than average" if bits else
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
        lines.append("Lineups come out two to four hours before first pitch; a hitter who isn't in the "
                     "lineup won't bat, so skip that read")
    lines.append("A probable starter can be scratched up to first pitch — the line moves when one is")
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
        bits.append(f"striking out {_pct(sp['k_rate'])} of the batters faced")
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
    par = parlay_sentence(c)
    if par:
        items.append(par)
    return _section("short", "The short version", [_list(items)])


MLB = ((mlb_facts, sec_market, mlb_pitching, mlb_watch, mlb_park, mlb_injuries, sec_parlays, mlb_before),
       mlb_short)


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
               "rank_of": n,
               "note": f"Ranks out of {n}; 1st is the best — the most for, the fewest against. xG is "
                       "expected goals, the quality of the chances, from our own shot model; tonight's "
                       "figure is the game model's, goalies and rest included."}]
    # Each side's form this season first (`team_form`, filled by nhl_build).
    items = [(x, None) for x in form_lines(c, c.g.get("form") or {})]
    for t in c.teams:
        mine, them = sides.get(t) or {}, sides.get(c.opp[t]) or {}
        r_for, r_against = (mine.get("ranks") or {}).get("sog_for"), (them.get("ranks") or {}).get("sog_against")
        if r_for and r_against and r_for <= 8 and r_against >= n - 7:
            # Graded on a finished game: its shots on goal against its own a game.
            base = _f(mine.get("sog_for"))
            # The counts beside the ranks (step AHR): the tape's own numbers.
            took, let = base, _f(them.get("sog_against"))
            items.append(((f"{t} takes the {_ord(int(r_for))}-most shots ({_num(took)} a game), and {c.opp[t]} "
                           f"allows the {_ord(n - int(r_against) + 1)}-most ({_num(let)} a game) — a busy night "
                           f"for {c.opp[t]}'s goalie") if took is not None and let is not None else
                          (f"{t} takes the {_ord(int(r_for))}-most shots, and {c.opp[t]} allows the "
                           f"{_ord(n - int(r_against) + 1)}-most — a busy night for {c.opp[t]}'s goalie"),
                          {"kind": "team", "team": t, "opp": c.opp[t], "stat": "sog", "favors": "more",
                           **({"base": round(base, 2)} if base is not None else {})}))
    blocks.append(_claimed_list(items))
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
            from .nhl.scan import gsax_words
            bits.append(gsax_words(s["starter_gsax"], s.get("starter_gsax_games")))
        if _f(s.get("starter_share")) is not None:
            from .nhl.model import STARTER_WINDOW
            from .gamereport import team_owner
            bits.append(f"started {_pct(s['starter_share'])} of {team_owner(c, t)} last {STARTER_WINDOW} games")
        items.append(f"{s['starter']} for {t} — {'; '.join(bits)}")
    blocks = [_list(items)]
    goalies = _reads(c, pos={"G"})
    if goalies:
        blocks += [_h("How each goalie sets up"),
                   {"type": "verdicts", "items": [_verdict(r, both=True) for r in goalies]}]
    return _section("goalies", "In net", blocks)


def nhl_watch(c: Ctx) -> dict | None:
    return _section("watch", "Players to watch", shine_struggle(c, _reads(c, not_pos={"G"})))


#: Which of tonight's units the report names: the top two forward lines and
#: the top defence pair.
NHL_LINE_UNITS = (("forwards", 0, "Top line"), ("forwards", 1, "Second line"), ("defence", 0, "Top pair"))
NHL_OUT = ("out", "injured reserve", "ir", "ltir", "suspended")


def nhl_lines(c: Ctx) -> dict | None:
    """WHO PLAYS WITH WHOM TONIGHT, AND WHO IS MISSING (the research's "what
    the absences change", hockey's way): each team's top two forward lines
    and top defence pair, read off the shift charts of its newest games with
    tonight's ruled-out men left out (engine/nhl/lines, nhl_build.team_lines),
    how settled each is, and who they are built without. A shooter's line is
    his ice time and his linemates; a top-six man out moves somebody up."""
    lines = (c.result.get("lines") or {})
    blocks = []
    for t in c.teams:
        tl = lines.get(t) or {}
        items = []
        for kind, i, word in NHL_LINE_UNITS:
            grp = (tl.get(kind) or [])[i:i + 1]
            if not grp or not grp[0].get("players"):
                continue
            g = grp[0]
            tog = _f(g.get("together"))
            items.append(f"{word}: {_join(g['players'])}"
                         + (f" (together for {_pct(tog)} of their ice lately)" if tog else ""))
        out = [str(i.get("player")) for i in (_goalie(c, t).get("injuries") or [])
               if isinstance(i, dict) and i.get("player")
               and str(i.get("status") or "").strip().lower() in NHL_OUT]
        if out and items:
            items.append(f"Built without {_join(out)} (out): whoever takes their "
                         f"shifts gets more ice time")
        if items:
            blocks += [_h(c.name(t)), _list(items)]
    if not blocks:
        return None
    n = max((int((lines.get(t) or {}).get("games") or 0) for t in c.teams), default=0)
    blocks.append({"type": "note", "text": _sentence(
        f"From the shift charts of each team's last {n} games" if n else "From the shift charts of each team's "
        "newest games") + " The newest games count most; the morning skate can still change them."})
    return _section("lines", "The lines", blocks)


def hockey_meeting(conn, home: str, away: str, before: str) -> dict:
    """The last time these two met (`last_meeting`'s score), with who scored
    for each side that night (the history's box scores)."""
    m = last_meeting(conn, "nhl", home, away, before, None)
    if not m:
        return {}
    scorers = {}
    for t in (m["home"], m["away"]):
        rows = conn.execute(
            "SELECT player, value FROM player_game_logs WHERE sport='nhl' AND period=? AND team=? "
            "AND market='goals' AND value > 0 ORDER BY value DESC, player", (m["day"], t)).fetchall()
        scorers[t] = [{"player": r[0], "goals": int(r[1])} for r in rows[:4]]
    m["scorers"] = scorers
    m.pop("leaders", None)
    m.pop("missing", None)
    return m


def nhl_meeting(c: Ctx) -> dict | None:
    """THE LAST MEETING (the research's "direct precedent"): the score and who
    scored for each side."""
    m = c.g.get("last_meeting") or {}
    if not m.get("day") or not m.get("home") or not m.get("away"):
        return None
    from .gamereport import day_label
    h, a = m["home"], m["away"]
    hs, as_ = int(m.get("home_score") or 0), int(m.get("away_score") or 0)
    won, lost = (h, a) if hs > as_ else (a, h)
    when = day_label(m["day"], 0, 0) or m["day"]
    try:
        from .seasons import season_of
        if season_of("nhl", m["day"]) < season_of("nhl", c.g.get("date") or m["day"]):
            when += ", last season"
    except Exception:                                    # noqa: BLE001
        pass
    items = [f"{when}: {team_np(c, won)} beat {team_np(c, lost)} {max(hs, as_)}-{min(hs, as_)} "
             f"{'at home' if won == h else 'on the road'}"]
    for t in (a, h):
        sc = [x for x in (m.get("scorers") or {}).get(t) or [] if x.get("player")]
        if sc:
            items.append(cap(f"{team_owner(c, t)} goals: ")
                         + _join(f"{x['player']}" + (f" ({x['goals']})" if x.get("goals", 1) > 1 else "") for x in sc))
    return _section("meetings", "The last meeting", [_list(items)])


def nhl_injuries(c: Ctx) -> dict | None:
    items = []
    for t in c.teams:
        for i in (_goalie(c, t).get("injuries") or []):
            if isinstance(i, dict) and i.get("player"):
                items.append((f"{i['player']} ({t}) — {str(i.get('status') or '').lower()}"
                              + (f", {str(i['injury']).lower()}" if i.get("injury") else "")
                              # Which way his newest blurb leans (step ABY).
                              + (f"; {newest_word(c, t, i['player'])}" if newest_word(c, t, i["player"]) else ""),
                              injury_claim(i["player"], t, i.get("status"))))
    pulled = [p for p in _tape(c).get("pulled") or [] if p]
    blocks = [_claimed_list(items)]
    if pulled:
        who = "that player" if len(pulled) == 1 else "those players"
        blocks.append(_p(f"Every sportsbook pulled its props on {_join(pulled)} before puck drop, so we count "
                         f"{who} as out until the lineup or the books say otherwise"))
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
    par = parlay_sentence(c)
    if par:
        items.append(par)
    return _section("short", "The short version", [_list(items)])


#: The hockey report, in the research's order: the facts and the line, the
#: matchup, the goalies, who plays with whom (and who is missing), the
#: breakout candidates and fades, the last meeting, then the rest.
NHL = ((nhl_facts, sec_market, nhl_tape, nhl_goalies, nhl_lines, nhl_watch, nhl_meeting, nhl_injuries, sec_parlays,
        nhl_before), nhl_short)


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
#: How each rest state reads for its team in the facts list (2026-11-15,
#: Ethan: "if it's good, then green, if it's bad, then red"); one day off
#: is the usual and stays plain. Marked here, not on the page, because the
#: word "rested" means nothing on its own elsewhere ("for the rested and
#: the tournament-worn alike").
REST_TONE = {"b2b_home": "down", "3in4": "down", "4in6_road": "down", "2plus": "up"}

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
    marks = {}
    for t in c.teams:
        s = _spot(c, t)
        bits = []
        if s.get("rest") in REST_SHORT:
            bits.append(REST_SHORT[s["rest"]])
            if s["rest"] in REST_TONE:
                marks[REST_SHORT[s["rest"]]] = REST_TONE[s["rest"]]
        if _f(s.get("miles")) and s.get("from") and s.get("from") != c.home:
            trip = f"traveled {int(s['miles']):,} miles from {s['from']}"
            if s.get("days_since"):
                trip += f" {_plural_days(s['days_since'])} ago"
            bits.append(trip)
        tz = _f(s.get("tz_shift"))
        if tz:
            bits.append(f"{int(abs(tz))} time zone{'s' if abs(tz) != 1 else ''} "
                        f"{'east' if tz > 0 else 'west'} of its last game")
        if "altitude" in (s.get("flags") or []):
            bits.append("up from near sea level to altitude")
        if bits:
            items.append(f"{c.name(t)}: {'; '.join(bits)}")
    teams_only = teams_only_line(c)
    if teams_only:
        items.append(teams_only)
    claims = [None] * len(items)
    if any("blowout" in (_spot(c, t).get("flags") or []) for t in c.teams):
        items.append(BLOWOUT_WATCH)
        # What a finished game checks it by (engine/reportfacts): the margin.
        claims.append({"kind": "blowout"})
    block = _claimed_list(list(zip(items, claims)))
    if block and marks:
        block["marks"] = marks
    return _section("facts", "Game facts", [block])


def _plural_days(n) -> str:
    n = int(n)
    return "a day" if n == 1 else f"{n} days"


#: A REPORT THAT READS THE TEAMS ALONE (step AEM), marked on the report so the heartbeat can count them
#: (launch._board_counts, "reports_teams_only"); the report's own words say it in the facts (`teams_only_line`).
SCOPE_KEY, TEAMS_ONLY = "scope", "teams"


def _board_named(c: Ctx) -> list | None:
    """College basketball's priced games ("AWAY@HOME", `nba_build.college_board_games`), or None on a board that
    prices every game it carries."""
    if getattr(c, "sport", "") != "cbb":
        return None
    named = (c.result or {}).get("board_games")
    return list(named) if isinstance(named, list) else None


def teams_only_line(c: Ctx) -> str:
    """The facts' line for a college game whose players the board does not read (step AEM): what the report reads
    and why its players are missing, in plain words. "" for a priced game and every other league."""
    named = _board_named(c)
    if named is None or f"{c.away}@{c.home}" in named:
        return ""
    n = len(named)
    games = "the game" if n == 1 else f"the {n} games"
    return (f"Players: not read for this game. Tonight we read players and buy player prices for {games} we "
            f"price, the ranked and power-conference games first; this report reads the two teams and the "
            f"betting market") if n else ("Players: not read for this game; this report reads the two teams and "
                                          "the betting market")


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
                          "text": (f"{', '.join(bits)} a game over the last {r.get('games')}"
                                   if bits else "")})
        # His name wears his matchup read's colour (gamereport.color_names).
        blocks += [_h(f"{c.name(t)}"), {"type": "players", "items": items}]
    if not blocks:
        return None
    return _section("carry", "Who carries each team", blocks)


def nba_defense(c: Ctx) -> dict | None:
    dvp = c.meta.get("dvp") or {}
    items: list = []
    for t in c.teams:
        d = dvp.get(t) or {}
        soft, hard = [], []
        # What a finished game grades each line by (engine/reportgrade): what
        # the opponent made of each stat against the number allowed a game.
        soft_checks, hard_checks = [], []
        for k, word in DEF_STATS:
            r = d.get(k) or {}
            rank, of = r.get("rank"), r.get("of")
            if not rank or not of or _f(r.get("pg")) is None:
                continue
            # "gives up the most points (118.2 a game, 2nd-most; league 113)"
            # said "the most" and "2nd" of one number (Ethan, 2026-11-15:
            # "hard to read"): it is "the second-most points (118.2 a game;
            # the league average is 113)".
            avg = f"; the league average is {_num(r.get('league'))}" if _f(r.get("league")) is not None else ""
            if rank <= 5:
                soft.append(f"the {_ord(int(rank))}-most {word} ({_num(r['pg'])} a game{avg})")
                soft_checks.append({"stat": k, "pg": round(float(r["pg"]), 2), "side": "soft"})
            elif rank > of - 5:
                hard.append(f"the {_ord(int(of - rank + 1))}-fewest {word} ({_num(r['pg'])} a game{avg})")
                hard_checks.append({"stat": k, "pg": round(float(r["pg"]), 2), "side": "hard"})
        if soft:
            items.append((f"{t}'s defense gives up {_join(soft)}",
                          {"kind": "allowed", "team": t, "opp": c.opp[t], "checks": soft_checks}))
        if hard:
            items.append((f"{t}'s defense gives up {_join(hard)}",
                          {"kind": "allowed", "team": t, "opp": c.opp[t], "checks": hard_checks}))
    if not items:
        return None
    note = ("Per game, not per possession: a fast team's defense looks a little worse than it is"
            + ("; these are last season's numbers, because this season is too young to rank"
               if c.meta.get("dvp_last") else ""))
    return _section("defense", "Where each defense gives", [_claimed_list(items),
                                                            {"type": "note", "text": _sentence(note)}])


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
    # The page colours each rank by its quarter of the league (js/report.js);
    # pace is no better or worse at either end, so its row stays plain.
    blocks = [{"type": "table", "title": "Tale of the tape", "head": ["", c.away, c.home], "rows": table,
               "rank_of": int(t.get("teams") or 30), "rank_skip": [r["label"] for r in rows if r.get("plain")],
               "note": _sentence(note) if note else ""}]
    edges = [(e.get("text"), _unit_claim(e)) for e in t.get("edges") or []
             if isinstance(e, dict) and e.get("text") and _ours(c, e)]
    if edges:
        blocks += [_h("Key matchups"), _claimed_list(edges)]
    return _section("tape", "The matchup", blocks)


def _unit_claim(e: dict) -> dict | None:
    """A key matchup as a finished game grades it (engine/reportgrade): the
    offense on the floor, its unit and its own number coming in, and which
    way the edge points — more for the offense's edge in a unit where more is
    better, less for the defense's (turnovers the other way round)."""
    off, dfn, unit, base = e.get("off"), e.get("def"), e.get("off_unit"), _f(e.get("base"))
    if not off or not dfn or not unit or base is None or e.get("tone") not in ("off", "def"):
        return None
    from .nba.teams import BETTER
    more_better = BETTER.get(unit, True)
    more = more_better if e["tone"] == "off" else not more_better
    return {"kind": "unit", "off": off, "def": dfn, "unit": unit, "base": base, "favors": "more" if more else "less"}


def nba_watch(c: Ctx) -> dict | None:
    """The research's breakout candidates (a breakout spot first) and fades
    (`shine_struggle`, engine/breakouts)."""
    return _section("watch", "Players to watch", shine_struggle(c, c.reads))


def _game_day(c: Ctx) -> str | None:
    """The game's weekday, Eastern ("Sunday"), or None."""
    from zoneinfo import ZoneInfo
    from .gameparlays import game_start
    t = game_start(c.g)
    return t.astimezone(ZoneInfo("America/New_York")).strftime("%A") if t else None


def nba_word(c: Ctx, i: dict) -> str:
    """A listed player's status in words: under ESPN's bare "Day-To-Day", the league's own word for this game
    when his blurb gives one ("questionable", "probable", engine/sources/espninjuries.designation, step ABU)."""
    status = str(i.get("status") or "").lower()
    if status == "day-to-day" and i.get("comment"):
        from .sources.espninjuries import designation
        word = designation(i.get("comment"), _game_day(c))
        if word:
            return word
    return status


def _recent_line(x: dict) -> dict:
    """{"min", "pts", "games"}: a player's minutes and points a game over the newest ten (the history's own order),
    {} with fewer than three games."""
    mins = [float(v) for v in (x.get("minutes") or [])[:10] if v is not None]
    if len(mins) < 3:
        return {}
    pts = [float(v) for v in (x.get("pts") or [])[:10] if v is not None]
    return {"min": round(sum(mins) / len(mins), 1), "games": len(mins),
            **({"pts": round(sum(pts) / len(pts), 1)} if pts else {})}


def nba_injuries(c: Ctx) -> dict | None:
    inj = [i for i in c.meta.get("injuries") or [] if isinstance(i, dict) and i.get("player")
           and i.get("team") in c.teams]
    if not inj:
        return None

    def puts_up(i):
        if _f(i.get("min")) is None or not i.get("games"):
            return ""
        what = f"{_num(i['min'])} minutes" + (f" and {_num(i['pts'])} points" if _f(i.get("pts")) is not None else "")
        return f" — {what} a game over the last {i['games']}"
    items = [(f"{i['player']} ({i['team']}) — {nba_word(c, i)}"
              # Which way his newest blurb leans, the league's word already said (step ABY).
              + (f"; {newest_word(c, i['team'], i['player'], designations=False)}"
                 if newest_word(c, i["team"], i["player"], designations=False) else "")
              + (f", {str(i['injury']).lower()}" if i.get("injury") else "") + puts_up(i),
              injury_claim(i["player"], i["team"], i.get("status"))) for i in inj]
    return _section("injuries", "Injuries", [_claimed_list(items)])


def nba_before(c: Ctx) -> dict | None:
    lines = ["The injury report updates through the day; starting lineups come about half an hour "
             "before tip-off"]
    q = [i for i in c.meta.get("injuries") or [] if isinstance(i, dict) and i.get("team") in c.teams
         and str(i.get("status") or "").lower() in ("questionable", "doubtful", "probable", "day-to-day", "game time decision")]
    if q:
        lines.append("Still to be decided: " + _join(f"{i['player']} ({i['team']}, {nba_word(c, i)})"
                                                     for i in q))
    lines += _stale(c)
    return _section("before", "Before tip-off", [_list(lines)])


def nba_stepup_sentence(c: Ctx) -> str:
    """WHO STEPS UP, in the basketball short version (step AHW; Ethan, 26 November: "when there is alot of players
    out ... we dont ... say anything about them or how there usage could step up in the game reports"). The
    report's "What the absences change" section (`nba_absences`) has who took the biggest absent man's share of the
    points in the games he missed; the short version said only who was out. Said here only where that section says
    it: enough missed games, and a teammate whose share rose."""
    ab = c.meta.get("absences") or {}
    parts = []
    for t in c.teams:
        a = ab.get(t) or {}
        of, n = a.get("of") or "", int(a.get("n_out") or 0)
        takers = [x for x in a.get("takers") or [] if isinstance(x, dict) and x.get("player")]
        if not (of and a.get("enough") and takers):
            continue
        parts.append(_sentence(
            f"Who steps up for {team_np(c, t)}: in the {n} games {of} missed this season, " + _join(
                f"{x['player']} took {_pct(x['without'])} of the points ({_pct(x['with'])} with {of} playing)"
                for x in takers)))
    return " ".join(parts)


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
    steps = nba_stepup_sentence(c)
    if steps:
        items.append(steps)
    carry = c.meta.get("carry") or {}
    leads = []
    for t in c.teams:
        rows = [r for r in carry.get(t) or [] if isinstance(r, dict) and _f(r.get("pts")) is not None]
        if rows:
            r = rows[0]
            n = int(r.get("games") or 0)
            leads.append(f"{r['player']} for {team_np(c, t)} ({_num(r['pts'])} points a game"
                         + (f" over the last {n}" if n else "") + ")")
    if leads:
        items.append(_sentence("Leading the scoring lately: " + _join(leads)))
    edges = [e for e in (c.g.get("nba_tape") or {}).get("edges") or []
             if isinstance(e, dict) and e.get("text") and _ours(c, e)]
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
        items.append(BLOWOUT_WATCH + ".")
    par = parlay_sentence(c)
    if par:
        items.append(par)
    return _section("short", "The short version", [_list(items)])




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
                "status": (i or {}).get("status") or "", "injury": (i or {}).get("injury") or "",
                # WHAT HE PUTS UP (step AHR): his minutes and points over his last ten, so a reader weighs who is
                # missing by what goes missing.
                **_recent_line(hist.get(p) or {}),
                # ESPN's blurb: the league's own word under its "Day-To-Day" (nba_word, step ABU).
                **({"comment": str(i["comment"])[:400]} if (i or {}).get("comment") else {})}
               for p, i in (listed or {}).items() if (hist.get(p) or {}).get("team") in (a, h)]
        out[f"{a}@{h}"] = {"carry": carry, "injuries": sorted(inj, key=lambda i: (i["team"], i["player"])),
                           "injuries_read": bool(injuries_read),
                           "dvp": {t: (dvp or {}).get(t) or {} for t in (a, h)}, "dvp_last": bool(dvp_last),
                           "missed": missed_last(hist, (a, h), listed)}
    return out


#: A teammate's gain in his share of the team's points, in the games a player
#: missed, that the absences section names (2 points of the team's total).
TAKER_GAIN = 0.02
TAKERS_N, ABSENT_N = 3, 4
#: A rotation player's minutes, for "who was missing" in the last meeting.
MEETING_ROTATION_MPG = 20.0
#: Pace and points past the league's average that the game's line says out loud.
PACE_SAID, POINTS_SAID, CLOSE_SPREAD = 1.5, 6.0, 4.0
#: One club, every spelling a feed gives it (the history's NBA finals carry the
#: league's three-letter codes; the board may carry ESPN's).
CLUB_ALIASES = [{"NYK", "NY"}, {"GSW", "GS"}, {"NOP", "NO"}, {"SAS", "SA"}, {"UTA", "UTAH"}, {"PHX", "PHO"},
                {"BKN", "BRK"}, {"CHA", "CHO"}, {"WAS", "WSH"}]


def _clubs(code) -> list:
    c = str(code or "").upper()
    for group in CLUB_ALIASES:
        if c in group:
            return sorted(group)
    return [c]


def _avg10(x: dict, k: str):
    vs = [float(v) for v in ((x or {}).get(k) or [])[:10] if v is not None]
    return round(sum(vs) / len(vs), 1) if vs else None


def last_meeting(conn, sport: str, home: str, away: str, before: str, hist: dict | None = None) -> dict:
    """THE LAST TIME THESE TWO MET (the research's "direct precedent": "On
    March 28, the Pistons crushed the Timberwolves 109-87 ... Edwards,
    McDaniels and Dosunmu were all absent"): the newest final between the
    two clubs before ``before`` in the history (`games`), its leading
    scorers and the rotation men each side played without, from the build's
    own player history. {} when they have not met in what the history holds."""
    if conn is None or not home or not away:
        return {}
    hs, as_ = _clubs(home), _clubs(away)
    q = ",".join("?" * len(hs)), ",".join("?" * len(as_))
    row = conn.execute(
        f"SELECT period, home, away, home_score, away_score FROM games WHERE sport=? AND home_score IS NOT NULL "
        f"AND away_score IS NOT NULL AND period < ? AND ((home IN ({q[0]}) AND away IN ({q[1]})) "
        f"OR (home IN ({q[1]}) AND away IN ({q[0]}))) ORDER BY period DESC LIMIT 1",
        (sport, str(before or "")[:10], *hs, *as_, *as_, *hs)).fetchone()
    if not row:
        return {}
    day, h, hsc, asc = row[0], row[1], row[3], row[4]
    # The board's own codes, whatever the history spelled them.
    h_code = home if str(h).upper() in hs else away
    a_code = away if h_code == home else home
    out = {"day": str(day)[:10], "home": h_code, "away": a_code,
           "home_score": int(hsc), "away_score": int(asc), "leaders": {}, "missing": {}}
    for t in (h_code, a_code):
        played, missing = [], []
        for p, x in (hist or {}).items():
            if (x or {}).get("team") != t:
                continue
            wk = (x.get("by_week") or {})
            g = wk.get(out["day"])
            if g is not None:
                if _f(g.get("pts")) is not None:
                    played.append((float(g["pts"]), p))
            elif (_avg10(x, "minutes") or 0) >= MEETING_ROTATION_MPG and wk and min(wk) < out["day"]:
                missing.append(p)
        played.sort(key=lambda z: (-z[0], z[1]))
        out["leaders"][t] = [{"player": p, "pts": int(v)} for v, p in played[:2]]
        out["missing"][t] = sorted(missing)[:3]
    return out


#: Recent form: the newest finals this season a team's form reads, and the
#: fewest that say anything.
FORM_N, FORM_MIN = 10, 3


def team_form(conn, sport: str, home: str, away: str, before: str) -> dict:
    """EACH TEAM'S FORM THIS SEASON (the research's spread reads: who has won
    eight of ten, a team that is 5-1 at home): its newest FORM_N finals before
    ``before`` with the record and the average margin, and this season's
    record where it plays tonight (the home side at home, the visitors on the
    road). Finals from the history's `games`; a team with fewer than FORM_MIN
    this season says nothing. ``{team: {"n", "w", "l", "margin", "where",
    "venue_w", "venue_l"}}``; {} without a history."""
    if conn is None or not home or not away or not before:
        return {}
    from .seasons import season_of
    day = str(before)[:10]
    season = season_of(sport, day)
    out: dict = {}
    for t, where in ((away, "road"), (home, "home")):
        cl = _clubs(t)
        q = ",".join("?" * len(cl))
        rows = conn.execute(
            f"SELECT period, home, home_score, away_score FROM games WHERE sport=? AND period < ? "
            f"AND home_score IS NOT NULL AND away_score IS NOT NULL AND (home IN ({q}) OR away IN ({q})) "
            f"ORDER BY period DESC LIMIT 120", (sport, day, *cl, *cl)).fetchall()
        mine = []
        for period, h, hs, as_ in rows:
            if season_of(sport, str(period)[:10]) != season:
                continue
            at_home = str(h).upper() in cl
            us, them = (int(hs), int(as_)) if at_home else (int(as_), int(hs))
            mine.append((at_home, us, them))
        if len(mine) < FORM_MIN:
            continue
        last = mine[:FORM_N]
        wins = sum(1 for _at, u, o in last if u > o)
        here = [(u, o) for at, u, o in mine if at == (where == "home")]
        out[t] = {"n": len(last), "w": wins, "l": len(last) - wins,
                  "margin": round(sum(u - o for _at, u, o in last) / len(last), 1), "where": where,
                  "venue_w": sum(1 for u, o in here if u > o), "venue_l": sum(1 for u, o in here if u <= o)}
    return out


def basketball_research(g: dict, *, hist: dict, gone: dict | None = None, vacancy: dict | None = None,
                        prof: dict | None = None, conn=None, sport: str = "nba", day: str = "") -> dict:
    """WHAT THE RESEARCH LOOKED AT, FOR ONE GAME'S REPORT (2026-11-15; Ethan:
    "I want our game reports for each game to be scanning for all that type
    of data and matchup shit ... that research is already done for me").
    The facts the build already reads and the report did not say:

      * ``absences``: each team's ruled-out rotation men (nba_build.absences:
        minutes and points a game over their last ten), and who took the
        biggest one's share of the points in the games he missed this season
        (engine/nba/onoff.inheritance, measured from the box scores — the
        research's "who absorbs the vacated roles");
      * ``script``: both teams' pace and points with their ranks and the
        league's averages, the lines' total and spread (the research's pace
        and game-environment read);
      * ``meeting``: the last time the two met (`last_meeting`);
      * ``form``: each team's last ten this season and its record where it
        plays tonight (`team_form`).
    """
    home, away = g.get("home"), g.get("away")
    out: dict = {}
    absences = {}
    for t in (away, home):
        gone_t = [(n, m) for n, m in (gone or {}).get(t) or []][:ABSENT_N]
        if not gone_t:
            continue
        inh = ((vacancy or {}).get(t) or {}).get("inherit") or {}
        out_names = {n for n, _m in gone_t}
        takers = [{"player": n, "with": round(float(b["with"]), 3), "without": round(float(b["without"]), 3)}
                  for n, b in (inh.get("beneficiaries") or {}).items()
                  if n not in out_names and (hist.get(n) or {}).get("team") == t
                  and float(b.get("delta") or 0) >= TAKER_GAIN][:TAKERS_N]
        absences[t] = {"out": [{"player": n, "mpg": round(float(m), 1), "ppg": _avg10(hist.get(n), "pts")}
                               for n, m in gone_t],
                       "of": inh.get("player") or "", "n_out": int(inh.get("n_out") or 0),
                       "enough": bool(inh.get("enough")), "takers": takers}
    if absences:
        out["absences"] = absences
    teams = (prof or {}).get("teams") or {}
    lg = (prof or {}).get("league") or {}
    if teams.get(home) and teams.get(away):
        out["script"] = {
            "pace": {t: _f(teams[t].get("pace")) for t in (away, home)},
            "pace_rank": {t: ((teams[t].get("ranks") or {}).get("pace")) for t in (away, home)},
            "pts": {t: _f(teams[t].get("pts")) for t in (away, home)},
            "league_pace": _f(lg.get("pace")), "league_pts": _f(lg.get("pts")),
            "teams": int((prof or {}).get("n") or 0),
            "spread": _f(g.get("spread")), "total": _f(g.get("total"))}
    try:
        m = last_meeting(conn, sport, home, away, day or g.get("date") or "", hist)
    except Exception:                                    # noqa: BLE001
        m = {}
    if m:
        out["meeting"] = m
    try:
        form = team_form(conn, sport, home, away, day or g.get("date") or "")
    except Exception:                                    # noqa: BLE001
        form = {}
    if form:
        out["form"] = form
    return out


def nba_absences(c: Ctx) -> dict | None:
    """WHAT THE ABSENCES CHANGE (the research's "who absorbs the vacated
    roles"): each ruled-out rotation man's minutes and points, and who took
    the biggest one's share of the points in the games he missed — measured
    from the box scores, never guessed; a sample too small says so."""
    ab = c.meta.get("absences") or {}
    blocks = []
    for t in c.teams:
        a = ab.get(t) or {}
        rows = [x for x in a.get("out") or [] if isinstance(x, dict) and x.get("player")]
        if not rows:
            continue
        items = []
        for x in rows:
            bits = [f"{_num(x.get('mpg'), 0)} minutes"] + ([f"{_num(x['ppg'])} points"] if x.get("ppg") else [])
            items.append(f"{x['player']} is out: {' and '.join(bits)} a game over the last ten")
        of, n = a.get("of") or "", int(a.get("n_out") or 0)
        takers = [x for x in a.get("takers") or [] if isinstance(x, dict) and x.get("player")]
        if of and a.get("enough") and takers:
            items.append(f"In the {n} games {of} missed this season, " + _join(
                f"{x['player']} took {_pct(x['without'])} of {team_owner(c, t)} points ({_pct(x['with'])} with "
                f"{of} playing)" for x in takers))
        elif of and n:
            items.append(f"{of} has missed {n} game{'s' if n != 1 else ''} this season — too few to say who takes "
                         f"those shots")
        elif of:
            items.append(f"{of} has not missed a game this season, so who takes those shots is still to be seen")
        blocks += [_h(c.name(t)), _list(items)]
    if not blocks:
        return None
    blocks.append({"type": "note", "text": _sentence(
        "Measured from the box scores: each teammate's share of the team's points in the games the player sat, "
        "against the games the player played")})
    return _section("absences", "What the absences change", blocks)


def nba_meeting(c: Ctx) -> dict | None:
    """THE LAST MEETING (the research's "direct precedent"): the score, who led
    each side, and who each side played without that night."""
    m = c.meta.get("meeting") or {}
    if not m.get("day") or not m.get("home") or not m.get("away"):
        return None
    from .gamereport import day_label
    h, a = m["home"], m["away"]
    hs, as_ = int(m.get("home_score") or 0), int(m.get("away_score") or 0)
    won, lost = (h, a) if hs > as_ else (a, h)
    score = f"{max(hs, as_)}-{min(hs, as_)}"
    where = "at home" if won == h else "on the road"
    when = day_label(m["day"], 0, 0) or m["day"]
    try:
        from .seasons import season_of
        if season_of(c.sport, m["day"]) < season_of(c.sport, c.g.get("date") or m["day"]):
            when += ", last season"
    except Exception:                                    # noqa: BLE001
        pass
    items = [f"{when}: {team_np(c, won)} beat {team_np(c, lost)} {score} {where}"]
    for t in (a, h):
        lead = [x for x in (m.get("leaders") or {}).get(t) or [] if x.get("player")]
        if lead:
            items.append(cap(f"{team_owner(c, t)} leading scorers: ")
                         + _join(f"{x['player']} ({x['pts']} points)" for x in lead))
        miss = [p for p in (m.get("missing") or {}).get(t) or [] if p]
        if miss:
            items.append(cap(f"{team_np(c, t)} played without {_join(miss)} that night"))
    return _section("meetings", "The last meeting", [_list(items)])


def _league(c: Ctx, own: bool = False) -> str:
    """"the league" ("the league's"), or college's "Division I"
    ("Division I's"): college's averages are its 360-odd teams'."""
    word = "Division I" if c.sport == "cbb" else "the league"
    return f"{word}'s" if own else word


def form_from_recent(recent: dict | None, teams) -> dict:
    """`team_form`'s record and margin from a board's `team_recent` (engine/
    teamlogs.recent_games: each club's newest ten finals this season, newest
    first), for a board that already carries it (MLB). No record where it
    plays tonight: the ten are all the board holds."""
    out: dict = {}
    for t in teams:
        games = [x for x in (recent or {}).get(t) or [] if isinstance(x, dict)][:FORM_N]
        if len(games) < FORM_MIN:
            continue
        w = sum(1 for x in games if x.get("won"))
        out[t] = {"n": len(games), "w": w, "l": len(games) - w,
                  "margin": round(sum(float(x.get("margin") or 0) for x in games) / len(games), 1)}
    return out


def form_lines(c: Ctx, form: dict) -> list:
    """"Form: the Heat is 6-4 over its last ten, outscoring teams by 2.1 points
    a game; ..."
    and "Where they play: the Celtics are 5-1 at home this season, the Heat
    2-3 on the road" (`team_form`)."""
    a, h = c.away, c.home
    said = []
    for t in (a, h):
        f = form.get(t) or {}
        n = int(f.get("n") or 0)
        if not n:
            continue
        its = team_be(c, t, "their", "its")
        span = f"over {its} last ten" if n == FORM_N else f"in {its} {n} games this season"
        m = _f(f.get("margin")) or 0.0
        unit = c.score_word if abs(m) == 1 else c.score_words
        by = (f", outscoring teams by {_num(m)} {unit} a game" if m > 0 else
              f", outscored by {_num(-m)} {unit} a game" if m < 0 else f", even on {c.score_words}")
        said.append(f"{team_np(c, t)} {team_be(c, t)} {int(f.get('w') or 0)}-{int(f.get('l') or 0)} {span}{by}")
    out = [f"Form: {'; '.join(said)}"] if said else []
    where = []
    for t, at in ((h, "at home"), (a, "on the road")):
        f = form.get(t) or {}
        w, lo = int(f.get("venue_w") or 0), int(f.get("venue_l") or 0)
        if w + lo:
            where.append(f"{team_np(c, t)} {team_be(c, t)} {w}-{lo} {at}")
    if where:
        # A NEUTRAL SITE (step AED): a tournament or a showcase game is no one's home floor tonight.
        from .gamereport import is_neutral
        out.append(f"Where they play: a neutral site tonight; {_join(where)} this season" if is_neutral(c) else
                   f"Where they play: {_join(where)} this season")
    return out


def nba_script(c: Ctx) -> dict | None:
    """HOW THE GAME SHOULD GO (the research's form and game environment: who
    is winning and where, "fast vs fast = inflated stats; slow vs slow =
    deflated", "high total = prop-friendly environment", "close game: stars
    play their minutes").
    Rest and the blowout are under the game facts already."""
    s = c.meta.get("script") or {}
    pace, lp = s.get("pace") or {}, _f(s.get("league_pace"))
    # Each line with what a finished game checks it by (engine/reportfacts):
    # the night's pace, its points and its margin.
    items = []
    a, h = c.away, c.home
    items += [(t, None) for t in form_lines(c, c.meta.get("form") or {})]
    pa, ph = _f(pace.get(a)), _f(pace.get(h))
    if pa is not None and ph is not None and lp:
        rk = s.get("pace_rank") or {}
        n = int(s.get("teams") or 0)

        def rank(t):
            r = rk.get(t)
            return f" ({_ord(int(r))}-fastest of {n})" if r and n else ""
        fast = [t for t, p in ((a, pa), (h, ph)) if p >= lp + PACE_SAID]
        slow = [t for t, p in ((a, pa), (h, ph)) if p <= lp - PACE_SAID]
        # Read per 48 in every league (engine/nba/teams: pace is 48 x
        # possessions / game minutes) and said in the league's own game, as
        # the tape's pace row on the same page says it: per 40 in college and
        # the WNBA (teams.GAME_MINUTES). The claim keeps the per-48 numbers it
        # is graded on, and the minutes its fact check says them in.
        from .nba.teams import game_minutes, pace_said
        gm = game_minutes(c.sport)
        pair = (f"{team_np(c, a)} {team_be(c, a, 'average', 'averages')} {_num(pace_said(pa, gm))} possessions "
                f"per {gm} minutes{rank(a)} and {team_np(c, h)} {_num(pace_said(ph, gm))}{rank(h)}; "
                f"{_league(c)} averages {_num(pace_said(lp, gm))}")
        claim = {"kind": "pace", "league": lp, "pace": [[a, pa], [h, ph]]}
        if gm != 48:
            claim["minutes"] = gm
        if len(fast) == 2:
            items.append((f"A fast game: {pair}. More possessions means more points, rebounds and assists to go "
                          f"around", dict(claim, read="fast")))
        elif len(slow) == 2:
            items.append((f"A slow game: {pair}. Fewer possessions shrinks every counting stat",
                          dict(claim, read="slow")))
        elif fast and slow:
            items.append((f"A tug of war on pace, {team_np(c, fast[0])} wanting to run and {team_np(c, slow[0])} "
                          f"to slow it down: {pair}", dict(claim, read="split", fast=fast[0], slow=slow[0])))
        else:
            items.append((f"An average pace: {pair}", dict(claim, read="average")))
    tot, lpts = _f(s.get("total")), _f(s.get("league_pts"))
    if tot and lpts:
        avg = 2 * lpts
        gap = tot - avg
        claim = {"kind": "scoring", "avg": round(avg, 1), "total": tot}
        if gap >= POINTS_SAID:
            items.append((f"The total, {tot:g}, is {_num(gap)} points over {_league(c, True)} average game "
                          f"({_num(avg)}): a high-scoring night by the line, friendly to overs",
                          dict(claim, read="high")))
        elif gap <= -POINTS_SAID:
            items.append((f"The total, {tot:g}, is {_num(-gap)} points under {_league(c, True)} average game "
                          f"({_num(avg)}): a low-scoring night by the line", dict(claim, read="low")))
        else:
            items.append((f"The total, {tot:g}, is close to {_league(c, True)} average game ({_num(avg)})",
                          dict(claim, read="average")))
    sp = _f(s.get("spread"))
    if sp is not None and abs(sp) <= CLOSE_SPREAD:
        fav = h if sp < 0 else a
        items.append((f"A close game by the line, {team_np(c, fav)} by {abs(sp):g}: the starters should play their "
                      f"full minutes, the stars included", {"kind": "close", "fav": fav, "spread": abs(sp)}))
    if not items:
        return None
    return _section("script", "How the game should go", [_claimed_list(items)])


def missed_last(hist: dict, teams, listed: dict | None = None) -> dict:
    """``{name key: {"team", "game", "kind"}}``: each rotation player of the
    two teams (three or more stored games) with no game on his team's newest
    night and no line on the injury report (engine/availability). College's
    injury report is all but empty, so on college this is the only word the
    report has that a man may sit; on the NBA it catches a rest night the
    report never listed."""
    from .availability import _key
    newest: dict = {}
    for x in (hist or {}).values():
        t, d = (x or {}).get("team"), ((x or {}).get("dates") or [None])[0]
        if t in teams and d and str(d) > newest.get(t, ""):
            newest[t] = str(d)[:10]
    out: dict = {}
    for p, x in (hist or {}).items():
        t, dates = (x or {}).get("team"), (x or {}).get("dates") or []
        if t not in newest or len(x.get("minutes") or []) < 3 or not dates or p in (listed or {}):
            continue
        if str(dates[0])[:10] < newest[t]:
            out[_key(p)] = {"team": t, "game": {"day": newest[t]}, "kind": "dnp"}
    return out


#: The basketball report (NBA, college, WNBA), in the research's order: the facts
#: and the line, how the game should go, the matchup, what the absences
#: change, the breakout candidates and fades, the last meeting, then the rest.
NBA = ((nba_facts, sec_market, nba_script, nba_tape, nba_absences, nba_watch, nba_meeting, nba_carry, nba_defense,
        nba_injuries, sec_parlays, nba_before), nba_short)


# ═══ THE HOOK ════════════════════════════════════════════════════════════════════════
BUILDERS = {"mlb": MLB, "nhl": NHL, "nba": NBA, "wnba": NBA, "cbb": NBA}


def build(g: dict, result: dict, *, sport: str, names: dict | None = None, meta: dict | None = None,
          changes: dict | None = None, conn=None) -> dict | None:
    """One game's report, or None for a row with no teams or a league this
    module does not write."""
    if not isinstance(g, dict) or not g.get("away") or not g.get("home") or sport not in BUILDERS:
        return None
    c = Ctx(g, result, names=names if names is not None else team_names(sport), sport=sport,
            meta=meta, changes=changes, conn=conn)
    fns, short = BUILDERS[sport]
    return finish(c, fns, short)


def attach(result: dict, sport: str, *, meta: dict | None = None, out=None, at: str | None = None) -> str:
    """``result["game_reports"]`` for every game on an MLB, NHL, NBA or WNBA
    board. ``meta`` is {"AWAY@HOME": what the build knows of a game and the
    board leaves off} (basketball's: nba_meta). ``out`` is the board's
    public path; what changed is kept beside its private copy, stamped
    ``at``. One line for the build log; never raises. The history database
    is opened for what only it knows (our team ratings' own chance on the
    call, gamereport.ratings_chance); a report is written without it."""
    conn = None
    try:
        try:
            from .db import connect
            conn = connect()
        except Exception:                                    # noqa: BLE001
            conn = None
        names = team_names(sport)
        if sport == "cbb":
            # College's names are the night's own (the board's teams table):
            # the school, as a reader says it ("Duke", "Kansas").
            names = {code: (t.get("loc") or t.get("short") or t.get("name") or code)
                     for code, t in (result.get("teams") or {}).items()}
        # COLLEGE WRITES EVERY GAME STILL TO TIP (step AEM, 24 November 2026). It wrote the games it prices
        # alone (`nba_build.college_board_games`: five of the night's sixty to a hundred and fifty), 7 reports
        # of 87 games that night. Ethan's decision B the same day: "we always want every sport posting props
        # and bets and game reports at all times for every games so we learn and dial in and calibrate". The
        # board reads the players of the games it prices; every other game's report reads the two teams (the
        # tale of the tape and its key matchups, each graded on the box score once the game is final,
        # engine/reportgrade) and the betting market, and says in its facts that its players are not read
        # (`teams_only_line`). A game already under way when first seen is not written: a report written after
        # the tip is no pregame call, so only one kept from before its start stands (engine/reportkeep.hold).
        board = set(result.get("board_games") or []) if sport == "cbb" else None
        if board is not None:
            from .reportkeep import stamps as _stamps, started as _started
            _utc = _stamps(at)[0]
        prepared = []
        for g in result.get("games") or []:
            if not isinstance(g, dict) or not g.get("home") or not g.get("away"):
                continue
            if board is not None and f"{g['away']}@{g['home']}" not in board and _started(g, _utc):
                continue
            m = (meta or {}).get(f"{g['away']}@{g['home']}") or {}
            more = (mlb_more(g, result) if sport == "mlb" else nhl_more(g, result) if sport == "nhl"
                    else nba_more(g, m))
            prepared.append((g, m, more))
        logged = log_changes(result, [(g, {}, more) for g, _m, more in prepared], sport, out, at)
        # The parlays each game posted last build, posted again while they hold (ZQ).
        from .gamereport import _posted_before
        _posted_before(result, sport, out)
        reports = []
        for g, m, _more in prepared:
            r = build(g, result, sport=sport, names=names, meta=m, conn=conn,
                      changes=logged.get(f"{g['away']}@{g['home']}|{str(g.get('date') or '')[:10]}"))
            if r:
                if board is not None and f"{g['away']}@{g['home']}" not in board:
                    r[SCOPE_KEY] = TEAMS_ONLY
                reports.append(r)
        # A GAME NO REPORT REBUILT POSTS NO THREE-LEG TICKET (GPLEGS1).
        from .gamereport import _report_only
        _report_only(result)
        # A game under way keeps the report it had before it started, college's
        # too once the board prices none of the night (engine/reportkeep).
        # HOW THESE READS HAVE DONE (engine/reportrecord): each graded section opens
        # with its kind of read's record so far, before a started game's is kept.
        stamp_track(reports, sport, out)
        reports, kept = keep_started(result, reports, sport, out, at, conn)
        result[KEY] = reports
        n_bets = _lift_bets(result)
        from .gamereport import lift_both
        lift_both(result)
        if not reports:
            return "Game reports: no games on the board"
        return summary(reports, logged, out) + kept + n_bets
    except Exception as exc:                                 # noqa: BLE001
        result.pop(KEY, None)
        return f"⚠️  Game reports skipped ({type(exc).__name__}: {exc})"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:                                # noqa: BLE001
                pass
