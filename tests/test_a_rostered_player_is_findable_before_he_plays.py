"""Search finds a man on the roster, not only one with a stat line.

Ethan, 2026-09-19: *"a lot of CFB players dont show up in the player
search."*

They could not. `statlogs.search` reads `player_game_logs` — everyone
who has APPEARED IN AN INGESTED GAME — and in September a college roster
is a hundred men of whom a couple of dozen have a stat line. Backups,
freshmen, specialists, anyone whose week has not been ingested: not
ranked low, ABSENT. And the page could not tell that apart from "we have
never heard of him", which is the silent-failure shape this codebase
keeps paying for.

College is where it bites hardest — 136 FBS teams against the NFL's 32,
and rosters four times the size — but the hole is every league's, so the
fix is too.

THE ROSTERS WERE ALREADY ON DISK. `web/data/rosters_<sport>.json` is
published every night and the roster page draws from it. Nothing here
fetches; the only thing missing was reading it.

AND THE LOGS STILL WIN. A man with a stat line outranks one without,
always — the roster only fills the space the logs left empty, so a thin
log store degrades into a roster search instead of into a blank page.

Run directly:
`python3 tests/test_a_rostered_player_is_findable_before_he_plays.py`
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import db as hist_db                               # noqa: E402
from engine import statlogs                                    # noqa: E402

PLAYED = "Gunner Stockton"
BENCHED = "Deshawn Pellerin"


def _roster(tmp, shape="dict"):
    """A published roster payload, in the shape `rosters.build` writes."""
    players = [
        {"player": PLAYED, "team": "UGA", "position": "QB",
         "headshot": "http://x/1.png"},
        {"player": BENCHED, "team": "UGA", "position": "WR",
         "headshot": "http://x/2.png"},
    ]
    doc = {"teams": {"UGA": {"players": players} if shape == "dict"
                     else players}}
    with open(os.path.join(tmp, "rosters_cfb.json"), "w",
              encoding="utf-8") as fh:
        json.dump(doc, fh)
    statlogs._ROSTER.clear()
    return tmp


def _logs(path):
    """A history store where ONE of the two men has played."""
    conn = hist_db.connect(path)
    hist_db.upsert_player_logs(conn, [{
        "sport": "cfb", "season": 2026, "period": "2026-09-13",
        "game_id": "g1", "player": PLAYED, "team": "UGA",
        "opponent": "CLEM", "position": "QB", "home": 1,
        "market": "pass_yds", "value": 240.0}])
    conn.close()
    return path


def _tmp():
    return tempfile.mkdtemp()


def _names(hits):
    return [h["player"] for h in hits]


# --- the man nobody has a stat line for --------------------------------
def test_a_rostered_player_who_has_not_played_is_found():
    """THE BUG. He is on the roster, he has never logged a snap, and the
    search returned nothing at all."""
    d = _roster(_tmp())
    db = _logs(os.path.join(_tmp(), "h.db"))
    hits = statlogs.search("cfb", "pellerin", db_path=db, data_dir=d)
    assert _names(hits) == [BENCHED], hits


def test_he_is_marked_as_having_no_games_rather_than_faked():
    """`games: 0` is the honest part — the page must not promise a chart
    for a man with no logged game, and "we know who he is, he has not
    played" is a different fact from "we have never heard of him"."""
    d = _roster(_tmp())
    db = _logs(os.path.join(_tmp(), "h.db"))
    got = statlogs.search("cfb", "pellerin", db_path=db, data_dir=d)[0]
    assert got["games"] == 0, got
    assert got["team"] == "UGA" and got["position"] == "WR", got
    assert got["sport"] == "cfb", got
    assert got["headshot"].endswith("2.png"), got


def test_a_played_man_still_outranks_a_rostered_one():
    """The roster TOPS UP, it does not replace. A stat line is better
    evidence than a name on a list and must sort first."""
    d = _roster(_tmp())
    db = _logs(os.path.join(_tmp(), "h.db"))
    hits = statlogs.search("cfb", "n", db_path=db, data_dir=d)
    assert hits, hits
    assert hits[0]["player"] == PLAYED, _names(hits)
    assert hits[0]["games"] >= 1, hits[0]


def test_the_roster_fills_in_BESIDE_a_log_hit_not_only_instead_of_one():
    """THE MIXED CASE, and the common one: the logs answer for some of
    the men who match and the roster has to fill the rest of the page.

    Found by mutation — every other test here matched only men with no
    stat line, so deleting the top-up entirely left them all green. The
    early return covered the empty board; nothing covered a page that
    was merely SHORT, which is what a real board looks like."""
    d = _roster(_tmp())
    db = _logs(os.path.join(_tmp(), "h.db"))
    got = _names(statlogs.search("cfb", "n", db_path=db, data_dir=d))
    assert PLAYED in got, got
    assert BENCHED in got, got
    assert got.index(PLAYED) < got.index(BENCHED), got


def test_the_roster_cannot_overflow_the_page():
    """`limit` is what the page asked for. A roster of hundreds topping
    up past it would push the log hits off the bottom of the list it was
    supposed to be completing."""
    d = _tmp()
    many = [{"player": f"Deshawn Player{i}", "team": "UGA",
             "position": "WR", "headshot": ""} for i in range(40)]
    with open(os.path.join(d, "rosters_cfb.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"teams": {"UGA": {"players": many}}}, fh)
    statlogs._ROSTER.clear()
    db = _logs(os.path.join(_tmp(), "h.db"))
    hits = statlogs.search("cfb", "deshawn", limit=5, db_path=db, data_dir=d)
    assert len(hits) == 5, len(hits)


def test_the_log_hit_is_not_duplicated_by_the_roster():
    d = _roster(_tmp())
    db = _logs(os.path.join(_tmp(), "h.db"))
    hits = statlogs.search("cfb", "stockton", db_path=db, data_dir=d)
    assert _names(hits) == [PLAYED], hits


def test_a_misspelling_still_reaches_the_roster():
    """The forgiving match is the whole reason the search feels usable
    (Ethan, 2026-08-23). It has to work on the roster half too, or the
    men it just made findable are findable only when typed perfectly."""
    d = _roster(_tmp())
    db = _logs(os.path.join(_tmp(), "h.db"))
    assert _names(statlogs.search("cfb", "pelerin", db_path=db,
                                  data_dir=d)) == [BENCHED]


# --- and it degrades the right way -------------------------------------
def test_a_league_with_no_history_store_still_answers():
    """A league whose logs have not landed must not read as a league
    with no players in it."""
    d = _roster(_tmp())
    hits = statlogs.search("cfb", "pellerin",
                           db_path=os.path.join(_tmp(), "missing.db"),
                           data_dir=d)
    assert _names(hits) == [BENCHED], hits


def test_a_league_with_no_roster_published_is_unchanged():
    """The logs-only behaviour has to survive for any league whose
    roster file is absent — silently, and without raising."""
    db = _logs(os.path.join(_tmp(), "h.db"))
    hits = statlogs.search("cfb", "stockton", db_path=db, data_dir=_tmp())
    assert _names(hits) == [PLAYED], hits
    assert statlogs.search("cfb", "pellerin", db_path=db,
                           data_dir=_tmp()) == []


def test_a_name_on_no_roster_and_in_no_log_is_still_nothing():
    """The search must not start inventing people."""
    d = _roster(_tmp())
    db = _logs(os.path.join(_tmp(), "h.db"))
    assert statlogs.search("cfb", "zzqqx", db_path=db, data_dir=d) == []


def test_an_older_payload_shape_is_still_read():
    """`{team: [players]}` rather than `{team: {"players": [...]}}`. A
    payload on disk from before the current shape must not read as an
    empty league."""
    d = _roster(_tmp(), shape="list")
    db = _logs(os.path.join(_tmp(), "h.db"))
    assert _names(statlogs.search("cfb", "pellerin", db_path=db,
                                  data_dir=d)) == [BENCHED]


def test_unreadable_roster_json_costs_the_roster_not_the_search():
    d = _tmp()
    with open(os.path.join(d, "rosters_cfb.json"), "w",
              encoding="utf-8") as fh:
        fh.write("{ this is not json")
    statlogs._ROSTER.clear()
    db = _logs(os.path.join(_tmp(), "h.db"))
    assert _names(statlogs.search("cfb", "stockton", db_path=db,
                                  data_dir=d)) == [PLAYED]


def test_nothing_here_fetches():
    """The argument for this whole change is that the rosters are
    already on disk. A network call would make that untrue."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "statlogs.py"),
        encoding="utf-8").read()
    import re
    body = src[src.index("def _roster_players("):]
    body = body[:body.index("\ndef ", 10)]
    # DOCSTRING STRIPPED FIRST. The function's own prose says "Nothing
    # here fetches", and a check that the sentence can trip is measuring
    # the sentence — the mirror image of the `clv_coverage` guard a
    # comment could satisfy (2026-09-19).
    body = re.sub(r"(?s)([\"']{3}).*?\1", " ", body)
    body = re.sub(r"(?m)#.*$", " ", body)
    for buy in ("requests", "urlopen", "http", "fetch"):
        assert buy not in body, f"{buy} — the roster is supposed to be local"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
