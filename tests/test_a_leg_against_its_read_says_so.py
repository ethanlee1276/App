"""A parlay leg against its player's read on the report says so (step AIA, 26 November 2026).

Bears at Lions, Thanksgiving: the report called Amon-Ra St. Brown a good spot under Who's guarding who and named
St. Brown for a big day, and one of its three-leg tickets took St. Brown's catches under 7.5 (it won, 7 catches).
Both were our numbers: a read never moves a number (the scan measured no lift over the model, engine/likely's
LEAN), and the Most Likely card already said "matchup read leans the other way" (likelyboard.matchup_warning; Ethan,
6 October: "keep 3 with the warning"). The ticket said nothing, so the report read as arguing with itself, the thing
Ethan's screenshots of the same game asked us to fix ("how we show the data"). What holds:

  * a leg whose player's read leans its market the other way carries ``read_against`` (gameparlays.read_against);
  * its ticket says so with our number: our projection where the leg carries one, else our chance;
  * a read that agrees, leans another market, or is mixed (it leans nowhere) says nothing;
  * a name keeps its particle: "St. Brown", "Van Noy" (gamereport._last_name).

Offline. Run directly: `python3 tests/test_a_leg_against_its_read_says_so.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP                                 # noqa: E402
from engine import gamereport as R                                   # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)


def _leans():
    return {(GP._key("Amon-Ra St. Brown"), "DET", "receptions"): {"side": "over", "read": "good",
                                                                  "label": "Good spot"}}


def _leg(**kw):
    leg = {"player": "Amon-Ra St. Brown", "team": "DET", "market": "receptions", "market_label": "Receptions",
           "side": "Under", "line": 7.5, "p": 0.62, "odds": -150}
    leg.update(kw)
    return leg


def test_a_leg_against_its_players_read_is_marked_and_one_that_agrees_is_not():
    got = GP.read_against(_leg(), _leans())
    assert got == {"read": "good", "label": "Good spot", "side": "over"}, got
    assert GP.read_against(_leg(side="Over"), _leans()) is None, "a leg that agrees says nothing"
    assert GP.read_against(_leg(market="rec_yds"), _leans()) is None, "a market the read does not lean"
    assert GP.read_against(_leg(player="Jared Goff"), _leans()) is None, "no read"


def test_the_ticket_says_it_with_our_number():
    leg = dict(_leg(projection=6.4), read_against={"read": "good", "label": "Good spot", "side": "over"})
    assert GP.read_against_words(leg) == (
        "Amon-Ra St. Brown under 7.5 receptions goes against this report's good spot for St. Brown: our number is "
        "6.4 receptions, under the line even so")
    # Without a projection (or one on the other side of the line), our chance.
    leg.pop("projection")
    assert GP.read_against_words(leg) == (
        "Amon-Ra St. Brown under 7.5 receptions goes against this report's good spot for St. Brown: our numbers make "
        "the under the likelier side even so (62%)")
    avoid = dict(_leg(side="Over", line=4.5, projection=5.2),
                 read_against={"read": "avoid", "label": "Avoid", "side": "under"})
    assert GP.read_against_words(avoid).startswith(
        "Amon-Ra St. Brown over 4.5 receptions goes against this report's call to avoid St. Brown: our number is 5.2")
    assert GP.read_against_words(_leg()) == "", "a leg that agrees"
    words = GP.read_against_words(dict(_leg(projection=6.4), read_against=GP.read_against(_leg(), _leans())))
    assert " his " not in f" {words} " and " him " not in f" {words} ", words


def test_a_built_ticket_carries_the_line():
    b = EG.board()
    diggs = next(r for r in b["most_likely"] if r["player"] == "Stefon Diggs")
    diggs["projection"] = 36.2
    b["scan_reads"]["WAS@NYG"]["players"].append(
        {"player": "Stefon Diggs", "team": "WAS", "opp": "NYG", "pos": "WR", "read": "tough", "label": "Tough matchup",
         "lean": ["receptions", "rec_yds"], "usage": {"tgt_share": 0.22}, "pro": [], "con": ["x"], "notes": []})
    legs = GP.legs_for(b, "nfl")
    leg = next(l for l in legs if l["player"] == "Stefon Diggs")
    assert leg["read_against"]["read"] == "tough" and leg["projection"] == 36.2, leg
    assert not any(l.get("read_against") for l in legs if l["player"] != "Stefon Diggs"), "only the one against"
    t = GP.ticket("nfl", [leg] + [l for l in legs if l["player"] in ("Malik Nabers", "Isaiah Likely")][:2], EG.GAME)
    assert t is not None
    want = ("Stefon Diggs over 29.5 receiving yards goes against this report's tough matchup for Diggs: our number is "
            "36.2 receiving yards, over the line even so")
    assert want in t["caveats"], t["caveats"]


def test_a_mixed_read_leans_nowhere_so_nothing_is_said():
    b = EG.board()
    b["scan_reads"]["WAS@NYG"]["players"].append(
        {"player": "Stefon Diggs", "team": "WAS", "opp": "NYG", "pos": "WR", "read": "neutral", "label": "Neutral",
         "mixed": "NYG gives up the most receiving yards to wide receivers", "mixed_was": "tough",
         "lean": ["receptions", "rec_yds"], "pro": [], "con": [], "notes": []})
    assert not any(l.get("read_against") for l in GP.legs_for(b, "nfl"))


def test_a_report_pick_against_its_read_says_so_first_on_its_card():
    g = {"away": "CHI", "home": "DET", "date": "2026-11-26"}
    read = {"player": "Amon-Ra St. Brown", "team": "DET", "pos": "WR", "read": "good", "label": "Good spot",
            "spot": True, "lean": ["receptions", "rec_yds", "anytime_td"],
            "pro": ["The lines expect DET to score about 28"], "con": ["CHI holds receivers to 5.1 catches a game"]}
    c = R.Ctx(g, {"games": [g], "scan_reads": {"CHI@DET": {"players": [read]}}},
              names={"CHI": "Bears", "DET": "Lions"}, sport="nfl")
    pick = {"player": "Amon-Ra St. Brown", "team": "DET", "market": "receptions", "market_label": "Receptions",
            "side": "Under", "line": 7.5, "model_prob": 0.62, "projection": 6.4}
    why = R.card_why(c, pick, {})
    assert why[0] == ("This pick goes against this report's good spot for St. Brown: our number is 6.4 receptions, "
                      "under the line even so"), why
    assert why[-1] == "The main way it loses: The lines expect DET to score about 28", why
    agrees = R.card_why(c, dict(pick, side="Over", line=5.5), {})
    assert not any("goes against" in w for w in agrees), agrees
    td = R.card_why(c, dict(pick, market="anytime_td", side="Under", line=0.5), {})
    assert not any("goes against" in w for w in td), "a touchdown rides its own research"


def test_a_name_keeps_its_particle():
    assert R._last_name("Amon-Ra St. Brown") == "St. Brown"
    assert R._last_name("Kyle Van Noy") == "Van Noy"
    assert R._last_name("Van Jefferson") == "Jefferson", "a first name is not a particle"
    assert R._last_name("Marvin Harrison Jr.") == "Harrison" and R._last_name("Jared Goff") == "Goff"


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
