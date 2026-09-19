"""The search forgives a typo on every list it matches, and remembers.

Ethan, 2026-09-05: "search that forgives typos and remembers". The league
search has forgiven one since 2026-08-23 (engine/playersearch,
tests/test_fuzzy_search.py); the board and the roster still matched by
exact substring, so "jamar chase" on the NFL tab lost Ja'Marr Chase's
priced card and drew his history instead. The same four tiers now run
on the page, over tonight's board and the roster directory, and say
when the answer is a spelling correction. The search history the site
already keeps is offered as chips while the box is empty.

The ranking runs for real in node (skipped without it).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[i - 6:i] == "async ":
        i -= 6
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ", "\n//")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join(_fn(n) for n in ("searchNorm", "searchDist", "searchClose", "searchRank", "searchFar", "searchPick", "recentSearchPick"))
    prog = f"""
      const SEARCH_FUZZ_MIN = 4;
      {src}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_names_are_reduced_to_what_a_person_types():
    got = _node("""return [searchNorm("Ja'Marr Chase"), searchNorm("José Ramírez"), searchNorm("Amon-Ra St. Brown"), searchNorm(null)];""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["ja marr chase", "jose ramirez", "amon ra st brown", ""], got


def test_the_four_tiers_answer_the_four_misses():
    got = _node("""
      const r = searchRank;
      return {
        starts: r("Aaron Judge", "jud"), word: r("Aaron Judge", "judge"),
        accent: r("José Ramírez", "jose"), stbrown: r("Amon-Ra St. Brown", "st brown"),
        oneal: r("Shaquille O'Neal", "oneal"), amonra: r("Amon-Ra St. Brown", "amonra"),
        backwards: r("Aaron Judge", "judge aaron"), initials: r("Aaron Judge", "aa ju"),
        jamar: r("Ja'Marr Chase", "jamar chase"), mahomez: r("Patrick Mahomes", "mahomez"),
        jugde: r("Aaron Judge", "jugde"), alen: r("Josh Allen", "alen"),
        other: r("Aaron Judge", "smith"), short: r("Aaron Judge", "jdg"), three: r("Aaron Judge", "jug"),
        kik: r("Kirk Cousins", "kik"), ali: r("Ali", "alu"),
        far: r("Josh Allen", "jonathan"), empty: r("Aaron Judge", ""), none: r("", "judge"),
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["starts"] == 0 and got["word"] == 0 and got["accent"] == 0, got
    assert got["stbrown"] == 1 and got["oneal"] == 1 and got["amonra"] == 0, got
    assert got["backwards"] == 2 and got["initials"] == 2, got
    assert got["jamar"] == 3, "the miss Ethan named: one letter short, one apostrophe out"
    assert got["mahomez"] == 3 and got["jugde"] == 3 and got["alen"] == 3, got
    assert got["other"] is None and got["far"] is None, "a different man is still no match"
    assert got["short"] is None and got["three"] is None, "three letters are too few to guess from"
    assert got["kik"] is None and got["ali"] is None, "one edit from a short name is still three letters — no guess"
    assert got["empty"] is None and got["none"] is None


def test_a_list_answers_best_tier_first_in_its_own_order_and_says_when_it_guessed():
    got = _node("""
      // Chase Young LISTED FIRST: the guessing tier has to reorder him behind the closer name.
      const rows = [{player: "Patrick Mahomes"}, {player: "Chase Young"}, {player: "Ja'Marr Chase"}, {player: "Josh Allen"}];
      const name = (r) => r.player;
      const chase = searchPick(rows, "chase", name);
      const jamar = searchPick(rows, "jamar chase", name);
      const alen = searchPick(rows, "alen", name);
      const none = searchPick(rows, "brady", name);
      return {
        chase: chase.rows.map(name), chaseRanks: chase.ranks, chaseGuess: chase.guessed,
        jamar: jamar.rows.map(name), jamarGuess: jamar.guessed,
        alen: alen.rows.map(name), alenGuess: alen.guessed,
        none: none.rows, noneGuess: none.guessed,
        empty: searchPick(null, "x", name).rows,
      };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["chase"] == ["Chase Young", "Ja'Marr Chase"] and got["chaseRanks"] == [0, 0] and not got["chaseGuess"], \
        "inside a tier the list's own order holds"
    # Chase Young qualifies too — his one exact word is the server's own
    # rule — but the closer whole name leads the guessing tier.
    assert got["jamar"] == ["Ja'Marr Chase", "Chase Young"] and got["jamarGuess"] is True, got["jamar"]
    assert got["alen"] == ["Josh Allen"] and got["alenGuess"] is True
    assert got["none"] == [] and got["noneGuess"] is False and got["empty"] == []


def test_recent_searches_are_newest_first_one_per_spelling_and_capped():
    got = _node("""
      const log = [{q: "judge"}, {q: "Judge"}, {q: "a"}, {q: "Mahomes"}, {q: " jamar chase "}, {q: "Judge "},
                   {q: "St. Brown"}, {q: "st brown"}, {q: "Allen"}, {q: "Kelce"}, {q: "Chase"}];
      return { five: recentSearchPick(log, 5), two: recentSearchPick(log, 2), none: recentSearchPick([], 5), nul: recentSearchPick(null, 5) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["five"] == ["Chase", "Kelce", "Allen", "st brown", "Judge"], got["five"]
    assert got["two"] == ["Chase", "Kelce"] and got["none"] == [] and got["nul"] == []


def test_the_board_and_the_roster_match_through_the_tiers_and_say_when_they_guessed():
    i = APP.index("async function renderPlayers()")
    body = APP[i:APP.index("\n/* The UFC hero", i)]
    assert "const picked = searchPick(recs, state.search, (r) => r.player);" in body
    assert 'recs.filter((r) => (r.player || "").toLowerCase().includes(q))' not in body, "the board still matches by exact substring"
    assert "Closest match on tonight’s board" in body and "boardGuess ?" in body
    assert "const found = q ? await rosterMatches(state.search) : { rows: [], guessed: false };" in body
    assert "No roster name is spelled exactly that way" in body
    roster = _fn("rosterMatches")
    assert "const k = searchRank(p.player, q);" in roster
    assert "guessed: hits.length > 0 && hits.every((h) => h.rank >= 3)" in roster
    assert "x.rank - y.rank || x.far - y.far || (y.p.games || 0) - (x.p.games || 0)" in roster, \
        "best tier first, the closer whole name inside the guessing tier, most games inside the rest"


def test_recent_chips_show_while_the_box_is_empty_and_read_the_existing_log():
    assert '<div class="std-chips search-recent" id="search-recent" hidden></div>' in HTML
    fn = _fn("renderSearchRecent")
    assert "const names = state.search.trim() ? [] : recentSearches();" in fn, "chips hide the moment a letter is typed"
    assert "host.hidden = !names.length;" in fn
    assert 'class="al-cat sr-chip" data-q="${escapeAttr(q)}"' in fn
    rs = _fn("recentSearches")
    assert "localStorage.getItem(ACCT_SEARCH_KEY)" in rs, "the log the account already syncs, not a second store"
    assert "return recentSearchPick(log, n);" in rs
    i = APP.index("async function renderPlayers()")
    assert "renderSearchScope();\n  renderSearchRecent();" in APP[i:i + 400]
    j = APP.index('e.target.closest(".sr-chip")')
    seg = APP[j:j + 200]
    assert "acctSearchLog(chip.dataset.q);" in seg and "openPlayer(chip.dataset.q);" in seg
    assert ".search-recent .sr-label" in CSS


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
