"""The short version reads as sentences, not a wire slip.

Ethan, 2026-10-22, at the Patriots–Bears report on his phone: "Fix how in
the short version that we need to be more descriptive in the wording. It's
very blunt." It read:

    CHI by 3 at home, total 50.5: the books expect about CHI 26.8, NE 23.8;
    the moneyline makes CHI a 60% favorite.
    Out: T.J. Edwards (CHI LB), Kyle Monangai (CHI RB), …
    Last meeting: 2024 week 10 at CHI: NE won 19-3 · CHI −6.5, NE covered
    · total 37.5, under.

What this file holds the short version (engine/gamereport.sec_short, and
leaguereport's MLB, NHL and NBA ones) to:

* SENTENCES. The teams by name, never a code; a position in words; and
  what each number means — who is favored and the score it points to, what
  an edge does on the field, what a passer rating means, why a player could
  have a big day, how the last meeting went against its line.
* THE SAME FACTS. Every number is the one the board held before; nothing is
  added that the sections below do not hold; no player line, price or
  chance.
* GRAMMAR BY LEAGUE. "The Lions are", "the Heat is", "Indiana is": a club's
  plural nickname takes a plural verb, a singular one and a school do not,
  and a scan's "GB gives up" becomes "the Packers give up" only for a verb
  it knows.

Run directly: `python3 tests/test_the_short_version_reads_as_sentences.py`
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamereport as R                                  # noqa: E402
from engine import leaguereport as L                                # noqa: E402


def _chi_ne():
    """Ethan's game, rebuilt from what his screenshot showed."""
    game = {"away": "NE", "home": "CHI", "date": "2026-10-25", "kickoff": "13:00",
            "spread": -3.0, "total": 50.5, "home_ml": -166, "away_ml": 140,
            "sim": {"trials": 4000, "p_home_win": 0.59, "one_score": 0.44},
            "scan": {
                "edges": [{"unit": "explosive", "off": "NE", "def": "CHI", "off_rank": 10, "def_rank": 30, "gap": 20},
                          {"unit": "rushing", "off": "CHI", "def": "NE", "off_rank": 9, "def_rank": 22, "gap": 13},
                          {"unit": "pressure", "off": "CHI", "def": "NE", "off_rank": 2, "def_rank": 15, "gap": 13}],
                "coverage": {"CHI": {"corners": [{"name": "Tyrique Stevenson", "spot": "RCB", "targets": 17,
                                                  "rating": 139.0}], "weakest": "Tyrique Stevenson"}},
                "injuries": [{"team": "CHI", "player": "T.J. Edwards", "position": "LB", "status": "OUT"},
                             {"team": "CHI", "player": "Kyle Monangai", "position": "RB", "status": "OUT"},
                             {"team": "CHI", "player": "Dayo Odeyingbo", "position": "DE", "status": "OUT"},
                             {"team": "CHI", "player": "Montez Sweat", "position": "DE", "status": "OUT"},
                             {"team": "NE", "player": "Carlton Davis III", "position": "CB", "status": "OUT"}],
                "numbers": {"NE": {"to_margin": {"value": -6, "rank": 30}},
                            "CHI": {"to_margin": {"value": -2, "rank": 19}}},
                "method": {"teams": 32}}}
    reads = [{"player": "D'Andre Swift", "team": "CHI", "pos": "RB", "read": "good",
              "pro": ["NE gives up the 6th-most rushing yards to running backs (98.4 a game)"],
              "usage": {"carry_share": 0.55, "carries_pg": 15.0},
              "td": {"model_prob": 0.4321, "odds": 333}, "lean": ["rush_yds"]},
             {"player": "A.J. Brown", "team": "NE", "pos": "WR", "read": "good",
              "pro": ["CHI gives up the 3rd-most passing yards (265 a game)"],
              "usage": {"tgt_share": 0.27, "targets_pg": 8.4}}]
    board = {"date": "2026-W8", "games": [game], "scan_reads": {"NE@CHI": {"players": reads}}}
    meetings = [{"season": 2024, "week": 10, "round": "", "day": "2024-11-10", "home": "CHI", "away": "NE",
                 "hs": 3, "as": 19, "neutral": False, "winner": "NE", "spread_home": -6.5, "total": 37.5,
                 "covered": "NE", "ou": "under"}]
    return R.build(game, board, names={"NE": "Patriots", "CHI": "Bears"}, meetings=meetings)


def _short(rep):
    sec = next(s for s in rep["sections"] if s["key"] == "short")
    return [it for blk in sec["blocks"] for it in blk.get("items", [])]


def _ctx(away="GB", home="DET", names=None, sport="nfl", **g):
    game = {"away": away, "home": home, **g}
    return R.Ctx(game, {"games": [game]}, names=names if names is not None else
                 {"GB": "Packers", "DET": "Lions"}, sport=sport)


# --- Ethan's game -----------------------------------------------------------------------
def test_ethans_game_reads_as_sentences():
    got = _short(_chi_ne())
    assert got == [
        "The Bears are 3-point favorites at home, and the total is 50.5, which works out to about Bears 27, "
        "Patriots 24. Take out the book's cut and the moneyline gives the Bears a 60% chance to win.",
        "Where the matchup tilts: the Patriots' big plays (10th in the league) meet a Bears defense that "
        "gives them up (30th), so the Patriots should find some chunk plays. The Bears' run game (9th) faces "
        "the Patriots' run defense (22nd), so there is room to run for the Bears. The Bears' pass protection "
        "(2nd) faces the Patriots' pass rush (15th), so the Bears' quarterback should have time to throw.",
        "The softest spot in coverage: the Bears' right cornerback Tyrique Stevenson has allowed a 139 passer "
        "rating on 17 targets. A perfect passer rating is 158.3, so the receivers who line up across from him "
        "have the easier matchup.",
        "Who could have a big day: D'Andre Swift, the Bears' running back — the Patriots give up the "
        "sixth-most rushing yards to running backs (98.4 a game). A.J. Brown, the Patriots' wide receiver — "
        "the Bears give up the third-most passing yards (265 a game).",
        "The Patriots are without cornerback Carlton Davis III; the Bears are missing linebacker T.J. "
        "Edwards, running back Kyle Monangai and defensive ends Dayo Odeyingbo and Montez Sweat.",
        "The last time they met (week 10 of 2024), the Patriots won 19-3 on the road as 6.5-point underdogs; "
        "the 22 points went under the 37.5 total.",
        "In turnover margin this season, the Patriots are −6 (30th, near the bottom of the league) and the "
        "Bears −2 (19th).",
        "Our simulator, which plays the game out drive by drive 4,000 times, has the Bears winning 59% of the "
        "time; 44% of the games are decided by 8 points or fewer.",
    ], got


def test_the_wire_slip_is_gone():
    text = " ".join(_short(_chi_ne()))
    for old in ("CHI by", "Out: ", "Could shine: ", "Last meeting: ", "Turnovers this season", "edge NE",
                " · ", "the moneyline makes"):
        assert old not in text, old
    assert not re.search(r"\b(NE|CHI)\b", text), "a team code survived into the short version"
    # Still no player line, price or chance: the read's touchdown chance
    # and price are on the board, and nowhere here.
    for mark in ("43.2", "0.4321", "+333", "rush_yds"):
        assert mark not in text, mark


# --- the words ------------------------------------------------------------------------------
def test_a_code_becomes_the_team_and_the_verb_agrees():
    c = _ctx()
    assert R.named(c, "GB gives up the 2nd-most touchdowns to running backs (1.7 a game)") == \
        "the Packers give up the second-most touchdowns to running backs (1.7 a game)"
    assert R.named(c, "DET's pass defense ranks 22nd; GB rarely allows a sack") == \
        "the Lions' pass defense ranks 22nd; the Packers rarely allow a sack"
    assert R.named(c, "The lines expect DET to score about 28") == "The lines expect the Lions to score about 28"
    assert R.named(c, "DET gives up the 1st-most passing yards") == "the Lions give up the most passing yards"
    assert R.named(c, "GB 31, DET 24") == "the Packers 31, the Lions 24", "a code with no verb after it"
    # A singular nickname keeps its verb; a school is its name.
    heat = _ctx("MIA", "BOS", {"MIA": "Heat", "BOS": "Celtics"}, sport="nba")
    assert R.named(heat, "MIA gives up the most points; BOS's offense is 1st") == \
        "the Heat gives up the most points; the Celtics' offense is 1st"
    cfb = _ctx("MIA", "IND", {"MIA": "Miami", "IND": "Indiana"}, sport="cfb")
    assert R.named(cfb, "MIA allows 5.1 yards a carry; IND's line") == "Miami allows 5.1 yards a carry; Indiana's line"
    assert R.team_be(cfb, "IND") == "is" and R.team_be(heat, "MIA") == "is" and R.team_be(heat, "BOS") == "are"


def test_a_reason_ends_a_sentence_without_shouting():
    known = {"Zack Wheeler", "Miami"}
    assert R._clause("Takes 69% of the carries (18 a game).", known) == "takes 69% of the carries (18 a game)"
    assert R._clause("A soft corner", known) == "a soft corner"
    assert R._clause("Faces Jeremy Swayman, +4.2 goals saved", known) == "faces Jeremy Swayman, +4.2 goals saved"
    assert R._clause("Zack Wheeler holds righties to a .330 SLG", known) == "Zack Wheeler holds righties to a .330 SLG"
    assert R._clause("CHC strikes out 25.0% of the time", known) == "CHC strikes out 25.0% of the time"
    assert R._clause("Miami allows 5.1 yards a carry", known) == "Miami allows 5.1 yards a carry"


def test_who_is_out_is_said_by_position_and_doubtful_is_not_out():
    c = _ctx()
    rows = [{"team": "DET", "player": "A One", "position": "DE", "status": "OUT"},
            {"team": "DET", "player": "B Two", "position": "DE", "status": "OUT"},
            {"team": "DET", "player": "C Three", "position": "S", "status": "IR"},
            {"team": "GB", "player": "D Four", "position": "CB", "status": "DOUBTFUL"}]
    assert R.absent_sentence(c, rows) == (
        "Cornerback D Four is doubtful for the Packers; the Lions are missing defensive ends A One and B Two "
        "and safety C Three."), R.absent_sentence(c, rows)
    assert R.pos_word(c, "S", 2) == "safeties" and R.pos_word(_ctx(sport="nhl"), "D", 2) == "defensemen"


def test_the_last_meeting_says_who_was_favored_and_how_it_went():
    c = _ctx()
    base = {"season": 2025, "week": 13, "round": "", "day": "2025-11-27", "home": "DET", "away": "GB",
            "neutral": False}
    say = lambda **m: R.meeting_sentence(c, {**base, **m})                         # noqa: E731
    assert say(hs=24, **{"as": 31}, winner="GB", spread_home=-2.5, total=48.5, covered="GB", ou="over") == \
        ("The last time they met (week 13 of 2025), the Packers won 31-24 on the road as 2.5-point underdogs; "
         "the 55 points went over the 48.5 total.")
    assert say(hs=27, **{"as": 24}, winner="DET", spread_home=-6.5, covered="GB") == \
        "The last time they met (week 13 of 2025), the Lions won 27-24 at home as 6.5-point favorites, but did not cover."
    assert say(hs=34, **{"as": 31}, winner="DET", spread_home=-3.0, covered="push", total=65, ou="push") == \
        ("The last time they met (week 13 of 2025), the Lions won 34-31 at home as 3-point favorites, winning by "
         "exactly the spread; the 65 points landed right on the 65 total.")
    assert say(hs=20, **{"as": 20}, winner=None) == "The last time they met (week 13 of 2025), they tied 20-20."
    assert "(the 2024 divisional round)" in R.meeting_sentence(c, {**base, "round": "divisional round",
                                                                   "season": 2024, "hs": 17, "as": 20, "winner": "GB"})


def test_baseball_and_hockey_lead_with_the_moneyline():
    mlb = _ctx("PHI", "CHC", {"PHI": "Phillies", "CHC": "Cubs"}, sport="mlb",
               spread=1.5, total=9.5, home_ml=140, away_ml=-165)
    assert R.market_sentence(mlb) == ("The Phillies are the moneyline favorites, with a 60% chance to win once "
                                      "the book's cut is taken out. They are −1.5 on the run line, and the total "
                                      "is 9.5 runs.")
    nhl = _ctx("BOS", "TOR", {"BOS": "Bruins", "TOR": "Maple Leafs"}, sport="nhl", spread=-1.5, total=6.5)
    assert R.market_sentence(nhl) == "The Maple Leafs are −1.5 on the puck line, and the total is 6.5 goals."


def test_a_pick_em_a_neutral_site_and_a_school():
    assert R.market_sentence(_ctx(spread=0.0, total=44.0)) == \
        "The books have this one as a pick'em, and the total is 44, about 22 points each."
    cfb = _ctx("MIA", "IND", {"MIA": "Miami", "IND": "Indiana"}, sport="cfb", spread=7.5, total=47.0,
               neutral_site=True)
    assert R.market_sentence(cfb) == ("Miami is a 7.5-point favorite at a neutral site, and the total is 47, "
                                      "which works out to about Miami 27, Indiana 20.")


def test_the_total_is_placed_on_the_board_only_at_either_end():
    games = [{"away": f"A{i}", "home": f"H{i}", "total": t} for i, t in enumerate((41, 43, 44, 45, 46, 48, 52))]
    for g, want in ((games[-1], "the highest total on the board"), (games[-2], "the second-highest total on the board"),
                    (games[0], "the lowest total on the board"), (games[3], "")):
        c = R.Ctx(g, {"games": games}, names={})
        assert R._slate_spot(c) == want, (g, R._slate_spot(c))
    few = R.Ctx(games[-1], {"games": games[:3] + [games[-1]]}, names={})
    assert R._slate_spot(few) == "", "four games is not a board to rank on"


# --- Ethan's research on the same game, 2026-10-22 -------------------------------------------
def test_every_soft_corner_is_named_and_one_who_may_sit_says_so():
    """The research went at Jaylon Johnson (22 of 28 for 412 yards); this
    named only Stevenson, and never said Stevenson was questionable."""
    corners =[{"name": "Tyrique Stevenson", "spot": "RCB", "status": "QUESTIONABLE", "targets": 17, "rating": 139.0},
               {"name": "Jaylon Johnson", "spot": "LCB", "status": "", "targets": 28, "rating": 130.7},
               {"name": "Kyler Gordon", "spot": "NB", "status": "", "targets": 3, "rating": 150.0},
               {"name": "Nahshon Wright", "spot": "LCB", "status": "", "targets": 9, "rating": 88.0}]
    g = {"away": "NE", "home": "CHI", "scan": {"coverage": {"CHI": {"corners": corners, "weakest": "Tyrique Stevenson"}},
                                               "method": {"teams": 32}}}
    c = R.Ctx(g, {"games": [g]}, names={"NE": "Patriots", "CHI": "Bears"})
    got = [x for x in R.sec_short(c, {})["blocks"][0]["items"] if "coverage" in x]
    assert got == [
        "The softest spots in coverage: the Bears' right cornerback Tyrique Stevenson (questionable) has allowed "
        "a 139 passer rating on 17 targets, and left cornerback Jaylon Johnson a 130.7 on 28. A perfect passer "
        "rating is 158.3, so the receivers who line up across from them have the easier matchup."], got
    # Three targets is not a sample, and 88 is not soft; one corner past
    # the bar is still said as one.
    one = [dict(x, status="") for x in corners[:1]] + corners[2:]
    g["scan"]["coverage"]["CHI"]["corners"] = one
    got = [x for x in R.sec_short(R.Ctx(g, {"games": [g]}, names={"NE": "Patriots", "CHI": "Bears"}), {})
           ["blocks"][0]["items"] if "coverage" in x]
    assert got and got[0].startswith("The softest spot in coverage: the Bears' right cornerback Tyrique Stevenson "
                                     "has allowed a 139") and got[0].endswith("across from him have the easier matchup."), got


def test_a_reason_is_said_without_the_models_footnotes():
    said = ("Kyle Monangai (RB) is out — 36% of the carries (12.7 a game) to go around; not enough games without "
            "him to measure who takes them · our projection counts it: +10% rushing yards")
    assert R.short_reason(said) == "with Kyle Monangai out, 36% of the carries (12.7 a game) are up for grabs"
    assert R.short_reason("Romeo Doubs (WR) is out — 16% of the targets (4.6 a game) to go around · not in our "
                          "number: no lift measured across positions") == \
        "with Romeo Doubs out, 16% of the targets (4.6 a game) are up for grabs"
    plain = "NE gives up the 6th-most rushing yards to running backs (98.4 a game)"
    assert R.short_reason(plain) == plain
    c = _ctx("NE", "CHI", {"NE": "Patriots", "CHI": "Bears"})
    r = {"player": "D'Andre Swift", "team": "CHI", "pos": "RB", "read": "good",
         "pro": ["The lines expect CHI to score about 27 (−3 at home, total 50.5)", said]}
    assert R.player_clause(c, r, "up") == ("D'Andre Swift, the Bears' running back — with Kyle Monangai out, 36% of "
                                           "the carries (12.7 a game) are up for grabs")


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
