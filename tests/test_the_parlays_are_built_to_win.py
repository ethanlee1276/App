"""The game reports' parlays are built to win (PARLAYWIN1, 2026-11-19).

Ethan, 2026-11-19: "if the three-leg parlays aren't working and aren't making
money, then we're not making good selections and good picks ... Clearly we're
doing okay on the picks, but the parlays we make are not doing good, so work
on that, make those better."

What the record said (record.json, 19 November):

  * every graded ticket (2,085): the 1,321 priced with a positive link between
    their legs hit 382, where the link said 443 and the legs alone 407 — the
    link pushed our number further from the truth (z -3.7 with it, -1.5
    without), so a ticket's chance counts a positive link at the weight the
    record supports, 0 until it shows the linked legs hit together
    (`link_weight`, fitted nightly);
  * since the parlays were built from the report's own picks (17 November),
    hockey's three-leg tickets hit 4 of 10 and the NBA's two-leg ones 9 of 11,
    where a prop the report never picked hit 62% as a leg against the picks'
    75% (step WH): a game fills with the report's own picks first and takes
    another prop only at 60% or better;
  * a market benched for losing money (stakeplan.MARKET_BENCH) is no leg;
  * the bars a ticket clears are said without the link: two picks at 63%
    (40%), three at 63% (25%).

    python3 tests/test_the_parlays_are_built_to_win.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gameparlays as GP, modelstate, parlayledger as PL  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                    # the shared fixture
GAME = EG.GAME


def _leg(player, market, p, team="NYG", pos="WR", side="Over", line=2.5):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "home": "NYG",
            "away": "WAS", "position": pos, "market": market, "market_label": market, "side": side,
            "line": line, "odds": -150, "book": "DraftKings", "p": p, "game_date": "2099-11-12"}


class _Models:
    """A models directory of the test's own, and the link's cache cleared."""

    def __enter__(self):
        self.was = os.environ.get(modelstate.ENV_VAR)
        self.dir = tempfile.mkdtemp()
        os.environ[modelstate.ENV_VAR] = self.dir
        GP._LINK.clear()
        return self

    def __exit__(self, *exc):
        if self.was is None:
            os.environ.pop(modelstate.ENV_VAR, None)
        else:
            os.environ[modelstate.ENV_VAR] = self.was
        GP._LINK.clear()


def _linked_pair():
    """A quarterback's yards and the receiver's: legs our relation links."""
    qb = _leg("Jaxson Dart", "pass_yds", 0.66, pos="QB", line=210.5)
    wr = _leg("Malik Nabers", "rec_yds", 0.65, line=60.5)
    fits, rho, _why, _cav = GP.pair_link("nfl", qb, wr, GAME)
    assert fits and rho > 0, ("the fixture needs a positive link", rho)
    return qb, wr


def test_a_positive_link_does_not_raise_a_tickets_chance_until_the_record_says_so():
    qb, wr = _linked_pair()
    with _Models():
        assert GP.link_weight() == GP.LINK_WEIGHT_DEFAULT == 0.0
        t = GP.ticket("nfl", [qb, wr], GAME)
        assert t["joint"] == round(0.66 * 0.65, 4), (t["joint"], "the legs alone")
        assert not t["links"], "a link we do not price is not said as one"
        # A fit that found the linked legs did hit together: the link counts.
        import json
        with open(modelstate.path(GP.LINK_FILE), "w") as f:
            json.dump({"weight": 1.0, "fitted": True}, f)
        GP._LINK.clear()
        assert GP.link_weight() == 1.0
        assert GP.ticket("nfl", [qb, wr], GAME)["joint"] > round(0.66 * 0.65, 4)
        # A file that cannot be read is said, and the default is in force.
        with open(modelstate.path(GP.LINK_FILE), "w") as f:
            f.write("{not json")
        GP._LINK.clear()
        assert GP.link_weight() == GP.LINK_WEIGHT_DEFAULT and GP.LINK_ERROR, GP.LINK_ERROR


def _record(rows):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    for i, (m, ind, st) in enumerate(rows):
        c.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified, was_play,"
                  " notional_units, stake_units, source, status, modeled_joint, independent_joint)"
                  " VALUES ('2026-11-19T00:00:00','nba','2026-11-18',?,'same_game',3,'A@B',1,0,1,0,'game_three',?,?,?)",
                  (f"k{i}", st, m, ind))
    c.commit()
    return c


def test_the_link_weight_is_fitted_on_the_record():
    with _Models():
        # Too few linked tickets settled: the default, said why.
        few = GP.fit_link_weight(_record([(0.34, 0.30, "won")] * 20))
        assert few["weight"] == GP.LINK_WEIGHT_DEFAULT and not few["fitted"] and "waiting on the record" in few["why"]
        # 300 linked tickets that hit at the legs' own rate, 30%: the link earned nothing.
        flat = GP.fit_link_weight(_record([(0.34, 0.30, "won")] * 90 + [(0.34, 0.30, "lost")] * 210))
        assert flat["fitted"] and flat["raw"] == 0.0 and flat["weight"] == 0.0, flat
        # 300 that hit at the link's 34%: it earned all of it, shrunk toward the default.
        full = GP.fit_link_weight(_record([(0.34, 0.30, "won")] * 102 + [(0.34, 0.30, "lost")] * 198))
        assert full["raw"] == 1.0 and full["weight"] == round(300 / (300 + GP.LINK_PRIOR_N), 3), full
        GP._LINK.clear()
        assert GP.link_weight() == full["weight"], "the weight written is the weight read"
    m = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert "gameparlays.fit_link_weight(lconn)" in m, "fitted nightly with the one-club bar"


def test_a_prop_the_report_did_not_pick_fills_one_a_ticket_at_55():
    b = EG.board()
    b["most_likely"] = []
    b["td_field"] = []
    recs = [EG._rec("A One", "NYG", "WR", "receptions", "Over", 2.5, 0.72, -150),
            EG._rec("B Two", "WAS", "RB", "rush_yds", "Over", 40.5, 0.70, -150),
            EG._rec("C Three", "NYG", "TE", "rec_yds", "Over", 30.5, 0.68, -150),
            EG._rec("D Four", "WAS", "WR", "receptions", "Over", 3.5, 0.53, -150),   # no pick, under 55%
            EG._rec("E Five", "NYG", "RB", "rush_att", "Over", 12.5, 0.62, -150),   # no pick, 55% or better
            EG._rec("F Six", "WAS", "TE", "rec_yds", "Over", 20.5, 0.60, -150)]     # no pick, 55% or better
    b["recommendations"] = recs
    b["game_parlays"] = GP.build(b, "nfl")
    picks = [{"player": r["player"], "market": r["market"], "side": "OVER", "line": r["line"]} for r in recs[:3]]
    x = GP.from_report(b, "nfl", GAME, picks)
    legs = {l["player"] for t in x["threes"] for l in t["legs"]}
    assert "D Four" not in legs, "a prop the report never picked, under 55%, is no leg"
    assert len(x["threes"]) == GP.THREE_MIN and "E Five" in legs, "one at 55% or better fills the second ticket"
    picked = {"A One", "B Two", "C Three"}
    outside = [sum(l["player"] not in picked for l in t["legs"]) for t in x["threes"]]
    assert outside[:2] == [0, 1], [[l["player"] for l in t["legs"]] for t in x["threes"]]
    assert (GP.FILL_OTHER_FLOOR, GP.FILL_OUTSIDE_MAX) == (0.55, 1)
    # Three picks can ride on two such tickets at most (a leg rides on MAX_USES):
    # the game's best props make up the third, last, each named (ZR).
    last = x["threes"][-1]
    assert outside[2] > GP.FILL_OUTSIDE_MAX and x["threes_props_filled"] == 1, (outside, x.get("threes_props_filled"))
    assert any("props the board priced, added so the game has 3 three-leg parlays" in c for c in last["caveats"]), \
        last["caveats"]


def test_a_benched_market_is_no_leg():
    b = EG.board()
    b["recommendations"] = [EG._rec("Jayden Daniels", "WAS", "QB", "pass_cmp", "Over", 19.5, 0.70, -150),
                            EG._rec("Jalen Hurts", "WAS", "QB", "pass_yds", "Over", 210.5, 0.70, -150)]
    got = {l["market"] for l in GP.legs_for(b, "nfl")}
    assert "pass_cmp" not in got and "pass_yds" in got, got


def test_the_record_says_how_the_rebuilt_tickets_did_apart():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    rows = [("2026-11-18", "2026-11-18T19:00:00", "lost", 0.31), ("2026-11-19", "2026-11-19T15:00:00", "won", 0.27),
            ("2026-11-20", "2026-11-20T12:05:00", "lost", 0.26), ("2026-11-21", "2026-11-21T12:00:00", "open", 0.28),
            # A week-labelled league counts by when its ticket was journaled.
            ("2026-W12", "2026-11-18T10:00:00", "won", 0.3)]
    for i, (date, ts, st, joint) in enumerate(rows):
        sport = "nfl" if date.startswith("2026-W") else "nba"
        c.execute("INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, qualified, was_play,"
                  " notional_units, stake_units, source, status, modeled_joint, pnl_units, at_start)"
                  " VALUES (?,?,?,?,'same_game',3,'A@B',1,0,1,0,'game_three',?,?,?,1)",
                  (ts, sport, date, f"k{i}", st, joint, {"won": 2.5, "lost": -1.0}.get(st)))
    c.commit()
    rec = PL.game_parlay_record(c)
    nr = rec["nba"]["three"]["since_rules"]
    assert (nr["from"], nr["graded"], nr["wins"], nr["open"]) == (PL.RULES_SINCE, 2, 1, 1), nr
    assert nr["chance"] == 0.265 and nr["net_units"] == 1.5, nr
    assert "since_rules" not in rec["nfl"]["three"], "journaled before the rebuild: not the new rules'"
    js = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
    assert "const nr = b.since_rules;" in js and "${tiles}</div>${close}${rebuilt}" in js


def test_a_card_says_its_chance_once():
    t = {"joint": 0.3412, "independent": 0.3412, "fair_words": "+193", "take_words": "+207", "legs": []}
    line = GP.card(t, 1, "three", "nba")["price_line"]
    assert line.startswith("34% by our numbers · fair +193") and "unrelated" not in line, line
    linked = GP.card(dict(t, joint=0.37), 1, "three", "nba")["price_line"]
    assert "37% by our numbers (34% if the legs were unrelated)" in linked, linked
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert "pct(t.independent) !== pct(t.joint)" in js, "the page's own card says it once too"


def test_the_bars_are_said_without_the_link():
    assert GP.THREE_FLOOR == 0.25 and round(0.63 ** 3, 2) == GP.THREE_FLOOR
    # The two-leg tickets are retired, and their bar with them (ZR).
    assert not hasattr(GP, "TWO_FLOOR") and GP.RETIRED == ("two",)


def test_the_reports_own_picks_are_never_crowded_out_of_the_fill():
    """The fill's tickets take two of the report's picks where they can, so the
    picks enter its pool first: sorted by chance alone, a game's other props at
    70% took the MAX_POOL places ahead of its picks at 52-58%, and it built
    nothing."""
    g = GAME
    picks = [_leg("A One", "receptions", 0.58), _leg("B Two", "rush_att", 0.55, team="WAS"),
             _leg("C Three", "rec_yds", 0.52, pos="TE")]
    others = [_leg(f"Other {i}", "receptions", 0.70, team="NYG" if i % 2 else "WAS") for i in range(GP.MAX_POOL)]
    made = GP.tickets_of("nfl", g, [], extra=picks + others, picks={GP._leg_id(l) for l in picks})
    assert made["wider_own"] == 3, made["wider_own"]
    assert len(made["threes"]) == GP.THREE_MIN, made
    # The tickets the picks make come first; the game's best props make up the
    # place they leave, around the pick still free (ZR).
    own = [sum(l["player"] in ("A One", "B Two", "C Three") for l in t["legs"]) for t in made["threes"]]
    assert own == [3, 2, 1] and made["props_filled"] == 1, (own, made["props_filled"])


def test_the_most_likely_boards_picks_stand_in_where_a_report_has_too_few():
    """BOARDFILL1: on the Thursday Sunday's props were bought, five Sunday games made no three-leg
    ticket: their reports carried 15 player picks, 5 of them legs (scorers and tackles are never legs),
    and a ticket takes two of the report's. The game's Most Likely picks at 60% or better stand in,
    on a ticket that clears 25%, each named; any other prop rides one a ticket beside
    two of the report's picks, or makes up the game's last tickets (ZR)."""
    g = GAME
    own = [_leg("A One", "receptions", 0.66)]                               # the report's one usable pick
    likely = [dict(_leg("B Two", "rush_att", 0.68, team="WAS", pos="RB"), pool="likely"),
              dict(_leg("C Three", "rec_yds", 0.66, pos="TE"), pool="likely"),
              dict(_leg("D Four", "receptions", 0.64, team="WAS"), pool="likely"),
              dict(_leg("E Five", "rush_yds", 0.62, pos="RB"), pool="likely")]
    mine = {GP._leg_id(l) for l in own}
    made = GP.tickets_of("nfl", g, own, extra=likely, picks=mine)
    assert len(made["threes"]) == GP.THREE_MIN and made["board_filled"] == GP.THREE_MIN, made
    said = f"for this game the report's card did not list, added so the game has {GP.THREE_MIN} three-leg parlays"
    for t in made["threes"]:
        assert float(t["joint"]) >= GP.THREE_FLOOR, t["joint"]
        assert any(said in c and "Most Likely pick" in c for c in t["caveats"]), t["caveats"]
    assert any("A One" in {l["player"] for l in t["legs"]} for t in made["threes"]), "the report's pick rides first"
    # The same props from any other source do not stand in for the report's
    # picks: they make up the game's tickets last, as its props (ZR), named so.
    priced = [dict(l, pool="priced") for l in likely]
    none = GP.tickets_of("nfl", g, own, extra=priced, picks=mine)
    assert none["board_filled"] == 0 and none["props_filled"] == len(none["threes"]) > 0, none
    assert all(not any("Most Likely pick" in c for c in t["caveats"]) for t in none["threes"])
    # Nor a Most Likely pick under 60%, nor a ticket under 25%: last, each named.
    weak = [dict(l, p=0.58) for l in likely]
    wk = GP.tickets_of("nfl", g, own, extra=weak, picks=mine)
    assert wk["board_filled"] == 0 and wk["props_filled"] == len(wk["threes"]) > 0, wk
    for t in wk["threes"]:
        assert any("under the 60% a leg is built to" in c for c in t["caveats"]), t["caveats"]
        assert float(t["joint"]) >= GP.THREE_FLOOR or any(c.startswith("A longer ticket") for c in t["caveats"])
    assert not GP.board_pick(dict(likely[0], p=0.59)) and GP.board_pick(likely[0]) and not GP.board_pick(priced[0])
    # A report with its two picks keeps to them: nothing stands in where the fill already made two.
    two = [_leg("A One", "receptions", 0.66), _leg("E Five", "rush_att", 0.66, team="WAS", pos="RB"),
           _leg("F Six", "rec_yds", 0.66, pos="TE"), _leg("G Seven", "receptions", 0.66, team="WAS")]
    full = GP.tickets_of("nfl", g, two, extra=likely, picks={GP._leg_id(l) for l in two})
    assert len(full["threes"]) >= GP.THREE_MIN and full["board_filled"] == 0, full
    # The heartbeat counts the tickets they stood in on, no pick named.
    import json
    import launch as L
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_parlays": {"games": [{"home": "A", "threes": [{"legs": []}, {"legs": []}], "threes_board_filled": 2}],
                              "counts": {"games": 1, "threes": 2}}}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            assert L._board_counts(path)["threes_board_filled"] == 2
        finally:
            L._full_copy = was


def _under(player, team, market, sport_game, p=0.72, line=0.5):
    home, away = sport_game["home"], sport_game["away"]
    return {"player": player, "team": team, "opponent": away if team == home else home, "home": home,
            "away": away, "market": market, "market_label": market, "side": "Under", "line": line,
            "odds": -220, "book": "FanDuel", "p": p, "game_date": "2099-11-18"}


def test_two_unders_in_one_game_share_a_ticket():
    """Two unders want the same quiet game, so they share a ticket (parlays.relate_prior, PARLAYWIN1).
    The pair was killed as a script clash, which kept a report's strongest picks off its parlays:
    Avalanche at Utah, 18 November, a report of seven unders and no three-leg ticket."""
    game = {"home": "UTA", "away": "COL", "date": "2099-11-18"}
    legs = [_under("MacKenzie Weegar", "UTA", "points", game), _under("Clayton Keller", "UTA", "goals", game),
            _under("Brock Nelson", "COL", "assists", game), _under("Artturi Lehkonen", "COL", "assists", game),
            _under("Michael Carcone", "UTA", "points", game)]
    made = GP.tickets_of("nhl", game, legs)
    assert len(made["threes"]) >= GP.THREE_MIN, made
    assert all(l["side"] == "Under" for t in made["threes"] for l in t["legs"])
    # Basketball: two teammates under on one stat split one pie and stay apart, as their overs do;
    # on two stats, or across the game, they pair.
    g = {"home": "DEN", "away": "BOS"}
    pts, pts2 = _under("A One", "DEN", "pts", g, 0.66, 18.5), _under("B Two", "DEN", "pts", g, 0.66, 9.5)
    assert not GP.pair_link("nba", pts, pts2, g)[0], "one pie"
    assert GP.pair_link("nba", pts, _under("B Two", "DEN", "reb", g, 0.66, 6.5), g)[0]
    assert GP.pair_link("nba", pts, _under("C Three", "BOS", "pts", g, 0.66, 20.5), g)[0]
    # An over beside an under still wants the game two ways.
    assert not GP.pair_link("nba", dict(pts, side="Over"), _under("C Three", "BOS", "pts", g, 0.66, 20.5), g)[0]
    # Two teammates' receiving unders: the shared-passing-game exception is for their overs.
    a = _leg("Malik Nabers", "rec_yds", 0.66, side="Under", line=70.5)
    b = _leg("Darius Slayton", "receptions", 0.66, side="Under", line=3.5)
    assert not GP.pair_link("nfl", a, b, GAME)[0]
    assert GP.pair_link("nfl", dict(a, side="Over"), dict(b, side="Over"), GAME)[0], "their overs still may"
    # Baseball's games are not in the count, so its unders stay apart.
    from engine import parlays as P
    m = {"home": "NYY", "away": "BOS"}
    k = dict(_under("Gerrit Cole", "NYY", "strikeouts", m, 0.62, 6.5), opponent="BOS")
    tb = _under("Rafael Devers", "BOS", "total_bases", m, 0.62, 1.5)
    assert P.relate("mlb", k, tb).verdict == "kill"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
