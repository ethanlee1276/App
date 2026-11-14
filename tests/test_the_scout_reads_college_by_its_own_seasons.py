"""College basketball's cards carry the scout's flags, by college's own seasons.

Ethan, 2026-11-13: every NBA tool on college. The NBA scout's fourteen flags
(engine/nba/scout) were measured on NBA games only, and college's board
carried none of them. On 2026-11-14 three game-script thresholds were
written for college BEFORE any flag was measured on its games (a projected
blowout of fifteen; fast and slow games read against the league's own usual
total at the NBA's ratios), then every flag was measured on five Division I
seasons through the board's own projection at college's tuning
(docs/CBB_LAB.md, "The scout"), by a bar written before the run:

  * WARNING on college's card: an under while a regular teammate sits, his
    first game back, a minutes drop, a minutes jump, the second of two
    straight days, a regular's return, a man barely into his season;
  * REFUSED: a starter's over in a projected blowout, an under in a
    projected shootout (the NBA's warning, not college's);
  * PRICED: a projected grind, a hot shooting run; MIXED: the swing (it
    came and went with the spread); UNMEASURED: a line far from his five.

College's graded record learns the same flags the NBA's does
(engine/likelyctx.LEARNS), each settled pick rebuilt by engine/nba/
scoutrecord with college's names, seasons and usual total — and a regular
who SAT read off this season's games, so a senior who graduated in March
never "sat" an opener.

Run directly: `python3 tests/test_the_scout_reads_college_by_its_own_seasons.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QB_MODELS_DIR"] = tempfile.mkdtemp()
os.environ.pop("QB_LIKELY_CAL", None)
os.environ.pop("QB_LIKELY_CTX", None)                   # the stores live in the sandbox above

from engine import db                                                 # noqa: E402
from engine import ledger as LG                                       # noqa: E402
from engine import likelyctx as C                                     # noqa: E402
from engine.nba import scout as S                                     # noqa: E402
from engine.nba import scoutrecord as R                               # noqa: E402

WARNINGS = ("b2b_over", "mate_out_under", "mate_back_over", "role_up_under", "role_down_over",
            "back_over", "thin")


def test_colleges_thresholds_are_the_ones_written_before_the_run():
    assert S.LEAGUE["cbb"] == {"blowout_spread": 15.0, "fast_ratio": 1.04, "slow_ratio": 0.94}
    assert S.LEAGUE["nba"] == {"blowout_spread": 10.0, "fast_total": 236.0, "slow_total": 214.0}, \
        "the NBA's are the NBA's"


def test_every_flag_has_a_college_verdict_and_only_colleges_warnings_reach_its_card():
    assert set(S.VERDICT_CBB) == set(S.FLAGS)
    assert S.card_for("cbb") == WARNINGS
    kind = lambda v: {c for c, (k, _t) in S.VERDICT_CBB.items() if k == v}   # noqa: E731
    assert kind("refused") == {"blowout_over", "fast_under"}
    assert kind("priced") == {"slow_over", "hot_hand_over"}
    assert kind("mixed") == {"boom_bust"}
    assert kind("unmeasured") == {"line_stretch_over", "line_shrink_under"}
    assert all("college seasons" in t for c, (k, t) in S.VERDICT_CBB.items() if k in ("warning", "refused")), \
        "each college sentence says whose seasons measured it"
    assert S.CARD == S.card_for("nba"), "the NBA's card is the one it was"
    assert S.card_for("wnba") == () and S.LEAGUES == ("nba", "cbb"), "the WNBA was not measured"


CTX = {"starter": True, "spread": -12.0, "total": 158.0, "rest": "b2b_home", "total_norm": 145.0,
       "values": [12.0, 14.0, 10.0, 13.0, 11.0, 12.0, 15.0, 9.0, 12.0, 12.0],
       "minutes": [30.0, 30.0, 31.0, 30.0, 29.0, 30.0, 31.0, 30.0, 30.0, 29.0],
       "games_season": 9, "missed_last": True, "mate_out": True, "mate_back": False}


def test_a_college_card_reads_colleges_verdicts_never_the_nbas():
    college = dict(CTX, league="cbb")
    under, said = S.read(college, "pts", "UNDER", 12.5)
    assert under == ["mate_out_under"], "a projected shootout is refused in college: only the teammate"
    assert "five college seasons" in said[0] and "4-6% less often" in said[0], said
    over, said = S.read(college, "pts", "OVER", 12.5)
    assert over == ["b2b_over", "back_over"], over
    assert all(t.endswith(".") for t in said) and "7-12% less often" in said[1], said
    # The same facts on an NBA card: the shootout warns, the back-to-back and
    # the first game back do not (the NBA refused one and prices the other).
    nba = dict(CTX, total=240.0)
    assert S.read(nba, "pts", "UNDER", 12.5)[0] == ["fast_under", "mate_out_under"]
    assert S.read(nba, "pts", "OVER", 12.5)[0] == []
    assert S.league_of(nba) == "nba" and S.league_of(college) == "cbb" and S.league_of(None) == "nba"


def test_colleges_game_script_reads_its_own_numbers():
    def raised(side, spread=-3.0, total=None, norm=145.0, league="cbb"):
        return S.flags(S.situation("pts", side, 12.5, CTX["values"], CTX["minutes"], True, spread, total,
                                   "1day", 9, False, False, False, total_norm=norm, league=league))
    assert "blowout_over" in raised("OVER", spread=-12.0, league="nba")
    assert "blowout_over" not in raised("OVER", spread=-12.0), "a college favourite of twelve is no blowout"
    assert "blowout_over" in raised("OVER", spread=-15.0) and "blowout_over" in raised("OVER", spread=16.5)
    assert "fast_under" in raised("UNDER", total=151.0) and "fast_under" not in raised("UNDER", total=150.5), \
        "fast is 4% over the usual 145: 150.8"
    assert "slow_over" in raised("OVER", total=136.0) and "slow_over" not in raised("OVER", total=137.0), \
        "slow is 6% under it: 136.3"
    assert not {"fast_under", "slow_over"} & set(raised("UNDER", total=170.0, norm=None) +
                                                   raised("OVER", total=100.0, norm=None)), \
        "without the league's usual total, college reads neither"
    assert "fast_under" in raised("UNDER", total=240.0, norm=None, league="nba"), "the NBA reads its own numbers"


def test_the_college_build_hands_the_scout_its_league_and_its_usual_total():
    import nba_build as B
    h = {"team": "DUKE", "starter": True, "pts": [12.0] * 12, "minutes": [30.0] * 12, "dates": []}
    ctx = B.scout_context("Pick Man", "pts", h, -4.5, 151.5, "1day", 0, {}, {}, "cbb", 0, total_norm=146.2)
    assert (ctx["league"], ctx["total_norm"]) == ("cbb", 146.2)
    assert len(ctx["values"]) == 10 and ctx["spread"] == -4.5 and ctx["total"] == 151.5
    src = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    assert "from engine.nba.scout import LEAGUES as _scout_leagues" in src
    assert "minutes_window.get(\"season\") or 0, total_norm=norm_total)" in src
    assert "if args.league in _scout_leagues else None" in src


# --- college's record ---------------------------------------------------------------------------
#: Duke's last three games of last season, then this season's.
LAST = ("2026-03-03", "2026-03-06", "2026-03-10")
NOW = ("2026-11-03", "2026-11-06", "2026-11-08")


def _hist():
    """Duke against others. A 32-minute senior played last season's three
    and graduated; Big Man played all of them and this season's first two,
    and sits the third; Pick Man plays all. Sixty other finals of 150
    points each, for the league's usual total."""
    c = db.connect(os.path.join(tempfile.mkdtemp(), "h.db"))
    games, logs = [], []

    def log(player, day, minutes, season, pts=10.0):
        for mk, v in (("min", minutes), ("pts", pts)):
            logs.append(("cbb", season, day, f"g{day}", player, "DUKE", "UNC", "S", 1, mk, v))

    for d in LAST + NOW:
        season = 2025 if d < "2026-07-01" else 2026
        games.append(("cbb", season, d, f"g{d}", "DUKE", "UNC", 80, 70, None, None, d))
        log("Pick Man", d, 30.0, season)
        if d in LAST:
            log("Senior Star", d, 32.0, season)
        if d != NOW[-1]:
            log("Big Man", d, 30.0, season)
    for i in range(60):
        d = f"2026-02-{(i % 27) + 1:02d}"
        games.append(("cbb", 2025, d, f"o{i}", f"T{i}", f"U{i}", 75, 75, None, None, d))
    c.executemany("INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
                  "spread, total, date) VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)
    c.executemany("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, "
                  "position, home, market, value) VALUES (?,?,?,?,?,?,?,?,?,?,?)", logs)
    c.commit()
    return c


def _pick(day, **kw):
    return {"player": "Pick Man", "day": day, "market": "pts", "side": "UNDER", "line": 9.5, "team": "DUKE", **kw}


def test_a_college_pick_is_rebuilt_with_colleges_season_and_usual_total():
    data = R.load(_hist(), NOW[0], "cbb")
    opener = R.context(_pick(NOW[0]), data)
    assert opener["league"] == "cbb" and opener["total_norm"] == 150.0, opener
    assert opener["games_season"] == 0 and opener["values"][:3] == [10.0, 10.0, 10.0], \
        "last season's games are his form, not his season"
    assert opener["mate_out"] is False, "the senior who graduated did not sit tonight"
    third = R.context(_pick(NOW[-1]), data)
    assert third["mate_out"] is True, "Big Man played this season's first two and sits the third"
    assert third["games_season"] == 2
    assert "thin" in R.flagged([_pick(NOW[0])], _hist(), "cbb")[0]["flags"]
    nba = R.context({"player": "Pick Man", "day": NOW[0], "market": "pts", "side": "UNDER", "line": 9.5,
                     "team": "DUKE"}, dict(data, sport="nba"))
    assert "league" not in nba, "the NBA's rebuild is the one it was"


def test_colleges_record_reads_only_its_picks_own_schools():
    h = _hist()
    h.execute("INSERT INTO player_game_logs (sport, season, period, game_id, player, team, opponent, position, "
              "home, market, value) VALUES ('cbb', 2026, '2026-11-06', 'x', 'Elsewhere', 'espn:9', 'UNC', '', 1, "
              "'min', 30.0)")
    h.commit()
    every = R.load(h, NOW[0], "cbb")["games"]
    mine = R.load(h, NOW[0], "cbb", teams={"duke"})["games"]
    assert "Elsewhere" in every and "Elsewhere" not in mine and set(mine) == {"Pick Man", "Senior Star", "Big Man"}
    assert "Elsewhere" in R.load(h, NOW[0], "cbb", teams={"espn:9"})["games"], "a small school's key, any case"
    rows = R.flagged([_pick(NOW[-1])], h, "cbb")
    assert rows[0]["ctx"]["mate_out"] is True, "the pick's own school is all its rebuild needs"


def _ledger():
    led = LG.connect(Path(tempfile.mkdtemp()) / "ledger.db")
    led.execute("INSERT INTO bets (sport, date, game_day, player, team, market, side, line, odds, hit_prob, "
                "status, category) VALUES ('cbb',?,?,'Pick Man','DUKE','pts','UNDER',9.5,-150,0.66,'won','likely')",
                (NOW[-1], NOW[-1]))
    led.commit()
    return led


def test_colleges_record_learns_its_own_flags():
    assert "cbb" in C.LEARNS and "cbb" not in C.SPORTS, "football's read stays football's"
    rows = C.flagged_journal(_ledger(), _hist(), "cbb")
    assert rows[0]["ctx"]["league"] == "cbb" and "mate_out_under" in rows[0]["flags"], rows[0]
    assert C.note("b2b_over", "cbb") == S.FLAGS["b2b_over"]
    from engine import boardlearn as B
    e = B.learn_sport(_ledger(), _hist(), "cbb", log=lambda *_: None)
    assert e["scout"]["matched"] == 1 and e["scout"]["passed"] is False, e.get("scout")


def test_the_college_board_reads_its_cards_and_moves_nothing_unproven():
    from engine import likely as L
    from engine import likelyboard as LB
    ctx = dict(CTX, league="cbb", mate_out=False, missed_last=False)
    games = [{"home": "DUKE", "away": "UNC", "date": "2099-11-14", "kickoff": "2099-11-15T00:00Z", "live": None}]
    rec = {"player": "Pick Man", "team": "DUKE", "opponent": "UNC", "market": "pts", "market_label": "pts",
           "side": "OVER", "line": 12.5, "odds": -140, "book": "DraftKings", "hit_prob": 0.64, "fair_prob": 0.58,
           "projection": 13.5, "reasons": ["because"], "recent_values": [12, 14, 10, 13], "injury_status": "",
           "scout_ctx": ctx}
    rows = [L._row_from(rec, "pts", "cbb", lambda m: True, 0.64, shown=0.64, source="model")]
    result = {"most_likely": rows, "games": games, "recommendations": [], "scan_reads": {}}
    got = {r["player"]: r for r in LB.build(result, record={}, sport="cbb", band_verdict=None)["rows"]}
    row = got["Pick Man"]
    assert row["scout_flags"] == ["b2b_over"] and "college seasons" in row["scout_notes"][0], row.get("scout_notes")
    assert row["model_prob"] == 0.64 and not row.get("ctx_note"), "no proven store, nothing moves"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
