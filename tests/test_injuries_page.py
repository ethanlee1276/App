"""The injury report page — every sport, one league-wide status board.

Ethan, 2026-08-10: "Implement an injury report page for all sports...
it should be easier to find them [than] digging through fantasy."

What is pinned here: the parser reads ESPN's envelope by KEY and drops
rather than guesses; the build fails per-league instead of whole-board;
the page is wired end to end (nav tab, view, router, sport-switch
re-render) with UFC's tab hidden because no MMA injury feed exists; and
the launcher refreshes the file the page fetches. The live endpoint is
unreachable from this sandbox — same as every ESPN feed here — so shape
comes from fixtures and the laptop's `--check` probes the real host.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import espninjuries as inj                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


FIXTURE = {
    "injuries": [
        {"id": "22", "displayName": "Arizona Cardinals", "injuries": [
            {"status": "Injured Reserve", "date": "2026-08-05T18:16Z",
             "shortComment": "Placed on IR Tuesday.",
             "athlete": {"displayName": "Sam Player",
                         "position": {"abbreviation": "LB"},
                         "headshot": {"href": "https://a.espncdn.com/x.png"}},
             "details": {"type": "Achilles", "detail": "Tear",
                         "side": "Left", "returnDate": "2027-09-01"}},
            {"status": "Questionable", "date": "2026-08-09T11:00Z",
             "athlete": {"displayName": "Jo Backup"},
             "details": {"type": "Hamstring", "side": "Not Specified"}},
            # No player name → not a row. No status → not a row.
            {"status": "Out", "athlete": {}},
            {"athlete": {"displayName": "No Status"}},
        ]},
        {"displayName": "Buffalo Bills", "injuries": []},
    ],
}


def test_parser_reads_by_key_and_drops_rather_than_guesses():
    rows = inj.parse_injuries(FIXTURE)
    assert len(rows) == 2
    a = rows[0]
    assert a["team"] == "Arizona Cardinals"
    assert a["player"] == "Sam Player" and a["pos"] == "LB"
    assert a["status"] == "Injured Reserve"
    assert a["injury"] == "Achilles Tear" and a["side"] == "Left"
    assert a["return_date"] == "2027-09-01"
    assert a["face"].startswith("https://")
    b = rows[1]
    # "Not Specified" is ESPN's null — it must come through as None, not
    # as a word the page prints as though it meant something.
    assert b["side"] is None
    assert b["injury"] == "Hamstring"
    assert b["face"] is None and b["return_date"] is None


def test_parser_survives_garbage():
    for junk in (None, {}, {"injuries": None}, {"injuries": [{}]},
                 {"injuries": [{"injuries": [None]}]}):
        try:
            assert inj.parse_injuries(junk) == []
        except AttributeError:
            raise AssertionError(f"choked on {junk!r}")


def test_every_league_has_a_feed_and_ufc_deliberately_does_not():
    assert set(inj.LEAGUES) == {"nfl", "mlb", "nba", "wnba", "cfb"}
    for url in inj.LEAGUES.values():
        assert url.endswith("/injuries")


def test_build_fails_per_league_not_whole_board():
    """A dead basketball feed must not blank the NFL board."""
    import injuries_build
    from engine.sources.fetch import DataUnavailable

    def half_dead(league):
        if league in ("nba", "wnba"):
            raise DataUnavailable("refused")
        return FIXTURE

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "injuries.json"
        with mock.patch.object(injuries_build, "fetch_injuries", half_dead):
            injuries_build.main(["--out", str(out)])
        d = json.loads(out.read_text())
    assert d["status"] == "live"
    assert len(d["sports"]["nfl"]) == 2
    assert "nba" not in d["sports"]
    assert len(d["notes"]) == 2


def test_the_page_is_wired_end_to_end():
    html = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()
    assert 'data-view="injuries"' in html
    assert 'id="view-injuries"' in html and 'id="injuries-body"' in html
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    assert "async function renderInjuries" in js
    assert "data/injuries.json" in js
    assert 'if (name === "injuries") renderInjuries();' in js
    # Switching sport while ON the page must redraw it for the new league,
    # the same contract rosters and standings already keep.
    assert 'if (state.view === "injuries") renderInjuries();' in js
    order = js[js.index("const VIEW_ORDER"):]
    assert '"injuries"' in order[:order.index("]")]
    hidden = js[js.index("const HIDDEN_VIEWS"):]
    ufc_line = [l for l in hidden[:hidden.index("};")].splitlines()
                if l.strip().startswith("ufc:")]
    assert ufc_line and '"injuries"' in ufc_line[0], \
        "UFC has no injury feed anywhere — the tab must hide, not render empty"


def test_the_launcher_refreshes_what_the_page_fetches():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def refresh_injuries")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "injuries_build.py" in body and "web/data/injuries.json" in body
    j = src.index("def refresh_all")
    assert "refresh_injuries(" in src[j:src.index("\ndef ", j + 10)]
    assert "web/data/injuries.json" in src[src.index("Product data"):]


def test_the_recommended_board_carries_an_injury_watch():
    """The page is the library; the WATCH is the bettor's question at
    6pm — anyone on TONIGHT'S teams filed recently? Only fresh filings
    show (a two-month IL entry is already in every price), an unmatched
    team name refuses to join rather than guessing, and the async fill
    re-judges the sub-tab rooms so the Watchlists tab tells the truth."""
    html = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()
    assert 'id="injury-watch"' in html
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    assert "async function renderInjuryWatch" in js
    assert "\n  renderInjuryWatch();" in js, "missing from the load() chain"
    rooms = js[js.index("const REC_ROOMS"):]
    assert '"injury-watch"' in rooms[:rooms.index("];")], \
        "the block would float outside every room"
    fn = js[js.index("async function renderInjuryWatch"):]
    fn = fn[:fn.index("\nfunction renderGameBets")]
    assert "10 * 86400e3" in fn, "the ten-day recent cut is gone"
    assert 'href="#injuries"' in fn, "no escalation to the full board"
    assert "groupRecommended()" in fn, "async fill never re-judges the rooms"
    assert "r.abbr && tonight.has(r.abbr)" in fn, \
        "an unmatched team name must not join"


def test_the_injuries_probe_is_reachable():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--injuries" in argv' in src
    i = src.index("def show_injuries")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "injuries_build" in body


def test_availability_tone_is_keyword_not_exact_match():
    """ESPN's wordings drift ("Out", "Injured Reserve", "60-Day IL").
    The tone map must key on availability words so a new phrasing lands
    in a sane bucket instead of silently rendering unstyled."""
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    fn = js[js.index("function injTone"):]
    fn = fn[:fn.index("\n}")]
    for word in ("injured reserve", "questionable", "day-to-day",
                 "probable"):
        assert word in fn, word



# --- the "showing active while injured" class of defect ---------------------
# Ethan, 2026-08-12: "nfl injuries are not updating. there is lions players
# injured that are showing active on the site." Three separate causes, all
# pinned below: ESPN keeps a cleared player in the feed as "Active" with no
# injury; it accumulates every filing a player has ever had; and a declining
# feed is answered from cache with no error, so old rows wear a fresh stamp.

def _iso(days_ago: float) -> str:
    """A feed-style stamp N days back from now. The fixture dates are
    RELATIVE on purpose: the build ages return notices out, so a fixture
    with absolute dates is a test that starts failing by calendar."""
    import datetime as dtm
    t = dtm.datetime.now(dtm.timezone.utc) - dtm.timedelta(days=days_ago)
    return t.strftime("%Y-%m-%dT%H:%MZ")


RETURNED_THEN_HURT = {
    "injuries": [
        {"displayName": "Detroit Lions", "injuries": [
            # Oldest first, deliberately: the feed's order is not chronology.
            {"status": "Out", "date": _iso(17),
             "athlete": {"displayName": "Two Filings",
                         "position": {"abbreviation": "WR"}},
             "details": {"type": "Hamstring"}},
            {"status": "Active", "date": _iso(12),
             "athlete": {"displayName": "Two Filings",
                         "position": {"abbreviation": "WR"}},
             "details": {}},
            # ...then hurt again, which is the row that must win.
            {"status": "Injured Reserve", "date": _iso(7),
             "athlete": {"displayName": "Two Filings",
                         "position": {"abbreviation": "WR"}},
             "details": {"type": "Knee"}},
            {"status": "Active", "date": _iso(8),
             "athlete": {"displayName": "Fully Cleared",
                         "position": {"abbreviation": "RB"}},
             "details": {}},
            # The Cade Mays shape: cleared long ago, nothing filed since —
            # August carries no filing duty, so no newer row ever arrives
            # to beat this one. The BUILD must age it out.
            {"status": "Active", "date": _iso(40),
             "athlete": {"displayName": "Old News",
                         "position": {"abbreviation": "C"}},
             "details": {}},
            # And a return notice with no date at all can never age out,
            # so it must not survive either.
            {"status": "Active",
             "athlete": {"displayName": "No Date",
                         "position": {"abbreviation": "G"}},
             "details": {}},
        ]},
    ],
}


def test_a_cleared_player_is_not_a_designation():
    """"Active" with no injury named is a RETURN notice. Counting it as a
    designation reports healthy players as hurt; showing it in green on a
    board headed "Injury watch" reports hurt players as available."""
    rows = inj.parse_injuries(RETURNED_THEN_HURT)
    cleared = [r for r in rows if r["player"] == "Fully Cleared"][0]
    assert inj.is_return(cleared)
    hurt = [r for r in rows if r["status"] == "Injured Reserve"][0]
    assert not inj.is_return(hurt)
    # An "Active" row that DOES name an injury is a real designation
    # (a player active but carrying something) — not a return.
    assert not inj.is_return({"status": "Active", "injury": "Knee"})


def test_only_the_newest_filing_per_player_survives():
    """The exact shape of Ethan's report: a Lion who was hurt, cleared, and
    hurt again. All three filings rendered means one player reads as three,
    and the stale "Active" can sit above the live "Injured Reserve"."""
    rows = inj.current_rows(inj.parse_injuries(RETURNED_THEN_HURT))
    assert len(rows) == 4, "one row per player"
    by_name = {r["player"]: r for r in rows}
    assert by_name["Two Filings"]["status"] == "Injured Reserve"
    assert by_name["Two Filings"]["injury"] == "Knee"
    assert by_name["Fully Cleared"]["status"] == "Active"


def test_a_return_notice_ages_out_a_designation_does_not():
    """Cade Mays broke a wrist bone in camp on 2026-08-09 and the page
    still said "Active" nine days later — off a return notice ESPN never
    retires, with no newer filing to beat it because August carries no
    reporting duty. A cleared-to-play row is news for RETURN_NOTE_DAYS
    and a standing claim of health afterwards; a designation stays for
    as long as the league lists it, however old."""
    now = 1_800_000_000.0
    day = 86400.0
    stamp = lambda days: inj.dt.datetime.fromtimestamp(  # noqa: E731
        now - days * day, inj.dt.timezone.utc).isoformat()
    fresh_ret = {"status": "Active", "injury": None, "date": stamp(3)}
    stale_ret = {"status": "Active", "injury": None, "date": stamp(40)}
    undated = {"status": "Active", "injury": None, "date": None}
    old_desig = {"status": "Out", "injury": "Knee", "date": stamp(200)}
    kept = inj.drop_stale_returns([fresh_ret, stale_ret, undated, old_desig],
                                  now=now)
    assert fresh_ret in kept, "a recent return IS team news"
    assert stale_ret not in kept, "a month-old Active is a health claim"
    assert undated not in kept, "no date means it can never age out"
    assert old_desig in kept, "designations never age out — they ARE status"


def test_the_build_applies_the_return_cut():
    """End to end through the builder: Old News (40 days) and No Date
    must not reach the file the page serves; the fresh return and the
    live designation must."""
    import injuries_build

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "injuries.json"
        with mock.patch.object(injuries_build, "fetch_injuries",
                               lambda league: RETURNED_THEN_HURT), \
             mock.patch.object(injuries_build, "cache_age_s",
                               lambda league: 60.0):
            injuries_build.main(["--out", str(out)])
        d = json.loads(out.read_text())
    names = {r["player"] for r in d["sports"]["nfl"]}
    assert names == {"Two Filings", "Fully Cleared"}


def test_the_build_dedupes_and_reports_how_old_the_rows_are():
    """`fetch_json` answers a failed request from cache and raises nothing,
    so the build stamps `generated_at` = now over data that stopped moving
    days ago. The age of the CACHE FILE is the age of the rows."""
    import injuries_build

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "injuries.json"
        with mock.patch.object(injuries_build, "fetch_injuries",
                               lambda league: RETURNED_THEN_HURT), \
             mock.patch.object(injuries_build, "cache_age_s",
                               lambda league: 4 * 86400):
            injuries_build.main(["--out", str(out)])
        d = json.loads(out.read_text())
    assert len(d["sports"]["nfl"]) == 2, "the build must dedupe per player"
    assert d["ages_s"]["nfl"] == 4 * 86400
    assert d["stale_after_s"] > 0
    assert any("declining" in n for n in d["notes"]), \
        "four-day-old rows must say so"


def test_a_fresh_pull_raises_no_staleness_note():
    """The banner has to stay quiet on a healthy day, or it is noise."""
    import injuries_build

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "injuries.json"
        with mock.patch.object(injuries_build, "fetch_injuries",
                               lambda league: RETURNED_THEN_HURT), \
             mock.patch.object(injuries_build, "cache_age_s",
                               lambda league: 60.0):
            injuries_build.main(["--out", str(out)])
        d = json.loads(out.read_text())
    assert not d["notes"], d["notes"]
    assert d["ages_s"]["nfl"] == 60


def test_both_surfaces_agree_on_what_a_row_means():
    """The page's fresh strip cut returns; the recommended board's injury
    watch did not, and read the same file. One helper, both callers."""
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    assert "function isReturnRow(" in js
    i = js.index("async function renderInjuryWatch(")
    watch = js[i:i + 2000]
    assert "isReturnRow(" in watch, "the watch still lists cleared players"
    j = js.index("async function renderInjuries(")
    page = js[j:js.index("\nasync function ", j + 10)]
    assert "isReturnRow(" in page


def test_the_page_says_when_the_data_stopped_moving():
    js = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
    i = js.index("async function renderInjuries(")
    page = js[i:js.index("\nasync function ", i + 10)]
    assert "ages_s" in page and "stale_after_s" in page
    assert "staleBanner" in page
    # And the footer must stop claiming a refresh time it cannot vouch for.
    assert "Designations collected" in page

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
