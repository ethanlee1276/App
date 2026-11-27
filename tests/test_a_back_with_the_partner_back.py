"""A back's touchdown chance with the backfield partner back (step AIE, 27 November 2026; engine/tdpartner).

Ethan's own Bears at Lions research split Swift's touchdowns by whether Monangai played ("Swift scored in only 2
of the 5 games both were active"). Measured on 2022-2025, held out: a back whose partner missed some of the back's
recent games and plays tonight scored 26.6% against our 30.4%, and read over the games both played 28.1%. So the
share, the red-zone touches and this season's touchdown history are read over those games.

The names and numbers in these fixtures are the test's own, not a real team's.

Offline. Run directly: `python3 tests/test_a_back_with_the_partner_back.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db, pipeline, tdpartner as T                                  # noqa: E402
from engine.models import ANYTIME_TD, RUSH_YDS, GameLog, Prop                    # noqa: E402
from engine.nflusage import red_zone_usage                                       # noqa: E402
from engine.touchdowns import RedZoneUsage                                       # noqa: E402

LEAD, MATE = "Lead Back", "Second Back"


class G:
    """A game with a lineup the way engine/teammates.stamp puts one on."""
    def __init__(self, mate_weeks, out=(), basis="snaps", mine=range(1, 9)):
        self.home, self.away = "CHI", "DET"
        self.lineup = {"CHI": {"seen": {"RB": [[LEAD, 0.6, len(mine), max(mine), list(mine)],
                                               [MATE, 0.4, len(mate_weeks), max(mate_weeks), list(mate_weeks)]]},
                               "out": list(out), "basis": basis}}


def _prop(market, vals, player=LEAD, pos="RB", prior=()):
    logs = [GameLog(week=w, opponent="DET", value=v) for w, v in vals]
    logs += [GameLog(week=w, opponent="DET", value=v, prior=True) for w, v in prior]
    return Prop(player=player, team="CHI", opponent="DET", position=pos, market=market, logs=logs,
                career_avg=0.0, vs_opponent_avg=None, lines=[])


def test_the_partner_back_after_missing_games_is_found():
    # The partner played weeks 1-4 and 8; the lead back's last six are weeks 3-8, three without the partner.
    info = T.find(_prop(ANYTIME_TD, []), G([1, 2, 3, 4, 8]), playing={LEAD, MATE})
    assert info == {"partner": MATE, "shared": [1, 2, 3, 4, 8], "missed": 3, "window": 6}, info
    assert T.words(info, LEAD) == ("Backfield partner back: Second Back missed 3 of Lead Back's last 6 games and "
                                   "plays tonight, so the chance is read over the 5 games both played "
                                   "(measured 2022-2025)")


def test_nothing_changes_unless_the_partner_is_back_tonight():
    p = _prop(ANYTIME_TD, [])
    assert T.find(p, G(range(1, 9)), {LEAD, MATE}) is None, "the partner played every game: nothing to cut"
    assert T.find(p, G([1, 2, 3, 4, 8], out=[MATE]), {LEAD, MATE}) is None, "ruled out tonight: the absence step's"
    assert T.find(p, G([1, 2, 3, 4, 8]), {LEAD}) is None, "not on tonight's slate: cut, traded or on reserve"
    assert T.find(p, G([1, 8]), {LEAD, MATE}) == {"partner": MATE, "shared": [1, 8], "missed": 5, "window": 6}
    assert T.find(p, G([8]), {LEAD, MATE}) is None, f"fewer than {T.MIN_SHARED} games both played"
    assert T.find(p, G([1, 2, 3, 4, 8], basis="cfb"), {LEAD, MATE}) is None, "college is not measured"
    assert T.find(_prop(ANYTIME_TD, [], pos="WR"), G([1, 2, 3, 4, 8]), {LEAD, MATE}) is None


def test_this_seasons_touchdowns_are_cut_and_last_seasons_stay():
    p = _prop(ANYTIME_TD, [(w, 1.0 if w in (5, 6, 7) else 0.0) for w in range(1, 9)], prior=[(17, 1.0), (16, 0.0)])
    q = T.chance_prop(p, [1, 2, 3, 4, 8])
    assert [(g.week, g.value, g.prior) for g in q.logs] == [(1, 0.0, False), (2, 0.0, False), (3, 0.0, False),
                                                             (4, 0.0, False), (8, 0.0, False), (17, 1.0, True),
                                                             (16, 0.0, True)]
    assert len(p.logs) == 10, "the prop the page shows keeps every game"


def _log(player, wk, market, value, team="CHI"):
    return {"sport": "nfl", "season": 2025, "period": f"{wk:03d}", "game_id": f"{team}-{wk:03d}", "player": player,
            "team": team, "opponent": "DET", "position": "", "home": 1, "market": market, "value": value}


def test_the_red_zone_is_read_again_over_the_games_both_played():
    conn = db.connect(":memory:")
    rows = []
    for wk in range(1, 9):
        alone = wk in (5, 6, 7)
        rows += [_log("L.Back", wk, "rz_car", 6 if alone else 3), _log("L.Back", wk, "i5_car", 2 if alone else 1),
                 _log("L.Back", wk, "rz_tgt", 1), _log("S.Back", wk, "rz_car", 0 if alone else 3),
                 _log("S.Back", wk, "rz_tgt", 0)]
    db.upsert_player_logs(conn, rows)
    rz = red_zone_usage(conn)[("l", "back", "CHI")]
    assert rz.games == 6 and rz.carries_inside_10 == 4.5, rz          # weeks 3-8: (3+3+6+6+6+3)/6
    assert sorted(rz.by_week) == list(range(1, 9)) and rz.by_week[5]["team"] == 7.0, rz.by_week[5]
    both = rz.over([1, 2, 3, 4, 8])
    assert both.games == 5 and both.carries_inside_10 == 3.0 and both.carries_inside_5 == 1.0, both
    assert both.rz_touch_share == round(4 / 7, 3), "his 3 carries and a target of the team's 7 a game"
    assert both.season_counts == rz.season_counts, "the season's counts stay whole"
    assert RedZoneUsage(measured=True).over([1, 2]) is None, "no games kept: nothing to read"


def test_the_board_reads_all_three_over_the_games_both_played():
    lead_yds = [(w, 120.0 if w in (5, 6, 7) else 60.0) for w in range(1, 9)]
    mate_yds = [(w, 50.0) for w in (1, 2, 3, 4, 8)]

    class Slate:
        props = [_prop(RUSH_YDS, lead_yds), _prop(RUSH_YDS, mate_yds, player=MATE),
                 _prop(ANYTIME_TD, [(w, 0.0) for w in range(1, 9)]), _prop(ANYTIME_TD, [], player=MATE)]
    rz = RedZoneUsage(carries_inside_10=4.5, measured=True, games=6,
                      by_week={w: {"rz_car": 6 if w in (5, 6, 7) else 3, "i5_car": 1, "rz_tgt": 1, "i10_tgt": 0,
                                   "team": 7, "implied": 24.0} for w in range(1, 9)})
    td = Slate.props[2]
    share, rz2, chance, partner = pipeline._partner_back(Slate, td, G([1, 2, 3, 4, 8]), 0.6, rz, {})
    # His yards a game: 82.5 over all eight, 60 over the five both played; the partner's 50. 60 / (60 + 50).
    assert abs(share - 60 / 110) < 1e-9, share
    assert rz2.carries_inside_10 == 3.0 and rz2.games == 5, rz2
    assert [g.week for g in chance.logs] == [1, 2, 3, 4, 8]
    assert partner["reason"].startswith("Backfield partner back: Second Back missed 3 of Lead Back's last 6"), partner
    same = pipeline._partner_back(Slate, td, G(range(1, 9)), 0.6, rz, {})
    assert same == (0.6, rz, None, None), "a partner who played throughout: the inputs as they were"


def test_the_report_says_what_the_chance_was_read_over():
    from engine import gamereport as R, gamescan as S
    from engine.touchdowns import partner_row
    cand = {"partner_back": {"partner": MATE, "shared": [1, 2, 3, 4, 8], "missed": 3, "window": 6, "reason": "x"}}
    row = partner_row(cand)
    assert row == {"partner": MATE, "games": 5, "missed": 3, "window": 6} and partner_row({}) is None
    reads = {"CHI@DET": {"players": [{"player": LEAD, "team": "CHI", "pos": "RB"}]}}
    result = {"longshot_watch": [{"player": LEAD, "model_prob": 0.41, "odds": -115, "book": "DraftKings",
                                  "partner_back": row, "reasons": ["Backfield partner back: ..."]}]}
    assert S.stamp_touchdowns(reads, result) == 1
    td = reads["CHI@DET"]["players"][0]["td"]
    assert td["partner"] == row and td["why"][0].startswith("Backfield partner back"), td
    g = {"away": "CHI", "home": "DET", "date": "2026-11-26", "kickoff": "13:00", "spread": 1.5, "total": 45.5}
    c = R.Ctx(g, {"games": [g], "scan_reads": reads}, names={"CHI": "Bears", "DET": "Lions"}, sport="nfl")
    line = R.td_chance_pairs(c, "CHI")[0][0]
    assert line.startswith("Lead Back (RB): 41% to score, at −115; Second Back is back from missing 3 of the last 6, "
                           "so this reads only the 5 games both played"), line


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
