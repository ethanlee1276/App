"""Head-to-head: a player's past games against one opponent.

Ethan, 2026-09-01: "Add an option too be able too look up past game data
for player for nfl and CFB. For example, the rams take on the 49ers week
one and I wanna see how Devonte Adam's did the last time the 49ers
played the rams. Also make sure we don't have any issues with the names
like we did before."

Two contracts under test. The data one: `statlogs.versus` filters the
already-ingested game logs to one opponent, across every stored season,
one row PER GAME with every market on it. The names one — the half he
called out — is a design rather than a patch: the typed player name goes
through the SAME ranked resolution the search box uses (his own
misspelling is pinned below), and the opponent is never typed at all —
`opponents_of` hands the page the exact stored keys, the page offers
them as a picker, and the choice comes back verbatim.

Run directly: `python3 tests/test_versus.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db
from engine import statlogs


def _fixture():
    """Adams's history: 49ers games across three seasons and two clubs,
    plus a Chiefs game that must never leak into the 49ers answer."""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "hist.db")
    conn = _db.connect(path)
    rows = []
    games = [(2022, "005", "LV", "SF", 1, {"rec_yds": 81.0,
                                           "receptions": 7.0}),
             (2023, "017", "LV", "SF", 0, {"rec_yds": 101.0,
                                           "receptions": 8.0,
                                           "anytime_td": 1.0}),
             (2025, "012", "LA", "SF", 1, {"rec_yds": 66.0,
                                           "receptions": 5.0}),
             (2025, "004", "LA", "KC", 0, {"rec_yds": 120.0})]
    for season, wk, team, opp, home, stats in games:
        for market, value in stats.items():
            rows.append(dict(sport="nfl", season=season, period=wk,
                             game_id=f"G{season}{wk}",
                             player="Davante Adams", team=team,
                             opponent=opp, position="WR", home=home,
                             market=market, value=value))
    # A CFB receiver, dated periods and a school-name opponent key.
    for d, opp in (("2024-11-30", "Ohio State"), ("2025-08-30", "Akron")):
        rows.append(dict(sport="cfb", season=int(d[:4]), period=d,
                         game_id=f"C{d}", player="Jeremiah Smith",
                         team="Michigan", opponent=opp, position="WR",
                         home=1, market="rec_yds", value=90.0))
    _db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    return path


def _fresh_index():
    """The fuzzy fallback caches each league's name list for 15 minutes —
    right for the droplet, wrong across tests that each build their own
    DB under the same sport key."""
    statlogs._NAME_INDEX.clear()


# --- the names half, pinned with Ethan's own misspelling ---------------------
def test_ethans_own_misspelling_resolves_to_the_stored_player():
    """"Devonte Adam's" — wrong vowels, stray apostrophe — must land on
    Davante Adams exactly as the search box would land him, because it is
    the search box's resolver doing the landing."""
    path = _fixture()
    _fresh_index()
    got = statlogs.opponents_of("nfl", "Devonte Adam's", db_path=path)
    assert got.get("player") == "Davante Adams", got
    got = statlogs.versus("nfl", "devonte adams", "SF", db_path=path)
    assert got.get("player") == "Davante Adams"
    assert len(got["games"]) == 3


def test_a_name_that_resolves_to_nobody_returns_empty_not_a_guess():
    path = _fixture()
    _fresh_index()
    assert statlogs.opponents_of("nfl", "Zzyzx Quorblat", db_path=path) == {}
    assert statlogs.versus("nfl", "Zzyzx Quorblat", "SF", db_path=path) == {}


# --- the picker's options are stored keys, most recently met first -----------
def test_opponents_are_exact_stored_keys_most_recently_met_first():
    path = _fixture()
    _fresh_index()
    got = statlogs.opponents_of("nfl", "Davante Adams", db_path=path)
    opps = got["opponents"]
    assert [o["opponent"] for o in opps] == ["SF", "KC"]
    assert opps[0]["games"] == 3 and opps[1]["games"] == 1


# --- the head-to-head itself -------------------------------------------------
def test_every_stored_game_against_them_newest_first_other_teams_excluded():
    path = _fixture()
    _fresh_index()
    got = statlogs.versus("nfl", "Davante Adams", "SF", db_path=path)
    games = got["games"]
    assert [g["season"] for g in games] == [2025, 2023, 2022]
    assert [g["week"] for g in games] == [12, 17, 5]
    assert all("KC" not in str(g) for g in games), \
        "a Chiefs game leaked into the 49ers history"
    # One row per GAME, every ingested market on it, in display order.
    g23 = games[1]
    assert list(g23["stats"]) == ["Receiving Yards", "Receptions",
                                  "Anytime TD"]
    assert g23["stats"]["Receiving Yards"] == 101.0
    assert g23["home"] is False


def test_the_history_follows_the_man_not_the_laundry():
    """His Raiders games against the 49ers belong in the answer next to
    his Rams ones — and each row says which club he was on."""
    path = _fixture()
    _fresh_index()
    games = statlogs.versus("nfl", "Davante Adams", "SF",
                            db_path=path)["games"]
    assert [g["team"] for g in games] == ["LA", "LV", "LV"]


def test_cfb_rides_the_same_rails_with_dated_games_and_tolerant_keys():
    """He asked for CFB by name. School keys are words, so the resolver
    accepts a casual spelling of a school the player has actually faced
    — but only from his own logged opponents, never the whole FBS."""
    path = _fixture()
    _fresh_index()
    got = statlogs.versus("cfb", "Jeremiah Smith", "ohio state",
                          db_path=path)
    assert got["opponent"] == "Ohio State"
    assert got["games"][0]["date"] == "2024-11-30"
    assert "week" not in got["games"][0]
    miss = statlogs.versus("cfb", "Jeremiah Smith", "Alabama",
                           db_path=path)
    assert miss["games"] == [] and miss["opponent"] == ""


def test_no_db_degrades_to_empty_like_everything_else_here():
    assert statlogs.opponents_of("nfl", "Anyone",
                                 db_path="/no/such.db") == {}
    assert statlogs.versus("nfl", "Anyone", "SF",
                           db_path="/no/such.db") == {}
    assert statlogs.versus("ufc", "Anyone", "SF") == {}, \
        "no log-backed sport, no head-to-head"


# --- the server route: exists, reads statlogs, gates nothing -----------------
def test_the_server_serves_the_head_to_head_and_gates_it_not():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    assert '"/api/players/versus"' in src
    i = src.index("def _players_versus(")
    body = src[i:src.index("\n    def ", i + 10)]
    assert "statlogs.versus" in body and "statlogs.opponents_of" in body
    assert "_entitled" not in body, "_players_versus grew a paywall"


# --- the page: picked, never typed; drawn on every profile variant -----------
def test_the_page_offers_stored_opponents_and_sends_the_choice_verbatim():
    src = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    assert "function vsBlockHTML(" in src
    # Both card variants carry the tail, so a priced star and a
    # searched-up bench player get the same option.
    assert "pricedProfileHTML(priced.get(mkt), chips, vsTail)" in src
    assert "historyProfileHTML(rows[0], mkt, stats[mkt] || [], chips, vsTail)" in src
    # The picker is a select built from the endpoint's own opponent
    # keys — no free-typed team name anywhere in the flow.
    i = src.index('e.target.closest(".vs-open")')
    body = src[i:i + 2500]
    assert "/api/players/versus" in body
    assert 'value="${escapeAttr(o.opponent)}"' in body
    assert "teamNameIn(sport, o.opponent)" in body, \
        "the option must show the club's name, not its abbreviation"
    # Handlers are delegated at the document like .prof-tab — profile
    # cards are innerHTML'd away on every refresh.
    j = src.index('e.target.closest(".vs-select")')
    sel = src[j:j + 2500]
    assert "vs=${encodeURIComponent(sel.value)}" in sel \
        or "vs=${encodeURIComponent(vs)}" in sel


def test_a_card_that_knows_tonights_opponent_loads_that_matchup_in_one_tap():
    """Ethan's flow IS the one-tap case: "the rams take on the 49ers week
    one and I wanna see how Devonte Adam's did the last time the 49ers
    played the rams." A priced card knows who he plays, so the button
    names them and the tap that opens the box picks them — the full
    picker still stands for every other club he has faced."""
    src = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = src.index("function vsBlockHTML(")
    blk = src[i:i + 1400]
    assert 'data-opp="${escapeAttr(opp)}"' in blk
    assert "teamNameIn(lg, opp)" in blk, \
        "the button must name the club, not print an abbreviation"
    j = src.index('e.target.closest(".vs-open")')
    body = src[j:j + 3000]
    assert "box.dataset.opp" in body
    assert "opps.some((o) => o.opponent === tonight)" in body, \
        "preselect only a club we actually hold games against"
    assert 'dispatchEvent(new Event("change", { bubbles: true }))' in body


def test_no_league_or_team_names_are_hardcoded_in_the_flow():
    """The block is data-driven end to end: the sports list is the only
    constant, and 49ers/Rams/schools never appear in the code."""
    import re
    src = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = src.index("const VS_SPORTS")
    block = src[i:src.index("function pricedProfileHTML")]
    assert '"nfl", "cfb"' in src[i:i + 120], "NFL and CFB are the ask"
    # Ethan's quote lives in the comments and names his example teams —
    # the CODE is what must stay data-driven.
    code = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    for word in ("49ers", "Rams", "Adams", "Ohio State"):
        assert word not in code, f"{word} hardcoded in the head-to-head"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
