"""The full fantasy profile (engine/ffprofile.py) — the dossier's data.

Ethan, 2026-08-18, with a competitor's player-page render: "Follow this
exact render." The render is a layout; this file defends the CLAIMS the
layout makes with our data:

  * A season rank is computed among same-position peers with a real
    sample, or not claimed at all.
  * The weekly series is nflverse's own fp_ppr — never a sum this module
    invented from parts.
  * Defense ranks come from the fantasy points our logs saw them ALLOW
    to the position — rank 1 allows the least, and a defense with two
    games is not ranked.
  * August belongs to two seasons: the stats season is the player's
    last, the schedule rolls forward to the first season with unplayed
    games, and the payload names both.

Everything runs on its own temp DB, per the statlogs convention.

Run directly: `python3 tests/test_ffprofile.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db as _db
from engine import ffprofile


def _fixture():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "hist.db")
    conn = _db.connect(path)
    rows = []
    # Five QBs, six weeks each: our man throws the most; QB Two the least.
    for qi in range(1, 6):
        name = "QB Hero" if qi == 1 else f"QB Peer {qi}"
        for wk in range(1, 7):
            # Rotate the schedule so each defense is met by different
            # QBs in different WEEKS — five same-week games collapse to
            # one (opponent, period) group, which is one game, not five.
            opp = f"D{((qi + wk) % 6) + 1}"
            base = [("pass_yds", 300 - qi * 20), ("fp_ppr", 25.0 - qi * 2),
                    ("pass_att", 33), ("carries", 4), ("snap_pct", 0.97)]
            for mk, v in base:
                rows.append(dict(sport="nfl", season=2025, period=f"{wk:03d}",
                                 game_id=f"G{qi}{wk}", player=name,
                                 team=f"T{qi}", opponent=opp,
                                 position="QB", home=1, market=mk,
                                 value=float(v)))
    # A defense with only TWO games against QBs must not be ranked.
    for wk in (1, 2):
        rows.append(dict(sport="nfl", season=2025, period=f"{wk:03d}",
                         game_id=f"THIN{wk}", player="QB Thin", team="T9",
                         opponent="DTHIN", position="QB", home=1,
                         market="fp_ppr", value=10.0))
    _db.upsert_player_logs(conn, rows)
    conn.execute("INSERT INTO games (sport, season, period, game_id, home, "
                 "away, home_score, away_score, spread, total) VALUES "
                 "('nfl', 2025, '001', 'X', 'T1', 'D1', 27, 20, 0, 44)")
    conn.commit()
    conn.close()
    return path


def test_the_profile_reads_identity_from_the_latest_log():
    p = ffprofile.profile("QB Hero", db_path=_fixture())
    assert p["team"] == "T1" and p["position"] == "QB"
    assert p["season"] == 2025 and p["games"] == 6


def test_season_tiles_rank_among_position_peers():
    p = ffprofile.profile("QB Hero", db_path=_fixture())
    tiles = {t["market"]: t for t in p["season_stats"]}
    assert tiles["pass_yds"]["rank"] == 1 and tiles["pass_yds"]["of"] == 5
    assert tiles["fp_ppr"]["rank"] == 1
    assert tiles["pass_yds"]["total"] == 280.0 * 6
    assert tiles["pass_yds"]["per_game"] == 280.0


def test_the_weekly_series_is_fp_ppr_itself():
    p = ffprofile.profile("QB Hero", db_path=_fixture())
    assert [w["fp"] for w in p["weekly"]] == [23.0] * 6
    assert [w["week"] for w in p["weekly"]] == list(range(1, 7))


def test_the_gamelog_carries_the_games_own_final():
    p = ffprofile.profile("QB Hero", db_path=_fixture())
    rows = {r["week"]: r for r in p["gamelog"]["rows"]}
    assert rows[1]["result"] == "W 27-20"
    assert "result" not in rows[2], "an unscored week must not invent one"


def test_defense_ranks_need_a_real_sample():
    path = _fixture()
    conn = _db.connect(path)
    ranks, n = ffprofile._defense_ranks(conn, "QB", 2025)
    conn.close()
    assert "DTHIN" not in ranks, "two games is one Thursday, not a rank"
    # Every full-sample defense ranked; rank 1 allows the least.
    assert n == 6
    least = min(ranks.values(), key=lambda d: d["allowed_pg"])
    assert least["rank"] == 1


def test_utilization_speaks_per_game_and_snap_share():
    p = ffprofile.profile("QB Hero", db_path=_fixture())
    u = p["utilization"]
    assert u["snap_pct"] == 97
    assert ("Pass attempts / game", 33.0) in u["rows"]
    assert all(k != "Air yards / game" for k, _ in u["rows"]), \
        "receiving air yards on a passer is a broken stat wearing a zero"


def test_no_db_degrades_to_empty():
    assert ffprofile.profile("Anyone", db_path="/no/such.db") == {}


def test_the_server_serves_it_ungated():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "server.py"), encoding="utf-8").read()
    assert '"/api/players/fantasy"' in src
    i = src.index("def _players_fantasy(")
    body = src[i:src.index("\n    def ", i + 10)]
    assert "ffprofile" in body and "_entitled" not in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
