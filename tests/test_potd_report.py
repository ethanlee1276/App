"""The funnel a person can actually run on the box.

Ethan, 2026-09-15: "I wanna make sure we access all the data we can and
all the tools we can to dish out the best picks of the day possible."

THE QUESTION NO TEST CAN ANSWER is whether a real Tuesday board carries
anything for the selector's rules to bite on. The suite proves the rules
are obeyed; `potd_report.py` is how a person finds out whether the POOL
is wrong — "68 rows considered, 61 outside the band, 0 picks" is not a
bug report, it is the name of the gate to argue with.

What is guarded here is that the tool stays honest about three things: it
never writes, it never invents a pick, and an absent board reads as an
absent board rather than as an empty day.

Run directly: `python3 tests/test_potd_report.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import potd_report as R                                       # noqa: E402
from engine import potd                                       # noqa: E402

ET = ZoneInfo("America/New_York")


def _row(**kw):
    """A board row three hours from kickoff that clears every bar."""
    t = dt.datetime.now(ET) + dt.timedelta(minutes=180)
    r = {"kind": "prop", "player": "A Player", "team": "AAA",
         "opponent": "BBB", "market": "receptions",
         "market_label": "Receptions", "side": "over", "line": 3.5,
         "book": "DraftKings", "odds": -110, "sharp_anchored": True,
         "sharp_fair": 0.60, "model_prob": 0.58, "implied_prob": 0.5238,
         "rank_auc": 0.71, "bettable": True, "injury_status": "",
         "game_date": t.strftime("%Y-%m-%d"), "kickoff": t.strftime("%H:%M")}
    r.update(kw)
    return r


def _board(rows):
    return {"built_at": "2026-09-15T12:00:00", "most_likely": rows}


def _in_tmp(files: dict):
    """A throwaway data dir. NEVER the box's own `web/data` — a test that
    reads the machine it runs on passes or fails on what happened to be
    built there this morning, which is the house rule this obeys."""
    d = tempfile.mkdtemp(prefix="potd-report-")
    for name, payload in files.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    return d


# --- it reports what the selector actually did -------------------------------
def test_the_pick_and_the_gates_both_appear():
    out = R.report(_board([_row(player="Good"), _row(odds=-400)]), "nfl")
    assert "PICK" in out and "Good" in out, out
    assert "the payout is outside the even-money band" in out, out
    assert "2 row(s) considered" in out, out


def test_a_day_with_no_pick_names_the_binding_gate_rather_than_shrugging():
    """The whole reason the tool exists. A blank day must say which bar
    it was, or the next hour is spent guessing at it."""
    out = R.report(_board([_row(sharp_fair=0.53)]), "nfl")
    assert "no pick" in out, out
    assert "not far enough off the fair" in out, out
    assert "shown, not recorded" in out, out


def test_an_empty_board_says_the_pool_was_empty_not_that_the_day_was_quiet():
    out = R.report(_board([]), "nfl")
    assert "no Most Likely rows at all" in out, out
    assert "PICK" not in out, out


def test_a_board_it_cannot_read_says_so_and_does_not_pretend():
    out = R.report({"_error": "JSONDecodeError: line 1"}, "nfl")
    assert "could not read the board" in out, out
    assert "JSONDecodeError" in out, out


def test_the_near_misses_carry_the_reason_each_one_missed_by():
    rows = [_row(player="Thin", sharp_fair=0.53),
            _row(player="Flip", rank_auc=0.49),
            _row(player="Ours", sharp_anchored=False, sharp_fair=None,
                 model_prob=0.70)]
    out = R.report(_board(rows), "nfl", rows_shown=5)
    for who, why in (("Thin", "not far enough off the fair"),
                     ("Flip", "ranks no better than a coin flip"),
                     ("Ours", "only our own model disputes this price")):
        assert who in out and why in out, (who, out)


def test_a_reserve_candidate_is_labelled_where_it_is_printed():
    """It can be the pick now (engine/potd.shortfall), so a reader of
    this tool has to be able to see that that is what happened."""
    out = R.report(_board([_row(reserve=True, sharp_fair=0.62, odds=100)]), "nfl")
    assert "[reserve]" in out, out


def test_the_line_names_the_witness_and_never_only_a_number():
    """"60%" means a different thing from a sharp book than from us, and
    a report that prints the number alone is the failure this whole
    rebuild was about."""
    out = R.report(_board([_row()]), "nfl")
    assert "sharp fair" in out, out
    out2 = R.report(_board([_row(sharp_anchored=False, sharp_fair=None,
                                 prob_source="market", implied_prob=0.56)]), "nfl")
    assert "market fair" in out2, out2


# --- what the ladder could recover, measured before it is built --------------
def _with_ladder(most_likely, recs):
    return {"built_at": "2026-09-15T12:00:00", "most_likely": most_likely,
            "recommendations": recs}


def test_a_price_refused_row_with_a_band_legal_rung_is_counted():
    """THE MEASUREMENT THAT DECIDES A BUILD. A -400 read is out of the
    band by the widest margin available, and the same book quotes the
    same player at other numbers — so the read is not unbettable, it is
    unbettable AT THAT PRICE. `likely._row_from` drops `alt_lines` from
    the rows this module sees, so the ladder never reaches the selector;
    the ladder is still in the published board on the Edge rows. This
    counts what wiring it through would recover, WITHOUT pricing
    anything, so the decision rests on a number rather than on a hunch."""
    board = _with_ladder(
        [_row(player="Heavy", market="rush_yds", odds=-400, line=24.5)],
        [{"player": "Heavy", "market": "rush_yds", "alt_lines": [
            {"book": "DraftKings", "line": 34.5,
             "over_odds": -115, "under_odds": -105}]}])
    out = R.report(board, "nfl")
    assert "Ladder" in out, out
    assert "1 of 1" in out, out
    assert "34.5 at -115" in out, "it shows the rung that was reachable"


def test_a_ladder_with_nothing_in_the_band_says_there_is_nothing_to_recover():
    """The answer that saves the work. A report that only ever said
    "there is more out there" would argue for the build either way."""
    board = _with_ladder(
        [_row(player="Deep", market="rec_yds", odds=-400, line=40.5)],
        [{"player": "Deep", "market": "rec_yds", "alt_lines": [
            {"book": "DraftKings", "line": 20.5,
             "over_odds": -600, "under_odds": 400}]}])
    out = R.report(board, "nfl")
    assert "nothing to recover here" in out, out


def test_the_ladder_line_is_absent_when_there_is_no_ladder_to_read():
    """An older board, or a sport whose pull never bought alternates,
    must not grow a line claiming zero opportunities — that reads as a
    measurement and is an absence."""
    out = R.report(_board([_row(odds=-400)]), "nfl")
    assert "Ladder" not in out, out


def test_the_ladder_count_only_looks_at_rows_refused_on_PRICE():
    """A row refused for an injury or a coin-flip market is not waiting
    on a better number, and counting it would inflate the case for a
    build that would not help it."""
    board = _with_ladder(
        [_row(player="Hurt", market="rush_yds", injury_status="questionable")],
        [{"player": "Hurt", "market": "rush_yds", "alt_lines": [
            {"book": "DraftKings", "line": 34.5,
             "over_odds": -115, "under_odds": -105}]}])
    out = R.report(board, "nfl")
    assert "Ladder" not in out, out


def test_a_spread_prints_its_number_once_here_too():
    """The same join, the same bug, this tool’s own copy. Ethan’s MLB
    card read "LAA +1.5 1.5 Spread" (2026-09-15); so did this report."""
    row = _row(player="LAA", team="LAA", market="spread",
               market_label="Spread", side="+1.5", line=1.5, odds=-113)
    line = R._one_line(row)
    assert "LAA +1.5 Spread" in line, line
    assert "1.5 1.5" not in line, line
    # A team total’s side is a word, so its line still has to be drawn.
    tt = _row(player="SEA", team="SEA", market="team_total",
              market_label="Team Total", side="over", line=4.5)
    assert "4.5" in R._one_line(tt), R._one_line(tt)


def test_the_board_says_whose_opinion_it_is_made_of():
    """Ethan’s MLB card said "only our own model disputes this price",
    and the useful question is not why that ONE row was refused — it is
    whether ANY row on the board had a sharper witness. A board that is
    all model rows is a PULL problem, and no amount of arguing with the
    selector’s bars would ever have found it."""
    all_ours = [_row(sharp_anchored=False, sharp_fair=None, model_prob=0.59)
                for _ in range(3)]
    out = R.report(_board(all_ours), "mlb")
    assert "Evidence" in out and "3 model" in out, out
    assert "NO sharp or market witness anywhere" in out, out
    assert "Check the odds pull" in out, "it must name where to look"


def test_a_board_with_a_sharp_witness_does_not_cry_wolf():
    out = R.report(_board([_row(), _row(sharp_anchored=False, sharp_fair=None,
                                        model_prob=0.6)]), "nfl")
    assert "1 sharp" in out and "1 model" in out, out
    assert "NO sharp or market witness" not in out, out


# --- and it is safe to point at the production box ---------------------------
def test_a_missing_league_is_skipped_and_a_missing_everything_explains():
    d = _in_tmp({})
    assert R.main(["nfl", "--dir", d]) == 1, "nothing found is a non-zero exit"
    d2 = _in_tmp({"nfl_picks.json": _board([_row()])})
    assert R.main(["nfl", "--dir", d2]) == 0
    # A league simply out of season is not an error beside one in season.
    assert R.main(["nfl", "wnba", "--dir", d2]) == 0


def test_the_tool_writes_nothing():
    """Read-only is the claim that lets this run on the droplet mid-cycle,
    so it is asserted rather than trusted: the data dir is byte-identical
    after a full run."""
    d = _in_tmp({"nfl_picks.json": _board([_row(), _row(odds=-400)])})
    before = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d)}
    R.main(["nfl", "--dir", d])
    after = {n: open(os.path.join(d, n), "rb").read() for n in os.listdir(d)}
    assert before == after, "the report modified the board it was reading"
    assert sorted(before) == sorted(after), "the report added or removed a file"


def test_the_header_quotes_the_band_from_the_engine_not_from_a_copy():
    """A tool printing its own idea of the band would tell a reader the
    selector is doing something it is not."""
    out = R.report(_board([_row()]), "nfl")
    assert f"{potd.MIN_ODDS:+d}" in out and f"{potd.MAX_ODDS:+d}" in out, out
    assert f"{potd.MIN_EV:.0%}" in out, out


# ── it reads the files the builds actually write ────────────────────

def test_it_looks_for_the_real_board_names_not_the_league_code():
    """THE BUG THIS EXISTS FOR, and the third instance of it in a day.
    A board’s file is not named after its league: the NFL writes
    `recommendations.json` and MLB `mlb_recommendations.json`; only cfb,
    nba and wnba match their own code. This tool looked for
    `{sport}_picks.json` and so skipped the two leagues at the top of
    SPORT_PRIORITY — and its "no board found" message only fires when
    NOTHING is found, so with college football present it reported
    happily and said nothing about the other two."""
    for sport, expect in (("nfl", "recommendations_picks.json"),
                          ("mlb", "mlb_recommendations_picks.json"),
                          ("cfb", "cfb_picks.json")):
        names = [os.path.basename(p)
                 for p in R.board_paths(sport, "web/data")]
        assert expect in names, (sport, names)


def test_the_light_copy_is_preferred_and_the_full_board_is_the_fallback():
    """The light copy is small and keeps `pick_of_the_day` whole —
    `lightboard.DROP_TOP` drops only `player_stats`. A box that has not
    written one yet still gets an answer from the full board."""
    names = [os.path.basename(p)
             for p in R.board_paths("nfl", "web/data")]
    assert names[0] == "recommendations_picks.json", names
    assert "recommendations.json" in names, names


def test_a_league_with_no_board_is_named_rather_than_skipped():
    """Skipping in silence is exactly how this tool hid two leagues from
    its own reader for a day."""
    import contextlib
    import io
    d = _in_tmp({"wnba_picks.json": _board([_row()])})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R.main(["nfl", "cfb", "wnba", "--dir", d])
    out = buf.getvalue()
    assert "No board on disk for" in out, out
    assert "nfl" in out and "cfb" in out, out


# ── the cross-league layer ──────────────────────────────────────────

def test_the_top_report_shows_the_board_answer_beside_the_locked_one():
    """The gap between them is the point: when they differ, a league has
    moved off the pick it journaled this morning, which is ordinary and
    correct and is also the thing most likely to look like a bug."""
    card = {"player": "KC ML", "team": "KC", "market": "moneyline",
            "kind": "game", "odds": -130, "sharp_anchored": True,
            "sharp_fair": 0.60, "fair_prob": 0.60, "evidence": "sharp"}
    boards = {"nfl": {"pick_of_the_day": {"date": "2026-04-01", "pick": card}}}
    out = R.top_report(boards, "2026-04-01",
                                 {"nfl": ("KC", "moneyline", "OVER", 0.5)})
    assert "boards say" in out and "locked" in out, out
    assert "NFL KC ML" in out, out
    # CASE-INSENSITIVE, because the banner reads "THE TWO DISAGREE" and
    # the first version of this asserted lowercase — which made the
    # negative here pass for the wrong reason and the positive below
    # fail for it.
    assert "disagree" not in out.lower(), out


def test_the_top_report_shouts_when_the_two_disagree():
    card = {"player": "KC ML", "team": "KC", "market": "moneyline",
            "kind": "game", "odds": -130, "sharp_anchored": True,
            "sharp_fair": 0.60, "fair_prob": 0.60, "evidence": "sharp"}
    boards = {"nfl": {"pick_of_the_day": {"date": "2026-04-01", "pick": card}}}
    out = R.top_report(boards, "2026-04-01",
                       {"nfl": ("BUF", "moneyline", "OVER", 0.5)})
    assert "disagree" in out.lower(), out


def test_no_journal_and_an_empty_journal_read_differently():
    """None is "this box has no journal to ask"; {} is "asked, nothing
    locked". The second is a real answer about the day, the first is a
    missing tool, and a report that conflated them would send somebody
    looking for a bug in the selector."""
    boards = {"nfl": {"pick_of_the_day": {"date": "2026-04-01", "pick": None,
                                          "note": "the board had no rows"}}}
    none_out = R.top_report(boards, "2026-04-01", None)
    empty_out = R.top_report(boards, "2026-04-01", {})
    assert "no ledger on this box" in none_out, none_out
    assert "NOTHING IS LOCKED TODAY" in empty_out, empty_out
    assert none_out != empty_out


def test_the_top_report_never_comes_back_empty():
    for boards in ({}, {"nfl": {}}, {"nfl": {"pick_of_the_day": {}}}):
        out = R.top_report(boards, "2026-04-01", {})
        assert out.strip() and "DAY TOP PICK" in out, (boards, out)


# ── why the TOP rung of the ladder is empty ─────────────────────────

def _model_row(**kw):
    """A row with no witness but our own — the state every league's board
    was in on 2026-09-15, and the only state where the exchange question
    is worth asking."""
    r = _row(sharp_anchored=False, sharp_fair=None)
    r.update(kw)
    return r


def _xboard(rows=None, **top):
    b = _board(rows if rows is not None else [_model_row()])
    b.update(top)
    return b


def test_a_dead_exchange_feed_is_named_and_not_blamed_on_the_budget():
    """Kalshi is keyless. A reader who sees an empty tier and assumes we
    ran out of API credits will go and look at the wrong thing."""
    out = R.report(_xboard(exchange_fair_error="TimeoutError: kalshi"), "mlb")
    assert "TimeoutError: kalshi" in out, out
    assert "costs no credits" in out, out


def test_the_markets_it_threw_away_are_named_with_their_reasons():
    """`exchangefair.quality` refuses a market for a stated reason — too
    wide, too thin, a last trade rather than a two-sided book. The census
    keys ARE those reasons, so the report quotes them rather than saying
    "0 priced" and stopping."""
    out = R.report(_xboard(exchange_fair_census={
        "rows": 4, "attached": 0, "usable markets": 0,
        "book 9c wide": 3, "last trade only": 2}), "mlb")
    assert "0 of 4 moneyline row(s) priced" in out, out
    assert "3 book 9c wide" in out and "2 last trade only" in out, out


def test_usable_markets_that_matched_nothing_say_it_is_a_NAME_problem():
    """The two ways to land zero are opposite jobs. Markets refused on
    quality is a venue problem and nothing to do; markets that were fine
    but matched no game is our own name matching, which is fixable."""
    out = R.report(_xboard(exchange_fair_census={
        "rows": 4, "attached": 0, "usable markets": 6}), "mlb")
    assert "name-matching problem" in out, out
    assert "not a liquidity one" in out, out


def test_a_board_of_player_props_is_told_it_can_never_reach_this_tier():
    """`exchangefair.MARKETS` is moneyline and nothing else — the venue
    lists game winners. A baseball board that is 57 total-bases rows has
    no path to the top rung, and a reader deserves to know that rather
    than hunting for a broken feed."""
    out = R.report(_xboard(exchange_fair_census={
        "rows": 0, "attached": 0, "usable markets": 6}), "mlb")
    assert "no moneyline rows on this board" in out, out
    assert "game winners and nothing else" in out, out


def test_a_board_with_no_census_at_all_says_the_hook_did_not_reach_it():
    """Distinct from "the hook ran and found nothing", which is every
    case above. This one means the build did not write it."""
    out = R.report(_xboard(), "mlb")
    assert "no exchange census" in out, out


def test_it_says_nothing_when_the_tier_actually_worked():
    """A line printed on a healthy board is a line nobody reads. The
    whole section exists to explain an absence."""
    good = _model_row(market="moneyline", exchange_fair=0.61)
    out = R.report(_xboard([good], exchange_fair_census={
        "rows": 1, "attached": 1, "usable markets": 6}), "mlb")
    assert "Exchange    " not in out, out
    assert "1 exchange" in out, out       # the tier tally still shows it


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
