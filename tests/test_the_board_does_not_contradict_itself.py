"""The cross-board contradiction reader (engine/contradictions) and the NHL
no-picks diagnostic (engine/nhlcheck), on fixtures — no box, no network.

Ethan, 2026-10-06: "I feel like we have a lot of contradictions in our
picks and the data and what we are saying… Also hockey (nhl) has not had
any most likely pick or edge picks."
"""
import datetime as dt

from engine import contradictions as C
from engine import nhlcheck

NOW = dt.datetime(2026, 10, 11, 12, 0, tzinfo=dt.timezone.utc)
LATER = "2026-10-11T17:00:00Z"


def _edge(player, market, side, line, p, proj=None, **kw):
    return dict(player=player, market=market, side=side, line=line, hit_prob=p, projection=proj,
                recommended=True, kickoff=LATER, **kw)


def _clean():
    return {
        "recommendations": [_edge("A. Back", "rush_yds", "OVER", 60.5, 0.62, 71.0)],
        "most_likely": [dict(player="A. Back", market="rush_yds", side="OVER", line=60.5, model_prob=0.63,
                             projection=71.0, kickoff=LATER, bold_why=["DAL gives up the 3rd-most rushing yards"])],
        "likely_board": {"rows": [dict(player="A. Back", market="rush_yds", side="over", line=60.5,
                                       model_prob=0.62, case_lines=["Soft matchup for backs"])]},
        "game_plans": [{"steps": [
            {"key": "fits", "rows": [dict(player="A. Back", market="rush_yds", side="OVER", line=60.5,
                                          model_prob=0.62, why=["Script: favored in a shootout — everyone eats.",
                                                                "Against it — the script: leads late."])]},
            {"key": "avoid", "rows": [dict(player="B. Wide", market="rec_yds", side="OVER", why="Chasing")]}]}],
        "scan_reads": {"NYG@DAL": {"players": [dict(player="A. Back", read="good", label="Could shine",
                                                    lean=["rush_yds", "rush_att", "anytime_td"])]}},
    }


def test_a_board_that_agrees_with_itself_reads_clean():
    assert C.scan(_clean(), now=NOW) == []


def test_an_over_and_an_under_on_one_window_is_not_a_contradiction():
    d = _clean()
    d["most_likely"].append(dict(player="A. Back", market="rush_yds", side="UNDER", line=89.5,
                                 model_prob=0.7, projection=71.0))
    assert [f for f in C.scan(d, now=NOW) if f["kind"] == "BOTH WAYS"] == []


def test_the_contradictions_a_reader_would_catch_are_named():
    d = _clean()
    # The one board says under the same line Edge says over, at another chance.
    d["likely_board"]["rows"].append(dict(player="A. Back", market="rush_yds", side="under", line=60.5,
                                          model_prob=0.55, case_lines=["Tough matchup for backs"]))
    # Most Likely posts the over the plan lists to avoid.
    d["most_likely"].append(dict(player="B. Wide", market="rec_yds", side="OVER", line=50.5,
                                 model_prob=0.58, projection=44.0, kickoff=LATER))
    # A pick under even, and one on a man ruled out.
    d["recommendations"].append(_edge("C. End", "receptions", "OVER", 3.5, 0.47, 3.9))
    d["recommendations"].append(_edge("D. Hurt", "receptions", "OVER", 2.5, 0.6, 3.1, injury_status="Out"))
    # Most Likely's chance for A. Back's over drifts from Edge's.
    d["most_likely"][0]["model_prob"] = 0.71
    kinds = {f["kind"] for f in C.scan(d, now=NOW)}
    assert {"BOTH WAYS", "TWO NUMBERS", "AVOID vs PICK", "PROJECTION", "UNDER 50%",
            "NOT PLAYING", "READ vs PICK"} <= kinds
    # The under's own reason argues for it, so no REASON AGAINST from it.
    assert not any(f["kind"] == "REASON AGAINST" for f in C.scan(d, now=NOW))


def test_a_plus_money_edge_under_even_is_a_value_bet_not_a_contradiction():
    d = _clean()
    d["recommendations"].append(_edge("C. End", "receptions", "OVER", 4.5, 0.46, 4.8, odds=140))
    assert not any(f["kind"] == "UNDER 50%" for f in C.scan(d, now=NOW))


def test_a_reason_that_argues_the_other_way_is_caught():
    d = _clean()
    d["likely_board"]["rows"][0]["case_lines"].append("DAL gives up the 2nd-fewest rushing yards")
    d["game_plans"][0]["steps"][0]["rows"][0]["why"].append("Script: expected to trail and throw.")
    got = [f["text"] for f in C.scan(d, now=NOW) if f["kind"] == "REASON AGAINST"]
    assert any("2nd-fewest" in t for t in got) and any("trail and throw" in t for t in got)


def test_a_started_game_still_on_the_board_is_caught():
    d = _clean()
    d["recommendations"][0]["kickoff"] = "2026-10-11T11:00:00Z"
    assert any(f["kind"] == "STARTED" for f in C.scan(d, now=NOW))


def test_the_text_reader_only_reads_what_it_knows():
    assert C.text_sign("Against it — the script: leads late and runs the clock.", "receptions") == 0
    assert C.text_sign("He has a nice haircut", "receptions") == 0
    assert C.text_sign("Script: leads late and runs the clock — run volume up", "rush_yds") == 1
    assert C.text_sign("Script: leads late and runs the clock — run volume up", "receptions") == -1
    assert C.text_sign("Only 31% of the games went over", "rec_yds") == -1


def test_the_report_counts_by_kind():
    found = [{"kind": "UNDER 50%", "player": "X", "text": "t1"}, {"kind": "UNDER 50%", "player": "Y", "text": "t2"}]
    out = C.report(found)
    assert out[0].startswith("2 contradiction(s)") and "UNDER 50%  (2)" in out
    assert C.report([]) == ["No contradictions found."]


# ─── hockey ────────────────────────────────────────────────────────────────

def _nhl(**kw):
    return dict({"date": "2026-10-06", "status": "no games today", "games": [], "recommendations": [],
                 "most_likely": []}, **kw)


def test_preseason_says_no_picks_are_expected():
    out = nhlcheck.verdict(_nhl(), [{"type": 1}, {"type": 1}], 50000, ["nhl:shots"])
    assert out[-1].startswith("NO PICKS EXPECTED — preseason only")


def test_games_today_and_none_on_the_board_is_a_stale_board():
    out = nhlcheck.verdict(_nhl(), [{"type": 2}], 50000, ["nhl:shots"])
    assert "stale" in out[-1]


def test_no_history_and_no_rank_and_no_prices_each_named():
    assert "ingest.py nhl" in nhlcheck.verdict(_nhl(), [{"type": 2}], 0, [])[-1]
    board = _nhl(status="slate", games=[{"home": "BOS", "away": "TOR"}],
                 recommendations=[{"player": "X", "recommended": False, "odds": None}])
    out = nhlcheck.verdict(board, [{"type": 2}], 50000, ["nfl:rush_yds"])
    assert any("no prices" in ln for ln in out) and any("rankfit measure nhl" in ln for ln in out)


def test_every_priced_prop_refused_shows_the_census():
    board = _nhl(status="slate", games=[{"home": "BOS", "away": "TOR"}],
                 recommendations=[{"player": "X", "recommended": False, "odds": -120}],
                 gate_census={"edge under the floor": 9, "goalie unconfirmed": 2})
    out = nhlcheck.verdict(board, [{"type": 2}], 50000, ["nhl:shots"])
    assert any("edge under the floor ×9" in ln for ln in out)


def test_an_unreadable_schedule_stops_there():
    assert nhlcheck.verdict(_nhl(), None, 0, [])[-1].startswith("STOP — the NHL schedule")


# ─── one bet, one chance on the game plan ──────────────────────────────────

def test_a_play_that_fits_shows_the_boards_chance_and_only_its_own_lines_tier():
    from engine import gameplan as P
    g = {"home": "BUF", "away": "LAC"}
    play = {"kind": "prop", "player": "K. Shakir", "team": "BUF", "opponent": "LAC", "market": "receptions",
            "side": "OVER", "line": 3.5, "odds": -150, "book": "DraftKings", "model_prob": 0.61}
    same = {"player": "K. Shakir", "market": "receptions", "side": "OVER", "line": 3.5, "game": "LAC@BUF",
            "tier": "strong", "tier_label": "Strong", "model_prob": 0.57}
    row = P.fits(g, {"td": [], "props": [play]}, [], [same])[0]
    assert row["model_prob"] == 0.57 and row["tier"] == "strong", "the board's number beside the board's tier"
    other = dict(same, line=4.5, model_prob=0.52)
    row = P.fits(g, {"td": [], "props": [play]}, [], [other])[0]
    assert row["model_prob"] == 0.61 and not row["on_board"], "another line's tier is not this play's"
    # Pulled under the bar by the board, it is not shown as a fit at all.
    assert P.fits(g, {"td": [], "props": [play]}, [], [dict(same, model_prob=0.53)]) == []
