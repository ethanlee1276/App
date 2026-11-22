"""Every league's game reports post three two-leg player-prop parlays (2026-11-20).

Ethan, the evening basketball's came back: "we should be doing two-leg player
prop parlays for our game reports, because I was looking at NBA and I see the
two-leg NBA parlays win a lot. So we should be adding that, obviously, to the
NBA game reports, college football game reports, NFL game reports, all other
game reports, and dial those in as well, just as you're doing for the
three-leg ones. So we want 3 two-leg parlays for each game report as well."

Started sets on the record that day: the NBA's two-leg tickets 12 of 16 beside
its three-leg 6 of 27, and hockey's two-leg 14 of 20 before they were stopped
for a day. What these hold:

  * every league's game builds three two-leg tickets (TWO_SPORTS is every
    league) beside its three three-leg ones, and football and hockey keep
    their three scorer pairs: nine tickets a football game, six a basketball
    one;
  * each is two of the game's own legs at TWO_FLOOR or better (two picks at
    63%), three different tickets, no leg shared while the game has six to
    spread them over, and never a leg the parlay rules keep off (the same
    `legs_for` the three-leg tickets are made of);
  * a report rebuilds them from its own picks, as it does the three-leg ones;
  * the build log names each kind, the heartbeat counts them in every league,
    the journal files them, and the record counts every league's (none is
    retired).

    python3 tests/test_every_league_posts_three_two_leg_parlays.py
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, parlayledger as PL            # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
TP = __import__("test_the_parlays_are_made_of_the_reports_picks")   # a report's picks for it
GAME = EG.GAME
#: The fixture's eight Most Likely rows as each league's own props (football's are its own).
MARKETS = {"nba": ("pts", "reb", "ast", "threes", "pts", "reb", "ast", "pts"),
           "cbb": ("pts", "reb", "ast", "threes", "pts", "reb", "ast", "pts"),
           "wnba": ("pts", "reb", "ast", "threes", "pts", "reb", "ast", "pts"),
           "nhl": ("shots", "points", "assists", "shots", "points", "blocks", "saves", "shots"),
           "mlb": ("hits", "total_bases", "strikeouts", "hits", "rbis", "runs", "hits", "total_bases")}
PAIRS = ("nfl", "cfb")                                               # the fixture prices touchdown scorers


class _Uncapped:
    """The NBA caps a leg at two of a game's parlays (step ABG; tests/test_an_nba_leg_rides_two_of_a_games_parlays.py).
    This fixture's five NBA legs at 60% or better fill its three-leg tickets twice over, leaving the cap no
    room for a two-leg one, so the counts here, which ask that every league can make three of each, are
    read with the cap off."""

    def __enter__(self):
        self.was = os.environ.get("QB_GAME_LEG_CAP")
        os.environ["QB_GAME_LEG_CAP"] = "off"

    def __exit__(self, *exc):
        if self.was is None:
            os.environ.pop("QB_GAME_LEG_CAP", None)
        else:
            os.environ["QB_GAME_LEG_CAP"] = self.was


def _board(sport):
    b = EG.board()
    for r, m in zip(b["most_likely"], MARKETS.get(sport) or ()):
        r["market"], r["market_label"] = m, m
    return b


def test_every_league_builds_three_of_each_size():
    assert GP.TWO_SPORTS == GP.SPORTS and GP.TWO_PER_GAME == GP.TWO_MIN == GP.THREE_PER_GAME == 3
    for sport in GP.SPORTS:
        with _Uncapped():
            gp = GP.build(_board(sport), sport)
        g = gp["games"][0]
        twos = g["twos"]
        assert len(twos) == 3 and len(g["threes"]) == 3, (sport, len(twos), len(g["threes"]), g.get("twos_note"))
        assert all(len(t["legs"]) == 2 and t["joint"] >= GP.TWO_FLOOR for t in twos), (sport, [t["joint"] for t in twos])
        assert len({GP.ident(t) for t in twos}) == 3, (sport, "three different tickets")
        assert "twos_note" not in g and gp["counts"]["twos"] == 3 and gp["two_floor"] == GP.TWO_FLOOR, sport
        # Football keeps its touchdown pairs beside them: nine tickets a game.
        assert len(g["scorers"]) == (3 if sport in PAIRS else 0), (sport, len(g["scorers"]))


def test_the_three_share_no_leg_while_the_game_has_six():
    g = GP.build(EG.board(), "nfl")["games"][0]
    legs = [GP._leg_id(l) for t in g["twos"] for l in t["legs"]]
    assert len(legs) == 6 and len(set(legs)) == 6, legs


def test_they_are_made_of_the_legs_the_three_leg_tickets_are():
    b = EG.board()
    pool = {GP._leg_id(l) for l in GP.legs_for(b, "nfl")}
    g = GP.build(b, "nfl")["games"][0]
    assert all(GP._leg_id(l) in pool for t in g["twos"] for l in t["legs"])
    # A pick the parlay rules keep off (a backup back's yards, tests/test_the_v31_...) is on no
    # ticket of either size: both are built from `legs_for`.
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert "made2 = tickets_of(sport, game, legs, memo, size=2, books=books,\n" in src


def test_a_football_report_rebuilds_them_from_its_own_picks():
    b = EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    x = GP.from_report(b, "nfl", GAME, TP.PICKS)
    own = {(p["player"], p["market"]) for p in TP.PICKS}
    assert len(x["twos"]) == 3 and "twos_note" not in x, x.get("twos_note")
    assert all((l["player"], l["market"]) in own for t in x["twos"] for l in t["legs"]), \
        [[l["player"] for l in t["legs"]] for t in x["twos"]]
    assert not any(t.get("filled") for t in x["twos"]), "five picks make three without a fill"
    GP.report_only(b)
    assert b["game_parlays"]["counts"]["twos"] == 3


def test_the_build_log_names_each_kind():
    nfl = GP.summary(GP.build(EG.board(), "nfl"))
    assert "Game parlays: 3 three-leg, 3 two-leg and 3 scorer pair(s) across 1 game(s)" in nfl, nfl
    with _Uncapped():
        nba = GP.summary(GP.build(_board("nba"), "nba"))
    assert "Game parlays: 3 three-leg and 3 two-leg across 1 game(s)" in nba, nba
    nhl = GP.summary(GP.build(_board("nhl"), "nhl"))
    assert "Game parlays: 3 three-leg, 3 two-leg and 0 scorer pair(s) across 1 game(s)" in nhl, nhl


def test_the_heartbeat_counts_them_in_football():
    import launch as L
    b = EG.board()
    GP.attach(b, "nfl")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(b, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert (got["sgp_threes"], got["sgp_twos"], got["td_pairs"]) == (3, 3, 3), got
    assert got["twos_short"] == 0 and got["threes_short"] == 0, got


def test_the_journal_files_them_and_the_record_counts_every_leagues():
    from engine import ledger
    assert not any(GP.retired(k, s) for k in ("three", "two", "scorers") for s in GP.SPORTS)
    conn = ledger.connect(":memory:")
    PL.ensure_schema(conn)
    for sport in ("nfl", "cfb", "nhl", "nba"):
        with _Uncapped():
            PL.log_game_parlays(conn, GP.build(_board(sport), sport), sport, "2099-11-12")
        n = conn.execute("SELECT count(*) FROM parlays WHERE source='game_two' AND sport=?", (sport,)).fetchone()[0]
        assert n == 3, (sport, n)
    conn.execute("UPDATE parlays SET status='won', pnl_units=1.0, at_start=1 WHERE source='game_two'")
    rec = PL.game_parlay_record(conn)
    for sport in ("nfl", "cfb", "nhl", "nba"):
        two = rec[sport]["two"]
        assert (two["graded"], two["wins"]) == (3, 3), (sport, two)


def test_every_page_draws_them_beside_the_others():
    from engine import gamereport as GR
    b = EG.board()
    GP.attach(b, "nfl")
    c = GR.Ctx(GAME, b, sport="nfl")
    blocks = GR.sec_parlays(c)["blocks"]
    heads = [x.get("text") for x in blocks if x.get("type") == "h"]
    assert heads == ["Three-leg parlays", "Two-leg parlays", "Touchdown pairs"], heads
    kinds = [x.get("kind") for x in blocks if x.get("type") == "parlays"]
    assert kinds == ["three", "two", "scorers"], kinds
    two = next(x for x in blocks if x.get("kind") == "two")
    assert [i["title"] for i in two["items"]] == ["Two-leg parlay 1", "Two-leg parlay 2", "Two-leg parlay 3"]
    line = GR.parlay_sentence(c)
    assert "Best three-leg parlay: " in line and "Best two-leg parlay: " in line and "Best touchdown pair: " in line, line
    js = {n: (ROOT / "web" / "js" / f"{n}.js").read_text(encoding="utf-8") for n in ("report", "reportpicks", "record")}
    assert "const both = (g.twos || []).length > 0;" in js["report"], "each ticket says its size beside the other"
    assert 'sec("The two-leg parlays", rpTicketsHTML(twos, "twos", sport, game))' in js["reportpicks"]
    assert 'const GP_KINDS = ["three", "two", "scorers"];' in js["record"]
    for name in ("more", "account"):
        copy = (ROOT / "web" / "js" / f"{name}.js").read_text(encoding="utf-8")
        assert "three two-leg parlays" in copy and "in basketball, three two-leg" not in copy, name


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
