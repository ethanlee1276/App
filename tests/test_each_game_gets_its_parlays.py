"""Each game gets three 3-leg parlays (two at least, THREELEG1) and three 2-leg
touchdown parlays, built the way Ethan's own reports build them
(engine/gameparlays, 2026-11-14; Ethan, 2026-11-19: "We need 2 3-leg parlays,
or maybe 2 to 3 3-leg parlays on the game reports").

Ethan, 2026-11-14: "we need to make 3-leg or 2-leg same game parlays ... we
throw like 8 legs in it and it's unrealistic ... making sure no legs have
conflicts and backups"; "for each game, when it comes to every sport, I want
you to make 4 3-leg parlays and 3 2-leg touchdown parlays for each game";
and of his Commanders–Giants touchdown pair: "Isaiah Likely and Cam
Skattebo ... the Commanders ... one of the worst in the league against
guarding tight ends ... a rainy game and they were probably going to run
more than pass, and he's a good red zone usage ... that bet won".

The fixture is that game, Thursday 12 November, with the board's own kind
of rows.

    python3 tests/test_each_game_gets_its_parlays.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gameparlays as GP                # noqa: E402


#: The matchup scan's numbers for the game (engine/gamescan): each defence's
#: rank against the pass and the run, and red-zone trips both ways — what the
#: touchdown pairs' research reads (gameparlays.research, 2026-11-14).
SCAN = {"n_teams": 32,
        "units": {"WAS": {"def": {"passing": {"rank": 27}, "rushing": {"rank": 22}}},
                  "NYG": {"def": {"passing": {"rank": 12}, "rushing": {"rank": 18}}}},
        "redzone": {"NYG": {"off": 3.1, "off_rel": 0.08, "def": 2.9, "def_rel": 0.02},
                    "WAS": {"off": 3.2, "off_rel": 0.10, "def": 3.3, "def_rel": 0.12}}}
GAME = {"home": "NYG", "away": "WAS", "date": "2099-11-12", "kickoff": "20:15", "spread": -2.5, "total": 40.5,
        "scan": SCAN}


def _ml(player, team, pos, market, side, line, p, odds, label):
    opp = "WAS" if team == "NYG" else "NYG"
    return {"player": player, "team": team, "opponent": opp, "home": "NYG", "away": "WAS", "position": pos,
            "market": market, "market_label": label, "side": side, "line": line, "odds": odds, "book": "DraftKings",
            "model_prob": p, "game_date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00",
            "reasons": [f"Projection clears {line} in most of our simulated games"]}


def _td(player, team, pos, p, odds, reasons=()):
    opp = "WAS" if team == "NYG" else "NYG"
    return {"player": player, "team": team, "opponent": opp, "position": pos, "market": "anytime_td",
            "side": "Over", "line": 0.5, "model_prob": p, "odds": odds, "book": "FanDuel", "home": "NYG",
            "away": "WAS", "game_date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00",
            "reasons": list(reasons)}


def board():
    return {
        "date": "2099-W10", "games": [GAME],
        "most_likely": [
            _ml("Malik Nabers", "NYG", "WR", "receptions", "Over", 4.5, 0.72, -250, "Receptions"),
            _ml("Jayden Daniels", "WAS", "QB", "rush_yds", "Over", 24.5, 0.68, -200, "Rushing Yards"),
            _ml("Cam Skattebo", "NYG", "RB", "rush_att", "Over", 11.5, 0.67, -200, "Rush Attempts"),
            _ml("Isaiah Likely", "NYG", "TE", "receptions", "Over", 3.5, 0.70, -225, "Receptions"),
            _ml("Chig Okonkwo", "WAS", "TE", "receptions", "Over", 2.5, 0.66, -190, "Receptions"),
            _ml("Stefon Diggs", "WAS", "WR", "rec_yds", "Over", 29.5, 0.665, -225, "Receiving Yards"),
            _ml("Rachaad White", "WAS", "RB", "rush_yds", "Over", 29.5, 0.62, -226, "Rushing Yards"),
            _ml("Jayden Daniels", "WAS", "QB", "pass_cmp", "Under", 19.5, 0.551, -119, "Completions"),
        ],
        "td_field": [
            _td("Cam Skattebo", "NYG", "RB", 0.45, 130,
                ["Team implied total 21.5 → 2.60 expected offensive TDs", "Goal-line work: 6 carries inside the 5",
                 "Red-zone touch share ~38% (3.1 expected chances)"]),
            _td("Malik Nabers", "NYG", "WR", 0.36, 165, ["Red-zone touch share ~22% (1.8 expected chances)"]),
            _td("Isaiah Likely", "NYG", "TE", 0.30, 210, ["Red-zone touch share ~24% (1.9 expected chances)"]),
            _td("Rachaad White", "WAS", "RB", 0.30, 165),
            _td("Jayden Daniels", "WAS", "QB", 0.12, 260),
        ],
        # (Reads carry their usage and touchdown stamp since 2026-11-14: the
        # touchdown pairs are chosen on that research, gameparlays.research.)
        "scan_reads": {"WAS@NYG": {"players": [
            {"player": "Isaiah Likely", "team": "NYG", "opp": "WAS", "pos": "TE", "read": "good",
             "label": "Good matchup", "usage": {"tgt_share": 0.20},
             "td": {"model_prob": 0.30, "odds": 210, "implied_total": 21.5, "rz_chances": 1.9},
             "pro": ["WAS gives up the 4th-most receiving yards to tight ends (68.8 a game)"],
             "notes": ["WAS gives up the 2nd-most touchdowns to tight ends (1.0 a game)"]},
            {"player": "Cam Skattebo", "team": "NYG", "opp": "WAS", "pos": "RB", "read": "good",
             "label": "Good matchup", "usage": {"carry_share": 0.62},
             "td": {"model_prob": 0.45, "odds": 130, "implied_total": 21.5, "rz_chances": 3.1},
             "pro": ["Rain is 74% likely at kickoff: teams run more in rain and a back keeps his share, about "
                     "6% more carries (measured, 2016-2025)"], "notes": []},
            {"player": "Malik Nabers", "team": "NYG", "opp": "WAS", "pos": "WR", "read": "neutral",
             "label": "Neutral", "usage": {"tgt_share": 0.27},
             "td": {"model_prob": 0.36, "odds": 165, "implied_total": 21.5, "rz_chances": 1.8},
             "pro": [], "notes": []},
            {"player": "Rachaad White", "team": "WAS", "opp": "NYG", "pos": "RB", "read": "neutral",
             "label": "Neutral", "usage": {"carry_share": 0.45},
             "td": {"model_prob": 0.30, "odds": 165, "implied_total": 19.0, "rz_chances": 1.2},
             "pro": [], "notes": []}]}},
    }


def test_three_three_leg_parlays_with_no_conflict():
    gp = GP.build(board(), "nfl")
    g = gp["games"][0]
    assert GP.THREE_PER_GAME == 3 and GP.THREE_MIN == 2
    assert g["game"] == "WAS@NYG" and len(g["threes"]) == 3, (len(g["threes"]), g.get("threes_note"))
    for t in g["threes"]:
        names = [l["player"] for l in t["legs"]]
        assert len(names) == 3 and len(set(names)) == 3, "no player twice"
        mk = {(l["player"], l["market"]) for l in t["legs"]}
        # (Pin updated 2026-11-14: his carries want the Giants ahead and
        # Nabers's catches want them chasing. They were never one ticket, and
        # that refused Ethan's own; they may share one now, priced as
        # unrelated, and the ticket says the scripts pull apart.)
        if {("Cam Skattebo", "rush_att"), ("Malik Nabers", "receptions")} <= mk:
            assert any("scripts pull apart" in c for c in t["caveats"]), t["caveats"]
            assert t["script"].startswith("a close game"), t["script"]
        assert t["take"] > t["fair"] if t["fair"] > 0 else True
        assert 0 < t["joint"] < 1 and t["script"]
        assert not t["staked"] and t["stake_units"] == 0.0, "tracked, never staked"
    # Three tickets, each its own: no two the same, no leg on more than two.
    ids = [{GP._leg_id(l) for l in t["legs"]} for t in g["threes"]]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            assert ids[i] != ids[j]
    from collections import Counter
    assert max(Counter(x for i in ids for x in i).values()) <= GP.MAX_USES
    # Two Giants receivers can share a ticket, saying both need the passing game.
    both = [t for t in g["threes"] if {"Malik Nabers", "Isaiah Likely"} <= {l["player"] for l in t["legs"]}]
    for t in both:
        assert any("passing game" in c for c in t["caveats"]), t["caveats"]
    assert all(t.get("backups") is not None for t in g["threes"])


def test_his_own_ticket_is_built_and_priced():
    """Ethan's report: Nabers 5+ receptions (max -250) + Skattebo 12+ rush
    attempts (max -200) + Daniels 25+ rush yds (max -250), "~32-33% with
    mildly positive correlation, so the fair price is ≈ +205". The first cut
    refused it: the back's carries and the receiver's catches want opposite
    Giants leads. Now it is priced, the pair as unrelated, and said."""
    b = board()
    legs = {(l["player"], l["market"]): l for l in GP.enrich(GP.legs_for(b, "nfl"), b)}
    trio = [legs[("Malik Nabers", "receptions")], legs[("Cam Skattebo", "rush_att")],
            legs[("Jayden Daniels", "rush_yds")]]
    t = GP.ticket("nfl", trio, GAME)
    assert t is not None, "his ticket"
    indep = 0.72 * 0.67 * 0.68
    assert indep - 0.001 <= t["joint"] < indep + 0.03, (t["joint"], indep)     # only the two 0.10 floors lift it
    assert any("scripts pull apart" in c for c in t["caveats"]), t["caveats"]
    assert t["script"].startswith("a close game") and 0 < t["script_chance"] < 1, t
    # A leg that needs points beside one that needs a quiet game is still refused.
    under = dict(legs[("Malik Nabers", "receptions")], player="Daniel Jones", position="QB", market="pass_yds",
                 side="Under", line=199.5, p=0.66)
    over = dict(legs[("Jayden Daniels", "rush_yds")], player="Jayden Daniels", position="QB", market="pass_yds",
                side="Over", line=210.5, p=0.66)
    ok, _rho, why, _cav = GP.pair_link("nfl", under, over, GAME)
    assert not ok, why


def _rec(player, team, pos, market, side, line, p, odds, book="DraftKings", **kw):
    opp = "WAS" if team == "NYG" else "NYG"
    r = {"player": player, "team": team, "opponent": opp, "home": "NYG", "away": "WAS", "position": pos,
         "market": market, "side": side, "line": line, "odds": odds, "book": book, "hit_prob": p,
         "has_market": True, "recommended": False, "game_date": "2099-11-12",
         "kickoff": "2099-11-12T20:15:00-05:00", "reasons": [f"Projection clears {line}"]}
    r.update(kw)
    return r


def test_every_priced_prop_is_a_leg_inside_the_cap():
    """The first NFL board built on the posted picks alone counted 13, then
    14, three-leg tickets across 13 games: about six posted picks a game.
    Every prop the board priced at a named book is a leg now, at our own
    chance, inside the Most Likely cap."""
    b = {"date": "2099-W10", "games": [GAME],
         "most_likely": [_ml("Malik Nabers", "NYG", "WR", "receptions", "Over", 4.5, 0.72, -250, "Receptions"),
                         _ml("Jayden Daniels", "WAS", "QB", "rush_yds", "Over", 24.5, 0.68, -200, "Rushing Yards")],
         "recommendations": [
             _rec("Cam Skattebo", "NYG", "RB", "rush_att", "Over", 11.5, 0.67, -200),
             _rec("Isaiah Likely", "NYG", "TE", "receptions", "Over", 3.5, 0.70, -225),
             _rec("Chig Okonkwo", "WAS", "TE", "receptions", "Over", 2.5, 0.66, -190),
             _rec("Stefon Diggs", "WAS", "WR", "rec_yds", "Over", 29.5, 0.665, -225),
             _rec("Terry McLaurin", "WAS", "WR", "receptions", "Over", 2.5, 0.80, -400),     # past the cap
             _rec("Rachaad White", "WAS", "RB", "rush_yds", "Over", 29.5, 0.64, -180, book="proxy"),
             _rec("Wan'Dale Robinson", "NYG", "WR", "receptions", "Over", 3.5, 0.66, -170,
                  injury_status="OUT"),
             _rec("Daniel Jones", "NYG", "QB", "pass_yds", "Over", 199.5, 0.52, -115)]}  # under the floor
    legs = {l["player"] for l in GP.legs_for(b, "nfl")}
    assert {"Cam Skattebo", "Isaiah Likely", "Chig Okonkwo", "Stefon Diggs"} <= legs, legs
    assert not legs & {"Terry McLaurin", "Rachaad White", "Wan'Dale Robinson", "Daniel Jones"}, legs
    g = GP.build(b, "nfl")["games"][0]
    assert len(g["threes"]) == GP.THREE_PER_GAME, (len(g["threes"]), g.get("threes_note"))
    assert len(GP.build(dict(b, recommendations=[]), "nfl")["games"][0]["threes"]) == 0, \
        "two posted picks alone make no three-leg ticket"


def test_the_rows_the_most_likely_seats_dropped_are_legs_and_built_once():
    """Live, with every posted number in the pool, the NFL board counted 28
    three-leg tickets across 13 games: a posted number is mostly a main line,
    where our chance rarely reaches the floor. A prop's likeliest number on
    its ladder is what the Most Likely board computes for every prop and
    seats eight a market; the rest ride on the board for the Pick of the Day
    (`potd.POOL_KEY`). They are legs now."""
    from engine.potd import POOL_KEY
    b = {"date": "2099-W10", "games": [GAME],
         "most_likely": [_ml("Malik Nabers", "NYG", "WR", "receptions", "Over", 4.5, 0.72, -250, "Receptions"),
                         _ml("Jayden Daniels", "WAS", "QB", "rush_yds", "Over", 24.5, 0.68, -200, "Rushing Yards")],
         POOL_KEY: [_ml("Cam Skattebo", "NYG", "RB", "rush_att", "Over", 11.5, 0.67, -200, "Rush Attempts"),
                    _ml("Isaiah Likely", "NYG", "TE", "receptions", "Over", 3.5, 0.70, -225, "Receptions"),
                    _ml("Chig Okonkwo", "WAS", "TE", "receptions", "Over", 2.5, 0.66, -190, "Receptions"),
                    _ml("Stefon Diggs", "WAS", "WR", "rec_yds", "Over", 29.5, 0.665, -225, "Receiving Yards"),
                    dict(_ml("Terry McLaurin", "WAS", "WR", "receptions", "Over", 2.5, 0.75, -200, "Receptions"),
                         bettable=False)]}
    legs = {l["player"] for l in GP.legs_for(b, "nfl")}
    assert {"Cam Skattebo", "Isaiah Likely", "Chig Okonkwo", "Stefon Diggs"} <= legs and "Terry McLaurin" not in legs
    GP.attach(b, "nfl")
    first = b["game_parlays"]
    assert first.get("pooled") and len(first["games"][0]["threes"]) == GP.THREE_PER_GAME, \
        first["games"][0].get("threes_note")
    # College builds them again after the Pick of the Day has taken the pool:
    # the build made with it stands.
    b.pop(POOL_KEY)
    GP.attach(b, "nfl")
    assert b["game_parlays"] is first
    # A board that never had the pool builds as before.
    c = {k: v for k, v in b.items() if k != "game_parlays"}
    GP.attach(c, "nfl")
    assert not c["game_parlays"].get("pooled")


def test_three_touchdown_pairs_with_his_reasons():
    gp = GP.build(board(), "nfl")
    pairs = gp["games"][0]["scorers"]
    assert len(pairs) == 3
    from collections import Counter
    assert max(Counter(l["player"] for t in pairs for l in t["legs"]).values()) <= GP.MAX_USES
    legs = {l["player"]: l for t in pairs for l in t["legs"]}
    sk = " | ".join(legs["Cam Skattebo"]["why"])
    assert "Goal-line work" in sk and "rain" in sk.lower(), sk
    assert all(l["player"] != "Jayden Daniels" for t in pairs for l in t["legs"]), "12% is under the scorer bar"
    # (Added 2026-11-14.) White is priced at 30% and has no research case:
    # 19 expected points, a run defence 18th, a 45% share — 3 of 13.
    assert all(l["player"] != "Rachaad White" for t in pairs for l in t["legs"]), "no research case, no leg"
    assert all(l.get("research", 0) >= GP.RESEARCH_MIN for t in pairs for l in t["legs"])
    assert "WAS’s run defense ranks 22nd of 32" in sk, sk
    # His pair, asked directly: two Giants scorers, priced as unrelated, the
    # caveat that both need the Giants to score twice, and Likely's reason
    # the defence's touchdowns to tight ends.
    b = board()
    sc = {l["player"]: l for l in GP.enrich(GP.scorer_legs(b, "nfl"), b)}
    t = GP.ticket("nfl", [sc["Cam Skattebo"], sc["Isaiah Likely"]], GAME)
    assert t and abs(t["joint"] - 0.45 * 0.30) < 0.002, t and t["joint"]
    assert any("share NYG's scoring" in c for c in t["caveats"]), t["caveats"]
    assert "touchdowns to tight ends" in " | ".join(sc["Isaiah Likely"]["why"])


def test_the_card_says_it_in_words():
    gp = GP.build(board(), "nfl")
    t = gp["games"][0]["scorers"][0]
    c = GP.card(t, 1, "scorers", "nfl")
    assert c["title"] == "Touchdown pair 1"
    assert "by our numbers" in c["price_line"] and "take it at" in c["price_line"]
    assert all(l["pick"].endswith("to score a touchdown") for l in c["legs"])
    three = GP.card(gp["games"][0]["threes"][0], 1, "three", "nfl")
    assert three["title"] == "Parlay 1" and len(three["legs"]) == 3
    assert GP.pick_words({"player": "Malik Nabers", "market": "receptions", "market_label": "Receptions",
                          "side": "Over", "line": 4.5}) == "Malik Nabers over 4.5 receptions"


def test_basketball_says_it_has_no_scorer_market():
    b = board()
    for r in b["most_likely"]:
        r["market"], r["market_label"] = "pts", "Points"
    gp = GP.build(b, "nba")
    g = gp["games"][0]
    assert g["scorers"] == [] and "No scorer market" in g["scorers_note"]


def test_the_report_and_the_record_carry_them():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "sec_parlays, sec_weather, sec_before)" in src
    assert "par = parlay_sentence(c)" in src
    lg = (ROOT / "engine" / "leaguereport.py").read_text(encoding="utf-8")
    assert lg.count("sec_parlays,") >= 3 or lg.count("sec_parlays") >= 4
    pz = (ROOT / "engine" / "parlays.py").read_text(encoding="utf-8")
    assert "gameparlays.attach(slate, sport)" in pz, "every build's parlay hook"
    gate = (ROOT / "engine" / "gate.py").read_text(encoding="utf-8")
    assert '"game_parlays",' in gate, "a paid key"
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert 'b.type === "parlays"' in js
    from engine import parlayledger as PL
    assert PL.TWO_LEG_CATS["game_three"] == (PL.PARLAY_LEG_CATEGORY,)
    assert PL.BOARD_FILES["nhl"] == "web/data/nhl.json"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    gp = GP.build(board(), "nfl")
    n = PL.log_game_parlays(conn, gp, "nfl", "2099-W10")
    assert n == 8, n          # two two-leg tickets (GPWIN1), three three-leg, three scorer pairs
    rows = conn.execute("SELECT source, n_legs, stake_units FROM parlays").fetchall()
    assert sorted({r["source"] for r in rows}) == ["game_td", "game_three", "game_two"]
    assert {r["n_legs"] for r in rows if r["source"] == "game_two"} == {2}
    assert all(r["stake_units"] == 0 for r in rows)
    assert PL.log_game_parlays(conn, gp, "nfl", "2099-W10") == 0, "a ticket is journaled once"
    legs = GP.journal_rows(gp)
    assert legs and all(l["model_prob"] for l in legs)


def test_every_ticket_grades_off_its_legs():
    import os
    import tempfile
    from engine import ledger
    from engine import parlayledger as PL
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    b = board()
    GP.attach(b, "nfl")
    legs = PL.journal_game_parlay_legs(conn, b, "nfl")
    assert legs == len(GP.journal_rows(b["game_parlays"])), legs
    n = PL.log_game_parlays(conn, b["game_parlays"], "nfl", b["date"])
    assert n == 8
    cats = {r[0] for r in conn.execute("SELECT DISTINCT category FROM bets")}
    assert cats == {PL.PARLAY_LEG_CATEGORY}, "the legs ride on paper in their own bucket"
    conn.execute("UPDATE bets SET status='won', pnl_units=1, actual=99")
    conn.commit()
    res = PL.settle(conn)
    assert res["settled"] == 8 and res["waiting"] == 0, res
    # One leg lost loses every ticket it is on.
    conn2 = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn2, starting=1000, unit_pct=1.0)
    PL.journal_game_parlay_legs(conn2, b, "nfl")
    PL.log_game_parlays(conn2, b["game_parlays"], "nfl", b["date"])
    conn2.execute("UPDATE bets SET status='won', pnl_units=1, actual=99")
    conn2.execute("UPDATE bets SET status='lost', pnl_units=-1, actual=0 WHERE player='Cam Skattebo'")
    conn2.commit()
    PL.settle(conn2)
    bad = conn2.execute("SELECT DISTINCT p.status FROM parlays p JOIN parlay_legs l ON l.parlay_id=p.id "
                        "WHERE l.player='Cam Skattebo'").fetchall()
    assert [r[0] for r in bad] == ["lost"], bad


def test_the_report_section_draws():
    from engine import gamereport as GR
    b = board()
    GP.attach(b, "nfl")
    c = GR.Ctx(GAME, b, sport="nfl")
    sec = GR.sec_parlays(c)
    assert sec and sec["key"] == "parlays"
    kinds = [x.get("kind") for x in sec["blocks"] if x.get("type") == "parlays"]
    assert kinds == ["two", "three", "scorers"], kinds      # the two strongest picks together lead (GPWIN1)
    line = GR.parlay_sentence(c)
    assert line.startswith("Strongest two-leg parlay:") and "Best three-leg parlay:" in line, line
    assert "Best touchdown pair:" in line, line


def test_the_heartbeat_counts_each_leagues_tickets_and_reports():
    """Both keys are paid and stripped from the public copy; the heartbeat
    is where anyone sees a league built them (launch._board_counts)."""
    import json
    import os
    import tempfile
    import launch as L
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "game_parlays": {"games": [{"home": "MIA"}, {"home": "NYG"}],
                              "counts": {"games": 2, "threes": 8, "scorers": 6}, "note": "tracked"},
             "game_reports": [{"game": "DUKE@MIA"}, {"game": "WAS@NYG"}]}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(board, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
            broken = dict(board, game_parlays={"sport": "nfl", "games": [],
                                               "note": "the game parlays did not build: KeyError"})
            with open(path, "w") as fh:
                json.dump(broken, fh)
            bad = L._board_counts(path)
        finally:
            L._full_copy = was
    assert (got["parlay_games"], got["sgp_threes"], got["td_pairs"], got["reports"]) == (2, 8, 6, 2), got
    assert "parlay_error" not in got
    assert bad["parlay_games"] == 0 and "did not build: KeyError" in bad["parlay_error"], bad


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
