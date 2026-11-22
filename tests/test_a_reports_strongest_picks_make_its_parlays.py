"""A game's three-leg tickets clear a bar of their own; the two-leg tickets are
retired (engine/gameparlays.tickets_of; GPWIN1, then ZR).

Ethan, 18 November 2026, over How our reports did (picks 6 of 11 and parlays
0 of 4, picks 4 of 5 and parlays 0 of 3): "how are we winning so many picks,
individual picks, but losing so many parlays? ... Make it so the parlays win as
well." GPWIN1 led each game with its two strongest picks as a two-leg ticket.
Then, 20 November: "i want 3 3 leg player prop parlays and 3 2 leg td prop
parlays". What these hold:

  * a three-leg ticket is posted ahead of the fill only at THREE_FLOOR or
    better by our numbers; a game whose tickets fall short fills to THREE_MIN
    with longer tickets that say so, and one that still falls short says why;
  * no football or hockey board builds a two-leg player-prop ticket any more,
    no report or page posts one for its games still to play, and the record
    leaves the retired kind off there (gameparlays.retired); basketball posts
    three a game in its scorer pairs' place (ZT, 20 November: "do 2-leg nba
    parlays"); the journal still holds every one, graded, and a finished game
    from before still lists its own;
  * the leg learner counts their legs with the three-leg ones, each bet once,
    and learns a shift for each market that runs hot (engine/legfit).

    python3 tests/test_a_reports_strongest_picks_make_its_parlays.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, legfit as LF, parlayledger as PL, reportoutcome as RO  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
GAME = EG.GAME


def _game():
    b = EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    return b, GP.for_game(b, "NYG", "WAS")


def test_every_ticket_clears_its_bar_three_legs_and_two():
    b, x = _game()
    threes = x["threes"]
    assert len(threes) == GP.THREE_MIN == GP.THREE_PER_GAME == 3, threes
    assert all(t["joint"] >= GP.THREE_FLOOR and len(t["legs"]) == 3 for t in threes), [t["joint"] for t in threes]
    # The two-leg tickets, every league's since 20 November (Ethan: "we want 3 two-leg parlays for each
    # game report as well"): three a game, each to its own bar, with no note and nothing held on paper.
    twos = x["twos"]
    assert len(twos) == GP.TWO_MIN == GP.TWO_PER_GAME == 3, twos
    assert all(t["joint"] >= GP.TWO_FLOOR and len(t["legs"]) == 2 for t in twos), [t["joint"] for t in twos]
    assert not any(k in x for k in ("paper_twos", "twos_note", "twos_paper")), sorted(x)
    assert b["game_parlays"]["counts"]["twos"] == 3 and b["game_parlays"]["two_floor"] == GP.TWO_FLOOR
    assert not any(GP.retired("two", s) for s in GP.SPORTS), "no league's two-leg tickets are retired"
    assert GP.SOURCES["two"] == "game_two"
    assert GP.TWO_SPORTS == GP.SPORTS, "every league's"
    for gone in ("RETIRED", "two_hold", "_twos_note"):
        assert not hasattr(GP, gone), gone
    assert not (ROOT / "engine" / "parlayhold.py").exists(), "no kind of ticket is held on paper"


def test_a_ticket_under_its_bar_is_not_made_and_the_game_says_why():
    legs = [l for l in GP.legs_for(EG.board(), "nfl")]
    for l in legs:
        l["p"] = 0.61                     # three legs at 61% together: about 23%, under THREE_FLOOR
    made = GP.tickets_of("nfl", GAME, legs)
    assert "twos" not in made, "a size's call makes that size only"
    # The three-leg tickets: none clears THREE_FLOOR, so the game fills its three
    # with longer tickets that say so (THREELEG1, 2026-11-19: "I want those for
    # every single game").
    assert made["threes_fit"] > 0 and made["threes_clear"] == 0, made
    assert len(made["threes"]) == GP.THREE_MIN and made["filled"] == GP.THREE_MIN, made["threes"]
    assert all(t["joint"] < GP.THREE_FLOOR and any(c.startswith("A longer ticket: ") for c in t["caveats"])
               for t in made["threes"])
    one = GP.tickets_of("nfl", GAME, legs[:1])
    # Too few legs for a three-leg ticket: the report says why.
    rnote = GP._report_note(1, 6, one)
    assert rnote == ("a three-leg parlay takes three legs, and this report's picks (1 of its 6 picks is at 60% "
                     "or better) make only 1 leg"), rnote


def test_a_reports_rebuild_posts_its_three_of_each_size():
    tp = __import__("test_the_parlays_are_made_of_the_reports_picks")
    b, _x = _game()
    x = GP.from_report(b, "nfl", GAME, tp.PICKS)
    assert len(x["threes"]) == GP.THREE_MIN and len(x["twos"]) == GP.TWO_MIN and "twos_note" not in x, sorted(x)
    # The two-leg tickets are the report's own picks too.
    own = {p["player"] for p in tp.PICKS}
    assert all(l["player"] in own for t in x["twos"] for l in t["legs"]), [[l["player"] for l in t["legs"]] for t in x["twos"]]
    # A game no report rebuilt posts no ticket of its own, of either size.
    b2, x2 = _game()
    x2.pop("legs_from", None)
    GP.report_only(b2)
    assert x2["threes"] == [] and x2["threes_note"] == GP.NO_REPORT_NOTE and x2["twos"] == [] and "twos_note" not in x2


def test_a_board_journals_its_two_leg_tickets_and_the_record_counts_the_old_ones_again():
    b, _x = _game()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert PL.log_game_parlays(conn, b["game_parlays"], "nfl", "2099-W10") == GP.THREE_PER_GAME + GP.TWO_PER_GAME + GP.SCORER_PER_GAME
    assert len(conn.execute("SELECT 1 FROM parlays WHERE source='game_two'").fetchall()) == GP.TWO_PER_GAME
    # One journaled before ZR still grades, reads back for its finished game, and counts on the record again.
    cur = conn.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, source, status,"
                       " at_start) VALUES ('2026-11-19T12:00', 'nfl', '2099-W10', 'old', 'same_game', 2, 'WAS@NYG',"
                       " 'game_two', 'won', 1)")
    for n, who in enumerate(("Malik Nabers", "Jayden Daniels"), 1):
        conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, status)"
                     " VALUES (?, ?, ?, 'receptions', 'OVER', 2.5, 'won')", (cur.lastrowid, n, who))
    conn.commit()
    got = RO.tickets(conn, "nfl", "2099-W10", "NYG", "WAS")
    assert [t["status"] for t in got["twos"]].count("won") == 1, {k: len(v) for k, v in got.items()}
    assert "game_two" in PL.NO_ROW_VOID_SOURCES and PL.TWO_LEG_CATS["game_two"] == (PL.PARLAY_LEG_CATEGORY,)
    started = {"games": [dict(g, kept="Sun 1:00 PM ET") for g in b["game_parlays"]["games"]]}
    assert PL.mark_started_games(conn, started, "nfl", "2099-W10") == GP.THREE_PER_GAME + GP.TWO_PER_GAME + GP.SCORER_PER_GAME
    rec = PL.game_parlay_record(conn)
    assert set(rec["nfl"]) <= {"three", "two", "scorers"} and rec["nfl"]["two"]["graded"] == 1 \
        and rec["nfl"]["two"]["wins"] == 1, rec["nfl"]


def test_the_leg_learner_counts_them_once_and_learns_each_market():
    conn = sqlite3.connect(":memory:")
    PL.ensure_schema(conn)

    def ticket(source, i, legs):
        cur = conn.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified,"
                           " was_play, notional_units, stake_units, source, status) VALUES (?,?,?,?,?,?,?,1,0,1,0,?,?)",
                           (f"2026-11-{1 + i // 20:02d}T12:00:00", "nfl", f"2026-11-{1 + i // 20:02d}",
                            f"{source}{i}", "same_game", len(legs), "A@B", source, "lost"))
        for n, (player, market, p, won) in enumerate(legs, 1):
            conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, odds, p_final,"
                         " status, pool, fair, p_raw) VALUES (?,?,?,?,'OVER',2.5,-200,?,?,?,?,?)",
                         (cur.lastrowid, n, player, market, p, "won" if won else "lost", "likely", 0.66, p))
    # 80 receptions legs claimed 72% that hit 40%; 80 rushing legs claimed 70% that hit 70%.
    for i in range(80):
        rec = (f"R{i}", "receptions", 0.72, i % 5 < 2)
        rush = (f"U{i}", "rush_att", 0.70, i % 10 < 7)
        ticket("game_three", i, [rec, rush, (f"X{i}", "pass_yds", 0.70, True)])
        ticket("game_two", i, [rec, rush])          # the same two picks again, on a two-leg ticket
    conn.commit()
    legs = LF.graded_legs(conn)[("nfl", "three")]
    assert len(legs) == 240, "each bet once, across both sizes of ticket"
    fit = LF.fit(conn, write=False)["fits"]["nfl:three"]
    m = fit["markets"]
    assert m["receptions"]["shift"] < 0 and m["receptions"]["n"] == 80, m["receptions"]
    assert "hit 40%" in m["receptions"]["why"], m["receptions"]["why"]
    assert m["receptions"]["shift"] < m["rush_att"]["shift"] + 1e-9, (m["receptions"], m["rush_att"])
    # Applied on top of the league's, to the market it was learned on.
    LF._HELD.clear()
    LF._HELD.update(key=None, data={"fits": {"nfl:three": fit}})
    real = LF.fits
    LF.fits = lambda: {"nfl:three": fit}
    try:
        got = LF.apply({"p": 0.72, "market": "receptions", "fair": 0.66}, "nfl", "three", 0.0, 0.0)
        assert got["p"] < 0.72 and got["p_raw"] == 0.72, got
        assert LF.market_shift_for("nfl", "three", "receptions") == m["receptions"]["shift"]
    finally:
        LF.fits = real
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert "            if leg:\n                # Its market's own shift rides on top" in src


def test_every_page_carries_three_of_each_and_keeps_old_two_leg_tickets_readable():
    from engine import gamereport as GR
    b, _x = _game()
    c = GR.Ctx(GAME, b, sport="nfl")
    sec = GR.sec_parlays(c)
    kinds = [x.get("kind") for x in sec["blocks"] if x.get("type") == "parlays"]
    assert kinds == ["three", "two", "scorers"], kinds
    three = next(x for x in sec["blocks"] if x.get("kind") == "three")
    assert len(three["items"]) == 3 and three["items"][0]["title"] == "Three-leg parlay 1"
    two = next(x for x in sec["blocks"] if x.get("kind") == "two")
    assert len(two["items"]) == 3 and two["items"][0]["title"] == "Two-leg parlay 1"
    assert "Best two-leg parlay: " in GR.parlay_sentence(c)
    assert GR.parlay_sentence(c).startswith("Best three-leg parlay: "), GR.parlay_sentence(c)
    js = {n: (ROOT / "web" / "js" / f"{n}.js").read_text(encoding="utf-8") for n in
          ("report", "reportpicks", "record", "detail")}
    # Every page draws the two-leg tickets beside the others.
    assert 'kind === "two" ? `Two-leg parlay ${n}`' in js["report"]
    assert '["Two-leg parlays", twos]' in js["reportpicks"] and 'gprTicketsRow(twos, "2-leg parlays"),' in js["detail"]
    assert 'const GP_KINDS = ["three", "two", "scorers", "sgpx_props", "sgpx_td"];' in js["record"], "the record lists the kinds built"
    ask = (ROOT / "engine" / "askbot.py").read_text(encoding="utf-8")
    assert 'TICKET_POOLS = (("twos", "two-leg parlay"), ("threes", "three-leg parlay"), ("scorers", "scorer pair"))' in ask
    from engine import askbot
    said = " ".join(t["description"] for t in askbot.TOOLS if t["name"] == "our_picks")
    assert "three three-leg and three two-leg player-prop parlays" in said and "scorer pairs" in said, said
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert "sgp_twos" in launch and ".lower() in TWO_SPORTS:" in launch, "counted on the heartbeat"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
