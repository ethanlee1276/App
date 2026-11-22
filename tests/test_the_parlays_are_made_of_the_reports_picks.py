"""A game's parlays are made of its report's own picks (engine/gameparlays.from_report,
report_only; engine/gamereport.finish), GPLEGS1.

Ethan, 2026-11-17, two screenshots of How our reports did, Monday's NBA, picks
4 of 5 and parlays 0 of 3, picks 6 of 7 and parlays 1 of 6: "how are we
hitting so many picks without winning any parlays, but we're still using those
picks? That doesn't make any sense, so fix that."

They were not using those picks. A game's tickets were built before its
report, from every prop the board priced at 60% or better, and more than half
their legs were no pick of the report's (50 of Monday's 90 NBA legs; the
report's own picks hit 75% as legs, the others 62%; Rockets at Heat's tickets
each lost on a leg the report never picked). What these hold:

  * a game's three-leg tickets are built inside its report, from the picks the
    report shows, under every rule a leg kept (the 60% floor, the clash rules);
  * a report whose picks make fewer than two tickets fills up to two from the
    game's other priced props, its own picks first, each such ticket naming
    the legs it did not pick (THREELEG1, 2026-11-19: "I want those for every
    single game"); a game whose props make fewer still says why under the one
    it made;
  * a game no report rebuilt posts no three-leg ticket, a started game's kept
    tickets stand, and no later pass of the parlay hook builds them again;
  * end to end: a whole NFL report's parlays, and the board's, carry only the
    report's picks, though the board held likelier props the report never
    picked.

    python3 tests/test_the_parlays_are_made_of_the_reports_picks.py
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gameparlays as GP, gamereport as GR             # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)

GAME = EG.GAME


def _pick(player, market, side, line, team="NYG"):
    opp = "WAS" if team == "NYG" else "NYG"
    return {"player": player, "market": market, "side": side, "line": line, "team": team, "opponent": opp}


#: Five of the fixture's priced picks, the report's; Rachaad White's rushing and
#: Stefon Diggs's yards are the board's, never the report's.
PICKS = [_pick("Malik Nabers", "receptions", "OVER", 4.5),
         _pick("Jayden Daniels", "rush_yds", "OVER", 24.5, team="WAS"),
         _pick("Cam Skattebo", "rush_att", "OVER", 11.5),
         _pick("Isaiah Likely", "receptions", "OVER", 3.5),
         _pick("Chig Okonkwo", "receptions", "OVER", 2.5, team="WAS")]


def _built():
    b = EG.board()
    b["game_parlays"] = GP.build(b, "nfl")
    return b


def _legs(x, key="threes"):
    return [l for t in x.get(key) or [] for l in t["legs"]]


def test_the_board_alone_reaches_past_the_reports_picks():
    """The fixture's board, as every board was built: its tickets take legs the
    report never picked. What the rest of these tests change."""
    b = _built()
    picked = {GP._pick_key(p) for p in PICKS}
    others = [l for l in _legs(GP.for_game(b, "NYG", "WAS")) if GP._pick_key(l) not in picked]
    assert others, "the board's own build reaches past the picks"


def test_a_games_tickets_are_its_reports_picks_and_nothing_else():
    b = _built()
    x = GP.from_report(b, "nfl", GAME, PICKS)
    assert x is GP.for_game(b, "NYG", "WAS") and x["legs_from"] == GP.LEGS_FROM_REPORT
    assert x["report_picks"] == 5 and x["threes"], x.get("threes_note")
    picked = {GP._pick_key(p) for p in PICKS}
    for t in x["threes"]:
        assert all(GP._pick_key(l) in picked for l in t["legs"]), [l["player"] for l in t["legs"]]
        assert len({l["player"] for l in t["legs"]}) == 3, "the clash rules still hold"
        for bk in t.get("backups") or []:
            assert GP._pick_key(bk["leg"]) in picked, "a backup is a report pick too"
    # Each leg keeps the chance the board gave it, and its ticket the joint of those.
    every = {GP._pick_key(l): l for l in GP.legs_for(EG.board(), "nfl")}
    for l in _legs(x):
        assert abs(float(l["p"]) - float(every[GP._pick_key(l)]["p"])) < 1e-9
    # The scorer pairs are the touchdown research's own, as built.
    assert x["scorers"] == GP.for_game(_built(), "NYG", "WAS")["scorers"]


def test_a_pick_matches_its_leg_however_the_side_is_spelled():
    assert GP._pick_key({"player": "Malik Nabers", "market": "Receptions", "side": "Over", "line": "4.5"}) == \
        GP._pick_key({"player": "Malik  Nabers", "market": "receptions", "side": "OVER", "line": 4.5})
    assert GP._pick_key({"player": "A", "market": "anytime_td", "side": "Yes", "line": 0.5})[2] == "OVER"


def test_too_few_picks_fill_from_the_games_other_props_and_say_so():
    b = _built()
    x = GP.from_report(b, "nfl", GAME, PICKS[:2])
    picked = {GP._pick_key(p) for p in PICKS[:2]}
    assert len(x["threes"]) == GP.THREE_MIN and x.get("threes_filled") == GP.THREE_MIN, x.get("threes_note")
    assert "threes_note" not in x
    # The report's picks first: both on the first two tickets (a leg rides on
    # MAX_USES tickets at most), and the game's Most Likely picks make up the
    # third, each named (ZR: "the 3 best parlays possible with the data we have").
    mine = [[l for l in t["legs"] if GP._pick_key(l) in picked] for t in x["threes"]]
    assert [len(m) for m in mine] == [2, 2, 0], [[l["player"] for l in m] for m in mine]
    assert GP.MAX_USES == 2 and x.get("threes_board_filled") == 1, x.get("threes_board_filled")
    assert "(70%), Cam Skattebo over 11.5 rush attempts (67%) and Rachaad White" in x["threes"][2]["caveats"][-1]
    for t in x["threes"]:
        assert any("this report's picks: " in c for c in t["caveats"]), t["caveats"]
    # A pick under the floor is no leg: Daniels's completions under, at 55%.
    low = GP.from_report(_built(), "nfl", GAME, PICKS[:2] + [_pick("Jayden Daniels", "pass_cmp", "UNDER", 19.5,
                                                                   team="WAS")])
    assert low["legs_read"] == 2 and len(low["threes"]) == GP.THREE_MIN, low
    # None at all on a player's line (a game bet only): the Most Likely board's
    # picks for the game stand in (BOARDFILL1, 2026-11-19: five of the NFL's
    # Sunday games had no ticket, their reports' picks scorers, tackles and game
    # lines), at 60% or better, on a ticket that clears 25%, each one named.
    game_bet = [{"player": "NYG", "market": "moneyline", "side": "NYG", "game": True}]
    none = GP.from_report(_built(), "nfl", GAME, game_bet)
    assert none["threes"] and none["threes_board_filled"] == len(none["threes"]), none.get("threes_note")
    for t in none["threes"]:
        assert all(l.get("pool") == "likely" and float(l["p"]) >= GP.LEG_FLOOR for l in t["legs"]), t["legs"]
        assert t["fill"] == "board", t.get("fill")
        assert float(t["joint"]) >= GP.THREE_FLOOR, t["joint"]
        assert any("Most Likely picks for this game the report's card did not list" in c for c in t["caveats"]), \
            t["caveats"]
    # Any other prop the board priced does not stand in for the report's picks
    # (PARLAYWIN1: the tickets that lost carried two or three of them): where
    # neither makes a ticket, the game's best props make its three, last, each
    # leg named (ZR, Ethan: "the 3 best parlays possible with the data we have").
    was_all = GP._board_legs
    GP._board_legs = lambda board, sp, now=None, **kw: [dict(l, pool="priced") for l in was_all(board, sp, now, **kw)]
    try:
        bare = GP.from_report(_built(), "nfl", GAME, game_bet)
    finally:
        GP._board_legs = was_all
    assert len(bare["threes"]) == GP.THREE_MIN and bare["threes_props_filled"] == GP.THREE_MIN, bare
    assert "threes_board_filled" not in bare and "threes_note" not in bare
    for t in bare["threes"]:
        assert any("props the board priced, added so the game has 3 three-leg parlays" in c for c in t["caveats"])
        assert t["fill"] == "props", t.get("fill")
    # A game whose props make one ticket posts it, and the note says why there is no second.
    keys3 = {GP._pick_key(p) for p in PICKS[:3]}
    was_legs = GP._board_legs
    GP._board_legs = lambda board, sp, now=None, **kw: [l for l in was_legs(board, sp, now, **kw)
                                                        if GP._pick_key(l) in keys3]
    try:
        three = GP.from_report(_built(), "nfl", GAME, PICKS[:3])
    finally:
        GP._board_legs = was_legs
    # Three legs make one trio: no more to make, whatever a leg rides on.
    assert len(three["threes"]) == 1 and three["threes_note"] == (
        "1 of 3: this report's picks (3 of its 3 picks are at 60% or better) make no other three-leg ticket "
        "without a conflict that reaches 15% by our numbers"), three.get("threes_note")
    # ...and the report says it under the ticket it made, on the page and in the report's section.
    import types
    was = GR._game_parlays
    GR._game_parlays = lambda c: three
    try:
        sec = GR.sec_parlays(types.SimpleNamespace(sport="nfl", result={}))
    finally:
        GR._game_parlays = was
    texts = [b.get("text") for b in sec["blocks"] if isinstance(b, dict)]
    kinds = [b.get("type") for b in sec["blocks"] if isinstance(b, dict)]
    said = GR._p(three["threes_note"])["text"]
    assert said in texts and kinds.index("parlays") < texts.index(said), sec
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    body = js[js.index("function gameTickets("):js.index("finally { RESULTS = was;")]
    assert '+ (g.threes_note ? `<p class="gr-note">${escapeHtml(g.threes_note)}</p>` : "")' in body


def test_an_entry_from_a_league_on_paper_posts_the_reports_tickets():
    """The three-leg hold is retired (THREELEG1): an entry built while its league
    was on paper posts the report's tickets on its next rebuild."""
    b = _built()
    x = GP.for_game(b, "NYG", "WAS")
    x.update(paper_threes=x.pop("threes"), threes=[], threes_paper=True, threes_note="On paper.")
    GP.from_report(b, "nfl", GAME, PICKS)
    assert x["threes"] and "paper_threes" not in x and "threes_paper" not in x and "threes_note" not in x
    picked = {GP._pick_key(p) for p in PICKS}
    assert all(GP._pick_key(l) in picked for l in _legs(x))


def test_a_game_no_report_rebuilt_posts_none_and_kept_tickets_stand():
    b = _built()
    other = copy.deepcopy(GP.for_game(b, "NYG", "WAS"))
    other.update(game="DAL@PHI", home="PHI", away="DAL")
    kept = copy.deepcopy(other)
    kept.update(game="KC@BUF", home="BUF", away="KC", kept=True)
    b["game_parlays"]["games"] += [other, kept]
    GP.from_report(b, "nfl", GAME, PICKS)
    n_kept = len(kept["threes"])
    assert GP.report_only(b) == 1
    assert other["threes"] == [] and other["threes_note"] == GP.NO_REPORT_NOTE
    assert len(kept["threes"]) == n_kept and "legs_from" not in kept, "a started game's kept tickets stand"
    assert b["game_parlays"]["from_reports"] and b["game_parlays"]["counts"]["threes"] == \
        len(GP.for_game(b, "NYG", "WAS")["threes"]) + n_kept
    # A later pass of the hook (college's, after its report) builds nothing.
    before = copy.deepcopy(b["game_parlays"])
    GP.attach(b, "nfl")
    assert b["game_parlays"] == before
    # A started game's kept entry is never rebuilt by a report either.
    assert GP.from_report(b, "nfl", {"home": "BUF", "away": "KC"}, PICKS) is kept and len(kept["threes"]) == n_kept


# --- end to end: a whole NFL report ----------------------------------------------------------------
NFL_GAME = {"home": "DET", "away": "GB", "date": "2099-10-25", "kickoff": "13:00", "spread": -2.5,
            "total": 47.5, "scan": {}}


def _row(player, team, market, label, line, prob, tier, odds, pos):
    opp = "GB" if team == "DET" else "DET"
    return {"kind": "prop", "player": player, "team": team, "opponent": opp, "home": "DET", "away": "GB",
            "position": pos, "market": market, "market_label": label, "side": "OVER", "line": line,
            "model_prob": prob, "tier": tier, "tier_label": {"top": "Top pick", "strong": "Strong"}[tier],
            "book": "DraftKings", "odds": odds, "game_date": "2099-10-25",
            "kickoff": "2099-10-25T13:00:00-04:00"}


def _priced(player, team, market, line, p, odds, pos):
    opp = "GB" if team == "DET" else "DET"
    return {"player": player, "team": team, "opponent": opp, "home": "DET", "away": "GB", "position": pos,
            "market": market, "side": "OVER", "line": line, "odds": odds, "book": "FanDuel", "hit_prob": p,
            "has_market": True, "recommended": False, "game_date": "2099-10-25",
            "kickoff": "2099-10-25T13:00:00-04:00", "reasons": [f"Projection clears {line}"]}


def _nfl_result():
    rows = [_row("Amon-Ra St. Brown", "DET", "receptions", "Receptions", 5.5, 0.72, "top", -220, "WR"),
            _row("Tucker Kraft", "GB", "receptions", "Receptions", 3.5, 0.78, "top", -240, "TE"),
            _row("Jahmyr Gibbs", "DET", "rush_yds", "Rushing Yards", 59.5, 0.66, "strong", -180, "RB"),
            _row("Romeo Doubs", "GB", "receptions", "Receptions", 2.5, 0.68, "strong", -200, "WR"),
            _row("Sam LaPorta", "DET", "receptions", "Receptions", 2.5, 0.70, "strong", -210, "TE")]
    # Likelier than every pick on the card, and none of them the report's.
    priced = [_priced("Josh Jacobs", "GB", "rush_att", 13.5, 0.80, -220, "RB"),
              _priced("Jared Goff", "DET", "pass_cmp", 19.5, 0.79, -230, "QB"),
              _priced("Jameson Williams", "DET", "rec_yds", 24.5, 0.77, -210, "WR")]
    result = {"date": "2099-W08", "games": [NFL_GAME], "likely_board": {"rows": rows, "held": []},
              "most_likely": [dict(r) for r in rows], "recommendations": priced, "scan_reads": {}}
    return result, priced


def test_end_to_end_a_reports_parlays_are_its_own_picks():
    # This game is in 2099, far before its post time (step ABD), so its report would say when its parlays
    # post (tests/test_a_game_report_says_what_the_board_posts.py); the tickets are read with that off.
    # Its picks wait the same way (step ABQ, tests/test_a_reports_picks_post_once_and_never_change.py): read with
    # that off too.
    import os
    was = {k: os.environ.get(k) for k in ("QB_PARLAY_POST_LATE", "QB_REPORT_PICKS_POST")}
    os.environ["QB_PARLAY_POST_LATE"] = os.environ["QB_REPORT_PICKS_POST"] = "off"
    try:
        _end_to_end()
    finally:
        for k, v in was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _end_to_end():
    result, priced = _nfl_result()
    result["game_parlays"] = GP.build(result, "nfl")
    others = {GP._pick_key(dict(p, side="OVER")) for p in priced}
    assert others & {GP._pick_key(l) for l in _legs(GP.for_game(result, "DET", "GB"))}, \
        "built on the board alone, the tickets take the props the report never picked"
    rep = GR.build(NFL_GAME, result, sport="nfl", names={"GB": "Packers", "DET": "Lions"})
    picks = {GP._pick_key(b) for b in rep.get("_bets") or []}
    assert len(picks) >= 3, rep.get("_bets")
    x = GP.for_game(result, "DET", "GB")
    assert x["legs_from"] == GP.LEGS_FROM_REPORT and x["threes"], x.get("threes_note")
    assert all(GP._pick_key(l) in picks for l in _legs(x)), [l["player"] for l in _legs(x)]
    assert not others & {GP._pick_key(l) for l in _legs(x)}
    # The report's own parlays section, and the card's parlay line, say those tickets.
    sec = next(s for s in rep["sections"] if s["key"] == "parlays")
    shown = [blk for blk in sec["blocks"] if blk.get("type") == "parlays" and blk.get("kind") == "three"]
    assert shown and len(shown[0]["items"]) == len(x["threes"])
    for item, t in zip(shown[0]["items"], x["threes"]):
        assert [l["player"] for l in item["legs"]] == [l["player"] for l in t["legs"]]
    card = next(s for s in rep["sections"] if s["key"] == "card")
    words = str(card)
    assert all(l["player"] in words for l in x["threes"][0]["legs"]), "the card's parlay line is the first ticket"
    assert not any(p["player"] in words for p in priced), "no pick the report did not make"
    # Its place in the report is where the parlays always stood (after the watch, before the weather).
    keys = [s["key"] for s in rep["sections"]]
    assert keys.index("parlays") > keys.index("card")


def test_a_game_s_label_on_a_pick_is_not_the_game_bet_flag():
    """A report's item flags a game bet ``game: True``; a row lifted onto the board carries its game's label
    under the same key ("WAS@NYG", reportbets.attach). Read as the flag, a label dropped every pick of the
    report, and each ticket named all three of its legs as no pick of the report's (seen in a preview render,
    19 November: the live path passes rows before the label is added)."""
    assert GP._player_pick({"player": "A", "market": "receptions", "game": "WAS@NYG"})
    assert GP._player_pick({"player": "A", "market": "receptions"})
    assert not GP._player_pick({"player": "NYG", "market": "moneyline", "game": True})
    assert not GP._player_pick({"player": "NYG", "market": "spread", "kind": "game"})
    assert not GP._player_pick({"player": "A"}) and not GP._player_pick(None)
    src = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")
    assert src.count("for b in picks or [] if _player_pick(b)}") == 2, "the rebuild and the census read one rule"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
