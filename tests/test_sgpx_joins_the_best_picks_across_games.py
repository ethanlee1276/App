"""SGPX: our best picks from different games in one ticket (step ACI, 22 November 2026).

Ethan: "we take the top touchdown score for one game and the top touchdown score for the other game, or like the
best picks we have ... Like we could have done Derrick Henry and Jahmyr Gibbs and St. Brown combined for a
parlay today ... We need to do those for player props and for touchdown props." What these hold:

  * the board's games fall into kickoff slots (a Sunday's 1 PM games, its 4:05 and 4:25 ones); a slot of one game
    has no SGPX;
  * a slot's tickets come from the legs its games posted: the player props of their three-leg and two-leg
    parlays, the scorers of their touchdown pairs, each once;
  * a ticket spans two games or more, two legs a game at most; legs from different games multiply, two from one
    game count as that game's own parlays count them, and a pair that conflicts there makes no ticket; the price
    to take it at is the fair price and 5%;
  * the likeliest three of each kind, each leg on two at most, no two sharing more than one leg;
  * a slot posts once every game in it has posted and before the first starts, is kept as posted and never
    changes; a report of a game in it gets an "SGPX parlays" section after its own parlays; Report Picks has the
    tab; the Record journals and counts the tickets.

    python3 tests/test_sgpx_joins_the_best_picks_across_games.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, sgpx as S                   # noqa: E402

UTC = dt.timezone.utc
#: A Sunday still to come, so no game of it is under way when the paper journal reads its legs.
DAY = "2030-11-24"


def _leg(player, team, home, away, market, p, odds=-150, line=0.5, side="Over", pos="WR"):
    return {"player": player, "team": team, "home": home, "away": away, "market": market, "side": side,
            "line": line, "odds": odds, "book": "DraftKings", "p": p, "position": pos, "game_date": DAY,
            "why": [f"{player}'s case"]}


def _game(away, home, kickoff, props, tds, **kw):
    """A game's posted entry, as engine/gameparlays leaves it: its tickets' legs are what SGPX reads."""
    return dict({"away": away, "home": home, "kickoff": kickoff, "date": DAY,
                 "threes": [{"legs": props[:3]}], "twos": [{"legs": props[3:5]}] if len(props) > 3 else [],
                 "scorers": [{"legs": tds}]}, **kw)


def _slate():
    det = _game("TB", "DET", "13:00",
                [_leg("Amon-Ra St. Brown", "DET", "DET", "TB", "receptions", 0.78),
                 _leg("Jahmyr Gibbs", "DET", "DET", "TB", "rush_yds", 0.72, line=59.5, pos="RB"),
                 _leg("Mike Evans", "TB", "DET", "TB", "rec_yds", 0.61, line=49.5),
                 _leg("Baker Mayfield", "TB", "DET", "TB", "moneyline", 0.66),             # a game line: not a prop
                 _leg("Jahmyr Gibbs", "DET", "DET", "TB", "rush_yds", 0.72, line=59.5, pos="RB")],
                [_leg("Jahmyr Gibbs", "DET", "DET", "TB", "anytime_td", 0.55, 120, side="Yes", pos="RB"),
                 _leg("Amon-Ra St. Brown", "DET", "DET", "TB", "anytime_td", 0.48, 140, side="Yes")])
    det["twos"][0]["legs"][0]["_game_leg"] = True
    bal = _game("CLE", "BAL", "13:00",
                [_leg("Derrick Henry", "BAL", "BAL", "CLE", "rush_yds", 0.74, line=79.5, pos="RB"),
                 _leg("Zay Flowers", "BAL", "BAL", "CLE", "receptions", 0.70)],
                [_leg("Derrick Henry", "BAL", "BAL", "CLE", "anytime_td", 0.60, -110, side="Yes", pos="RB")])
    kc = _game("LV", "KC", "13:00",
               [_leg("Travis Kelce", "KC", "KC", "LV", "receptions", 0.69, pos="TE")],
               [_leg("Isiah Pacheco", "KC", "KC", "LV", "anytime_td", 0.46, 130, side="Yes", pos="RB")])
    late = [_game("NYJ", "LAC", "16:05", [_leg("Ladd McConkey", "LAC", "LAC", "NYJ", "receptions", 0.7)],
                  [_leg("Omarion Hampton", "LAC", "LAC", "NYJ", "anytime_td", 0.5, 110, side="Yes", pos="RB")]),
            _game("PIT", "PHI", "16:25", [_leg("A.J. Brown", "PHI", "PHI", "PIT", "receptions", 0.66)],
                  [_leg("Saquon Barkley", "PHI", "PHI", "PIT", "anytime_td", 0.58, -105, side="Yes", pos="RB")],
                  post_at="2030-11-24T20:10:00Z")]
    snf = _game("MIN", "SF", "20:20", [_leg("Justin Jefferson", "MIN", "SF", "MIN", "receptions", 0.75)],
                [_leg("Christian McCaffrey", "SF", "SF", "MIN", "anytime_td", 0.62, -140, side="Yes", pos="RB")],
                post_at="2030-11-25T00:05:00Z")
    return [det, bal, kc, *late, snf]


def _result(games=None):
    games = _slate() if games is None else games
    return {"date": DAY, "games": [{"away": g["away"], "home": g["home"], "kickoff": g["kickoff"],
                                             "date": g["date"]} for g in games],
            "game_parlays": {"sport": "nfl", "games": games}}


def _stub_pairs():
    """Two legs of one game counted as 0.9 of their product (a link), or a conflict for two DET pass catchers'
    touchdowns, so the arithmetic is the test's own."""
    was = GP.ticket

    def pair(sport, legs, game, memo=None):
        if {l["player"] for l in legs} == {"Amon-Ra St. Brown", "Mike Evans"}:
            return None
        j = 0.9
        for l in legs:
            j *= float(l["p"])
        return {"joint": round(j, 4), "links": [f"{legs[0]['player']} and {legs[1]['player']}: one game"]}
    GP.ticket = pair
    return was


def test_the_games_fall_into_kickoff_slots():
    ss = S.slots(_slate())
    assert [[f"{x['away']}@{x['home']}" for x in s["games"]] for s in ss] == [
        ["TB@DET", "CLE@BAL", "LV@KC"], ["NYJ@LAC", "PIT@PHI"], ["MIN@SF"]]
    assert [s["key"] for s in ss] == ["2030-11-24T18:00Z", "2030-11-24T21:05Z", "2030-11-25T01:20Z"]
    assert ss[0]["label"] == "Sun 1:00 PM ET" and ss[1]["label"] == "Sun 4:05 PM ET"


def test_a_slot_reads_the_legs_its_games_posted():
    det = _slate()[0]
    props = S.legs_of(det, "props")
    assert [(l["player"], l["market"]) for l in props] == [
        ("Amon-Ra St. Brown", "receptions"), ("Jahmyr Gibbs", "rush_yds"), ("Mike Evans", "rec_yds")], \
        "each once; a game line and a touchdown are no player-prop leg"
    assert {l["sgpx_game"] for l in props} == {"TB@DET"}
    assert [l["player"] for l in S.legs_of(det, "tds")] == ["Jahmyr Gibbs", "Amon-Ra St. Brown"]


def test_a_ticket_multiplies_across_games_and_links_within_one():
    was = _stub_pairs()
    try:
        slate = _slate()
        by = {f"{g['away']}@{g['home']}": g for g in slate}
        sb, gibbs = S.legs_of(slate[0], "props")[:2]
        henry = S.legs_of(slate[1], "props")[0]
        kelce = S.legs_of(slate[2], "props")[0]
        t = S.ticket("nfl", [sb, henry, kelce], by)
        assert t["joint"] == round(0.78 * 0.74 * 0.69, 4) == t["independent"], "three games: the product"
        assert t["games"] == ["CLE@BAL", "LV@KC", "TB@DET"]
        assert t["take_dec"] == round(1 / (0.78 * 0.74 * 0.69) * 1.05, 4), "our fair price and 5%"
        dec = 1 + 100 / 150
        assert t["naive_dec"] == round(dec ** 3, 4)
        t2 = S.ticket("nfl", [sb, gibbs, henry], by)
        assert t2["joint"] == round(round(0.9 * 0.78 * 0.72, 4) * 0.74, 4) and t2["links"], "one game's pair, linked"
        assert S.ticket("nfl", [sb, gibbs, S.legs_of(slate[0], "props")[2]], by) is None, "one game only"
        evans = S.legs_of(slate[0], "props")[2]
        assert S.ticket("nfl", [sb, evans, henry], by) is None, "a pair that conflicts in its game"
    finally:
        GP.ticket = was


def test_the_likeliest_three_each_leg_on_two_at_most():
    def t(*ids, p=0.5):
        return {"joint": p, "legs": [{"player": i, "market": "m", "side": "OVER", "line": 1} for i in ids]}
    made = [t("a", "b", "c", p=0.40), t("a", "b", "d", p=0.39), t("a", "c", "d", p=0.38), t("a", "e", "f", p=0.37),
            t("b", "e", "f", p=0.36), t("c", "e", "g", p=0.35)]
    got = [[l["player"] for l in x["legs"]] for x in S.choose(made)]
    # abd and acd share two legs with abc; aef rides "a" a second time; bef shares e and f with aef.
    assert got == [["a", "b", "c"], ["a", "e", "f"], ["c", "e", "g"]], got


def _public(root):
    out = Path(root) / "web" / "data" / "recommendations.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def test_a_slot_posts_once_all_its_games_have_and_never_changes():
    was = _stub_pairs()
    try:
        root = tempfile.mkdtemp()
        out = _public(root)
        noon = dt.datetime(2030, 11, 24, 16, 50, tzinfo=UTC)            # 11:50 AM ET: the 1 PM games posted
        r = _result()
        line = S.attach(r, "nfl", out, now=noon)
        sg = r["sgpx"]
        early = next(e for e in sg["slots"] if e["key"] == "2030-11-24T18:00Z")
        assert early["posted"] and early["posted_at"] == "2030-11-24T16:50:00Z" and len(early["props"]) == 3
        assert all(len(set(x["games"])) >= 2 for k in S.KINDS for x in early[k])
        tds = [[l["player"] for l in x["legs"]] for x in early["tds"]]
        # Henry, Gibbs and Pacheco (60% x 55% x 46%) ahead of Henry and the Lions' pair (60% x 90% of 55% x 48%).
        assert tds[0] == ["Derrick Henry", "Jahmyr Gibbs", "Isiah Pacheco"], tds
        assert "posted now" in line and "SGPX parlays" in line
        late = next(e for e in sg["slots"] if e["key"] == "2030-11-24T21:05Z")
        assert "post_note" in late and "props" not in late, "a game in it still to post"
        assert all(e["key"] != "2030-11-25T01:20Z" for e in sg["slots"]), "one game: no SGPX"
        kept = json.loads((Path(root) / "data" / "built" / "sgpx_nfl.json").read_text(encoding="utf-8"))
        assert list(kept["slots"]) == ["2030-11-24T18:00Z"]
        # The next build: the legs' chances moved, and the posted tickets stand as posted.
        r2 = _result()
        for g in r2["game_parlays"]["games"]:
            for k in ("threes", "twos", "scorers"):
                for x in g.get(k) or []:
                    for l in x["legs"]:
                        l["p"] = 0.5
        S.attach(r2, "nfl", out, now=noon + dt.timedelta(minutes=10))
        again = next(e for e in r2["sgpx"]["slots"] if e["key"] == "2030-11-24T18:00Z")
        assert [x["joint"] for x in again["tds"]] == [x["joint"] for x in early["tds"]], "never changes"
        # A slot that started before it could post never posts.
        r3 = _result()
        S.attach(r3, "nfl", None, now=dt.datetime(2030, 11, 24, 21, 10, tzinfo=UTC))
        assert all(e["key"] != "2030-11-24T18:00Z" for e in r3["sgpx"]["slots"])
        os.environ[S.ENV] = "off"
        try:
            r4 = _result()
            assert S.attach(r4, "nfl", out, now=noon) == "" and "sgpx" not in r4
        finally:
            os.environ.pop(S.ENV, None)
        assert S.attach(_result(), "nba", out, now=noon) == ""
    finally:
        GP.ticket = was


def test_a_report_and_report_picks_show_them():
    was = _stub_pairs()
    try:
        from engine import gamereport as R
        r = _result()
        reports = [{"away": "TB", "home": "DET", "date": DAY,
                    "sections": [{"key": "card", "blocks": []}, {"key": "parlays", "blocks": []},
                                 {"key": "news", "blocks": []}]},
                   {"away": "MIN", "home": "SF", "date": DAY, "sections": [{"key": "parlays", "blocks": []}]}]
        R._sgpx(r, reports, "nfl", None, now=dt.datetime(2030, 11, 24, 16, 50, tzinfo=UTC))
        keys = [s["key"] for s in reports[0]["sections"]]
        assert keys == ["card", "parlays", "sgpx", "news"], keys
        assert [s["key"] for s in reports[1]["sections"]] == ["parlays"], "a game in no SGPX slot"
        sec = reports[0]["sections"][2]
        assert sec["title"] == "SGPX parlays"
        cards = [b for b in sec["blocks"] if b.get("type") == "parlays"]
        assert [b["kind"] for b in cards] == ["sgpx", "sgpx"]
        first = cards[0]["items"][0]
        assert first["title"] == "SGPX parlay 1" and all(l["game"] for l in first["legs"])
        assert cards[1]["items"][0]["title"] == "SGPX touchdown parlay 1"
        assert first["price_line"].startswith(f"{first['joint']:.0%} by our numbers · fair ")
        early = next(e for e in r["sgpx"]["slots"] if e.get("posted"))
        assert early["blocks"] == sec["blocks"], "the Report Picks tab draws what the report draws"
    finally:
        GP.ticket = was
    js = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    assert '["sgpx", "SGPX parlays", "Our strongest picks from different games, combined",' in js
    rjs = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert 'const cross = b.kind === "sgpx";' in rjs and "(!cross && settled(t))" in rjs, \
        "an SGPX card is never graded by one game's result"
    from engine import gate
    assert "sgpx" in gate.PAID_KEYS


def test_the_heartbeat_counts_them():
    was = _stub_pairs()
    try:
        import json as _json
        import launch as LA
        r = _result()
        S.attach(r, "nfl", None, now=dt.datetime(2030, 11, 24, 16, 50, tzinfo=UTC))
        path = Path(tempfile.mkdtemp()) / "recommendations.json"
        path.write_text(_json.dumps(r), encoding="utf-8")
        got = LA._board_counts(str(path)).get("sgpx")
        assert got == {"posted": 1, "waiting": 1, "props": 3, "tds": len(r["sgpx"]["slots"][0]["tds"])}, got
    finally:
        GP.ticket = was


def test_the_record_journals_and_counts_them():
    was = _stub_pairs()
    try:
        from engine import ledger, parlayledger as PL
        conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
        ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
        r = _result()
        S.attach(r, "nfl", None, now=dt.datetime(2030, 11, 24, 16, 50, tzinfo=UTC))
        made = {k: sum(len(e.get(k) or []) for e in r["sgpx"]["slots"] if e.get("posted_at")) for k in S.KINDS}
        n = PL.log_sgpx(conn, r["sgpx"], "nfl", r["date"], r["games"])
        assert n == made["props"] + made["tds"] and made["props"] == 3 and made["tds"] >= 1, (n, made)
        assert PL.log_sgpx(conn, r["sgpx"], "nfl", r["date"], r["games"]) == 0, "journaled once"
        rows = conn.execute("SELECT source, parlay_type, at_start, n_legs, grade FROM parlays").fetchall()
        assert sorted({x[0] for x in rows}) == ["sgpx_props", "sgpx_td"] and {x[1] for x in rows} == {"sgpx"}
        assert {x[2] for x in rows} == {1} and {x[3] for x in rows} == {3}
        assert all(x[4].startswith("SGPX ") for x in rows)
        rec = PL.game_parlay_record(conn, sources=PL.SGPX_SOURCES)
        assert rec["nfl"]["sgpx_props"]["open"] == 3 and rec["nfl"]["sgpx_td"]["open"] == made["tds"]
        assert "sgpx_props" in PL.NO_ROW_VOID_SOURCES
        src = (ROOT / "engine" / "parlayledger.py").read_text(encoding="utf-8")
        assert "wrote += log_sgpx(conn, sg, sport, board.get(\"date\") or \"\", board.get(\"games\"))" in src
    finally:
        GP.ticket = was


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
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
