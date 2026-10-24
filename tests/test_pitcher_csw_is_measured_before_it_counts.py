"""A starter's CSW% is read off the starts already cached, and moves a
strikeout number only once it is measured to help.

engine/mlb/statcast.py's CSW adjustment never ran: no pitcher profile ever
carried a `csw_pct`. Ethan, 2026-09-25, on the backlog that named it: "start
working on all of those". engine/mlb/csw.py computes it from the playByPlay
payloads velocity.py caches, measures the shipped formula against the
strikeout rate alone on the box's games, and stays off (SHIPPED False)
until that measurement says SHIP.
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.mlb import csw as C                                  # noqa: E402


def _pitch(code, ptype="FF"):
    return {"isPitch": True, "details": {"call": {"code": code}, "type": {"code": ptype}},
            "pitchData": {}}


def _payload(date="2026-07-01"):
    """Two starters, three batters each: pitcher 1 strikes out two."""
    plays = []
    for half, pid, outs in (("top", 1, ["strikeout", "strikeout", "field_out"]),
                            ("bottom", 2, ["single", "field_out", "strikeout"])):
        for i, ev in enumerate(outs):
            plays.append({"about": {"halfInning": half, "startTime": f"{date}T23:05:00Z",
                                    "atBatIndex": len(plays)},
                          "matchup": {"pitcher": {"id": pid}, "batter": {"id": 100 + i}},
                          "result": {"eventType": ev},
                          "playEvents": [_pitch("C"), _pitch("S"), _pitch("B"), _pitch("F")]})
    return {"allPlays": plays}


def test_csw_counts_called_strikes_and_whiffs_per_pitch():
    rows = [{"pitcher_id": 1, "called": c} for c in ["C"] * 30 + ["S"] * 20 + ["B"] * 150 + ["F"] * 50 + ["T"] * 10]
    rate, n = C.csw_rate(rows)
    assert (rate, n) == (round(50 / 260, 4), 260)
    assert C.csw_rate(rows[:100])[0] is None, "under the pitch floor it is not a number"


def test_a_game_gives_each_starter_his_line():
    got = {s["pitcher_id"]: s for s in C.starts_from_payload(_payload())}
    assert set(got) == {1, 2}
    assert (got[1]["bf"], got[1]["k"], got[1]["pitches"], got[1]["csw_hits"]) == (3, 2, 12, 6)
    assert got[1]["date"] == "2026-07-01" and got[2]["k"] == 1


def _season(tracks_csw: bool, seed=7):
    rnd = random.Random(seed)
    starts = []
    for pid in range(60):
        csw = rnd.uniform(0.24, 0.33)
        # A pitcher whose strikeouts follow his CSW, or ones whose do not.
        true_k = 0.22 * (csw / 0.28) ** 2.5 if tracks_csw else 0.22
        for g in range(20):
            bf = 25
            k = sum(1 for _ in range(bf) if rnd.random() < true_k)
            pitches = 95
            starts.append({"pitcher_id": pid, "date": f"2026-{4 + g // 5:02d}-{1 + (g % 5) * 5:02d}",
                           "pitches": pitches, "csw_hits": round(pitches * (csw + rnd.gauss(0, 0.02))),
                           "bf": bf, "k": k})
    return starts


def test_the_measurement_ships_a_signal_and_holds_noise():
    ship = C.measure(_season(True))
    assert ship["verdict"] == "SHIP" and ship["gain"] > 2 * ship["gain_se"], ship
    assert ship["slope"] > 0
    hold = C.measure(_season(False))
    assert hold["verdict"] == "HOLD", hold
    assert "SHIP needs two standard errors" in C.report(ship)
    assert C.measure([])["verdict"] == "HOLD"


def test_it_moves_nothing_until_shipped():
    assert C.SHIPPED is False, "flip only when `python3 -m engine.mlb.csw` says SHIP on the box"

    class P:
        def __init__(self, market):
            self.market, self.player, self.person_id, self.statcast = market, "X", 9, None
    props = [P("strikeouts"), P("hits")]
    real = C.recent
    C.recent = lambda pid, season, limit=C.LOOKBACK: {"csw": 0.31, "pitches": 480, "starts": 5}
    try:
        assert C.attach(props, 2026) == 1
        assert props[0].csw_recent["csw"] == 0.31 and props[0].statcast is None, "shown, not priced"
        C.SHIPPED = True
        C.attach(props, 2026)
        assert props[0].statcast.csw_pct == 0.31, "once shipped, the formula reads it"
        assert not hasattr(props[1], "csw_recent")
    finally:
        C.recent, C.SHIPPED = real, False


def test_the_pipeline_asks_only_when_shipped():
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"), encoding="utf-8").read()
    assert "from .csw import SHIPPED as _csw_on, attach as _csw_attach" in src
    assert "if _csw_on:" in src


def test_the_nfl_edge_board_says_why_yardage_is_never_checked():
    """The other half of the same backlog (2026-09-25): the NFL yardage edge
    bar stays — lowering it would stake edges the record says are not real —
    and the Edge board now says so, with the bars engine/quality ships."""
    from engine.quality import TIER_MIN_EDGE
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("const NFL_YARDAGE_NOTE = ")
    note = app[i:app.index("`;", i)]
    assert f"{TIER_MIN_EDGE[1] * 100:g}–{TIER_MIN_EDGE[2] * 100:g}% bar" in note, note
    assert "ranked on Most Likely" in note
    assert '${state.sport === "nfl" ? NFL_YARDAGE_NOTE : ""}' in app


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
