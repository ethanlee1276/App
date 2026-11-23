"""The conferences' own word on who plays, laid over ESPN's college board (decision 20, step ADB).

Ethan, 23 November: "decision 20 is a yes if it helps and get us more up to date info for the users". The ACC, the
SEC, the Big 12 and the Big Ten publish each school's availability report for every conference game, the evenings
before and about 90 minutes before kickoff. engine/sources/cfbavail reads the box's cache of those filings and lays
each school's newest one over ESPN's board: the newer word wins on a man both list; Available or Probable clears
him; ESPN's stale questionable on a man the school left off is dropped; ESPN's out stays; a man only the school
lists is added. A school with no filing keeps ESPN's board.

Run directly: `python3 tests/test_the_conferences_own_word_on_who_plays.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.models import Injury                       # noqa: E402
from engine.sources import cfbavail as CA              # noqa: E402
from engine.sources.oddsapi import normalize_name      # noqa: E402

LOOKUP = {"clemson": "CLEM", "south carolina": "SC", "ohio state": "OSU", "michigan": "MICH"}
GAMES = [{"home": "SC", "away": "CLEM", "date": "2026-11-28", "kickoff": "2026-11-28T19:30:00Z"},
         {"home": "MICH", "away": "OSU", "date": "2026-11-28", "kickoff": "2026-11-28T17:00:00Z"}]


def test_the_report_words_are_the_engine_statuses():
    assert CA.status_of("Out") == "OUT" and CA.status_of("OUT - Season") == "OUT"
    assert CA.status_of("Unavailable") == "OUT" and CA.status_of("Not Available") == "OUT"
    assert CA.status_of("Doubtful") == "DOUBTFUL" and CA.status_of("Questionable") == "QUESTIONABLE"
    assert CA.status_of("Game Time Decision") == "GTD" and CA.status_of("Game-Time Decision") == "GTD"
    assert CA.status_of("Available") == "" and CA.status_of("Probable") == ""
    assert CA.status_of("") is None and CA.status_of("Status") is None and CA.status_of(None) is None


def test_a_reports_names_read_first_name_first():
    assert CA.player_name("Smith, John") == "John Smith"
    assert CA.player_name("#12 Klubnik, Cade (QB)") == "Cade Klubnik"
    assert CA.player_name("Smith, Jr., John") == "John Smith Jr."
    assert CA.player_name("John Smith Jr.") == "John Smith Jr."
    assert CA.player_name("  7  Jeremiah Smith ") == "Jeremiah Smith"


def _cache(*reports):
    return {"reports": list(reports)}


def _rep(school, at, players, final=False):
    return {"conference": "acc", "school": school, "filed_at": at, "final": final,
            "players": [{"player": n, "pos": p, "word": w} for n, p, w in players]}


def test_a_schools_formal_name_finds_the_boards_school():
    assert CA.school_key("The Ohio State University", LOOKUP) == "OSU"
    assert CA.school_key("University of Michigan", LOOKUP) == "MICH"
    assert CA.school_key("Clemson University", LOOKUP) == "CLEM"
    assert CA.school_key("University of South Carolina", LOOKUP) == "SC"
    assert CA.school_key("Wake Forest University", LOOKUP) == "", "a school the board does not know is left out"
    assert CA.school_key("Pittsburgh", {"pitt": "PITT", "pittsburgh panthers": "PITT"}) == "PITT", \
        "the vendor's Pittsburgh is the board's Pitt"
    assert CA.school_key("Mississippi St.", {"ole miss": "MISS", "mississippi st": "MSST"}) == "MSST"


def test_each_school_keeps_its_newest_filing_for_this_game():
    cache = _cache(_rep("Clemson", "2026-11-25T23:00:00Z", [("Klubnik, Cade", "QB", "Questionable")]),
                   _rep("Clemson", "2026-11-27T23:00:00Z", [("Klubnik, Cade", "QB", "Probable")]),
                   _rep("Clemson", "2026-11-18T23:00:00Z", [("Old, Man", "RB", "Out")]),
                   _rep("Wake Forest", "2026-11-27T23:00:00Z", [("Not, Here", "WR", "Out")]),
                   _rep("Ohio State", "2026-11-29T05:00:00Z", [("Late, Filing", "WR", "Out")]))
    rows = CA.filed_for(GAMES, LOOKUP, cache)
    assert [(r["team"], r["player"], r["status"], r["word"]) for r in rows] == \
        [("CLEM", "Cade Klubnik", "", "Probable")], rows


def test_the_newer_word_wins_and_available_clears_him():
    espn = [Injury("Cade Klubnik", "CLEM", "QB", "qb", "QUESTIONABLE"),
            Injury("Phil Mafah", "CLEM", "RB", "rb", "OUT"),
            Injury("Antonio Williams", "CLEM", "WR", "wr", "QUESTIONABLE"),
            Injury("T.J. Parker", "CLEM", "DE", "de", "QUESTIONABLE"),
            Injury("LaNorris Sellers", "SC", "QB", "qb", "QUESTIONABLE")]
    dates = {("CLEM", "cade klubnik"): CA._ts("2026-11-24T12:00:00Z"),
             ("CLEM", "antonio williams"): CA._ts("2026-11-24T12:00:00Z"),
             ("CLEM", normalize_name("T.J. Parker")): CA._ts("2026-11-28T01:00:00Z")}
    filed = CA.filed_for(GAMES, LOOKUP, _cache(_rep("Clemson", "2026-11-27T23:00:00Z", [
        ("Klubnik, Cade", "QB", "Available"), ("Bryant Wesco", "WR", "Doubtful"),
        ("Phil Mafah", "RB", "Out")])))
    merged, note = CA.overlay(espn, dates, filed)
    got = {(i.team, i.player): i.status for i in merged}
    assert ("CLEM", "Cade Klubnik") not in got and note["cleared"] == [("CLEM", "Cade Klubnik", "QUESTIONABLE")]
    assert got[("CLEM", "Phil Mafah")] == "OUT"
    assert ("CLEM", "Antonio Williams") not in got, "ESPN's older questionable on a man the school left off"
    assert got[("CLEM", "T.J. Parker")] == "QUESTIONABLE", "ESPN's tag filed after the school's report stands"
    assert got[("CLEM", "Bryant Wesco")] == "DOUBTFUL", "a man only the school lists is added"
    assert got[("SC", "LaNorris Sellers")] == "QUESTIONABLE", "a school with no filing keeps ESPN's board"
    assert note["schools"] == 1 and note["added"] == 1 and note["dropped"] == 1


def test_the_schools_word_changes_espns_and_a_filing_listing_nobody_still_counts():
    espn = [Injury("Jeremiah Smith", "OSU", "WR", "wr", "QUESTIONABLE"),
            Injury("Caleb Downs", "OSU", "S", "s", "OUT")]
    filed = CA.filed_for(GAMES, LOOKUP, _cache(
        _rep("Ohio State", "2026-11-28T15:30:00Z", [("Jeremiah Smith", "WR", "Game Time Decision")], final=True),
        _rep("Michigan", "2026-11-28T15:30:00Z", [], final=True)))
    merged, note = CA.overlay(espn + [Injury("Bryce Underwood", "MICH", "QB", "qb", "QUESTIONABLE")], {}, filed)
    got = {(i.team, i.player): i.status for i in merged}
    assert got[("OSU", "Jeremiah Smith")] == "GTD" and note["changed"] == 1
    assert got[("OSU", "Caleb Downs")] == "OUT", "the board's out stays"
    assert ("MICH", "Bryce Underwood") not in got, "Michigan filed and listed nobody"
    assert note["schools"] == 2


def test_no_filings_leave_the_board_alone():
    espn = [Injury("Cade Klubnik", "CLEM", "QB", "qb", "QUESTIONABLE")]
    merged, note = CA.overlay(espn, {}, [])
    assert merged == espn and note["schools"] == 0


def test_the_injuries_page_shows_each_schools_filing_over_espns_rows():
    look = {"clemson": "CLEM", "clemson tigers": "CLEM", "ohio state": "OSU", "ohio state buckeyes": "OSU"}
    espn = [{"team": "Clemson Tigers", "player": "Cade Klubnik", "pos": "QB", "status": "Questionable",
             "date": "2026-11-24T12:00Z", "injury": "Ankle", "face": "x.png"},
            {"team": "Clemson Tigers", "player": "Antonio Williams", "pos": "WR", "status": "Questionable",
             "date": "2026-11-24T12:00Z", "injury": "Hamstring"},
            {"team": "Clemson Tigers", "player": "Phil Mafah", "pos": "RB", "status": "Out",
             "date": "2026-10-01T12:00Z", "injury": "Shoulder"},
            {"team": "Clemson Tigers", "player": "T.J. Parker", "pos": "DE", "status": "Questionable",
             "date": "2026-11-26T06:00Z"},
            {"team": "Ohio State Buckeyes", "player": "Caleb Downs", "pos": "S", "status": "Questionable",
             "date": "2026-11-24T12:00Z"}]
    cache = _cache(_rep("Clemson University", "2026-11-26T00:00:00Z", [
        ("Klubnik, Cade", "QB", "AVAILABLE"), ("Bryant Wesco", "WR", "Doubtful")]),
        _rep("Clemson", "2026-11-12T00:00:00Z", [("Old, Filing", "RB", "Out")]))
    rows, n = CA.page_rows(espn, cache, look, now=CA._ts("2026-11-26T12:00:00Z"))
    got = {(r["team"], r["player"]): r for r in rows}
    k = got[("Clemson Tigers", "Cade Klubnik")]
    assert k["status"] == "Available" and k["cleared"] is True and k["injury"] == "Ankle" and k["face"] == "x.png"
    assert k["comment"] == "ACC availability report" and k["date"] == "2026-11-26T00:00:00Z"
    assert ("Clemson Tigers", "Antonio Williams") not in got, "ESPN's older tag the school left off"
    assert got[("Clemson Tigers", "Phil Mafah")]["status"] == "Out", "ESPN's out stays"
    assert got[("Clemson Tigers", "T.J. Parker")]["status"] == "Questionable", "ESPN's newer tag stands"
    w = got[("Clemson Tigers", "Bryant Wesco")]
    assert w["status"] == "Doubtful" and w["cleared"] is False and w["source"] == "acc"
    assert got[("Ohio State Buckeyes", "Caleb Downs")]["status"] == "Questionable", "no filing, ESPN's board"
    assert ("Clemson Tigers", "Filing Old") not in got and n == 2
    from engine.sources.espninjuries import is_return
    assert is_return(k) and not is_return(w), "an Available row counts as cleared, never as listed"


def test_the_injuries_builder_reads_the_schools_filings_even_when_espn_fails():
    src = (ROOT / "injuries_build.py").read_text(encoding="utf-8")
    i = src.index("THE SCHOOLS' OWN FILINGS")
    body = src[i:src.index("board = {", i)]
    assert 'sports["cfb"], _n = _ca.page_rows(sports.get("cfb") or [], _cache' in body
    assert src.index("for league in LEAGUES:") < i, "after ESPN's boards, whatever they did"
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    fn = js[js.index("function isReturnRow"):]
    assert "(r || {}).cleared === true" in fn[:fn.index("\n}")]
    row = js[js.index("function injRow"):]
    assert 'r.source && r.comment ? escapeHtml(r.comment) : ""' in row[:row.index("\n}")], \
        "a school's row names its report on the line itself, not only on hover"


def test_the_injuries_page_reads_the_schools_words_in_the_right_tier():
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    fn = js[js.index("function injTone"):]
    fn = fn[:fn.index("\n}") + 2]
    words = ["Unavailable", "Not Available", "Out", "Game Time Decision", "Game-Time Decision", "Questionable",
             "Doubtful", "Available", "Probable"]
    out = subprocess.run([node, "-e", fn + f"process.stdout.write(JSON.stringify({json.dumps(words)}.map(injTone)))"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    tones = dict(zip(words, json.loads(out.stdout)))
    assert {w for w, t in tones.items() if t == "var(--bad)"} == {"Unavailable", "Not Available", "Out"}, tones
    assert {w for w, t in tones.items() if t == "var(--warn)"} == {"Game Time Decision", "Game-Time Decision",
                                                                  "Questionable", "Doubtful"}, tones
    assert tones["Available"] == tones["Probable"] == "var(--good)"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
