"""A game's parlays lead with its two strongest picks, and every ticket clears a
bar of its own (engine/gameparlays.tickets_of), GPWIN1.

Ethan, 18 November 2026, a day after the parlays were made of the report's own
picks, over How our reports did (picks 6 of 11 and parlays 0 of 4, picks 4 of
5 and parlays 0 of 3, picks 7 of 8 and parlays 2 of 9): "how are we winning so
many picks, individual picks, but losing so many parlays? ... Make it so the
parlays win as well." Then, of the NFL's three-leg tickets on paper: "track
them and learn and make them better".

What the record said that night: the NBA's report picks hit 41 of 62, priced
68% or better 24 of 31; three of a game's picks together hit one time in five
(96 of 480), two of them two times in five (86 of 220), and the two
shortest-priced 5 of 8; 85 of the NBA's 151 lost three-leg tickets lost by one
leg. What these hold:

  * a game's two strongest picks make its first ticket, two legs (and its next
    two a second, sharing no leg with the first), each at TWO_FLOOR or better by
    our numbers; a three-leg ticket is made only at THREE_FLOOR or better;
  * a game whose picks make fewer says why, on the board and in its report;
  * the two-leg tickets are journaled apart (source game_two), graded off
    their legs, read back for a finished game, counted on the record, and held
    on paper on their own record (engine/parlayhold, its own bar);
  * the leg learner counts their legs with the three-leg ones, each bet once,
    and learns a shift for each market that runs hot (engine/legfit);
  * the report, the Report Picks page, the finished game's card, the Record
    page, Ask and the heartbeat all carry them, the two-leg tickets first.

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

from engine import gameparlays as GP, legfit as LF, parlayhold, parlayledger as PL, reportoutcome as RO  # noqa: E402

GP.two_hold = lambda sport: None
EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
GAME = EG.GAME


def _game():
    b = EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    return b, GP.for_game(b, "NYG", "WAS")


def test_the_two_strongest_picks_lead_and_every_ticket_clears_its_bar():
    _b, x = _game()
    twos, threes = x["twos"], x["threes"]
    assert len(twos) == GP.TWO_PER_GAME == 2, twos
    assert all(len(t["legs"]) == 2 and t["joint"] >= GP.TWO_FLOOR for t in twos)
    assert [l["player"] for l in twos[0]["legs"]] == ["Malik Nabers", "Jayden Daniels"], "the likeliest pair that fits"
    first, second = ({GP._leg_id(l) for l in t["legs"]} for t in twos)
    assert not first & second, "the second two-leg ticket shares no pick with the first"
    assert threes and all(t["joint"] >= GP.THREE_FLOOR for t in threes), [t["joint"] for t in threes]
    # Two legs hit together more often than three, by our own numbers.
    assert min(t["joint"] for t in twos) > max(t["joint"] for t in threes)


def test_a_ticket_under_its_bar_is_not_made_and_the_game_says_why():
    legs = [l for l in GP.legs_for(EG.board(), "nfl")]
    for l in legs:
        l["p"] = 0.61                     # three legs at 61% together: about 23%, under THREE_FLOOR
    made = GP.tickets_of("nfl", GAME, legs)
    assert made["twos"] == [], "two at 61% together are about 37%, under TWO_FLOOR"
    note = GP._twos_note(made, own=True)
    assert "reach the 42% a two-leg parlay needs" in note and "this report's own picks" in note, note
    # The three-leg tickets: none clears THREE_FLOOR, so the game fills its two
    # with longer tickets that say so (THREELEG1, 2026-11-19: "I want those for
    # every single game").
    assert made["threes_fit"] > 0 and made["threes_clear"] == 0, made
    assert len(made["threes"]) == GP.THREE_MIN and made["filled"] == GP.THREE_MIN, made["threes"]
    assert all(t["joint"] < GP.THREE_FLOOR and any(c.startswith("A longer ticket: ") for c in t["caveats"])
               for t in made["threes"])
    one = GP.tickets_of("nfl", GAME, legs[:1])
    assert "takes two of this game's picks" in GP._twos_note(one), GP._twos_note(one)
    # Too few legs for a three-leg ticket: the report says why.
    rnote = GP._report_note(1, 6, one)
    assert rnote == "a three-leg parlay takes three legs, and this report's 1 pick at 60% or better makes 1", rnote


def test_a_reports_rebuild_makes_both_sizes_from_its_own_picks():
    tp = __import__("test_the_parlays_are_made_of_the_reports_picks")
    b, _x = _game()
    x = GP.from_report(b, "nfl", GAME, tp.PICKS)
    picked = {GP._pick_key(p) for p in tp.PICKS}
    assert x["twos"] and all(GP._pick_key(l) in picked for t in x["twos"] for l in t["legs"]), x["twos"]
    # Too few picks for a pair that clears the bar: none, and why.
    y = GP.from_report(_game()[0], "nfl", GAME, tp.PICKS[:1])
    assert y["twos"] == [] and "own picks" in y["twos_note"], y.get("twos_note")
    # A game no report rebuilt posts neither size.
    b2, x2 = _game()
    x2.pop("legs_from", None)
    GP.report_only(b2)
    assert x2["twos"] == [] and x2["twos_note"] == GP.NO_REPORT_NOTE


def test_they_are_journaled_apart_graded_and_read_back():
    b, _x = _game()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert PL.log_game_parlays(conn, b["game_parlays"], "nfl", "2099-W10") == 2 + GP.THREE_PER_GAME + GP.SCORER_PER_GAME
    rows = conn.execute("SELECT source, n_legs FROM parlays WHERE source='game_two'").fetchall()
    assert len(rows) == 2 and {r["n_legs"] for r in rows} == {2}
    got = RO.tickets(conn, "nfl", "2099-W10", "NYG", "WAS")
    assert len(got["twos"]) == 2 and len(got["threes"]) == GP.THREE_PER_GAME and len(got["scorers"]) == 3, {k: len(v) for k, v in got.items()}
    assert "game_two" in PL.NO_ROW_VOID_SOURCES and PL.TWO_LEG_CATS["game_two"] == (PL.PARLAY_LEG_CATEGORY,)
    conn.execute("UPDATE parlays SET status='won' WHERE source='game_two'")
    conn.execute("UPDATE parlay_legs SET status='won'")
    conn.commit()
    # The game starts: the set it carried then (kept, engine/reportkeep) is
    # the set the record counts (parlayledger.mark_at_start).
    started = {"games": [dict(g, kept="Sun 1:00 PM ET") for g in b["game_parlays"]["games"]]}
    assert PL.mark_started_games(conn, started, "nfl", "2099-W10") == 2 + GP.THREE_PER_GAME + GP.SCORER_PER_GAME
    rec = PL.game_parlay_record(conn)
    assert rec["nfl"]["two"]["graded"] == 2 and rec["nfl"]["two"]["wins"] == 2, rec["nfl"].keys()


def test_the_two_leg_tickets_have_a_hold_of_their_own():
    conn = sqlite3.connect(":memory:")
    PL.ensure_schema(conn)
    for i, (src, won) in enumerate([("game_two", i < 12) for i in range(45)] + [("game_three", True)] * 60):
        conn.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified,"
                     " was_play, notional_units, stake_units, source, status, at_start)"
                     " VALUES (?,?,?,?,?,?,?,1,0,1,0,?,?,1)",
                     ("2026-11-19T12:00:00", "nba", "2026-11-19", f"k{i}", "same_game", 2 if src == "game_two" else 3,
                      "A@B", src, "won" if won else "lost"))
    conn.commit()
    path = Path(tempfile.mkdtemp()) / "parlayhold.json"
    import datetime as dt
    out = parlayhold.refresh(conn, path, today=dt.date(2026, 11, 20))
    two = parlayhold.held("nba", path, legs=2)
    assert two and two["n"] == 45 and two["won"] == 12 and two["legs"] == 2, two
    assert parlayhold.held("nba", path) is None, "the three-leg tickets hit 60 of 60: not held by the two-leg record"
    assert "our two-leg parlays in the NBA have hit 12 of their last 45 (27%), under the 36% they need" in \
        parlayhold.words(two)
    assert parlayhold.verdict(out)["two_leg_on_paper"] == ["nba"]


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


def test_every_page_carries_them_two_leg_first():
    from engine import gamereport as GR
    b, _x = _game()
    c = GR.Ctx(GAME, b, sport="nfl")
    sec = GR.sec_parlays(c)
    kinds = [x.get("kind") for x in sec["blocks"] if x.get("type") == "parlays"]
    assert kinds == ["two", "three", "scorers"], kinds
    two = next(x for x in sec["blocks"] if x.get("kind") == "two")
    assert two["items"][0]["title"] == "Two-leg parlay 1" and "td_rule" not in two["items"][0]
    assert GR.parlay_sentence(c).startswith("Strongest two-leg parlay: Malik Nabers")
    js = {n: (ROOT / "web" / "js" / f"{n}.js").read_text(encoding="utf-8") for n in
          ("report", "reportpicks", "record", "detail")}
    assert 'kind === "two" ? `Two-leg parlay ${n}`' in js["report"]
    assert "return `${twos}${(g.threes || []).length ?" in js["report"]
    assert 'bet_legs: ((gp[{ three: "threes", two: "twos" }[b.kind] || "scorers"] || [])[i] || {}).legs || []' in js["report"]
    assert '["Two-leg parlays", twos]' in js["reportpicks"] and "function rpParlays(tix)" in js["reportpicks"]
    assert 'const GP_KINDS = ["two", "three", "scorers"];' in js["record"]
    assert 'gprTicketsRow(twos, "2-leg parlays"),' in js["detail"]
    ask = (ROOT / "engine" / "askbot.py").read_text(encoding="utf-8")
    assert 'TICKET_POOLS = (("twos", "two-leg parlay"), ("threes", "three-leg parlay"), ("scorers", "scorer pair"))' in ask
    launch = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert 'out["sgp_twos"] = int(c.get("twos") or 0)' in launch


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
