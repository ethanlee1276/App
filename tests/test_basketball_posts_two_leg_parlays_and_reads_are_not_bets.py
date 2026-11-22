"""Basketball posts three two-leg player-prop parlays a game; a pick on a market
we can rank but not price is a read, not a bet (ZT, 2026-11-20).

Ethan, 20 November, to the two questions put to him: "yes to both, do 2-leg nba
parlays and label the yardage picks". What these hold:

  * basketball's games (the NBA, college and the WNBA, whose books post no
    anytime scorer) post three two-leg player-prop tickets in the scorer
    pairs' place, each at TWO_FLOOR or better (two legs at 63%), built from
    the report's own picks, journaled and recorded like the three-leg ones.
    That evening they became every league's (TWO_SPORTS; Ethan: "we want 3
    two-leg parlays for each game report as well";
    tests/test_every_league_posts_three_two_leg_parlays.py), football and
    hockey keeping their scorer pairs beside them, and no league's are left
    off the record (`retired`);
  * the heartbeat counts them, the report draws them under their own heading,
    and the Record and Report Picks pages list the kind;
  * a player pick on a market our calibration does not trust (calibrate:
    the NFL's rushing and receiving yards are shut) says so wherever it
    shows: the report's card and reads say "a read, not a bet" with no price
    to take it at, Report Picks marks it and leaves it out of its counts, a
    finished game's card leaves it out of "Our picks", and the report book
    never journals it (one journaled before is taken off while still open; a
    graded one keeps its grade).

    python3 tests/test_basketball_posts_two_leg_parlays_and_reads_are_not_bets.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, parlayledger as PL, reportbets as RB  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
GAME = EG.GAME
HOOPS = ("pts", "reb", "ast", "threes", "pts", "reb", "ast", "pts")


def _uncapped(fn):
    """The NBA caps a leg at two of a game's parlays (step ABG; tests/test_an_nba_leg_rides_two_of_a_games_parlays.py).
    This fixture's five NBA legs at 60% or better fill its three-leg tickets twice over and leave the cap no
    room for a two-leg one, so the tests that count three of them read the build with the cap off."""
    import functools

    @functools.wraps(fn)
    def run(*a, **kw):
        was = os.environ.get("QB_GAME_LEG_CAP")
        os.environ["QB_GAME_LEG_CAP"] = "off"
        try:
            return fn(*a, **kw)
        finally:
            if was is None:
                os.environ.pop("QB_GAME_LEG_CAP", None)
            else:
                os.environ["QB_GAME_LEG_CAP"] = was
    return run


def _hoops_board():
    """The shared football fixture's eight Most Likely rows as basketball props."""
    b = EG.board()
    for r, m in zip(b["most_likely"], HOOPS):
        r["market"], r["market_label"] = m, m
    return b


def _js(name):
    return (ROOT / "web" / "js" / f"{name}.js").read_text(encoding="utf-8")


@_uncapped
def test_basketball_posts_three_two_leg_tickets_and_football_its_three_too():
    gp = GP.build(_hoops_board(), "nba")
    g = gp["games"][0]
    assert len(g["twos"]) == GP.TWO_PER_GAME == GP.TWO_MIN == 3, g.get("twos")
    assert all(len(t["legs"]) == 2 and t["joint"] >= GP.TWO_FLOOR for t in g["twos"]), \
        [t["joint"] for t in g["twos"]]
    assert len({GP.ident(t) for t in g["twos"]}) == 3, "three different tickets"
    assert len(g["threes"]) == 3 and gp["counts"]["twos"] == 3 and gp["counts"]["threes"] == 3
    assert g["scorers"] == [] and "scorers_note" not in g, "the pair slot holds the two-leg tickets"
    assert "3 two-leg" in GP.summary(gp), GP.summary(gp)
    for sport in ("cbb", "wnba"):
        assert len(GP.build(_hoops_board(), sport)["games"][0]["twos"]) == 3, sport
    # Every league since that evening (Ethan: "we want 3 two-leg parlays for each game report as well").
    nfl = GP.build(EG.board(), "nfl")
    assert len(nfl["games"][0]["twos"]) == 3 and nfl["counts"]["twos"] == 3, "football posts its three too"
    assert len(nfl["games"][0]["scorers"]) == 3, "beside its touchdown pairs, not in their place"
    assert not any(GP.retired("two", s) for s in GP.SPORTS) and GP.TWO_SPORTS == GP.SPORTS
    assert not GP.retired("three", "nfl") and not GP.retired("scorers", "nhl")


@_uncapped
def test_a_report_rebuilds_them_from_its_own_picks_and_keeps_them():
    b = _hoops_board()
    b["game_parlays"] = GP.build(b, "nba")
    picks = [{"player": r["player"], "team": r["team"], "market": r["market"], "side": r["side"].upper(),
              "line": r["line"], "sources": ["card"]} for r in b["most_likely"][:5]]
    GP.from_report(b, "nba", GAME, picks)
    GP.report_only(b)
    x = GP.for_game(b, "NYG", "WAS")
    assert len(x["twos"]) == 3, x.get("twos_note")
    mine = {(p["player"], p["market"]) for p in picks}
    assert all(any((l["player"], l["market"]) in mine for l in t["legs"]) for t in x["twos"]), \
        "every two-leg ticket stands on one of the report's picks"
    assert b["game_parlays"]["counts"]["twos"] == 3
    # Posted, so kept: the next build reads them back by identity, as the three-leg ones are.
    assert set(GP.POSTED_LISTS) == {"threes", "twos", "scorers"} and GP.POSTED_LISTS["twos"] == ("twos",)


def test_the_heartbeat_counts_them_in_every_league():
    import launch as L
    t2 = {"legs": [{"player": "A"}, {"player": "B"}]}
    t3 = {"legs": [{"player": "A"}, {"player": "B"}, {"player": "C"}]}

    def counts(sport, games, c):
        board = {"most_likely": [], "recommendations": [], "game_bets": [],
                 "game_parlays": {"sport": sport, "games": games, "counts": c}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            with open(path, "w") as fh:
                json.dump(board, fh)
            was = L._full_copy
            L._full_copy = lambda p: p
            try:
                return L._board_counts(path)
            finally:
                L._full_copy = was
    got = counts("nba", [{"home": "A", "threes": [t3] * 3, "twos": [t2] * 3, "scorers": []},
                         {"home": "B", "threes": [t3] * 3, "twos": [t2], "scorers": []},
                         {"home": "C", "threes": [], "twos": [], "scorers": [], "kept": "7:00 PM ET"},
                         {"home": "D", "threes": [], "twos": [], "scorers": [], "no_props": "props_not_bought"}],
                 {"games": 4, "threes": 6, "twos": 4, "filled_twos": 1, "scorers": 0})
    assert (got["sgp_twos"], got["twos_short"], got["twos_filled"]) == (4, 1, 1), got
    nfl = counts("nfl", [{"home": "A", "threes": [t3] * 3, "scorers": [t2] * 3}],
                 {"games": 1, "threes": 3, "scorers": 3})
    assert (nfl["sgp_twos"], nfl["twos_short"]) == (0, 1), "a football game with none is short of its three"


@_uncapped
def test_the_record_keeps_every_leagues_two_leg_tickets():
    from engine import ledger
    conn = ledger.connect(":memory:")
    PL.ensure_schema(conn)
    gp = GP.build(_hoops_board(), "nba")
    PL.log_game_parlays(conn, gp, "nba", "2099-11-12")
    assert conn.execute("SELECT count(*) FROM parlays WHERE source='game_two' AND sport='nba'").fetchone()[0] == 3
    # A football two-leg ticket from before the retirement, graded, as the journal still holds them.
    conn.execute("INSERT INTO parlays (sport, date, source, grade, status, pnl_units, at_start, legs_key) "
                 "SELECT 'nfl', date, source, 'DEN@KC', status, pnl_units, at_start, legs_key || 'x' "
                 "FROM parlays WHERE source='game_two' LIMIT 1")
    conn.execute("UPDATE parlays SET status='won', pnl_units=1.0, at_start=1 WHERE source='game_two'")
    rec = PL.game_parlay_record(conn)
    # Football's count again, the ones from before the day they were stopped included.
    assert rec["nfl"]["two"]["graded"] == 1 and rec["nfl"]["two"]["wins"] == 1, rec.get("nfl")
    two = rec["nba"]["two"]
    assert (two["graded"], two["wins"]) == (3, 3), two


def test_the_pages_carry_the_kind():
    record, reportpicks, report = _js("record"), _js("reportpicks"), _js("report")
    assert 'const GP_KINDS = ["three", "two", "scorers"];' in record
    assert '["Two-leg parlays", twos]' in reportpicks and 'sec("The two-leg parlays", rpTicketsHTML(twos, "twos", sport, game))' \
        in reportpicks
    assert 'kind === "two" ? `Two-leg parlay ${n}`' in report
    # A game that posts both sizes names both ("Three-leg parlay 1" beside "Two-leg parlay 1"); one whose
    # pair slot holds no scorer pairs heads its tickets "Parlays", not "Parlays and pairs".
    # One name everywhere since step ACG: every three-leg ticket says its size.
    assert 'const title = kind === "three" ? `Three-leg parlay ${n}` : kind === "two" ? `Two-leg parlay ${n}`' in report
    assert '${(tix.scorers || []).length ? "Parlays and pairs" : "Parlays"}' in reportpicks
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert '("twos", "Best two-leg parlay", likeliest)' in gr and '_h("Two-leg parlays")' in gr
    from engine import askbot
    said = " ".join(t["description"] for t in askbot.TOOLS if t["name"] == "our_picks")
    assert "three three-leg and three two-leg player-prop parlays" in said, said


# --- a read, not a bet ---------------------------------------------------------

def _row(market="rush_yds", bettable=False, **kw):
    return {"player": "Jayden Daniels", "team": "WAS", "opponent": "NYG", "home": "NYG", "away": "WAS",
            "position": "QB", "market": market, "market_label": market.replace("_", " "), "side": "OVER",
            "line": 24.5, "odds": -115, "book": "DraftKings", "model_prob": 0.66, "bettable": bettable,
            "game_date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00", **kw}


def test_a_matchup_pick_on_a_market_we_cannot_price_carries_the_flag():
    from engine import calibrate, matchpicks as MP
    assert not calibrate.is_reliable("nfl", "rec_yds") and not calibrate.is_reliable("nfl", "rush_yds")
    lines = [{"book": "DraftKings", "line": 49.5, "over_odds": -110, "under_odds": -110}]
    props = [{"player": "Stefon Diggs", "team": "WAS", "opponent": "NYG", "market": "rec_yds",
              "market_label": "Receiving Yards", "line": 49.5, "hit_prob": 0.64, "side": "over",
              "all_lines": lines},
             {"player": "Stefon Diggs", "team": "WAS", "opponent": "NYG", "market": "receptions",
              "market_label": "Receptions", "line": 49.5, "hit_prob": 0.60, "side": "over", "all_lines": lines}]
    read = {"player": "Stefon Diggs", "team": "WAS", "opp": "NYG", "pos": "WR", "read": "good",
            "lean": ["rec_yds", "receptions"], "usage": {"targets_pg": 7.0}}
    got = MP.prop_picks({"home": "NYG", "away": "WAS"}, [read], props, sport="nfl")
    assert got and got[0]["market"] == "rec_yds", got
    assert all(r["bettable"] is calibrate.is_reliable("nfl", r["market"]) for r in got), got
    assert got[0]["bettable"] is False


def test_the_bet_carries_the_word_and_the_report_says_it():
    from engine import gamereport as GR, gameresults as GRS
    assert GRS.bet_of(_row())["read_only"] is True
    assert "read_only" not in GRS.bet_of(_row(bettable=True))
    assert "read_only" not in GRS.bet_of(dict(_row(), kind="game", market="spread")), "never a game bet"
    assert GRS.read_bet({"player": "Jayden Daniels", "team": "WAS", "pick": _row()})["read_only"] is True
    said = GR.read_pick({"pick": _row()})
    assert said.startswith("A read, not a bet: Over 24.5 rush yds") and "take it at" not in said, said
    assert "a market we can rank but not price yet" in said
    assert GR.read_pick({"pick": _row(bettable=True)}).startswith("Most Likely pick: ")
    mp = dict(_row(), matchup_pick=True)
    assert GR.read_pick({"matchup_pick": mp}).startswith("A read, not a bet: ")
    assert GR.read_pick({"matchup_pick": dict(mp, held_note="held back: under the bar")}).startswith(
        "Matchup pick, held back: "), "held back says so first"
    assert GR.card_numbers(_row()) == "Our chance 66%", "no fair price, no play-to: our number cannot price it"
    assert GR.card_numbers(_row(bettable=True)).startswith("Our chance 66% · fair ")
    assert GR.read_only(_row()) and not GR.read_only(_row(bettable=True))
    assert not GR.read_only(dict(_row(), kind="game"))
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert '**({"read_only": READ_ONLY} if read_only(r) else {}),' in src, "on the card's pick"
    assert '" A read is graded on this page only."' in src and '"; every bet comes before a read. "' in src
    # The tag says "Read, not a bet"; the line under it says why, once, and a read wears no tier beside it.
    assert GR.READ_ONLY == "A market we can rank but not price yet, so it isn't counted on the record"
    assert '"tier": "" if read_only(r) else str(r.get("tier_label") or ""),' in src


def test_a_reads_stamped_pick_keeps_the_flag():
    """A matchup read's own Most Likely pick is a brief copy of the board's row (likely._pick_brief, stamped by
    gamescan.stamp_picks). It dropped ``bettable``, so a read's rushing-yards pick said "take it at" and went on
    the record as a bet; the copy keeps it now, so the read says what it is and the record passes it by."""
    from engine import gamereport as GR, gameresults as GRS
    from engine.likely import _pick_brief
    brief = _pick_brief(_row())
    assert brief["bettable"] is False and set(brief) >= {"player", "market", "side", "line", "odds", "model_prob"}
    read = {"player": "Jayden Daniels", "team": "WAS", "pick": brief}
    assert GR.read_pick(read).startswith("A read, not a bet: ") and "take it at" not in GR.read_pick(read)
    assert GRS.read_bet(read)["read_only"] is True
    assert _pick_brief(_row(bettable=True))["bettable"] is True


def test_a_read_never_takes_a_bets_place_on_the_card():
    """The card ranks four picks (six on a featured game), one a player: every bet comes before any read,
    so a market we cannot price never pushes a bet off the card and the record."""
    from types import SimpleNamespace
    from engine import gamereport as GR
    reads = [_row(player=f"Read {i}", model_prob=0.80 - i / 100) for i in range(4)]
    bets = [_row(market="receptions", bettable=True, player=f"Bet {i}", model_prob=0.62 - i / 100)
            for i in range(3)]
    c = SimpleNamespace(result={"likely_board": {"rows": reads + bets}}, teams=("NYG", "WAS"), featured=False)
    got = [r["player"] for r in GR._card_rows(c)]
    assert got == ["Bet 0", "Bet 1", "Bet 2", "Read 0"], got
    c.featured = True
    assert [r["player"] for r in GR._card_rows(c)] == ["Bet 0", "Bet 1", "Bet 2", "Read 0", "Read 1", "Read 2"]


def _sections(*bets):
    return [{"key": "card", "blocks": [{"type": "picks", "items": [{"bet": b} for b in bets]}]}]


def test_the_record_never_journals_a_read_and_takes_an_open_one_off():
    from engine import gameresults as GRS, ledger
    conn = ledger.connect(":memory:")
    read, bet = _row(), _row(market="receptions", bettable=True, player="Malik Nabers", team="NYG",
                             opponent="WAS", line=4.5)
    rows = RB.bets_of(_sections(GRS.bet_of(read), GRS.bet_of(bet)), RB.pool([read, bet], []))
    assert [r.get("read_only") for r in rows] == [True, None], rows
    board = {"date": "2099-W10", "games": [], RB.KEY: [dict(r, game="WAS@NYG") for r in rows]}
    assert RB.journal(conn, board, "nfl") == 1
    assert [r[0] for r in conn.execute("SELECT player FROM bets")] == ["Malik Nabers"], "the read is passed by"
    # Journaled before the report called it a read (as the NFL's yardage picks were): taken off while open.
    was = dict(rows[0], game="WAS@NYG")
    was.pop("read_only")
    assert RB.journal(conn, {"date": "2099-W10", "games": [], RB.KEY: [was]}, "nfl") == 1
    assert conn.execute("SELECT count(*) FROM bets WHERE player='Jayden Daniels'").fetchone()[0] == 1
    assert RB.journal(conn, board, "nfl") == 0
    assert conn.execute("SELECT count(*) FROM bets WHERE player='Jayden Daniels'").fetchone()[0] == 0
    # A graded one keeps its grade: what the record said stands.
    assert RB.journal(conn, {"date": "2099-W11", "games": [], RB.KEY: [was]}, "nfl") == 1
    conn.execute("UPDATE bets SET status='won' WHERE player='Jayden Daniels'")
    RB.journal(conn, board, "nfl")
    assert conn.execute("SELECT status FROM bets WHERE player='Jayden Daniels'").fetchone()[0] == "won"


def test_the_pick_census_counts_a_read_as_a_read():
    """What became of each report pick (gameparlays._picks_census, the heartbeat's pick_fates): a read is
    said as one, ahead of any other fate, since no ticket takes it."""
    b = EG.board()
    read = {"player": "Jayden Daniels", "team": "WAS", "market": "rush_yds", "side": "OVER", "line": 24.5,
            "read_only": True}
    bet = {"player": "Malik Nabers", "team": "NYG", "market": "receptions", "side": "OVER", "line": 4.5}
    got = GP._picks_census(b, "nfl", GAME, [read, bet])
    assert got.get("read") == 1 and sum(got.values()) == 2, got
    assert GP.PICK_FATES[0] == "read"


def test_the_pages_mark_a_read_and_leave_it_out_of_the_counts():
    rp, report, detail = _js("reportpicks"), _js("report"), _js("detail")
    assert 'const RP_READ = "Read, not a bet: a market we can rank but not price yet";' in rp
    assert "const st = rpBetsOnly(bets).map((b) => (R.grade(b) || {}).status);" in rp, "a finished game's tally"
    assert 'nReads ? plural(nReads, "read") : ""' in rp and "picks += rpBetsOnly(x.bets).length;" in rp
    assert '<span class="gr-pick-read">Read, not a bet</span>' in report and "gr-pick-readwhy" in report
    assert 'v.read_only ? " [a read, not a bet]" : ""' in report, "the copied text says it too"
    assert 'if (!r || (r.bettable === false && r.kind !== "game")) continue;' in detail
    css = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    assert ".gr-pick-read {" in css and ".gr-pick-readwhy {" in css
    # On Report Picks a read's chance is drawn muted, not the green of a pick we stake.
    assert "row.replace('class=\"hd-row', 'class=\"hd-row rpk-read')" in rp
    assert ".rpk-read .hd-p {" in (ROOT / "web" / "css" / "reportpicks.css").read_text(encoding="utf-8")
    ask = (ROOT / "engine" / "askbot.py").read_text(encoding="utf-8")
    assert '"read_not_a_bet"' in ask, "Ask says it too"


if __name__ == "__main__":
    import traceback
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
