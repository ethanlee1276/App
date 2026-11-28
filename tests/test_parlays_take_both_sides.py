"""A game's parlays and touchdown pairs take both sides unless the data clearly points one way.

Ethan, 2026-11-16, of the 49ers' game: "I don't like how a lot of these
parlays we are making are very one sided as in a lot of picks for both td
and player props are for one team only and we need too fix that. I
understand if all the data points too one side so that's fine but we just
need to make sure."

Ranked on the chance alone, a game's likeliest legs are usually one club's
busiest players, and "built to win together" keeps the next tickets on the
same script, so a game's four tickets could all be one club's when the other
club's legs were a point or two behind. engine/gameparlays.choose now takes
a one-club ticket only when it is clearly the stronger read than the best
two-club ticket that fits in its place: SIDE_EDGE likelier, or for a scorer
pair ranked on its research, SIDE_RESEARCH more research points. It takes at
most ONE_SIDED_MAX of them while a two-club ticket fits. A game whose other
club has nothing good enough posts what it has, and every one-club ticket
says which of the two it was.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gameparlays as GP  # noqa: E402

GAME = {"home": "DAL", "away": "SF", "date": "2099-11-15", "kickoff": "16:25", "spread": 2.5, "total": 47.5}


def _leg(player, team, pos, market, line, p, odds=-200, side="Over"):
    opp = "DAL" if team == "SF" else "SF"
    return {"player": player, "team": team, "opponent": opp, "home": "DAL", "away": "SF", "position": pos,
            "market": market, "market_label": market, "side": side, "line": line, "odds": odds,
            "book": "DraftKings", "p": p, "game_date": "2099-11-15", "why": []}


def _sf(p0=0.74):
    """Five 49ers legs, the likeliest on the board."""
    return [_leg("Christian McCaffrey", "SF", "RB", "receptions", 3.5, p0),
            _leg("George Kittle", "SF", "TE", "receptions", 3.5, p0 - 0.01),
            _leg("Jauan Jennings", "SF", "WR", "receptions", 2.5, p0 - 0.02),
            _leg("Ricky Pearsall", "SF", "WR", "rec_yds", 24.5, p0 - 0.03),
            _leg("Kyle Juszczyk", "SF", "FB", "receptions", 0.5, p0 - 0.04)]


def _dal(p0=0.71):
    """Four Cowboys legs, a point or two behind."""
    return [_leg("CeeDee Lamb", "DAL", "WR", "receptions", 5.5, p0),
            _leg("Jake Ferguson", "DAL", "TE", "receptions", 3.5, p0 - 0.01),
            _leg("George Pickens", "DAL", "WR", "rec_yds", 44.5, p0 - 0.02),
            _leg("Javonte Williams", "DAL", "RB", "receptions", 1.5, p0 - 0.03)]


def _clubs(t):
    return sorted({l["team"] for l in t["legs"]})


def _old_rule(fn):
    """The game built as before the rule: one-club tickets taken on the chance alone."""
    keep = (GP.ONE_SIDED_MAX, GP.SIDE_EDGE, GP.SIDE_RESEARCH)
    GP.ONE_SIDED_MAX, GP.SIDE_EDGE, GP.SIDE_RESEARCH = 99, -1.0, -99
    try:
        return fn()
    finally:
        GP.ONE_SIDED_MAX, GP.SIDE_EDGE, GP.SIDE_RESEARCH = keep


def test_a_game_that_leans_a_point_or_two_one_way_posts_both_sides():
    build = lambda: GP.build_game("nfl", GAME, _sf() + _dal(), [])  # noqa: E731
    before, after = _old_rule(build), build()
    old = [_clubs(t) for t in before["threes"]]
    assert sum(c == ["SF"] for c in old) >= 2, ("the old way: half the game's tickets the 49ers' alone", old)
    new = [_clubs(t) for t in after["threes"]]
    assert len(new) == GP.THREE_PER_GAME, (new, after.get("threes_note"))
    assert sum(len(c) == 1 for c in new) <= GP.ONE_SIDED_MAX, new
    assert sum(c == ["DAL", "SF"] for c in new) >= GP.THREE_PER_GAME - 1, ("both sides on the rest", new)
    for t in after["threes"]:
        if len(_clubs(t)) == 1:
            assert t.get("one_club") and any(c.startswith("Every leg here is SF's") for c in t["caveats"]), t["caveats"]


def test_a_one_club_ticket_clearly_the_stronger_read_is_kept_and_says_why():
    g = GP.build_game("nfl", GAME, _sf(0.86) + _dal(0.64), [])
    one = [t for t in g["threes"] if len(_clubs(t)) == 1]
    assert len(one) == 1, [_clubs(t) for t in g["threes"]]
    why = [c for c in one[0]["caveats"] if c.startswith("Every leg here is SF's")]
    assert why and "points likelier than the best ticket with both sides" in why[0], one[0]["caveats"]
    gap = int(why[0].split(": ")[1].split(" ")[0])
    assert gap >= round(GP.SIDE_EDGE * 100), why[0]
    assert all(len(_clubs(t)) == 2 for t in g["threes"] if t is not one[0]), "the rest take both sides"


def test_a_game_whose_other_side_has_nothing_posts_what_it_has():
    g = GP.build_game("nfl", GAME, _sf(), [])
    assert g["threes"] and all(_clubs(t) == ["SF"] for t in g["threes"])
    for t in g["threes"]:
        assert any("no ticket with the other side's picks fits this game" in c for c in t["caveats"]), t["caveats"]


def _scorer(player, team, pos, p, research, odds=150):
    leg = _leg(player, team, pos, "anytime_td", 0.5, p, odds)
    leg.update(research=research, research_of=GP.RESEARCH_MAX)
    return leg


def test_touchdown_pairs_take_a_scorer_from_each_side_unless_one_side_is_clearly_stronger():
    # Every scorer at our touchdown rule (40%), so the research alone orders them (a pair below the rule
    # ranks behind one at it since step AAP: tests/test_touchdown_pairs_take_two_scorers_at_the_rule_first.py).
    close = [_scorer("Christian McCaffrey", "SF", "RB", 0.48, 9), _scorer("George Kittle", "SF", "TE", 0.42, 8),
             _scorer("Javonte Williams", "DAL", "RB", 0.40, 7), _scorer("CeeDee Lamb", "DAL", "WR", 0.41, 6)]
    build = lambda: GP.build_game("nfl", GAME, [], close)  # noqa: E731
    old = [_clubs(t) for t in _old_rule(build)["scorers"]]
    assert old[0] == ["SF"], ("the old way: the 49ers' two strongest cases first", old)
    new = [_clubs(t) for t in build()["scorers"]]
    assert all(c == ["DAL", "SF"] for c in new), ("17 against 16 is no case for two of one club", new)
    # A clear case (12 and 11 against 5 and 4) keeps one pair of one club, saying so.
    clear = [_scorer("Christian McCaffrey", "SF", "RB", 0.52, 12), _scorer("George Kittle", "SF", "TE", 0.40, 11),
             _scorer("Javonte Williams", "DAL", "RB", 0.33, 5), _scorer("CeeDee Lamb", "DAL", "WR", 0.30, 4)]
    pairs = GP.build_game("nfl", GAME, [], clear)["scorers"]
    one = [t for t in pairs if len(_clubs(t)) == 1]
    assert len(one) == 1, [_clubs(t) for t in pairs]
    assert any("research case is 6 points stronger than the best pair with a scorer from each side" in c
               for c in one[0]["caveats"]), one[0]["caveats"]


def test_the_build_log_counts_the_one_club_tickets():
    gp = {"counts": {"games": 2, "threes": 8, "scorers": 6, "one_club_threes": 1, "one_club_scorers": 0}}
    assert GP.summary(gp).endswith("one club's alone: 1 three-leg, 0 pair(s)"), GP.summary(gp)


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
