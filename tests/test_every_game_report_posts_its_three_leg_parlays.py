"""Every game report posts its three-leg parlays: two at least, three at most
(2026-11-19, THREELEG1).

Ethan, 2026-11-19: "for the game report, 3-leg parlays, we need those back
immediately. I want those for every single game. Just how every single report
you went through and read gave me touchdown parlays and player prop parlays,
3-leg parlays, and then I go back and pick 2 of them ... We need 2 3-leg
parlays, or maybe 2 to 3 3-leg parlays on the game reports."

From 17 November a league whose three-leg tickets hit under 25% had them on
paper (engine/parlayhold): built and graded, posted nowhere, the NFL's from the
start and the NBA's by the record. And a game whose report's picks made fewer
than four tickets clearing 30% posted fewer, college's mostly none. What these
hold:

  * the three-leg hold is retired: no saved hold, the standing NFL one
    included, holds a three-leg ticket, the nightly pass measures the two-leg
    size alone, and no build moves a game's tickets to paper;
  * a game posts THREE_PER_GAME (3) tickets at most and fills up to THREE_MIN
    (2) when fewer clear THREE_FLOOR: from its own legs first (a report's
    picks), then the game's other priced props, then longer tickets down to
    LONG_FLOOR — each filled ticket saying on its card which legs are not the
    report's picks and when it is a longer ticket;
  * a ticket on paper from a board built before still journals and grades;
  * every game still to play has its entry (THREELEG3): one whose props all
    sit under 60% fills from them, and one with no prop priced yet says, once,
    when its props are bought (the NFL's Sunday games on a Thursday).

    python3 tests/test_every_game_report_posts_its_three_leg_parlays.py
"""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gameparlays as GP, parlayhold, parlayledger  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
DAY = dt.date(2026, 11, 20)


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    parlayledger.ensure_schema(c)
    return c


def _tickets(c, sport, won, lost, source, day="2026-11-01"):
    """Graded tickets, each in its game's set at the start (the ones the record counts)."""
    for i in range(won + lost):
        c.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified, was_play,"
                  " notional_units, stake_units, source, status, at_start) VALUES (?,?,?,?,?,?,?,1,0,1,0,?,?,1)",
                  (f"{day}T12:00:00", sport, day, f"{sport}-{source}-{day}-{i}", "same_game",
                   3 if source == "game_three" else 2, "A@B", source, "won" if i < won else "lost"))
    c.commit()


def _path():
    return Path(tempfile.mkdtemp()) / "parlayhold.json"


def test_the_three_leg_hold_is_retired_and_the_two_leg_one_stands():
    c, p = _conn(), _path()
    _tickets(c, "nba", 9, 91, "game_three")             # 9% three-leg: would have been held
    _tickets(c, "nhl", 10, 40, "game_two")              # 20% two-leg: held on its own bar
    out = parlayhold.refresh(c, p, today=DAY)
    assert [(h["sport"], h.get("legs")) for h in out["holds"]] == [("nhl", 2)], out["holds"]
    assert parlayhold.held("nba", p) is None and parlayhold.held("nfl", p) is None, "nothing holds three legs"
    assert parlayhold.held("nhl", p, legs=2)["won"] == 10
    assert 3 not in parlayhold.SIZES and parlayhold.RETIRED[3]["word"] == "three-leg"
    v = parlayhold.verdict(out)
    assert v["two_leg_on_paper"] == ["nhl"] and "on_paper" not in v, v
    # A state saved before (the NFL's standing hold and the NBA's measured one)
    # holds nothing now, and the next pass drops it.
    old = _path()
    old.write_text(json.dumps({"holds": [{"sport": "nfl", "since": "2026-11-17", "n": 175, "won": 30,
                                          "source": "standing"},
                                         {"sport": "nba", "since": "2026-11-17", "n": 100, "won": 9,
                                          "source": "measured"}], "released": []}))
    assert parlayhold.holds(old) == [] and parlayhold.held("nfl", old) is None
    assert parlayhold.refresh(_conn(), old, today=DAY)["holds"] == []


def test_no_build_moves_a_games_tickets_to_paper():
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert "def paper_hold(" not in src and "paper_hold(sp)" not in src
    build = src[src.index("def build(board: dict, sport: str, now=None) -> dict:"):src.index("def two_hold(")]
    assert '"threes_paper"' not in build, "no board says its three-leg tickets are on paper"
    old = _path()
    old.write_text(json.dumps({"holds": [{"sport": "nfl", "since": "2026-11-17", "n": 175, "won": 30,
                                          "source": "standing"}], "released": []}))
    orig = parlayhold.DEFAULT_PATH
    try:
        parlayhold.DEFAULT_PATH = old
        gp = GP.build(EG.board(), "nfl")
    finally:
        parlayhold.DEFAULT_PATH = orig
    g = gp["games"][0]
    assert len(g["threes"]) == GP.THREE_PER_GAME and not g.get("paper_threes") and not g.get("threes_paper")
    assert gp["counts"]["threes"] == GP.THREE_PER_GAME and gp["counts"]["filled_threes"] == 0


def _leg(player, market, p, team="NYG", odds=-200):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "home": "NYG",
            "away": "WAS", "position": "WR", "market": market, "market_label": market, "side": "Over",
            "line": 2.5, "odds": odds, "book": "DraftKings", "p": p, "game_date": "2099-11-12"}


def test_a_game_fills_up_to_two_and_its_cards_say_how():
    g = EG.GAME
    # Four legs whose best three make 0.62^3, about 24%: under THREE_FLOOR, so
    # none clears it, and the game fills its two with longer tickets.
    legs = [_leg("A One", "receptions", 0.62), _leg("B Two", "rush_att", 0.62, team="WAS"),
            _leg("C Three", "rec_yds", 0.62), _leg("D Four", "pass_cmp", 0.61, team="WAS")]
    made = GP.tickets_of("nfl", g, legs)
    assert made["threes_clear"] == 0 and len(made["threes"]) == GP.THREE_MIN, made
    assert made["filled"] == GP.THREE_MIN
    for t in made["threes"]:
        assert GP.LONG_FLOOR <= t["joint"] < GP.THREE_FLOOR and t["filled"]
        assert any(c.startswith(f"A longer ticket: {t['joint'] * 100:.1f}% by our numbers, under the "
                                f"{GP.THREE_FLOOR:.0%} a three-leg parlay is built to") for c in t["caveats"]), t["caveats"]
    # The report's own picks first: two of them and the game's other props fill
    # the third leg, each such ticket naming the leg that is not a pick.
    own = legs[:2]
    extra = [_leg("E Five", "receptions", 0.80, team="WAS"), _leg("F Six", "rush_yds", 0.78)]
    made = GP.tickets_of("nfl", g, own, extra=extra)
    assert len(made["threes"]) == GP.THREE_MIN and made["wider"] == 4, made
    mine = {GP._leg_id(l) for l in own}
    for t in made["threes"]:
        board = [l for l in t["legs"] if GP._leg_id(l) not in mine]
        assert len(board) == 1, "the report's two picks ride every ticket, one prop of the board's beside them"
        assert any("is not one of this report's picks" in c for c in t["caveats"]), t["caveats"]
    # Fewer than three legs make no ticket, and the game says why.
    few = GP.tickets_of("nfl", g, legs[:2])
    assert few["threes"] == [] and GP._threes_note(few).startswith("0 of 2: a three-leg parlay takes three legs")


def test_a_game_short_of_props_at_60_fills_with_legs_in_the_fifties_and_names_them():
    """THREELEG2: the first builds after THREELEG1 left games short (the NHL's
    twelve made 22 tickets, the NBA's four made 3): three or four props at 60%
    make no two tickets that fit. The fill takes legs down to FILL_LEG_FLOOR,
    each named on its card."""
    g = EG.GAME
    strong = [_leg("A One", "receptions", 0.72), _leg("B Two", "rush_att", 0.70, team="WAS"),
              _leg("C Three", "rec_yds", 0.66)]
    fifties = [_leg("D Four", "pass_cmp", 0.57, team="WAS"), _leg("E Five", "receptions", 0.55)]
    before = GP.tickets_of("nfl", g, strong)
    assert len(before["threes"]) == 1, "three legs at 60% make one ticket"
    made = GP.tickets_of("nfl", g, strong, extra=fifties, picks={GP._leg_id(l) for l in strong})
    assert len(made["threes"]) == GP.THREE_MIN, made
    low = [t for t in made["threes"] if any(float(l["p"]) < GP.LEG_FLOOR for l in t["legs"])]
    assert low, "a leg in the fifties fills the game"
    for t in low:
        assert any("under the 60% a leg is built to: this game had too few props that high" in c
                   for c in t["caveats"]), t["caveats"]
    assert GP.FILL_LEG_FLOOR == 0.50
    # The report's own path reads the game's legs down to the fill's floor and
    # keeps the tickets that clear THREE_FLOOR to its picks at 60%.
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert "legs_for(board, sport, now, floor=FILL_LEG_FLOOR)" in src
    i = src.index("def from_report(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert 'and float(l.get("p") or 0) >= LEG_FLOOR]' in body and "picks=picked" in body


def test_the_heartbeat_says_why_a_game_is_short_without_naming_a_pick():
    import os
    import launch as L
    t = {"legs": [{"player": "A"}, {"player": "B"}, {"player": "C"}]}
    games = [{"home": "A", "threes": [t, t]},                                          # two: not short
             {"home": "B", "threes": [], "legs_wider": 2, "legs_from": "report"},         # too few props
             {"home": "C", "threes": [t], "legs_wider": 6, "legs_from": "report"},        # none fit
             {"home": "D", "threes": [], "rebuild_error": "KeyError: 'Jalen Hurts'"},     # the rebuild failed
             {"home": "E", "threes": []},                                                # no report rebuilt it
             {"home": "F", "threes": [], "kept": "Sun 1:00 PM ET"},                       # started: not counted
             {"home": "G", "threes": [], "no_props": "props_not_bought", "legs_wider": 0},  # bought the day before
             {"home": "H", "threes": [], "no_props": "no_props_priced", "legs_wider": 0}]   # no book has one yet
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_parlays": {"games": games, "counts": {"games": 8, "threes": 3}}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert got["threes_short"] == 6, got
    assert got["threes_short_why"] == {"few_props": 1, "no_fit": 1, "rebuild_failed": 1, "no_report": 1,
                                       "props_not_bought": 1, "no_props_priced": 1}, got
    assert got["rebuild_errors"] == ["KeyError"], "the error's type, never its words (a pick may ride in them)"
    assert "threes_no_fit_why" not in got, "no fill counts on these entries: nothing said"
    # The report path keeps the error on the private board's entry, and a rebuild that runs clears it.
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'x["rebuild_error"] = f"{type(exc).__name__}: {exc}"[:200]' in src
    gp_src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert 'x.pop("rebuild_error", None)' in gp_src and 'legs_wider=int(made.get("wider") or 0)' in gp_src


def _rec(player, market, p, team="NYG", home="NYG", away="WAS", day="2099-11-12"):
    """A priced prop on the board (EG._rec's shape), of any game."""
    return {"player": player, "team": team, "opponent": away if team == home else home, "home": home,
            "away": away, "position": "WR", "market": market, "side": "Over", "line": 2.5, "odds": -150,
            "book": "DraftKings", "hit_prob": p, "has_market": True, "recommended": False, "game_date": day,
            "kickoff": f"{day}T13:00:00-05:00", "reasons": ["Projection clears 2.5"]}


def test_every_game_still_to_play_has_its_entry_and_one_with_no_prop_says_when():
    """THREELEG3: the NFL's Thursday board (19 November) held 13 games and
    posted parlays on 3. Sunday's props are bought the day before (Saturday),
    and a game with no leg at 60% had no entry, so its report said nothing."""
    from engine import gamereport as GR
    b = EG.board()
    sunday = {"home": "PHI", "away": "DAL", "date": "2099-11-15", "kickoff": "13:00"}
    b["games"] = b["games"] + [sunday]
    thursday = dt.datetime(2099, 11, 12, 14, 0)                     # 9 AM Eastern, the builders' UTC clock
    gp = GP.build(b, "nfl", now=thursday)
    assert [x["game"] for x in gp["games"]] == ["WAS@NYG", "DAL@PHI"], [x["game"] for x in gp["games"]]
    x = gp["games"][1]
    sat = (dt.date(2099, 11, 15) - dt.timedelta(days=1)).strftime("%A")
    assert x["no_props"] == GP.PROPS_WAIT and x["threes"] == [] and x["scorers"] == [], x
    assert x["props_note"] == (f"the books' player props for this game are bought the day before it, on {sat}, "
                               "and its parlays are built from them then"), x["props_note"]
    assert "twos_note" not in x and "scorers_note" not in x, "said once, not three times"
    assert gp["counts"]["no_props"] == {GP.PROPS_WAIT: 1} and gp["counts"]["games"] == 2
    # Its report says it in one line, where the tickets will be; the rebuild keeps it.
    b["game_parlays"] = gp
    GP.from_report(b, "nfl", sunday, [], now=thursday)
    assert x["threes_note"] == x["props_note"] and "twos_note" not in x
    sec = GR.sec_parlays(GR.Ctx(sunday, b, sport="nfl"))
    assert sec["title"] == "Parlays for this game" and len(sec["blocks"]) == 1, sec
    assert sec["blocks"][0]["text"] == f"No parlays yet: {x['props_note']}.", sec["blocks"][0]
    # A game that has started keeps no new entry (its kept one is engine/reportkeep's).
    b2 = EG.board()
    b2["games"] = b2["games"] + [dict(sunday, live={"state": "final"})]
    assert [x["game"] for x in GP.build(b2, "nfl", now=thursday)["games"]] == ["WAS@NYG"]
    # A stray prop or two on file while the game's own are still to be bought
    # (nine of the NFL's Sunday games, 19 November): when they come, all the same.
    b3 = EG.board()
    b3["games"] = b3["games"] + [sunday]
    b3["recommendations"] = [_rec("P One", "receptions", 0.66, team="PHI", home="PHI", away="DAL", day="2099-11-15")]
    gp3 = GP.build(b3, "nfl", now=thursday)
    x3 = gp3["games"][1]
    assert x3["no_props"] == GP.PROPS_WAIT and x3["threes_note"] == x3["props_note"], x3.get("threes_note")
    b3["game_parlays"] = gp3
    GP.from_report(b3, "nfl", sunday, [], now=thursday)
    assert x3["no_props"] == GP.PROPS_WAIT and x3["threes_note"] == x3["props_note"], x3.get("threes_note")
    # Far past the week the board holds, nothing is promised.
    assert GP.props_note("nfl", sunday)[0] == GP.PROPS_NONE, "2099 is no Saturday's pull"


def test_when_a_games_props_come_is_said_by_its_league_and_day():
    thu, sat = dt.datetime(2026, 11, 19, 17, 0), dt.datetime(2026, 11, 21, 17, 0)    # noon Eastern
    why, words = GP.props_note("nfl", {"date": "2026-11-22"}, now=thu)
    assert why == GP.PROPS_WAIT and "bought the day before it, on Saturday" in words, words
    # The day before, the pull buys it: no book has one priced yet.
    why, words = GP.props_note("nfl", {"date": "2026-11-22"}, now=sat)
    assert why == GP.PROPS_NONE and words.startswith("no book has priced a player prop in this game yet"), words
    # A daily league buys on the game's day.
    why, words = GP.props_note("nba", {"date": "2026-11-20"}, now=thu)
    assert why == GP.PROPS_WAIT and "bought on its game day, on Friday" in words, words
    assert GP.props_note("cbb", {"date": "2026-11-19"}, now=thu)[0] == GP.PROPS_NONE
    # After midnight, before the 5 AM roll, is still last night's slate
    # (a naive clock is UTC: 08:30 is 3:30 AM Eastern).
    late = dt.datetime(2026, 11, 20, 8, 30)
    assert GP.props_note("nba", {"date": "2026-11-20"}, now=late)[0] == GP.PROPS_WAIT
    assert GP.props_note("nfl", {"date": ""}, now=thu)[0] == GP.PROPS_NONE, "no date: no promise"


def test_a_game_whose_props_all_sit_under_60_has_its_entry_and_fills_from_them():
    b = EG.board()
    away = {"home": "PHI", "away": "DAL", "date": "2099-11-15", "kickoff": "13:00"}
    b["games"] = b["games"] + [away]
    fifties = [_rec("P One", "receptions", 0.56, team="PHI", home="PHI", away="DAL", day="2099-11-15"),
               _rec("P Two", "rush_att", 0.55, team="DAL", home="PHI", away="DAL", day="2099-11-15"),
               _rec("P Three", "rec_yds", 0.57, team="PHI", home="PHI", away="DAL", day="2099-11-15"),
               _rec("P Four", "rush_yds", 0.54, team="DAL", home="PHI", away="DAL", day="2099-11-15")]
    b["recommendations"] = list(b.get("recommendations") or []) + fifties
    gp = GP.build(b, "nfl")
    x = GP.for_game({"game_parlays": gp}, "PHI", "DAL")
    assert x is not None and "no_props" not in x, "priced props, under the floor: an entry, and no wait"
    assert x["threes"] == [], "no leg at 60%: nothing clears on the board's own pass"
    b["game_parlays"] = gp
    # Props the report never picked, in the fifties: no legs (PARLAYWIN1).
    GP.from_report(b, "nfl", away, [])
    assert x["threes"] == [], "a prop the report did not pick fills only at 60%"
    # The report's own picks in the fifties fill its two.
    GP.from_report(b, "nfl", away, [dict(r, side="OVER") for r in fifties])
    assert len(x["threes"]) == GP.THREE_MIN, x.get("threes_note")
    assert all(t.get("filled") for t in x["threes"]) and "threes_note" not in x


def test_the_longer_tickets_floor_and_a_short_game_says_what_stopped_it():
    """The heartbeat's first reasons (19 November, 12:42) read the NHL's two
    short games and college basketball's one as "no fit"; step YP lowered the
    longer ticket's floor to 12.5% for them, and with it live the reasons said
    "conflicts" (no three of their props fit at any chance). The floor is 15%
    again (PARLAYWIN1): it only let longer tickets in."""
    import os
    import launch as L
    assert GP.LONG_FLOOR == 0.15 and GP.LONG_WORDS == "15%"
    g = EG.GAME
    # Four unrelated picks of the report's at 52%: every trio is 14.1%, under the floor.
    legs = [_leg("A One", "receptions", 0.52), _leg("B Two", "rush_att", 0.52, team="WAS"),
            _leg("C Three", "rush_att", 0.52), _leg("D Four", "receptions", 0.52, team="WAS")]
    mine = {GP._leg_id(l) for l in legs}
    made = GP.tickets_of("nfl", g, [], extra=legs, picks=mine)
    assert made["threes"] == [] and made["fill_fit"] == 4 and made["fill_clear"] == 0, made
    # At 55% they are 16.6%: a longer ticket, said so on its card.
    made = GP.tickets_of("nfl", g, [], extra=[dict(l, p=0.55) for l in legs], picks=mine)
    assert len(made["threes"]) == GP.THREE_MIN and made["fill_clear"] == 4, made
    for t in made["threes"]:
        assert any(c.startswith("A longer ticket: 16.6% by our numbers") for c in t["caveats"]), t["caveats"]
    # One that clears nothing because every pair conflicts: the same player in each.
    same = [_leg("A One", m, 0.7) for m in ("receptions", "rec_yds", "rush_att")]
    none = GP.tickets_of("nfl", g, [], extra=same, picks={GP._leg_id(l) for l in same})
    assert none["threes"] == [] and none["fill_fit"] == 0 and none["fill_clear"] == 0
    assert "reach 15% by our numbers" in GP._threes_note(dict(none, wider=3))
    # Props the report did not pick ride one a ticket, beside two of its picks.
    two_picks = legs[:2]
    others = [dict(l, p=0.66) for l in legs[2:]]
    made = GP.tickets_of("nfl", g, [], extra=[dict(l, p=0.66) for l in two_picks] + others,
                         picks={GP._leg_id(l) for l in two_picks})
    assert made["threes"] and all(sum(GP._leg_id(l) not in mine or l["player"] in ("C Three", "D Four")
                                      for l in t["legs"]) <= GP.FILL_OUTSIDE_MAX for t in made["threes"]), made
    alone = GP.tickets_of("nfl", g, [], extra=others + [dict(legs[0], p=0.66)], picks={GP._leg_id(legs[0])})
    assert alone["threes"] == [] and alone["wider_own"] == 1, "one pick of the report's makes no ticket"
    assert GP._report_note(0, 1, alone).startswith("a three-leg parlay takes 2 of this report's own picks"), \
        GP._report_note(0, 1, alone)
    # A game that needs no fill counts none.
    full = GP.tickets_of("nfl", g, [_leg("A One", "receptions", 0.9), _leg("B Two", "rush_att", 0.9, team="WAS"),
                                    _leg("C Three", "rec_yds", 0.9), _leg("D Four", "pass_cmp", 0.9, team="WAS")])
    assert len(full["threes"]) >= GP.THREE_MIN and full["fill_fit"] is None
    t = {"legs": [{"player": "A"}, {"player": "B"}, {"player": "C"}]}
    games = [{"home": "A", "threes": [], "legs_wider": 5, "fill_fit": 0, "fill_clear": 0},
             {"home": "B", "threes": [], "legs_wider": 5, "fill_fit": 6, "fill_clear": 0},
             {"home": "C", "threes": [t], "legs_wider": 4, "fill_fit": 3, "fill_clear": 1},
             {"home": "D", "threes": [], "legs_wider": 2, "fill_fit": 0, "fill_clear": 0}]
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_parlays": {"games": games, "counts": {"games": 4, "threes": 1}}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert got["threes_short_why"] == {"no_fit": 3, "few_props": 1}, got
    assert got["threes_no_fit_why"] == {"conflicts": 1, "under_floor": 1, "one_trio": 1}, got


def test_a_ticket_on_paper_from_before_still_journals_and_grades():
    c = _conn()
    leg = lambda pl, m: {"player": pl, "team": "KC", "market": m, "side": "OVER", "line": 1.5, "odds": -150,
                         "book": "DraftKings", "p": 0.7}                                        # noqa: E731
    paper = {"legs": [leg("A", "receptions"), leg("B", "rush_att"), leg("C", "pass_yds")], "joint": 0.3,
             "take_dec": 3.5, "naive_dec": 3.4, "independent": 0.34}
    gp = {"games": [{"away": "DEN", "home": "KC", "game": "DEN@KC", "threes": [], "paper_threes": [paper],
                     "threes_paper": True, "threes_note": "On paper", "scorers": []}]}
    assert parlayledger.log_game_parlays(c, gp, "nfl", "2026-W12") == 1
    row = c.execute("SELECT source, n_legs, stake_units FROM parlays").fetchone()
    assert tuple(row) == ("game_three", 3, 0), tuple(row)
    assert [r["player"] for r in GP.journal_rows(gp)] == ["A", "B", "C"], "its legs are graded too"


def test_the_record_and_the_night_say_no_three_leg_hold():
    c = _conn()
    _tickets(c, "nfl", 3, 7, "game_three")
    old = _path()
    old.write_text(json.dumps({"holds": [{"sport": "nfl", "since": "2026-11-17", "n": 175, "won": 30,
                                          "source": "standing"}], "released": []}))
    orig = parlayhold.DEFAULT_PATH
    try:
        parlayhold.DEFAULT_PATH = old
        rec = parlayledger.game_parlay_record(c)
    finally:
        parlayhold.DEFAULT_PATH = orig
    three = rec["nfl"]["three"]
    assert (three["graded"], three["wins"]) == (10, 3) and "paper" not in three
    m = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert 'verdicts["two-leg parlays on paper"] = parlayhold.verdict(plh)' in m
    assert "three-leg parlays on paper" not in m
    # A game played while its league was on paper still says so on its page.
    rj = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "g.threes_paper ? `<p class=\"gr-note\">Three-leg parlays: on paper for now" in rj


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
