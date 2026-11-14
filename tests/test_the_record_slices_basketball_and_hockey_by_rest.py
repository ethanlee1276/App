"""The record slices basketball and hockey by their rest (2026-11-14).

Ethan, 2026-11-14: "make sure ... hypothesis is working ... for every single
sport". The hypothesis lab held 79 hypotheses on the public record and not
one for the NBA, the NHL or college basketball, though it reads every
league's settled picks. Its own watchlist said why: "WNBA ast OVERs ...
crossed with back-to-back scheduling — the rest menu has no
basketball-appropriate value, so this needs a rest dimension defined for
WNBA/NBA before it can be tested". The rest bands were football's (a short
week, a normal week, off a bye), and no basketball or hockey pick was
journaled with its rest at all, so neither the lab nor the loss miner could
ever ask about the second night of a back-to-back.

A league that plays nights in a row now bands the days since its team's
last game: back-to-back, one day off, two days off or more. Basketball's
and hockey's picks journal those days, and the loss veto reads them, so a
rest slice the record closes is refused on the board too.

    python3 tests/test_the_record_slices_basketball_and_hockey_by_rest.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import losspatterns as LP                # noqa: E402


def test_a_nightly_league_bands_the_days_since_its_last_game():
    assert LP.NIGHTLY_LEAGUES == frozenset({"nba", "wnba", "cbb", "nhl"})
    for sport in LP.NIGHTLY_LEAGUES:
        assert LP.rest_band(1, sport) == "back-to-back", sport
        assert LP.rest_band(2, sport) == "one day off"
        assert LP.rest_band(3, sport) == LP.rest_band(7, sport) == "two days off or more"
        assert LP.rest_band(None, sport) is None and LP.rest_band(0, sport) is None, "unknown, never rested"
    assert LP.rest_band(4, "nfl") == "short week" and LP.rest_band(14, "nfl") == "off a bye", \
        "football's bands are football's, unchanged"
    assert LP.rest_band(4) == "short week", "a caller with no league reads as before"


def test_the_miner_and_the_veto_read_a_back_to_back():
    feats = LP.features_of(side="OVER", odds=-110, prob=0.56, sport="nba", rest_days=1)
    assert feats["rest"] == "back-to-back"
    assert LP.features_of(sport="nhl", rest_days=2)["rest"] == "one day off"
    store = {"closed": [{"sport": "nba", "market": "pts", "dim": "rest", "value": "back-to-back",
                         "reading": "said 58%, hit 47% over 120 bets — ran hot"}]}
    import json
    import tempfile
    path = Path(tempfile.mkdtemp()) / "losspatterns.json"
    path.write_text(json.dumps(store))
    said = LP.veto("nba", "pts", side="OVER", odds=-110, prob=0.56, rest_days=1, path=path)
    assert said and "back-to-back" in said, said
    assert LP.veto("nba", "pts", side="OVER", odds=-110, prob=0.56, rest_days=3, path=path) is None
    assert LP.veto("nba", "pts", side="OVER", odds=-110, prob=0.56, path=path) is None, \
        "an unknown rest never matches a closure"


def test_basketballs_density_says_the_days_since_the_last_game():
    import nba_build as NB
    days = {"2026-11-13": [{"home": "BOS", "away": "NYK"}], "2026-11-11": [{"home": "LAL", "away": "BOS"}]}
    assert NB.schedule_density(days, "BOS", "2026-11-14")["rest_days"] == 1
    assert NB.schedule_density(days, "LAL", "2026-11-14")["rest_days"] == 3
    assert NB.schedule_density(days, "MIA", "2026-11-14")["rest_days"] == 7, "none in the six days read"
    assert NB.schedule_density(days, "BOS", "not a date")["rest_days"] is None


def test_the_basketball_card_journals_its_rest_and_the_veto_reads_it():
    from engine.hoops import NBA
    from engine.nba.pipeline import evaluate_prop
    prop = {"player": "Guard One", "team": "BOS", "opponent": "NYK", "market": "pts",
            "line": 22.5, "over_odds": 130, "under_odds": -110, "book": "DK",
            "minutes": [32.0] * 15, "values": [23.0] * 15,
            "is_starter": True, "spread": -3.0, "is_favorite": True, "rest": "b2b_home", "rest_days": 1}
    card = evaluate_prop(prop, NBA)
    assert card["kind"] != "skip" and card["rest_days"] == 1, card
    src = (ROOT / "engine" / "nba" / "pipeline.py").read_text(encoding="utf-8")
    assert 'lead_min=_lead, rest_days=prop.get("rest_days"),' in src
    nb = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert '"rest_days": density.get(h["team"], {}).get(' in nb, "every prop carries it from the schedule"


def test_hockey_reads_its_rest_off_the_teams_last_games():
    import nhl_build as NH
    ctx = {"last10": {"2026-11-13", "2026-11-10", "2026-11-08"}}
    assert NH._rest_days(ctx, "2026-11-14") == 1
    assert NH._rest_days({"last10": {"2026-11-11"}}, "2026-11-14") == 3
    assert NH._rest_days({"last10": set(), "b2b": True}, "2026-11-14") == 1
    assert NH._rest_days({}, "2026-11-14") is None
    assert NH._rest_days({"last10": {"2026-11-14"}}, "2026-11-14") is None, "tonight's own game is not rest"
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    body = src[src.index("def price_prop("):src.index("# --- game lines")]
    assert "horizon_days=0, rest_days=rest_days," in body and '"rest_days": rest_days,' in body


def test_the_journal_writes_the_rest_a_pick_carries():
    src = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    i = src.index("def log_recommendations(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert 'r.get("rest_days")' in body, "the prop journal already writes the column; the boards now fill it"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
