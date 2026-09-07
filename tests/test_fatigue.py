"""NFL schedule fatigue — §7's open item, finally read.

The spec carried this for a long time with an unusually specific note:
*"Kickoff/rest data exists in schedules; not yet a modifier."* It really
did: nflverse ships ``home_rest``/``away_rest`` precomputed, the Eastern
kickoff on every row, and a neutral-site flag that in the NFL means an
international trip. Three circumstances come out of that — the short
week, the body clock, and the trip.

It ships as EVIDENCE, not as a price: a reason, a warning, and a
journaled number the blind-spot miner can band, slice under false-
discovery control and convict on our own record. The published effect
sizes are small and contested, which is exactly where a hand-tuned
multiplier quietly becomes a permanent guess — so the multiplier waits
for measurement, the same order the comps and the rest watch shipped in.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import fatigue, ledger
from engine import losspatterns as lp
from engine.models import Game, Weather

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _game(home="KC", away="LV", kickoff="13:00", home_rest=7, away_rest=7,
          neutral=False):
    return Game(home=home, away=away, weather=Weather(dome=False),
                date="2026-10-04", kickoff=kickoff, home_rest=home_rest,
                away_rest=away_rest, neutral_site=neutral)


# --- the body clock ----------------------------------------------------------
def test_the_feeds_eastern_kickoff_becomes_each_teams_own_clock():
    """The one place a bare 'HH:MM' is legitimate: these times are
    documented Eastern and only the hour is needed. The capture-lag and
    closing-line layers still refuse the same string, because THEY need
    an instant and this does not."""
    assert fatigue.body_clock("LV", "13:00") == 10.0      # Pacific, early window
    assert fatigue.body_clock("KC", "13:00") == 12.0      # Central
    assert fatigue.body_clock("BUF", "13:00") == 13.0     # Eastern
    assert fatigue.body_clock("DEN", "13:00") == 11.0     # Mountain
    assert fatigue.body_clock("SEA", "09:30") == 6.5      # London window
    assert fatigue.body_clock("LV", "") is None
    assert fatigue.body_clock("XXX", "13:00") is None     # unknown team


def test_a_half_hour_kickoff_reads_as_the_time_it_is():
    """`%.0f` was wrong twice over — it dropped 8.5 to '8:00' and rounded
    9.5 up to '10:00', so the London window read an hour late."""
    assert fatigue.clock_str(8.5) == "8:30"
    assert fatigue.clock_str(9.5) == "9:30"
    assert fatigue.clock_str(16.08) == "16:05"
    assert fatigue.clock_str(None) == "?"


def test_an_unusable_kickoff_says_nothing_rather_than_guessing():
    for bad in ("", None, "not a time", "99:99", "13"):
        assert fatigue._kickoff_hour(bad) is None


# --- the rest bands ----------------------------------------------------------
def test_the_rest_bands_separate_a_thursday_from_a_bye():
    assert fatigue.rest_band(4) == "short week"
    assert fatigue.rest_band(6) == "6 days or fewer"
    assert fatigue.rest_band(7) == "normal week"
    assert fatigue.rest_band(10) == "extra days"
    assert fatigue.rest_band(14) == "off a bye"
    # Zero is the feed's "not known", not a team that played yesterday.
    assert fatigue.rest_band(0) is None
    assert fatigue.rest_band(None) is None and fatigue.rest_band("x") is None


# --- the state ---------------------------------------------------------------
def test_a_short_week_is_named_on_both_sides_of_a_thursday_game():
    g = _game(home_rest=4, away_rest=4, kickoff="20:15")
    for team in ("KC", "LV"):
        st = fatigue.state_for(g, team)
        assert st["rest_band"] == "short week"
        assert any("Short week" in n for n in st["notes"])


def test_a_rest_mismatch_warns_only_the_team_that_is_behind():
    # 16:05 ET is what a Pacific HOME game actually kicks at — the league
    # never schedules a 10am local start, so this isolates rest from the
    # body clock instead of tripping both at once.
    g = _game(home="SEA", away="TB", home_rest=10, away_rest=7,
              kickoff="16:05")
    rested = fatigue.state_for(g, "SEA")
    tired = fatigue.state_for(g, "TB")
    assert any("Rest edge" in n for n in rested["notes"])
    assert not any("Rest" in w for w in rested["warnings"])
    assert any("Rest deficit" in n for n in tired["notes"])
    assert any("Rest deficit" in w for w in tired["warnings"])


def test_an_even_rest_matchup_says_nothing_about_rest():
    st = fatigue.state_for(_game(home_rest=7, away_rest=7), "KC")
    assert not any("Rest" in n for n in st["notes"])


def test_the_early_body_clock_is_flagged_for_the_travelling_west_coast_team():
    g = _game(home="IND", away="LV", kickoff="13:00")
    away = fatigue.state_for(g, "LV")
    home = fatigue.state_for(g, "IND")
    assert away["body_clock"] == 10.0
    assert any("Body clock" in n for n in away["notes"])
    assert any("Early body clock" in w for w in away["warnings"])
    assert not home["warnings"], "an Eastern team at 13:00 ET is a normal spot"


def test_an_international_game_names_the_trip():
    st = fatigue.state_for(_game(kickoff="09:30", neutral=True), "KC")
    assert st["neutral_site"] is True
    assert any("Neutral site" in n for n in st["notes"])


def test_a_slate_with_no_schedule_rows_invents_nothing():
    """Rest defaults to 0 on a Game built without a schedule. That must
    read as 'not known', never as a normal week."""
    g = Game(home="KC", away="LV", weather=Weather(), kickoff="")
    assert fatigue.state_for(g, "KC") == {}
    # With a usable kickoff but no rest, the clock still reports and the
    # rest band stays silent.
    g2 = Game(home="KC", away="LV", weather=Weather(), kickoff="13:00")
    st = fatigue.state_for(g2, "KC")
    assert st["rest_band"] is None and st["rest_days"] is None
    assert st["body_clock"] == 12.0


# --- the decorator -----------------------------------------------------------
def test_the_board_carries_each_props_own_team_state():
    g = _game(home="IND", away="LV", kickoff="13:00", home_rest=7, away_rest=4)
    recs = [{"team": "LV", "reasons": [], "warnings": []},
            {"team": "IND", "reasons": [], "warnings": []}]
    out = fatigue.decorate(recs, [g])
    assert out["decorated"] == 2
    raiders, colts = recs
    assert raiders["rest_days"] == 4 and raiders["body_clock"] == 10.0
    assert raiders["rest_band"] == "short week"
    assert any("Short week" in r for r in raiders["reasons"])
    assert colts["rest_days"] == 7 and colts["body_clock"] == 13.0
    assert not colts["warnings"]


def test_fatigue_never_touches_a_price():
    """Evidence, not a modifier — the whole point of shipping it this way.

    Behavioural rather than a grep: the module's own docstring discusses
    the multiplier it deliberately does NOT apply, so searching the text
    for the word proves nothing. What matters is that a decorated card
    comes back priced exactly as it went in.
    """
    priced = {"team": "LV", "reasons": [], "warnings": [], "hit_prob": 0.56,
              "stake_units": 1.0, "recommended": True, "grade": "A",
              "edge": 0.04, "projection": 61.2}
    before = {k: priced[k] for k in
              ("hit_prob", "stake_units", "recommended", "grade", "edge",
               "projection")}
    fatigue.decorate([priced], [_game(home="IND", away="LV",
                                      kickoff="13:00", away_rest=4)])
    assert priced["reasons"], "it should still have said something"
    for k, v in before.items():
        assert priced[k] == v, f"fatigue moved {k}"


def test_the_nfl_board_ships_the_fatigue_block():
    from engine.pipeline import run_slate
    out = run_slate(os.path.join(ROOT, "data", "sample_slate.json"))
    assert "fatigue" in out and out["fatigue"]["decorated"] > 0


# --- the ladder: journal, mine, veto -----------------------------------------
def test_a_journaled_bet_carries_its_rest_and_body_clock():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    ledger.log_recommendations(conn, {
        "sport": "nfl", "date": "2099-01-01",
        "recommendations": [{
            "player": "Tired Back", "market": "rush_yds", "side": "OVER",
            "line": 60.5, "odds": -110, "grade": "A", "stake_units": 1.0,
            "hit_prob": 0.56, "edge": 0.04, "confidence": 8.0,
            "recommended": True, "team": "LV", "opponent": "IND",
            "rest_days": 4, "body_clock": 10.0}],
        "games": []})
    row = conn.execute("SELECT rest_days, body_clock FROM bets").fetchone()
    assert (row[0], row[1]) == (4, 10.0)


def test_the_miner_reads_the_schedule_off_the_journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds,"
        " hit_prob, stake_units, status, category, rest_days, body_clock)"
        " VALUES ('t','nfl','2026-10-04','X','rush_yds','OVER',60.5,-110,"
        "0.56,1.0,'lost','main',4,10.0)")
    conn.commit()
    feats = lp.records_from_ledger(conn)[0]["feats"]
    assert feats["rest"] == "short week"
    assert feats["clock"] == "body clock 10am or earlier"


def test_a_convicted_short_week_pocket_vetoes_the_next_matching_pick():
    import json as _json
    path = tempfile.mktemp(suffix=".json")
    open(path, "w").write(_json.dumps({"findings": [], "closed": [
        {"sport": "nfl", "market": "rush_yds", "dim": "rest",
         "value": "short week", "reading": "ran hot"}]}))
    hit = lp.veto("nfl", "rush_yds", side="OVER", odds=-110, rest_days=4,
                  path=path)
    assert hit and "short week" in hit
    # A normal week is a different, unconvicted band; an unknown rest is
    # never falsely blocked.
    assert lp.veto("nfl", "rush_yds", side="OVER", odds=-110, rest_days=7,
                   path=path) is None
    assert lp.veto("nfl", "rush_yds", side="OVER", odds=-110,
                   path=path) is None


def test_the_miner_can_convict_a_short_week_pocket():
    recs = []
    for i in range(120):        # short-week overs: said 60%, hit 40%
        recs.append({"sport": "nfl", "market": "rush_yds", "prob": 0.60,
                     "won": 1 if i < 48 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, rest_days=4)})
    for i in range(120):        # normal weeks: calibrated
        recs.append({"sport": "nfl", "market": "rush_yds", "prob": 0.60,
                     "won": 1 if i < 72 else 0,
                     "feats": lp.features_of(side="OVER", odds=-110,
                                             prob=0.60, rest_days=7)})
    out = lp.mine(recs)
    rests = [f for f in out["findings"] if f["dim"] == "rest"]
    assert any(f["value"] == "short week" for f in rests), out["findings"]


def test_the_nfl_gate_hands_the_veto_its_schedule():
    src = open(os.path.join(ROOT, "engine", "betting.py"),
               encoding="utf-8").read()
    i = src.index("pattern_block = lp_veto(")
    assert "_fatigue_state" in src[max(0, i - 500):i]
    assert "rest_days=_rest_days" in src[i:i + 800]


def test_the_lab_can_propose_on_rest_and_the_clock():
    from engine import hypotheses as hyp
    props = hyp.SCHEMA["properties"]["hypotheses"]["items"]
    for dim in ("rest", "clock"):
        assert dim in hyp.DIMS
        assert dim in props["properties"] and dim in props["required"]


def test_the_schedule_feed_carries_rest_onto_the_game():
    src = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"),
               encoding="utf-8").read()
    assert "home_rest=" in src and "away_rest=" in src
    assert "neutral_site=" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
