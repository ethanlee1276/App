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
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as _db
from engine import statlogs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _windows                                             # noqa: E402


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


def test_the_head_to_head_reads_an_index_not_the_whole_partition():
    """Ethan, 2026-09-01: "the versus button takes a long time to load."
    Every player_game_logs index led (sport, market, …) because the
    model reads one market at a time — but the site asks "everything on
    this man", and those queries were scanning the sport's entire
    partition (measured on a 2M-row fixture: 501ms for one head-to-head
    on a fast dev disk; the droplet's one core is where it hurt). The
    plan, not the timing, is what a test can hold still."""
    path = _fixture()
    conn = _db.connect(path)
    try:
        for sql in (
            "SELECT season, period, game_id, team, home, market, value "
            "FROM player_game_logs WHERE sport=? AND player=? AND opponent=?",
            "SELECT opponent, COUNT(DISTINCT game_id) FROM player_game_logs "
            "WHERE sport=? AND player=? GROUP BY opponent",
            "SELECT team, position FROM player_game_logs "
            "WHERE sport=? AND player=? ORDER BY season DESC, period DESC "
            "LIMIT 1",
        ):
            plan = " ".join(str(tuple(r)) for r in conn.execute(
                f"EXPLAIN QUERY PLAN {sql}",
                ("nfl", "Davante Adams") + (("SF",) if sql.count("?") == 3
                                            else ())))
            assert "idx_logs_player" in plan, (sql, plan)
    finally:
        conn.close()


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
    #
    # THE TAIL REACHES THE CALL, not the exact spelling of the call. This
    # pinned the whole argument list, which broke the day the priced card
    # grew a fourth argument (`deep`, 2026-09-10) — a change that had
    # nothing to do with the versus block and could not have removed it.
    assert re.search(r"pricedProfileHTML\(priced\.get\(mkt\), chips, vsTail\b",
                     src), "the priced card no longer gets the versus tail"
    assert re.search(
        r"historyProfileHTML\(rows\[0\], mkt, stats\[mkt\] \|\| \[\], chips, vsTail\b",
        src), "the history card no longer gets the versus tail"
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


# --- his line, read the way a box score is read -----------------------------
def _app():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def _vs_stats(stats):
    """Run the page's own `vsStatsHTML` over one game's stats.

    THE REAL FUNCTION, lifted out of app.js and executed — not a Python
    re-implementation of it, which would be a second copy of the rule
    that could agree with the test while disagreeing with the page.
    """
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:                       # a box with no JS runtime
        return None
    app = _app()
    i = app.index("const VS_PHASES = ")
    j = app.index("\n}\n", app.index("function vsStatsHTML(")) + 2
    src = ("const escapeHtml = (x) => String(x);\n" + app[i:j]
           + "\nconsole.log(vsStatsHTML(" + json.dumps(stats) + "));\n")
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "vs.js")
        open(f, "w", encoding="utf-8").write(src)
        out = subprocess.run([node, f], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", out.stdout)).strip()


def test_a_phase_he_never_took_part_in_is_not_drawn():
    """Ethan, 2026-09-10, over a receiver's head-to-head: "all the words
    are bunched and shit, it's kinda hard too read."

    More than half of that row was a phase he was never going to have —
    "0 rushing yards … 0 carries" on a wide receiver is not a light day,
    it is a stat that does not apply to him."""
    got = _vs_stats({"Rushing Yards": 0, "Receiving Yards": 139,
                     "Receptions": 11, "Targets": 15, "Carries": 0,
                     "Anytime TD": 0})
    if got is None:
        return
    assert "Rush Yds" not in got and "Car" not in got, got
    assert "139 Rec Yds" in got and "11 Rec" in got and "15 Tgts" in got, got


def test_a_zero_with_the_opportunity_behind_it_is_kept():
    """The rule this codebase settled the same day in
    `sources.cfbstats.ZERO_WHEN`: a zero with opportunity behind it is
    evidence. Nine carries for nothing is a bad day, not an absent one,
    and it is exactly what somebody checking a head-to-head wants."""
    got = _vs_stats({"Carries": 9, "Rushing Yards": 0, "Targets": 0,
                     "Receptions": 0, "Receiving Yards": 0, "Anytime TD": 0})
    if got is None:
        return
    assert "9 Car" in got and "0 Rush Yds" in got, got
    assert "Rec" not in got, "a phase with no opportunity survived"


def test_the_scoring_line_is_never_dropped_for_being_zero():
    """Anytime TD sits outside the phases, which is what keeps it: a zero
    there is the ANSWER to "did he score against them", not the absence
    of one.

    THE FIXTURE IS A BLANK RECEIVING DAY on purpose. Asserting it against
    a game he caught passes in would pass even if Anytime TD were folded
    into the receiving phase, because that phase would be drawn anyway —
    which is how the first cut of this test let exactly that mutation
    through."""
    got = _vs_stats({"Targets": 0, "Receptions": 0, "Receiving Yards": 0,
                     "Anytime TD": 0})
    if got is None:
        return
    assert "0 Anytime TD" in got, got
    assert "Rec" not in got, "the receiving phase was drawn on a blank day"
    app = _app()
    i = app.index("const VS_PHASES = ")
    assert "Anytime TD" not in app[i:app.index("]];", i)], \
        "the scoring line was folded into a phase that can drop it"


def test_a_sport_with_no_phases_is_left_exactly_as_it_was():
    """Grouping football phases over a baseball line would be nonsense,
    and "0 hits" IS the read there — so a label this table has no phase
    for is shown whatever its value."""
    got = _vs_stats({"Total Bases": 0, "Hits": 0, "Home Runs": 0})
    if got is None:
        return
    for want in ("0 Total Bases", "0 Hits", "0 Home Runs"):
        assert want in got, (want, got)


def test_a_game_with_nothing_on_it_says_so_rather_than_drawing_blank():
    got = _vs_stats({})
    if got is None:
        return
    assert "nothing recorded" in got, got


def test_the_line_is_one_element_per_stat_and_not_a_joined_string():
    """The other half of the report. The whole line used to be joined
    with middots into a right-aligned `num` cell, so the browser wrapped
    it wherever it ran out of room — a number ending one line and its
    unit starting the next. A pill per stat can only break between
    stats."""
    app = _app()
    i = app.index("function vsStatsHTML(")
    fn = app[i:app.index("\n}\n", i)]
    assert 'class="vs-stat"' in fn
    assert '.join(" · ")' not in fn, "the middot blob is back"
    # AND THE ROW IS A BLOCK, not a two-column table row that has to
    # share a phone's width with the stats.
    # THE LISTENER, sliced to its own end rather than to a character
    # count. The first cut used `app[j:j + 2500]`, which ran past the
    # listener into `_profileHead` — a function that joins a team, a
    # position and an opponent with a middot perfectly legitimately — so
    # the assertion below failed against correct code. `_windows.until`
    # is the house answer to exactly that.
    j = app.index('e.target.closest(".vs-select")')
    row = _windows.until(app, 'e.target.closest(".vs-select")',
                         "//: Shared head:")
    assert 'class="vs-game"' in row and 'class="vs-when"' in row
    assert "<td" not in row, "still a table row"
    # AND THE ROW GOES THROUGH THE HELPER. Asserting only inside
    # `vsStatsHTML` left the blob free to come back in the row builder,
    # which is where it lived in the first place — the mutation sweep
    # walked straight through that gap.
    assert "vsStatsHTML(g.stats)" in row, "the row builds its own line again"
    assert '.join(" · ")' not in row, "the middot blob is back in the row"


def test_the_head_to_head_surfaces_have_their_styles():
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    for sel in (".vs-games", ".vs-game", ".vs-when", ".vs-club", ".vs-line",
                ".vs-stat", ".vs-none"):
        assert sel + " " in css or sel + "," in css or sel + "{" in css, sel


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
