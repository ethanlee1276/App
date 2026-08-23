"""Fighters were never in the search, and no amount of adding leagues
would have put them there.

Ethan, 2026-08-23, an hour after the all-league search shipped: "also i
guess i should add im not able to search ufc players."

The league-wide search reads `player_game_logs`, and nothing writes a UFC
row to it — a fight is not a game with a stat line per market. The
promotion's numbers are career RATES and ours live in
`data/ufc_dossiers.json`, keyed by fighter. Different store, different
reader, so `engine/playersearch.py` is where the two answers are merged
and neither reader has to know the other exists.

Three things this pins:

  * a fighter is findable from any tab;
  * his card shows RATES and says so — an invented ten-fight bar chart
    would be worse than the blank space it filled;
  * our READ of him does not ride an ungated endpoint. The measured
    numbers are facts, on the same free footing as game logs. The
    archetype we assigned and the red flags we raised are analysis that
    blocks our own bets, and they stay with the picks.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, playersearch, statlogs
from engine.ufc import fighters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOOK = {
    "_readme": "bookkeeping, not a fighter",
    "_unfound": {"someone": 1},
    "Islam Makhachev": {
        "name": "Islam Makhachev", "age": 33, "division": "lightweight",
        "archetype": "grappler", "record": "27-1-0", "ufc_fights": 15,
        "fights": 28, "slpm": 2.6, "sapm": 1.5, "str_def": 0.58,
        "td_per15": 3.1, "td_acc": 0.61, "tdd": 0.94, "ctrl_per15": 5.2,
        "sub_att_per15": 1.1, "short_notice": False,
        "red_flags": ["chin damage — confirm"]},
    "Alex Pereira": {
        "name": "Alex Pereira", "age": 38, "division": "light_heavyweight",
        "archetype": "striker", "record": "12-2-0", "ufc_fights": 10,
        "fights": 14, "slpm": 4.9, "sapm": 4.1, "tdd": 0.72,
        "red_flags": []},
    "Debut Guy": {
        "name": "Debut Guy", "division": "featherweight", "ufc_fights": 0,
        "fights": 9, "record": "9-0-0", "red_flags": []},
}


def _book(data=None):
    p = os.path.join(tempfile.mkdtemp(), "ufc_dossiers.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(BOOK if data is None else data, fh)
    return p


def _logs():
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = db.connect(path)
    rows = []
    for i in range(6):
        rows.append({"sport": "nfl", "season": 2026, "period": f"{i:03d}",
                     "game_id": f"n{i}", "player": "Alex Highsmith",
                     "team": "PIT", "opponent": "CLE", "position": "LB",
                     "home": 1, "market": "pass_yds", "value": 3.0})
    db.upsert_player_logs(conn, rows)
    conn.close()
    return path


def _js():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


# --- the reader -----------------------------------------------------------

def test_a_fighter_is_findable():
    hits = fighters.search("makhachev", path=_book())
    assert [h["player"] for h in hits] == ["Islam Makhachev"]
    assert hits[0]["sport"] == "ufc"


def test_bookkeeping_keys_are_not_fighters():
    """`_readme` and `_unfound` live in the same file."""
    names = set(fighters.load(_book()))
    assert names == {"Islam Makhachev", "Alex Pereira", "Debut Guy"}


def test_a_hit_has_no_club_and_carries_its_division_instead():
    """A fighter has no team. Inventing one would put a logo and a set of
    team colours on a man who has neither."""
    h = fighters.search("pereira", path=_book())[0]
    assert h["team"] == ""
    assert h["position"] == "light heavyweight"


def test_the_deeper_record_leads_among_equals():
    hits = fighters.search("a", path=_book())
    assert [h["player"] for h in hits][:2] == ["Islam Makhachev",
                                               "Alex Pereira"]


def test_a_missing_store_searches_no_fighters_rather_than_failing():
    assert fighters.search("anyone", path="/no/such/file.json") == []
    assert fighters.load("/no/such/file.json") == {}


def test_a_half_written_store_is_not_a_crash():
    p = os.path.join(tempfile.mkdtemp(), "broken.json")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write('{"Someone": {"name": "Someone"')
    assert fighters.search("someone", path=p) == []


def test_a_blank_query_matches_nobody():
    assert fighters.search("   ", path=_book()) == []


# --- the line between a fact and our read ---------------------------------

def test_our_read_of_a_fighter_never_rides_the_ungated_endpoint():
    """Red flags and the archetype are analysis — they block our own
    bets. The measured rates and the public record are facts."""
    h = fighters.search("makhachev", path=_book())[0]
    f = h["fighter"]
    assert "red_flags" not in f and "archetype" not in f
    assert f["record"] == "27-1-0" and f["slpm"] == 2.6 and f["tdd"] == 0.94
    assert f["ufc_fights"] == 15 and f["career_fights"] == 28


def test_the_public_fields_are_an_allow_list_not_a_block_list():
    """A dossier gains fields over time. A new one must not reach a
    public endpoint because nobody remembered to exclude it."""
    book = {"X": dict(BOOK["Islam Makhachev"],
                      secret_model_note="do not ship", name="X")}
    f = fighters.search("x", path=_book(book))[0]["fighter"]
    assert "secret_model_note" not in f
    assert set(f) <= set(fighters.FACT_FIELDS) | {"ufc_fights",
                                                  "career_fights"}


# --- the merge ------------------------------------------------------------

def test_a_fighter_and_a_league_player_share_one_result_list():
    hits = playersearch.search("alex", limit=8, db_path=_logs(),
                               ufc_path=_book())
    got = {h["sport"] for h in hits}
    assert got == {"nfl", "ufc"}


def test_a_fighter_is_found_while_standing_on_the_nfl_tab():
    hits = playersearch.search("makhachev", prefer="nfl", db_path=_logs(),
                               ufc_path=_book())
    assert [h["player"] for h in hits] == ["Islam Makhachev"]


def test_ufc_is_one_of_the_sources_the_box_covers():
    assert "ufc" in playersearch.SOURCES
    # And it is NOT a log-backed league — the reason it needed its own
    # reader in the first place.
    assert "ufc" not in statlogs.SPORT_MARKETS


def test_the_preferred_source_leads_the_order():
    assert playersearch.source_order("ufc")[0] == "ufc"
    assert set(playersearch.source_order("ufc")) == set(playersearch.SOURCES)
    # An unknown tab is not an error, and removes nobody.
    assert set(playersearch.source_order("cricket")) == \
        set(playersearch.SOURCES)


def test_the_log_search_opens_one_connection_for_every_league():
    """The page re-runs this on every keystroke, and a connection per
    league on a one-core droplet is four times the cost for one answer."""
    import inspect
    src = inspect.getsource(statlogs.search_by_sport)
    assert src.count("_db.connect(") == 1


# --- the endpoint ---------------------------------------------------------

def test_the_endpoint_asks_the_merged_reader():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _players_search(")
    body = src[i:src.index("\n    def ", i + 10)]
    assert "playersearch.search(" in body
    assert "_entitled" not in body, "the search grew a paywall"


# --- the card -------------------------------------------------------------

def test_a_fighter_card_is_never_asked_for_game_logs():
    """A request that can only come back empty, whose empty answer reads
    as "we know nothing about him"."""
    js = _js()
    i = js.index("async function renderPlayers(")
    body = js[i:i + 9000]
    assert 'if (m.sport === "ufc") return;' in body


def test_the_fighter_card_says_the_numbers_are_career_rates():
    """No per-fight series exists to chart. Drawing one out of a rate
    would be inventing a series, which is worse than the blank space."""
    js = _js()
    i = js.index("function ufcProfileHTML(")
    body = js[i:i + 1800]
    assert "career" in body.lower()
    assert "gamelogBars" not in body, "a fighter card grew an invented chart"
    # And a fighter with no tracked stats says so rather than showing dashes.
    assert "no tracked fight stats for him yet" in body


def test_the_corner_block_has_exactly_one_implementation():
    """It was a closure inside renderUFC. Search needed the same block,
    and a second copy is a second thing to keep in step — the numbers are
    what would drift."""
    js = _js()
    assert js.count("function fighterColHTML(") == 1
    # The markup exists once. A second copy of the block would show up
    # here whatever it was named.
    assert js.count('<div class="ufc-corner">') == 1
    # And the UFC page reaches it by alias rather than by rebuilding it.
    # NOT a fixed slice from renderUFC: that function is long, the alias
    # sits well past any round number, and this test went red on its own
    # first run for exactly that reason. One definition, one alias.
    assert js.count("const fighterCol =") == 1
    assert "const fighterCol = fighterColHTML;" in js


def test_the_corner_block_reads_both_payload_shapes():
    """The card payload's brief says covered/career; a search hit says
    ufc_fights/career_fights, because that is what the dossier calls
    them. Renaming either would mean rewriting a payload to suit a
    renderer."""
    js = _js()
    i = js.index("function fighterColHTML(")
    body = js[i:i + 1400]
    for key in ("f.covered", "f.ufc_fights", "f.career", "f.career_fights"):
        assert key in body, key


def test_a_row_with_no_club_draws_no_team_chip():
    js = _js()
    i = js.index("async function renderPlayers(")
    body = js[i:i + 9000]
    assert "${m.team ? `${teamMarkIn(" in body
    assert "tracked fight(s)" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
