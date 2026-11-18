"""A locked board says it is locked, and a school is named on its own page
(USEREYES1, 18 November 2026).

Walking college basketball as a visitor: its Futures page said "No season to
project — This sport has no futures board yet", over a file the paywall had
kept (`locked: {"whole_board": 16}`) — every league's futures read the same to
anyone without a plan. Tennessee's team page was headed "TENN": a school's
name came from the books' spellings alone, and only the schools the books
had priced are in it. A school that matched nothing was told to try "Los
Angeles Rams". What these hold:

  * a futures board the paywall kept shows the members' card, not "no
    season";
  * a college basketball school no book has priced takes its name off its
    kept card; a book's spelling still wins where there is one;
  * a team that matched nothing is given an example in its own league.

    python3 tests/test_a_locked_board_and_a_school_say_what_they_are.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")


def test_a_kept_futures_board_is_for_members_not_missing():
    assert ('host.innerHTML = ((d || {}).locked || {}).whole_board ? memberLockHTML("The season’s projections '
            'are for members",') in APP
    i = APP.index("((d || {}).locked || {}).whole_board ? memberLockHTML(")
    assert APP.index("No season to project", i) > i, "the empty answer is the other branch"


def test_a_school_no_book_priced_is_named_off_its_card():
    from engine import cbbteams, teamdex
    d = tempfile.mkdtemp()
    cards = os.path.join(d, "cbb_cards.json")
    with open(cards, "w", encoding="utf-8") as fh:
        json.dump({"teams": {"TENN": {"name": "Tennessee Volunteers", "loc": "Tennessee", "short": "Tennessee"}}}, fh)
    keep_path, keep_map = cbbteams.CARDS_PATH, teamdex.name_map
    try:
        cbbteams.CARDS_PATH = cards
        teamdex._CBB_CARD_NAMES.clear()
        teamdex.name_map = lambda sport: {}
        assert teamdex.label("TENN", "cbb") == "Tennessee Volunteers"
        assert teamdex.label("ZZZ", "cbb") == "ZZZ", "no card, the code as before"
        teamdex.name_map = lambda sport: {"Tennessee": "TENN"}
        assert teamdex.label("TENN", "cbb") == "Tennessee", "a book's spelling still wins"
        teamdex.name_map = lambda sport: {}
        assert teamdex.label("TENN", "nba") == "TENN", "only college basketball reads the cards"
    finally:
        cbbteams.CARDS_PATH, teamdex.name_map = keep_path, keep_map
        teamdex._CBB_CARD_NAMES.clear()


def test_a_team_that_matched_nothing_gets_an_example_in_its_own_league():
    i = MORE.index("No team matched “${escapeHtml(st.team)}”")
    block = MORE[MORE.rindex("if (!d.profile) {", 0, i):MORE.index("return;", i)]
    assert "“Tennessee” or “TENN”" in block and 'sp === "cbb" || sp === "cfb"' in block
    assert "nhl: \"“Boston Bruins”, “Bruins” or “BOS”\"" in block
    assert "“Los Angeles Rams”, “Rams” or “LA”" in block, "football keeps its example"



def test_a_page_that_could_not_be_read_is_not_called_a_name_that_matched_nothing():
    # 18 November 2026: an answer cut short ("{}") read "No team matched “TENN”" for a school the site has.
    i = MORE.index("This team’s page could not be read just now.")
    assert "if (!d.profile && !Array.isArray(d.resolved)) {" in MORE[i - 300:i]
    assert i < MORE.index("No team matched “${escapeHtml(st.team)}”"), "asked before the no-match words"
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"sport": sport, "query": name, "resolved": [],' in srv, "the server's no-match answer carries its list"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
