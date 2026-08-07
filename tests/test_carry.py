"""The prior-season carry — the thing that gives weeks 1-3 a board at all.

Measured before it was written: on the cached 2025 season the prop board
builds 0 props in weeks 1-3 and 235 in week 4, because
``player_game_logs`` is single-season and ``build_slate`` wants three
logs. Week 1 has none, week 2 has one, week 3 has two.

Two decisions in here were made by fitting rather than by taste, and both
are pinned below because they are the kind that get "tidied" later by
someone reading only the code:

* the shrink is DELIBERATELY mild — a carried season is good evidence,
  and pulling it all the way to the positional mean cost 39% on receiving
  yards in the fit;
* the anchor is the mean of qualified players' SEASON MEANS, not the mean
  of every player-game row. Those differ by 12.6 yards at QB, and the
  shrink constant was fitted against the first one.

Run directly: `python3 tests/test_carry.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import carry, db, reset                              # noqa: E402
from engine.models import GameLog                                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _row(player, wk, value, pos="WR", team="MIA", season=2025,
         col="receiving_yards"):
    return {"season": str(season), "week": str(wk), "season_type": "REG",
            "player_display_name": player, "position": pos,
            "recent_team": team, "opponent_team": "OPP", col: str(value)}


def _sched(team, week, coach, season, opp="OPP"):
    return {"season": str(season), "week": str(week), "game_type": "REG",
            "home_team": team, "away_team": opp,
            "home_coach": coach, "away_coach": "Someone Else"}


# --- the shrink --------------------------------------------------------------
def test_the_shrink_leaves_a_full_season_almost_untouched():
    """The fit's headline. A carried season is good evidence; the constant
    that won the sweep pulls a 17-game log only 11% toward the mean."""
    assert abs(carry.shrink_weight(17) - 0.895) < 0.002
    assert carry.PRIOR_GAMES == 2.0


def test_the_shrink_bites_hardest_where_the_sample_is_thinnest():
    """n/(n+k) is the whole mechanism — six games keep less of themselves
    than seventeen do, with no separate rule for it."""
    assert carry.shrink_weight(6) < carry.shrink_weight(12) < carry.shrink_weight(17)
    assert carry.shrink_weight(0) == 0.0


def test_shrunk_mean_moves_toward_the_anchor_and_never_past_it():
    c = {"own_mean": 100.0, "anchor": 50.0, "weight": 0.9}
    assert abs(carry.shrunk_mean(c) - 95.0) < 1e-9
    # Below the anchor it must move UP, not further down.
    c2 = {"own_mean": 20.0, "anchor": 50.0, "weight": 0.9}
    assert 20.0 < carry.shrunk_mean(c2) < 50.0


def test_a_missing_anchor_leaves_the_players_own_mean_alone():
    """No positional mean is not licence to invent one."""
    assert carry.shrunk_mean({"own_mean": 77.0, "anchor": None,
                              "weight": 0.5}) == 77.0


# --- the anchor, which is a construction and not just a number ---------------
def test_the_anchor_averages_player_seasons_not_player_games():
    """The bug this pins: averaging rows lets every backup with four
    garbage-time snaps vote, and the shrink constant was fitted against
    the qualified-players construction. One starter at 100 and six
    one-game scrubs at 0 must read 100, not 14."""
    rows = [_row("Starter", w, 100.0) for w in range(1, 13)]
    for i in range(6):
        rows.append(_row(f"Scrub {i}", 1, 0.0))
    means = carry.positional_means(rows, "rec_yds")
    assert abs(means["WR"] - 100.0) < 1e-9, means


def test_a_player_under_the_floor_does_not_reach_the_anchor():
    rows = ([_row("Regular", w, 60.0) for w in range(1, 10)]
            + [_row("Cameo", w, 300.0) for w in range(1, carry.MIN_PRIOR_GAMES)])
    assert abs(carry.positional_means(rows, "rec_yds")["WR"] - 60.0) < 1e-9


def test_each_position_gets_its_own_anchor():
    rows = ([_row("Passer", w, 250.0, pos="QB", col="passing_yards")
             for w in range(1, 13)]
            + [_row("Catcher", w, 60.0, pos="WR") for w in range(1, 13)])
    assert abs(carry.positional_means(rows, "rec_yds")["WR"] - 60.0) < 1e-9
    assert abs(carry.positional_means(rows, "pass_yds")["QB"] - 250.0) < 1e-9


# --- the logs ----------------------------------------------------------------
def test_every_carried_game_is_flagged_as_carried():
    """The flag is what stops a carried week 17 being read as this
    season's week 17 — by the reset rule, and by anything else that
    compares week numbers."""
    rows = [_row("Man", w, 50.0) for w in range(1, 13)]
    logs = carry.carried_logs(rows, "Man", "rec_yds")
    assert len(logs) == 12
    assert all(g.prior for g in logs)


def test_carried_games_come_back_most_recent_first():
    rows = [_row("Man", w, float(w)) for w in (3, 1, 2)]
    assert [g.week for g in carry.carried_logs(rows, "Man", "rec_yds")] == [3, 2, 1]


def test_a_default_game_log_is_not_carried():
    """Everything already in the repo builds GameLog without this field,
    so the default decides whether the reset rule silently changes."""
    assert GameLog(week=1, opponent="X", value=1.0).prior is False


# --- the offseason reset -----------------------------------------------------
def test_the_last_team_of_the_prior_season_is_the_one_compared():
    rows = ([_row("Mover", w, 50.0, team="MIA") for w in range(1, 10)]
            + [_row("Mover", w, 50.0, team="NYJ") for w in range(10, 18)])
    assert carry.last_teams(rows)["Mover"] == "NYJ"


def test_a_team_change_over_the_offseason_is_detected():
    index = carry.build_index(
        [_row("Mover", w, 50.0, team="MIA") for w in range(1, 13)],
        {"Mover": {"team": "DEN", "position": "WR"}}, [], 2026)
    kind, detail = carry.reset_for(index, "Mover")
    assert kind == carry.TRADE
    assert "DEN" in detail and "MIA" in detail


def test_staying_put_is_not_a_reset():
    index = carry.build_index(
        [_row("Stayer", w, 50.0, team="MIA") for w in range(1, 13)],
        {"Stayer": {"team": "MIA", "position": "WR"}}, [], 2026)
    assert carry.reset_for(index, "Stayer") is None


def test_an_offseason_coach_change_reaches_every_player_on_that_team():
    sched = ([_sched("CAR", w, "Old Guy", 2025) for w in range(1, 18)]
             + [_sched("CAR", w, "New Guy", 2026) for w in range(1, 18)])
    assert carry.offseason_coach_changes(sched, 2026)["CAR"] == ("Old Guy", "New Guy")
    index = carry.build_index(
        [_row("Any Guy", w, 50.0, team="CAR") for w in range(1, 13)],
        {"Any Guy": {"team": "CAR", "position": "WR"}}, sched, 2026)
    kind, detail = carry.reset_for(index, "Any Guy")
    assert kind == carry.COACH and "New Guy" in detail


def test_a_team_missing_from_either_season_is_not_a_change():
    """A gap in the feed reported as a reset is a false detection, which
    the whole rule is written to avoid."""
    sched = [_sched("NEW", w, "Only Coach", 2026) for w in range(1, 18)]
    assert carry.offseason_coach_changes(sched, 2026) == {}


def test_a_mid_season_coach_change_carries_into_the_offseason_comparison():
    """The team's LAST coach of the old season is the incumbent, so firing
    in November and keeping the replacement is not a second change."""
    sched = ([_sched("XYZ", w, "Fired", 2025) for w in range(1, 10)]
             + [_sched("XYZ", w, "Kept", 2025) for w in range(10, 18)]
             + [_sched("XYZ", w, "Kept", 2026) for w in range(1, 18)])
    assert "XYZ" not in carry.offseason_coach_changes(sched, 2026)


def test_a_move_outranks_a_coach_change():
    """He has a new job at a new building; naming the coach of a building
    he has never worked in is the less useful of the two facts."""
    sched = ([_sched("DEN", w, "Old Guy", 2025) for w in range(1, 18)]
             + [_sched("DEN", w, "New Guy", 2026) for w in range(1, 18)])
    index = carry.build_index(
        [_row("Mover", w, 50.0, team="MIA") for w in range(1, 13)],
        {"Mover": {"team": "DEN", "position": "WR"}}, sched, 2026)
    assert carry.reset_for(index, "Mover")[0] == carry.TRADE


# --- what the reset does, and deliberately does not do -----------------------
def test_a_detected_reset_warns_and_keeps_the_sample():
    """The measured decision. Discarding an offseason mover leaves NOTHING
    to project from — he drops off the board, which is the failure this
    module exists to fix — and the fit found movers want the same k=2 as
    stayers, so there is no evidence the sample is worse."""
    assert carry.DISCARD_ON_RESET is False
    rows = [_row("Mover", w, 50.0, team="MIA") for w in range(1, 13)]
    index = carry.build_index(
        rows, {"Mover": {"team": "DEN", "position": "WR"}}, [], 2026)
    got = carry.carry_for(index, rows, "Mover", "rec_yds", {"WR": 40.0})
    assert got is not None, "the mover was discarded"
    assert got["reset"][0] == carry.TRADE
    assert got["games"] == 12


def test_the_discard_switch_actually_discards_when_flipped():
    """It is a real switch, not a decorative constant — so the decision
    can be revisited with data rather than rediscovered."""
    rows = [_row("Mover", w, 50.0, team="MIA") for w in range(1, 13)]
    index = carry.build_index(
        rows, {"Mover": {"team": "DEN", "position": "WR"}}, [], 2026)
    was = carry.DISCARD_ON_RESET
    try:
        carry.DISCARD_ON_RESET = True
        assert carry.carry_for(index, rows, "Mover", "rec_yds", {}) is None
    finally:
        carry.DISCARD_ON_RESET = was


def test_a_cameo_season_is_not_carried():
    rows = [_row("Cameo", w, 50.0) for w in range(1, carry.MIN_PRIOR_GAMES)]
    index = carry.build_index(rows, {"Cameo": {"team": "MIA",
                                               "position": "WR"}}, [], 2026)
    assert carry.carry_for(index, rows, "Cameo", "rec_yds", {}) is None


# --- the hole this opened in the reset rule ----------------------------------
def test_a_carried_game_never_survives_an_in_season_reset():
    """A carried game's week number belongs to LAST season, so without the
    guard a carried week 17 sails past a week-14 reset and becomes
    'post-reset' evidence about a job that ended a year earlier."""
    conn = db.connect(":memory:")
    logs = ([GameLog(week=w, opponent="X", value=50.0, prior=True)
             for w in (17, 16, 15)]
            + [GameLog(week=w, opponent="X", value=50.0) for w in (16, 15, 14)])

    class _P:
        player, team = "Traded Man", "PIT"

    p = _P()
    p.logs = logs

    class _S:
        props = [p]

    def _index(*_a, **_k):
        return {"moves": {"Traded Man": (14, "MIN", "PIT")},
                "roles": {}, "coaches": {}}

    was = reset.build
    try:
        reset.build = _index
        reset.apply_to_slate(_S(), conn, 2026, [])
    finally:
        reset.build = was
    assert p.logs, "the reset emptied the sample"
    assert not any(g.prior for g in p.logs), "a carried game survived a reset"
    assert len(p.logs) == 3


def test_the_reset_rule_is_unchanged_when_nothing_is_carried():
    """Every existing caller builds logs with prior=False, so the guard
    must be invisible to them."""
    conn = db.connect(":memory:")

    class _P:
        player, team = "Traded Man", "PIT"

    p = _P()
    p.logs = [GameLog(week=w, opponent="X", value=50.0) for w in range(17, 0, -1)]

    class _S:
        props = [p]

    def _index(*_a, **_k):
        return {"moves": {"Traded Man": (14, "MIN", "PIT")},
                "roles": {}, "coaches": {}}

    was = reset.build
    try:
        reset.build = _index
        rep = reset.apply_to_slate(_S(), conn, 2026, [])
    finally:
        reset.build = was
    assert [g.week for g in p.logs] == [17, 16, 15, 14]
    assert rep["reset"]["Traded Man"]["dropped"] == 13


# --- the card ----------------------------------------------------------------
def test_the_card_says_the_number_came_from_last_season():
    """A carried projection that reads like a played one is this
    feature's whole risk."""
    recs = [{"player": "Man"}]
    report = {"carried": {"Man": {"season": 2025, "games": 12,
                                  "weight": 0.857, "position": "WR",
                                  "reset": None}}}
    assert carry.decorate(recs, report) == 1
    warn = " ".join(recs[0]["warnings"])
    assert "2025" in warn and "12" in warn
    assert recs[0]["carried"]["games"] == 12


def test_the_card_also_says_he_changed_teams():
    recs = [{"player": "Mover"}]
    report = {"carried": {"Mover": {
        "season": 2025, "games": 12, "weight": 0.857, "position": "WR",
        "reset": (carry.TRADE, "joined DEN from MIA")}}}
    carry.decorate(recs, report)
    warn = " ".join(recs[0]["warnings"])
    assert "DEN" in warn and "MIA" in warn
    assert recs[0]["carried"]["reset"]["kind"] == carry.TRADE


def test_a_player_who_was_not_carried_gets_no_note():
    recs = [{"player": "Played"}]
    assert carry.decorate(recs, {"carried": {}}) == 0
    assert "warnings" not in recs[0]


# --- build_slate, with the feeds stubbed -------------------------------------
def _stub_slate(current_rows, week=1, season=2026):
    """build_slate with every feed replaced, so the carry logic is what is
    under test rather than the network."""
    from engine.sources import nflverse as nv
    from engine.models import Game, Weather

    prior = [_row("Carried Guy", w, 100.0, team="MIA") for w in range(1, 18)]
    games = [Game(home="MIA", away="BUF", weather=Weather(dome=True),
                  injuries=[], date="2026-09-09", kickoff="20:20",
                  spread=-3.0, total=44.5)]
    saved = {n: getattr(nv, n) for n in
             ("build_games", "load_weekly_stats", "roster_index",
              "load_schedules")}

    def _stats(s):
        return current_rows if s == season else prior

    nv.build_games = lambda s, w: games
    nv.load_weekly_stats = _stats
    nv.roster_index = lambda s: {
        "Carried Guy": {"team": "MIA", "position": "WR"}}
    nv.load_schedules = lambda: []
    try:
        report = {}
        slate = nv.build_slate(season, week, carry=True, report=report)
        return slate, report
    finally:
        for n, fn in saved.items():
            setattr(nv, n, fn)


def test_week_one_builds_a_board_where_it_used_to_build_nothing():
    """The measurement this whole module exists for."""
    slate, report = _stub_slate([])
    assert slate.props, "week 1 still builds nothing"
    assert report["carried_n"] == len(slate.props)
    assert all(g.prior for p in slate.props for g in p.logs)


def test_the_carry_stands_down_once_the_season_has_enough_games():
    """Three real games beat seventeen carried ones, and the carry must
    not keep topping up after the season can stand on its own."""
    current = [_row("Carried Guy", w, 10.0, team="MIA", season=2026)
               for w in range(1, 5)]
    slate, report = _stub_slate(current, week=5)
    assert report["carried_n"] == 0
    assert slate.props and not any(g.prior for g in slate.props[0].logs)


def test_current_games_are_ordered_ahead_of_carried_ones():
    """compute_form reads the list POSITIONALLY — last1, last3, last5 are
    slices, not week lookups. A carried week 17 sitting first would make
    last season's finale this week's most recent game."""
    current = [_row("Carried Guy", 1, 10.0, team="MIA", season=2026),
               _row("Carried Guy", 2, 10.0, team="MIA", season=2026)]
    slate, report = _stub_slate(current, week=3)
    assert report["carried_n"] == 1
    logs = slate.props[0].logs
    flags = [g.prior for g in logs]
    assert flags[0] is False and flags[1] is False
    assert all(flags[2:]), "carried games are not last"
    # …and the boundary is where the current season actually runs out.
    assert flags.index(True) == 2


def test_a_carried_player_keeps_a_career_anchor_from_the_right_season():
    """career_avg is read off the CURRENT season's rows, which for a
    carried player is an empty list — so compute_form would shrink him
    toward a career average of zero."""
    slate, _ = _stub_slate([])
    assert slate.props[0].career_avg > 0


# --- what it refuses to do ---------------------------------------------------
def test_the_carry_writes_nothing():
    src = open(os.path.join(ROOT, "engine", "carry.py"), encoding="utf-8").read()
    body = src.split('"""')[2]
    for forbidden in ("open(", "UPDATE ", "INSERT ", "commit("):
        assert forbidden not in body, forbidden


def test_the_fitted_constants_record_what_they_were_fitted_on():
    """These two numbers came off a sweep, not off a preference. A reader
    who cannot see that will round them to something tidier."""
    doc = " ".join((carry.__doc__ or "").split())
    assert "2024" in doc and "2025" in doc
    for measured in ("50.53", "14.96", "20.76", "196.7"):
        assert measured in doc or measured in " ".join(
            (carry.positional_means.__doc__ or "").split()), measured


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
