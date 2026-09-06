"""College player production, off a feed that lies in three specific ways.

`engine.cfb.tds` refuses to price a quoted player with no ingested
usage. On 2026-08-27 the database held TEN college player rows against
3,132 ingested games, so the college touchdown board could name nobody
and would have shipped empty on the first Saturday of the season.
`engine.sources.cfbstats` reads play-level production off the
sportsdataverse mirror — one request a season, 197,904 rows for 2024.

Every test below exists because reading that file naively produces a
number that looks right and is not:

  * the passer and the receiver are not reliably in their own columns,
    and ``touchdown_player`` names whichever of them the parser felt
    like that week;
  * the intended receiver is missing from 79% of incompletions, so a
    "targets" column would undercount every receiver in the country;
  * weeks 10-16 of the 2025 file have no scoring plays at all, which
    reads as a season where nobody scored after October.

Run directly: `python3 tests/test_cfbstats.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import cfbstats as C

#: NOTE THE ZERO. `points` is what the coverage audit weighs a week's
#: touchdowns against, and a two-play fixture with a real final score
#: would fail it every time — correctly, since two plays do not contain
#: a Saturday's scoring. A game with no stored score is not judged, so
#: the unit tests below can be two plays long. The audit gets its own
#: section, with real scores.
GAMES = {
    "401": {"period": "2024-09-14", "home": "UGA", "away": "OSU",
            "home_name": "Georgia", "away_name": "Ohio State", "points": 0},
}


def _play(**kw):
    row = {"game_id": "401", "season": "2024", "week": "3",
           "team": "Georgia", "opponent": "Ohio State",
           "yards_to_goal": "40", "down": "1", "distance": "10"}
    row.update(kw)
    return row


def _parse(rows, games=None, roster=None):
    return C.parse_player_stats(rows, 2024, games or GAMES, roster)


def _value(out, player, market):
    for row in out["rows"]:
        if row["player"] == player and row["market"] == market:
            return row["value"]
    return None


# --- the join ---------------------------------------------------------
def test_a_school_resolves_to_the_key_its_own_game_used():
    out = _parse([_play(rush_player="Nate Frazier", rush_yds="8")])
    row = next(r for r in out["rows"] if r["market"] == "carries")
    assert row["team"] == "UGA" and row["opponent"] == "OSU"
    assert row["home"] == 1 and row["period"] == "2024-09-14"


def test_the_away_school_is_keyed_and_flagged_away():
    out = _parse([_play(team="Ohio State", opponent="Georgia",
                        rush_player="Quinshon Judkins", rush_yds="5")])
    row = next(r for r in out["rows"] if r["market"] == "carries")
    assert (row["team"], row["opponent"], row["home"]) == ("OSU", "UGA", 0)


def test_a_game_we_never_ingested_is_skipped_not_guessed():
    out = _parse([_play(game_id="999", rush_player="Somebody")])
    assert out["rows"] == []
    assert out["skipped"]["game not ingested"] == 1


def test_a_school_that_was_not_in_this_game_is_skipped():
    out = _parse([_play(team="Alabama", rush_player="Jam Miller")])
    assert out["rows"] == []
    assert out["skipped"]["team not in this game"] == 1


# --- who threw it, who caught it --------------------------------------
def test_a_plain_completion_reads_the_columns_as_written():
    rows = [_play(incompletion_player="Carson Beck"),
            _play(completion_player="Carson Beck", completion_yds="18",
                  reception_player="Arian Smith", reception_yds="18")]
    out = _parse(rows)
    assert _value(out, "Arian Smith", "receptions") == 1
    assert _value(out, "Arian Smith", "rec_yds") == 18
    assert _value(out, "Carson Beck", "pass_yds") == 18
    assert _value(out, "Carson Beck", "receptions") is None


def test_the_swapped_columns_are_unswapped_by_the_qb_evidence():
    """The 2024 file puts the receiver in `completion_player` on 898 of
    53,472 completions. Nothing in the row says so — only the fact that
    the other name is the one taking the sacks."""
    rows = [_play(sack_taken_player="Carson Beck"),
            _play(completion_player="Arian Smith", completion_yds="30",
                  reception_player="Carson Beck", reception_yds="30")]
    out = _parse(rows)
    assert _value(out, "Arian Smith", "receptions") == 1
    assert _value(out, "Carson Beck", "pass_yds") == 30
    assert _value(out, "Carson Beck", "receptions") is None


def test_touchdown_player_never_decides_who_caught_it():
    """Alabama's file names the QUARTERBACK on 16 of 17 touchdown
    passes; Miami's names the receiver. A parser that trusted the column
    gave Cam Ward 35 receiving touchdowns."""
    qb = [_play(interception_thrown_player="Carson Beck") for _ in range(3)]
    scoring = _play(yards_to_goal="12",
                    completion_player="Carson Beck", completion_yds="12",
                    reception_player="Arian Smith", reception_yds="12",
                    touchdown_player="Carson Beck")
    out = _parse(qb + [scoring])
    assert _value(out, "Arian Smith", "rec_td") == 1
    assert _value(out, "Arian Smith", "anytime_td") == 1
    assert _value(out, "Carson Beck", "pass_td") == 1
    # A passing touchdown is not an ANYTIME touchdown. That is the whole
    # market, and the first cut of this parser got it backwards.
    assert _value(out, "Carson Beck", "anytime_td") == 0


def test_the_same_play_scores_the_same_way_with_the_names_reversed():
    qb = [_play(incompletion_player="Carson Beck") for _ in range(3)]
    scoring = _play(yards_to_goal="12",
                    completion_player="Arian Smith", completion_yds="12",
                    reception_player="Carson Beck", reception_yds="12",
                    touchdown_player="Arian Smith")
    out = _parse(qb + [scoring])
    assert _value(out, "Arian Smith", "rec_td") == 1
    assert _value(out, "Carson Beck", "pass_td") == 1


def test_a_tie_on_quarterback_evidence_falls_back_to_the_columns():
    out = _parse([_play(completion_player="A Passer", completion_yds="9",
                        reception_player="B Catcher", reception_yds="9")])
    assert _value(out, "B Catcher", "receptions") == 1
    assert _value(out, "A Passer", "pass_yds") == 9


def test_split_pass_is_decided_by_the_score_not_the_order():
    assert C.split_pass({"QB": 5}, "WR", "QB") == ("QB", "WR")
    assert C.split_pass({"QB": 5}, "QB", "WR") == ("QB", "WR")
    assert C.split_pass({}, "First", "Second") == ("First", "Second")


# --- rushing ----------------------------------------------------------
def test_a_rushing_touchdown_is_credited_to_the_ball_carrier():
    out = _parse([_play(yards_to_goal="3", rush_player="Nate Frazier",
                        rush_yds="3", touchdown_player="Nate Frazier")])
    assert _value(out, "Nate Frazier", "rush_td") == 1
    assert _value(out, "Nate Frazier", "anytime_td") == 1


def test_a_rushing_play_whose_scorer_is_somebody_else_credits_nobody():
    """A lateral, or a fumble returned. Compared rather than assumed, so
    a feed change lands the touchdown on nobody instead of the wrong
    player."""
    out = _parse([_play(yards_to_goal="3", rush_player="Nate Frazier",
                        rush_yds="3", touchdown_player="Someone Else")])
    assert _value(out, "Nate Frazier", "rush_td") is None   # zero, unwritten
    assert _value(out, "Nate Frazier", "anytime_td") == 0


# --- the red-zone cuts ------------------------------------------------
def test_red_zone_and_inside_five_use_the_same_cuts_as_the_nfl():
    rows = [_play(yards_to_goal="21", rush_player="RB", rush_yds="1"),
            _play(yards_to_goal="20", rush_player="RB", rush_yds="1"),
            _play(yards_to_goal="5", rush_player="RB", rush_yds="1")]
    out = _parse(rows)
    assert _value(out, "RB", "carries") == 3
    assert _value(out, "RB", "rz_car") == 2      # inside-20, i5 included
    assert _value(out, "RB", "i5_car") == 1


def test_a_red_zone_reception_lands_in_rz_rec_not_rz_tgt():
    """The name is deliberate: this feed cannot see a red-zone look that
    fell incomplete, so the quantity is not the NFL's ``rz_tgt`` and
    must not borrow its name."""
    rows = [_play(incompletion_player="QB"),
            _play(yards_to_goal="8", completion_player="QB",
                  completion_yds="8", reception_player="TE",
                  reception_yds="8")]
    out = _parse(rows)
    assert _value(out, "TE", "rz_rec") == 1
    assert "rz_tgt" not in C.MARKETS
    assert not any(r["market"] == "rz_tgt" for r in out["rows"])


def test_targets_are_not_invented_from_a_feed_that_cannot_see_them():
    assert "targets" not in C.MARKETS
    out = _parse([_play(incompletion_player="QB", target_player="WR",
                        target_stat="1")])
    assert not any(r["market"] == "targets" for r in out["rows"])


def test_a_play_with_no_field_position_still_counts_as_a_carry():
    out = _parse([_play(yards_to_goal="NA", rush_player="RB", rush_yds="4")])
    assert _value(out, "RB", "carries") == 1
    assert _value(out, "RB", "rz_car") is None


# --- what gets written ------------------------------------------------
def test_every_player_who_touched_the_ball_gets_an_anytime_td_row():
    """Including a zero. A walk-forward that only ever sees scorers has
    no negative cases and measures nothing."""
    out = _parse([_play(rush_player="RB", rush_yds="4")])
    assert _value(out, "RB", "anytime_td") == 0


def test_empty_markets_are_not_written():
    out = _parse([_play(rush_player="RB", rush_yds="4")])
    markets = {r["market"] for r in out["rows"]}
    assert markets == {"anytime_td", "carries", "rush_yds"}


# --- the roster join --------------------------------------------------
def _roster_rows():
    return [{"athlete_id": "1", "first_name": "Tetairoa",
             "last_name": "McMillan", "position": "wr",
             "headshot_url": "https://example/1.png"}]


def test_the_roster_supplies_position_name_and_face():
    roster = C.parse_rosters(_roster_rows())
    out = _parse([_play(rush_player="Tetairoa Mcmillan", rush_player_id="1",
                        rush_yds="6")], roster=roster)
    row = next(r for r in out["rows"] if r["market"] == "carries")
    assert row["player"] == "Tetairoa McMillan"      # not "Mcmillan"
    assert row["position"] == "WR"
    asset = out["assets"][0]
    assert asset["espn_id"] == "1"
    assert asset["headshot"].endswith("/1.png")
    assert asset["sport"] == "cfb"


def test_without_a_roster_the_feeds_own_spelling_stands():
    out = _parse([_play(rush_player="Tetairoa Mcmillan", rush_player_id="1",
                        rush_yds="6")])
    row = next(r for r in out["rows"] if r["market"] == "carries")
    assert row["player"] == "Tetairoa Mcmillan"
    assert row["position"] == ""


# --- the coverage audit -----------------------------------------------
def _week(week, games, scorers, name_them=True):
    """A week of `games` games, `scorers` of them producing touchdowns.

    ``name_them`` decides whether the feed puts a name on the scoring
    plays. Week 9 of 2025 is the case where it does not: the plays are
    all there and nobody is credited with any of them.
    """
    rows, table = [], {}
    for i in range(games):
        gid = f"{week}-{i}"
        table[gid] = {"period": f"2025-1{week}-01", "home": "H", "away": "A",
                      "home_name": "Home", "away_name": "Away", "points": 56,
                      "home_points": 56, "away_points": 0}
        rows.append({"game_id": gid, "season": "2025", "week": str(week),
                     "team": "Home", "opponent": "Away",
                     "yards_to_goal": "40", "rush_player": f"RB{i}",
                     "rush_yds": "9"})
        if i < scorers:
            for _n in range(8):
                row = {"game_id": gid, "season": "2025", "week": str(week),
                       "team": "Home", "opponent": "Away",
                       "yards_to_goal": "3", "rush_player": f"RB{i}",
                       "rush_yds": "3"}
                if name_them:
                    row["touchdown_player"] = f"RB{i}"
                rows.append(row)
    return rows, table


def test_a_week_the_feed_delivered_is_kept():
    rows, table = _week(3, games=10, scorers=10)
    out = C.parse_player_stats(rows, 2025, table)
    assert out["rows"]
    assert not any(k.startswith("week ") for k in out["skipped"])


def test_a_week_missing_its_scoring_plays_is_dropped_not_stored_as_zeros():
    """Weeks 10-16 of the 2025 file. Stored as written, every player who
    scored in the back half of last season becomes one who did not."""
    rows, table = _week(12, games=10, scorers=1)
    out = C.parse_player_stats(rows, 2025, table)
    assert out["rows"] == []
    note = next(k for k in out["skipped"] if k.startswith("week 12"))
    assert "dropped" in note


def test_a_week_with_the_plays_but_no_names_is_read_off_the_field():
    """Week 9 of 2025. The scoring plays are all present and the feed
    names nobody on any of them; the geometry — a gain of exactly the
    distance to the goal line — finds every one."""
    rows, table = _week(9, games=10, scorers=10, name_them=False)
    out = C.parse_player_stats(rows, 2025, table)
    scored = [r for r in out["rows"]
              if r["market"] == "anytime_td" and r["value"] > 0]
    assert len(scored) == 10
    note = next(k for k in out["skipped"] if k.startswith("week 9"))
    assert "field position" in note


def test_names_beat_the_field_where_names_exist():
    """The attribution column is the better instrument — measured
    against the final scores it over-credits one team-game a season
    where the geometry over-credits nine to thirteen. So a week that
    clears the bar on names is read on names, and a play the geometry
    would have called is not added on top."""
    rows, table = _week(3, games=10, scorers=10)
    for row in rows:                       # a gain that reaches the line…
        if row.get("touchdown_player"):
            row["touchdown_player"] = ""   # …but nobody named on THIS one
            break
    out = C.parse_player_stats(rows, 2025, table)
    total = sum(r["value"] for r in out["rows"] if r["market"] == "anytime_td")
    assert total == 10 * 8 - 1


def test_a_game_crediting_more_touchdowns_than_its_score_is_dropped():
    rows, table = _week(3, games=10, scorers=10)
    table["3-0"]["home_points"] = 14        # eight touchdowns, fourteen points
    out = C.parse_player_stats(rows, 2025, table)
    assert not any(r["game_id"] == "3-0" for r in out["rows"])
    assert any(k.startswith("game 3-0") for k in out["skipped"])


def test_one_impossible_game_does_not_delete_its_whole_week():
    """An earlier cut escalated the per-game bound to the week, so one
    mis-parsed play could take a hundred good games with it."""
    rows, table = _week(3, games=10, scorers=10)
    table["3-0"]["home_points"] = 14
    out = C.parse_player_stats(rows, 2025, table)
    kept = {r["game_id"] for r in out["rows"]}
    assert len(kept) == 9 and "3-0" not in kept


def test_a_game_with_no_final_score_is_not_judged_by_the_audit():
    rows, table = _week(3, games=10, scorers=10)
    for row in table.values():
        row["points"] = row["home_points"] = row["away_points"] = 0
    out = C.parse_player_stats(rows, 2025, table)
    assert out["rows"]


def test_the_three_modes_are_the_only_three():
    assert {C.NAMES, C.FIELD, C.DROP} == {"names", "field", "drop"}


# --- the zero that is evidence ----------------------------------------
#
# `if value or market in ALWAYS` filed a four-carry, no-gain game as
# "no rushing row", so the log that comes back out of the database is
# games in which he GAINED yards. That is survivorship landing on
# exactly the number a yardage model answers: engine.yardagefit measured
# the NFL's rushing distribution as 29% exact zeros and concluded the
# whole market misprices because a normal's negative tail stands in for
# that spike. A college log with the spike deleted cannot be asked.
def test_a_carry_for_no_gain_is_a_rushing_zero_not_a_missing_game():
    out = _parse([_play(rush_player="Nate Frazier", rush_yds="0")])
    assert _value(out, "Nate Frazier", "carries") == 1.0
    assert _value(out, "Nate Frazier", "rush_yds") == 0.0


def test_a_catch_for_no_gain_is_a_receiving_zero():
    out = _parse([_play(completion_player="Carson Beck",
                        reception_player="Arian Smith",
                        completion_yds="0", reception_yds="0")])
    assert _value(out, "Arian Smith", "receptions") == 1.0
    assert _value(out, "Arian Smith", "rec_yds") == 0.0


def test_the_zero_needs_the_opportunity_behind_it():
    """A receiver who never carried the ball writes no rushing row —
    the fix records blanks that HAPPENED, it does not invent games."""
    out = _parse([_play(completion_player="Carson Beck",
                        reception_player="Arian Smith",
                        completion_yds="14", reception_yds="14")])
    assert _value(out, "Arian Smith", "rush_yds") is None
    assert _value(out, "Arian Smith", "carries") is None


def test_the_opportunity_columns_are_named_rather_than_inferred():
    assert C.ZERO_WHEN == {"rush_yds": "carries", "rec_yds": "receptions"}


def test_the_markets_with_no_opportunity_column_are_left_alone():
    """`receptions` would need targets and this feed has none, so a
    receiver thrown at four times and catching none is ABSENT rather
    than zero. Pinned so nobody later reads a college receptions AUC as
    if it covered those player-games."""
    assert "receptions" not in C.ZERO_WHEN and "pass_yds" not in C.ZERO_WHEN


# --- the join, which failed to zero rows and said nothing ------------------
def test_the_schedule_keeps_the_mirror_numeric_id_it_no_longer_stores_under():
    """`parse_schedule` rewrites game_id to away@home so the ledger can
    look a college total up like every other sport (ab20781). Every OTHER
    file on the same mirror still keys by the numeric ESPN id, so dropping
    it there is what left this parser joining nothing."""
    from engine.sources import cfbfastr
    import json as _json

    row = {"game_id": "401628319", "season": 2024, "week": "1",
           "start_date": "2024-08-31T16:00:00.000Z",
           "home_id": "52", "away_id": "59",
           "home_team": "Florida State", "away_team": "Georgia Tech",
           "home_division": "fbs", "away_division": "fbs",
           "home_points": "21", "away_points": "24", "neutral_site": "FALSE"}
    got = cfbfastr.parse_schedule([row], 2024, {})["games"]
    assert len(got) == 1, got
    g = got[0]
    assert g["game_id"] == "espn:59@espn:52", g["game_id"]
    extra = _json.loads(g["extra"] or "{}")
    assert extra.get("espn_game_id") == "401628319", extra


def test_a_player_row_finds_its_game_by_the_numeric_id():
    """THE REGRESSION THIS PINS, and why it was invisible: a parser that
    cannot find a game just counts a skip, so the whole college player
    ingest joined ZERO rows without raising anything. Measured against
    the real 2023 mirror files at the time of the fix: 0 rows joined
    before, 117,415 of 182,694 after (the rest are FCS games the schedule
    correctly drops)."""
    from engine.sources import cfbfastr
    from engine import db, ingest

    row = {"game_id": "401628319", "season": 2024, "week": "1",
           "start_date": "2024-08-31T16:00:00.000Z",
           "home_id": "52", "away_id": "59",
           "home_team": "Florida State", "away_team": "Georgia Tech",
           "home_division": "fbs", "away_division": "fbs",
           "home_points": "21", "away_points": "24", "neutral_site": "FALSE"}
    conn = db.connect(":memory:")
    db.upsert_games(conn, cfbfastr.parse_schedule([row], 2024, {})["games"])
    games = ingest.cfb_games_for(conn, 2024)

    # The key the player-stats and closing-line files actually carry…
    assert "401628319" in games, sorted(games)
    # …and the key the row is stored under, which the ledger needs.
    assert "espn:59@espn:52" in games, sorted(games)
    # Same game, not two.
    assert games["401628319"] is games["espn:59@espn:52"]
    assert games["401628319"]["home"] == "espn:52"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
