"""The college usage table, per player instead of per board.

`usage_table` served the CURRENT season once MIN_SEASON_PLAYERS were
logged and the PREVIOUS one before that — for everybody at once. Two
things follow from that being a threshold on the whole table rather than
a blend per man:

  * a player with no prior season is INVISIBLE until the table flips,
    which is most of September, and first-year players are 36-40% of the
    logged college population and score about a fifth of its touchdowns;
  * a returner is served a stale season while this one is already
    informative.

Measured over 20,916 walked-forward college player-week states — what was
known at a point in the season against how the rest of it went:

    rule                      rank    MAE
    all-or-nothing           0.344  0.2863
    blend, k = 3             0.365  0.2593

on the rows the old rule can price at all, and it prices 5,327 more — a
quarter of the board — that the old rule cannot answer, 2,868 of them
first-year players. So the freshman hole was never a missing recruiting
feed. It was a missing blend, and the NFL side has had one since it
shipped (`projection.USAGE_PRIOR_GAMES`).

AND IT NEVER RAN IN SEASON (2026-11-09). Every test here used a thin
current season, where `usage_table` still falls back to last year; once a
season is a season the prior it read was the season itself, so every man
was blended toward himself. The tests at the bottom use a full season, and
pin what the touchdown replay measured: the touchdown rate blends with the
usage, and once a team has played, last season's men with no game yet
leave its volume (`volume_rows`) — counted in, they diluted every share.

Run directly: `python3 tests/test_cfbusage.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.cfb import tds as T                                # noqa: E402
from engine.sources.oddsapi import normalize_name              # noqa: E402


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, "
                 "period TEXT, game_id TEXT, player TEXT, team TEXT, "
                 "opponent TEXT, position TEXT, home INT, market TEXT, "
                 "value REAL)")
    return conn


def _log(conn, season, weeks, player, team, pos, carries, rec):
    for w in range(1, weeks + 1):
        for market, value in (("carries", carries), ("receptions", rec),
                              ("rush_yds", carries * 4.0),
                              ("rec_yds", rec * 9.0)):
            conn.execute("INSERT INTO player_game_logs VALUES "
                         "('cfb',?,?,?,?,?,'OPP',?,1,?,?)",
                         (season, f"{w:03d}", f"g{season}{w}", player, team,
                          pos, market, value))


def _season(conn, season, n=T.MIN_SEASON_PLAYERS + 10, weeks=8):
    """Enough logged players that the season counts as a season."""
    for i in range(n):
        _log(conn, season, weeks, f"Filler {i}", f"T{i % 20}", "RB",
             4.0, 1.0)


# --- the blend ------------------------------------------------------------
def test_a_first_year_player_is_priceable_from_his_own_first_games():
    """THE HOLE. He has no prior season anywhere, so the old rule could
    not see him until the whole table flipped to the current year — most
    of September, on a board where first-year players score a fifth of
    the touchdowns."""
    conn = _conn()
    _season(conn, 2025)
    _season(conn, 2026, n=30, weeks=2)          # a thin, live September
    _log(conn, 2026, 2, "Frosh Back", "UGA", "RB", 14.0, 2.0)
    conn.commit()
    _s, usage, why = T.merged_usage(conn, 2026)
    row = usage["UGA"][normalize_name("Frosh Back")]
    assert row["carries"] == 14.0, row
    assert why[("UGA", normalize_name("Frosh Back"))][0] == "own"
    # And the old rule genuinely could not: the 2026 table is too thin.
    old_season, old_usage = T.usage_table(conn, 2026)
    assert old_season == 2025
    assert normalize_name("Frosh Back") not in (old_usage.get("UGA") or {})


def test_a_returner_is_shrunk_toward_last_season_by_games_played():
    """One game this year does not overturn a season of evidence, and
    six games should mostly replace it. k = 3 is fitted, not chosen."""
    conn = _conn()
    _season(conn, 2025)
    _log(conn, 2025, 10, "Vet Back", "UGA", "RB", 10.0, 1.0)
    _season(conn, 2026, n=30, weeks=1)
    _log(conn, 2026, 1, "Vet Back", "UGA", "RB", 20.0, 1.0)
    conn.commit()
    _s, usage, why = T.merged_usage(conn, 2026)
    one = usage["UGA"][normalize_name("Vet Back")]["carries"]
    kind, games, prior = why[("UGA", normalize_name("Vet Back"))]
    assert kind == "blend" and games == 1 and prior == 10
    # 1/(1+3) of the new number, the rest of the old one.
    assert abs(one - (0.25 * 20.0 + 0.75 * 10.0)) < 1e-9, one

    conn2 = _conn()
    _season(conn2, 2025)
    _log(conn2, 2025, 10, "Vet Back", "UGA", "RB", 10.0, 1.0)
    _season(conn2, 2026, n=30, weeks=9)
    _log(conn2, 2026, 9, "Vet Back", "UGA", "RB", 20.0, 1.0)
    conn2.commit()
    _s, usage2, _w = T.merged_usage(conn2, 2026)
    nine = usage2["UGA"][normalize_name("Vet Back")]["carries"]
    assert nine > one, "more games must move him further"
    assert abs(nine - (0.75 * 20.0 + 0.25 * 10.0)) < 1e-9, nine


def test_a_player_with_no_game_yet_keeps_exactly_what_he_had():
    """The blend must never cost anybody what the old rule gave them."""
    conn = _conn()
    _season(conn, 2025)
    _log(conn, 2025, 10, "Bench Guy", "UGA", "RB", 7.0, 2.0)
    _season(conn, 2026, n=30, weeks=2)
    conn.commit()
    _s, usage, why = T.merged_usage(conn, 2026)
    row = usage["UGA"][normalize_name("Bench Guy")]
    assert row["carries"] == 7.0 and row["receptions"] == 2.0
    assert why[("UGA", normalize_name("Bench Guy"))][0] == "prior"


def test_preseason_falls_all_the_way_back_and_blends_nothing():
    """In August the current season has no logs at all. There is nothing
    to blend and the answer is last season, unchanged."""
    conn = _conn()
    _season(conn, 2025)
    _log(conn, 2025, 10, "Vet Back", "UGA", "RB", 10.0, 1.0)
    conn.commit()
    season, usage, why = T.merged_usage(conn, 2026)
    assert season == 2025
    assert usage["UGA"][normalize_name("Vet Back")]["carries"] == 10.0
    assert why == {}


def test_the_thin_season_guard_is_bypassed_only_on_purpose():
    """`merged_usage` needs THIS season's partial logs precisely so it can
    weight them by how few they are. Without `force` the thin-season guard
    would hand back last season twice and the blend would blend a table
    with itself — which reads as 'the blend does nothing' rather than as
    a bug."""
    conn = _conn()
    _season(conn, 2025)
    _season(conn, 2026, n=5, weeks=1)
    conn.commit()
    assert T.usage_table(conn, 2026)[0] == 2025
    assert T.usage_table(conn, 2026, force=True)[0] == 2026


# --- what the reader is told ---------------------------------------------
def test_the_card_says_which_season_the_role_came_from():
    """Two players on one card can legitimately be reading different
    evidence now — a returner four games in, and a freshman with nothing
    but those four games — so the sentence is per player."""
    assert "this season" in T.usage_reason(("own", 3, 0))
    assert "last season" in T.usage_reason(("prior", 0, 11))
    blended = T.usage_reason(("blend", 3, 10))
    assert "50%" in blended, blended        # 3 / (3 + 3)
    assert T.usage_reason(None) == ""


def test_a_first_year_player_with_two_games_is_marked_thinner():
    """DATA QUALITY HAD TO MOVE WITH THE TABLE OR IT WOULD HAVE LIED. The
    merged table reports the CURRENT season, so the old
    `usage_season == season` test would have called a role built entirely
    from last year's logs full quality."""
    assert T._usage_quality(("prior", 0, 11)) == 0.72
    assert T._usage_quality(("own", 8, 0)) == 0.80
    assert T._usage_quality(("own", 2, 0)) < 0.72, \
        "two games and nothing behind them is the thinnest case there is"
    mid = T._usage_quality(("blend", 3, 10))
    assert 0.72 < mid < 0.80, mid


def test_the_transfer_bridge_is_not_switched_off_by_the_blend():
    """THE REGRESSION THIS PINS. The current-season team map used to be
    built only when the usage table had fallen back to a prior season.
    The merged table reports the CURRENT season as soon as one game is
    played, so that guard would have switched the transfer bridge off in
    week two and left it off — and transfers are a quarter of the quoted
    college board."""
    import inspect
    src = inspect.getsource(T.build_cfb_td_longshots)
    assert "current = teams_by_name(conn, season)" in src
    head = src[:src.index("current = teams_by_name(conn, season)")]
    assert "if usage_season != season:" not in head, \
        "the bridge is gated on a condition the merged table breaks"


# --- in season: a full current season (2026-11-09) ----------------------
def _td(conn, season, weeks, player, team, scored_weeks):
    for w in range(1, weeks + 1):
        conn.execute("INSERT INTO player_game_logs VALUES ('cfb',?,?,?,?,?,'OPP','RB',1,'anytime_td',?)",
                     (season, f"{w:03d}", f"g{season}{w}", player, team, 1.0 if w in scored_weeks else 0.0))


def _full_seasons():
    conn = _conn()
    _season(conn, 2025)
    _season(conn, 2026, weeks=4)                 # a season that is a season
    return conn


def test_in_season_a_returner_blends_toward_last_season_not_himself():
    """THE BUG. With 2026 a full season, `usage_table(conn, 2026)` served
    2026 itself as the 'prior', so this man read 20 carries, not the
    documented 1/(1+3) of 20 and 3/4 of 10."""
    conn = _full_seasons()
    _log(conn, 2025, 10, "Vet Back", "UGA", "RB", 10.0, 1.0)
    _log(conn, 2026, 1, "Vet Back", "UGA", "RB", 20.0, 1.0)
    conn.commit()
    assert T._players_logged(conn, 2026) >= T.MIN_SEASON_PLAYERS
    season, usage, why = T.merged_usage(conn, 2026)
    assert season == 2026
    key = ("UGA", normalize_name("Vet Back"))
    assert why[key] == ("blend", 1, 10), why[key]
    row = usage["UGA"][normalize_name("Vet Back")]
    assert abs(row["carries"] - (0.25 * 20.0 + 0.75 * 10.0)) < 1e-9, row
    assert row["games"] == 11, "this season's games and last season's together"
    assert T._prior_table(conn, 2026)[0] == 2025 and T._prior_table(conn, 2025) == (0, {})


def test_the_touchdown_rate_blends_with_the_usage():
    """Blended like the usage, with the games together, it beat both the
    own rate and this season's games alone in every bucket of the replay."""
    conn = _full_seasons()
    _log(conn, 2025, 10, "Vet Back", "UGA", "RB", 10.0, 1.0)
    _td(conn, 2025, 10, "Vet Back", "UGA", {1, 2, 3, 4, 5})
    _log(conn, 2026, 1, "Vet Back", "UGA", "RB", 20.0, 1.0)
    _td(conn, 2026, 1, "Vet Back", "UGA", {1})
    conn.commit()
    row = T.merged_usage(conn, 2026)[1]["UGA"][normalize_name("Vet Back")]
    assert abs(row["anytime_td"] - (0.25 * 1.0 + 0.75 * 0.5)) < 1e-9, row


def test_once_a_team_has_played_last_seasons_men_leave_its_volume():
    """A graduate counted in the team's volume diluted every teammate's
    share — the blend 'as written' scored 0.1836 against 0.1765 for no
    blend at all, three games in. He stays priceable (a returner the books
    quote), and he counts when he is the man being priced."""
    conn = _full_seasons()
    for who, carries in (("Grad Back", 15.0), ("Vet Back", 10.0)):
        _log(conn, 2025, 10, who, "UGA", "RB", carries, 1.0)
    _log(conn, 2025, 10, "Bama Back", "BAMA", "RB", 12.0, 1.0)
    _log(conn, 2026, 2, "Vet Back", "UGA", "RB", 12.0, 1.0)
    _log(conn, 2026, 2, "New Back", "UGA", "RB", 8.0, 1.0)
    conn.commit()
    _s, usage, why = T.merged_usage(conn, 2026)
    grad, vet, new = (normalize_name(n) for n in ("Grad Back", "Vet Back", "New Back"))
    assert why[("UGA", grad)][0] == "prior" and grad in usage["UGA"], "still priceable"
    counted = T.volume_rows(usage["UGA"], why, "UGA")
    assert usage["UGA"][grad] not in counted
    assert {id(u) for u in counted} == {id(usage["UGA"][vet]), id(usage["UGA"][new])}
    assert any(u is usage["UGA"][grad] for u in T.volume_rows(usage["UGA"], why, "UGA", keep=grad)), \
        "the man being priced always counts"
    # A team that has not played yet is all last season, and all of it counts.
    assert len(T.volume_rows(usage["BAMA"], why, "BAMA")) == len(usage["BAMA"])
    # And with no provenance at all (August's fallback) nothing is left out.
    assert len(T.volume_rows(usage["UGA"], {}, "UGA")) == len(usage["UGA"])


def test_the_touchdown_board_and_the_scan_sum_their_volumes_over_volume_rows():
    import inspect
    from engine import gamescan as G
    src = inspect.getsource(T.build_cfb_td_longshots)
    assert "volume_rows(usage.get(usage_team) or {}, usage_why, usage_team, keep=norm)" in src
    assert 'for p in team_rows) or 1.0' in src and 'for p in team_rows)' in src.split("team_rz = ")[1][:80]
    assert "team_u.values()" not in src, "no volume summed over every row any more"
    conn = _full_seasons()
    for who, carries in (("Grad Back", 15.0), ("Vet Back", 10.0)):
        _log(conn, 2025, 10, who, "UGA", "RB", carries, 1.0)
    _log(conn, 2026, 2, "Vet Back", "UGA", "RB", 12.0, 1.0)
    _log(conn, 2026, 2, "New Back", "UGA", "RB", 8.0, 1.0)
    conn.commit()
    scan = {k: v for k, v in G.cfb_usage(conn, 2026).items() if k[0] == "UGA"}
    names = {v["name"] for v in scan.values()}
    assert names == {"Vet Back", "New Back"}, names
    assert abs(sum(v["carry_share"] for v in scan.values()) - 1.0) < 0.01


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
