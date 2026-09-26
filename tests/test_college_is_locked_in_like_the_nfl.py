"""College football, locked in the way the NFL is.

Ethan, 2026-09-26: "look back into our memory and into our chat and look
exactly what we did for NFL and make sure every single thing is done for
college football. we want it locked in and ready to go."

The NFL fixes of the last days that college did not have, each here:
  * ESPN's college injury board read by the college build (it fed only the
    Injuries page): listed players held, scorer rows stamped, the scan told;
  * a player every book took down before kickoff (Zay Flowers) is pulled;
  * a starting quarterback out, benched or back (Darnold/Lock) is shown
    under every card of that team — unmeasured for college, so not priced;
  * red-zone chances scaled to this week's offence (Skattebo);
  * anytime-TD prices follow the Novig rule (tested on its own).
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.cfb import qbchange as Q                          # noqa: E402
from engine.cfb import tds as T                               # noqa: E402
from engine.sources import injuries as I                      # noqa: E402

BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()


def test_the_espn_board_keys_to_college_schools():
    rows = [{"team": "Georgia Bulldogs", "player": "Gunner Stockton", "pos": "QB", "status": "Out",
             "date": "2099-01-01T00:00Z"},
            {"team": "Nowhere State", "player": "Some One", "pos": "WR", "status": "Out"},
            {"team": "Georgia Bulldogs", "player": "Cleared Man", "pos": "RB", "status": "Active"}]
    got = I.live_injuries(rows, team_key=lambda n: "UGA" if n.startswith("Georgia") else "")
    assert [(i.team, i.player, i.status) for i in got] == [("UGA", "Gunner Stockton", "OUT")]
    from engine.sources.oddsapi import normalize_name
    assert I.status_by_player(got) == {("UGA", normalize_name("Gunner Stockton")): "OUT"}
    # The NFL keeps its own table by default.
    src = open(os.path.join(ROOT, "engine", "sources", "injuries.py"), encoding="utf-8").read()
    assert "team_key = team_key or TEAM_ABBR.get" in src
    assert 'parse_injuries(fetch_injuries("cfb"))' in src


def test_the_college_build_reads_it_everywhere_the_nfl_does():
    for bit in ("_cfb_inj = load_cfb_injuries(out.get(\"games\") or [], lookup)",
                "_pg.injuries = [i for i in _cfb_inj if i.team in (_pg.home, _pg.away)]",
                '_r["injury_status"] = _st',
                "usage=_cfb_use, watch=watch, injuries=_cfb_inj)"):
        assert bit in BUILD, bit
    scan = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()
    assert 'injuries=[i for i in injuries or [] if getattr(i, "team", "") in (home, away)],' in scan
    assert 'pulled=gd.get("pulled_players") or [])' in scan


def test_a_player_every_book_took_down_is_pulled_in_college_too():
    body = BUILD[BUILD.index("def attach_player_quotes("):]
    body = body[:body.index("\ndef ", 10)]
    assert "_priced = _PricedTracker()" in body and "_priced.save()" in body
    assert "_gone = _priced.see(event_id, sorted(_who), age)" in body
    assert '_gd["pulled_players"] = list(_g["pulled_players"])' in BUILD


def _logs():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INTEGER, period TEXT, team TEXT, "
              "player TEXT, market TEXT, value REAL)")
    rows = [("A", "Usual QB", "1", 250), ("A", "Usual QB", "2", 280), ("A", "Fill In", "3", 190),
            ("B", "Their QB", "1", 200), ("B", "Their QB", "2", 210), ("B", "Their QB", "3", 230),
            ("C", "Star QB", "1", 300), ("C", "Star QB", "2", 310), ("C", "Backup QB", "2", 20)]
    c.executemany("INSERT INTO player_game_logs VALUES ('cfb', 2026, ?, ?, ?, 'pass_yds', ?)",
                  [(p, t, n, v) for t, n, p, v in rows])
    return c


def test_a_college_quarterback_out_benched_or_back():
    qb = Q.passers(_logs(), 2026, ["A", "B", "C"])
    assert qb["A"]["usual"] == "Usual QB" and qb["A"]["last"] == "Fill In"
    from types import SimpleNamespace as NS
    inj = [NS(team="C", player="Star QB", status="OUT")]
    ch = Q.changes(qb, inj, {"A": ["Usual QB"], "B": ["Somebody New"]})
    assert ch["A"]["status"] == "RETURNS" and Q.card(ch["A"])["headline"].startswith("Usual QB is back at QB")
    assert ch["B"]["status"] == "BENCHED" and "the books priced this week" in Q.card(ch["B"])["headline"]
    assert ch["C"]["status"] == "OUT" and ch["C"]["replacement"] == "Backup QB"
    c = Q.card(ch["C"])
    assert c["applied"] == 1.0 and "college has not been measured yet" in c["note"], "shown, never priced"
    rows = [{"player": "Wide Out", "team": "C"}, {"player": "Backup QB", "team": "C"}, {"player": "X", "team": "Z"}]
    assert Q.stamp(rows, ch) == 2
    assert rows[1]["qb_card"]["note"].startswith("Starting in place of Star QB") and "qb_card" not in rows[2]
    for bit in ("_cqb.changes(_cqb.passers(conn, day.year, _teams), _cfb_inj, _priced_qbs)",
                "_cqb.stamp(list(out.get(\"recommendations\") or []) + list(rows or []) + list(watch or []), _qb_ch)",
                '_gd["qb_cards"] = _cards'):
        assert bit in BUILD, bit


def test_college_red_zone_chances_scale_to_this_weeks_offence():
    assert T._rz_now(2.0, 42.0, 30.0) == {"rz_chances": 2.8, "rz_before": 2.0, "rz_then_implied": 30.0}
    assert T._rz_now(2.0, 14.0, 35.0)["rz_chances"] == 1.2, "clamped at 0.6"
    assert T._rz_now(2.0, None, 30.0)["rz_chances"] == 2.0 and T._rz_now(2.0, 30.0, None)["rz_chances"] == 2.0
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE games (sport TEXT, season INTEGER, home TEXT, away TEXT, home_score REAL, away_score REAL)")
    c.executemany("INSERT INTO games VALUES ('cfb', 2026, ?, ?, ?, ?)",
                  [("A", "B", 35, 14), ("B", "A", 21, 28), ("C", "A", 10, 3)])
    assert T.points_per_game(c, 2026) == {"A": 22.0, "B": 17.5}, "two games before a team has a number"


def test_a_college_teammate_out_says_what_it_opens_in_catches():
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from types import SimpleNamespace as NS
    import test_college_matchup_parity as P
    from engine import gamescan as G
    from engine.sources import cfbd
    teams = [P._row("Georgia", 700, 0.35, 70, 25), P._row("Tennessee", 700, -0.2, 35, 65)]
    teams += [P._row(f"T{i}", 700, 0.2 - i * 0.006, 50, 50) for i in range(60)]
    keys = {"Georgia": "UGA", "Tennessee": "TENN", **{f"T{i}": f"T{i}" for i in range(60)}}
    out = {"games": [{"home": "TENN", "away": "UGA", "pulled_players": ["Gone Guy"]}],
           "recommendations": [{"player": "Slot Guy", "team": "UGA", "opponent": "TENN", "position": "WR",
                                "market": "rec_yds", "line": 40.5, "hit_prob": 0.6},
                               {"player": "Gone Guy", "team": "UGA", "opponent": "TENN", "position": "WR",
                                "market": "rec_yds", "line": 30.5, "hit_prob": 0.6}]}
    usage = {("UGA", G._key("Wide Out")): {"name": "Wide Out", "position": "WR", "games": 4, "tgt_share": 0.3,
                                          "share_of": "catches", "rec_pg": 6.0},
             ("UGA", G._key("Slot Guy")): {"name": "Slot Guy", "position": "WR", "games": 4, "tgt_share": 0.2,
                                          "share_of": "catches", "rec_pg": 4.0}}
    G.attach_cfb(out, 2026, lambda s: keys.get(s), fetch=lambda y: cfbd.parse_advanced(teams) if y == 2026 else {},
                 usage=usage, injuries=[NS(team="UGA", player="Wide Out", status="OUT", position="WR", role="wr1")])
    reads = {x["player"]: x for x in out["scan_reads"]["UGA@TENN"]["players"]}
    assert "Wide Out (WR) is out — 30% of the catches to go around" in reads["Slot Guy"]["pro"]
    assert out["games"][0]["scan"]["injuries"][0]["opens"] == "30% of UGA's catches to share out"
    assert "Wide Out" not in reads, "a ruled-out player gets no read"
    assert "Gone Guy" not in reads, "nor one every book took down"


def test_every_card_names_the_likely_quarterbacks_instead_of_unconfirmed():
    """Ethan, 2026-09-26: "im noticing for cfb that every game is saying 'QB
    Unconfirmed'". The manual confirmation had never been filled in. The card
    now names each side's likely starter off the passing logs and ESPN's
    injury report; the conditional hold on game bets is left as it was."""
    from types import SimpleNamespace as NS
    qb = Q.passers(_logs(), 2026, ["A", "B", "C"])
    g = {"home": "B", "away": "C", "qb_confirmed": False,
         "qb_status": {"home": {"state": "unknown"}, "away": {"state": "unknown"}}}
    got = Q.read_game(g, qb, [NS(team="C", player="Star QB", status="OUT")])
    assert got["qb_read"]["home"] == {"starter": "Their QB", "why": "started the last game; not on ESPN's injury report"}
    assert got["qb_read"]["away"]["starter"] == "Backup QB" and got["qb_read"]["away"]["out"] == "Star QB"
    assert got["qb_confirmed"] is False, "the hold is Ethan's call, not this read's"
    a = Q.read_game({**g, "home": "A"}, qb, [])
    assert a["qb_read"]["home"]["starter"] == "Fill In", "whoever started last game"
    confirmed = {**g, "qb_status": {"home": {"state": "confirmed"}, "away": {"state": "confirmed"}}}
    assert "qb_read" not in Q.read_game(confirmed, qb, []), "a hand confirmation stands"
    assert '"qb_read": g.get("qb_read") or {},' in BUILD
    assert "games = [_cqb_read.read_game(g, _qb_logs, _inj_for_read) for g in games]" in BUILD
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "bits.push(`QB: ${named.map((r, i) => r ? esc(r.starter)" in js
    assert "} else bits.push(`${icon('warn')} QB unconfirmed`);" in js


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
