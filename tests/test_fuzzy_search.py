"""A name typed from memory has to find the man.

Ethan, 2026-08-23: "another thing i wanna fix for the search bar is if you
dont type the players name in exactly, they dont come up at all which
makes it feel broken."

It was one `LIKE '%q%'`, so FOUR different ordinary things each returned
nothing whatsoever — and the page could not tell any of them apart from
"we have never heard of him", which is what made it feel broken rather
than merely strict:

  * the stored spelling carries a mark nobody types. "Kauê Fernandes" is
    on his own droplet and `LIKE '%kaue%'` does not match a circumflex.
    Same for the period in "St. Brown" and the apostrophe in "A'ja".
  * the punctuation people leave OUT: "amonra", "oneal".
  * the words in the other order: "judge aaron".
  * one letter wrong: "mahomez", "jugde".

Four tiers, because those are four different misses and the reader
deserves to know which one they are looking at. The first three find the
right man and say so. The fourth is a spelling correction and the page
says THAT — a guess presented as the answer is its own kind of lying.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db, playersearch as ps, statlogs
from engine.ufc import fighters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PEOPLE = [("nfl", "Patrick Mahomes", "KC", "pass_yds"),
          ("nfl", "Amon-Ra St. Brown", "DET", "rec_yds"),
          ("mlb", "Aaron Judge", "NYY", "hits"),
          ("mlb", "José Ramírez", "CLE", "hits"),
          ("nba", "Nikola Jokić", "DEN", "pts"),
          ("wnba", "A'ja Wilson", "LV", "pts")]


def _logs():
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = db.connect(path)
    rows = []
    for i in range(5):
        for sport, who, team, mkt in PEOPLE:
            rows.append({"sport": sport, "season": 2026,
                         "period": f"{i:03d}" if sport == "nfl"
                                   else f"2026-08-{10 + i}",
                         "game_id": f"{who[:4]}{i}", "player": who,
                         "team": team, "opponent": "OPP", "position": "X",
                         "home": 1, "market": mkt, "value": 5.0})
    db.upsert_player_logs(conn, rows)
    conn.close()
    statlogs._NAME_INDEX.clear()       # a fresh DB is a fresh index
    return path


def _book():
    p = os.path.join(tempfile.mkdtemp(), "d.json")
    json.dump({"Kauê Fernandes": {"name": "Kauê Fernandes", "ufc_fights": 4,
                                  "fights": 11, "record": "11-1-0"},
               "Ilia Topuria": {"name": "Ilia Topuria", "ufc_fights": 8,
                                "fights": 16, "record": "16-0-0"}},
              open(p, "w"))
    return p


def _first(q, **kw):
    hits = ps.search(q, limit=4, **kw)
    return hits[0]["player"] if hits else None


def _fn(src, decl):
    """One function's source, cut at the next top-level declaration.

    NEVER A FIXED SLICE. `renderPlayers` is the function this suite keeps
    slicing, it is the one that keeps growing, and a window around it has
    now produced five false failures — the last of them for a COMMENT
    added inside it. A test that goes red when a file gets longer teaches
    people to stop reading it.
    """
    i = src.index(decl)
    j = len(src)
    for end in ("\nfunction ", "\nasync function ", "\nconst ", "\n/* "):
        k = src.find(end, i + len(decl))
        if k != -1:
            j = min(j, k)
    return src[i:j]


# --- the matcher ----------------------------------------------------------

def test_an_accent_in_the_stored_name_is_not_a_wall():
    """The one on Ethan's droplet right now."""
    assert ps.rank("Kauê Fernandes", "kaue") == 0
    assert ps.rank("José Ramírez", "jose ramirez") == 0
    assert ps.rank("Nikola Jokić", "jokic") == 0


def test_punctuation_is_optional_in_both_directions():
    """People leave it in and they leave it out."""
    assert ps.rank("Amon-Ra St. Brown", "amon ra") == 0
    assert ps.rank("Amon-Ra St. Brown", "amonra") == 0
    assert ps.rank("A'ja Wilson", "aja wilson") == 0
    assert ps.rank("Shaquille O'Neal", "oneal") is not None


def test_the_words_may_arrive_in_either_order():
    assert ps.rank("Aaron Judge", "judge aaron") == 2
    assert ps.rank("Amon-Ra St. Brown", "brown amon") == 2


def test_one_letter_wrong_still_finds_him():
    assert ps.rank("Patrick Mahomes", "mahomez") == 3
    assert ps.rank("Aaron Judge", "jugde") == 3


def test_a_different_man_is_still_no_match():
    """Loose is not the same as useless. If a search box answers
    everything it has told you nothing."""
    for q in ("zzzzzz", "wilson", "quarterback"):
        assert ps.rank("Aaron Judge", q) is None, q


def test_three_letters_are_too_few_to_guess_from():
    """At three characters half a league is within one edit, so the fuzzy
    tier stays out of it — the prefix tiers already cover short queries."""
    assert ps.rank("Aaron Judge", "xyz") is None
    assert ps.rank("Aaron Judge", "jud") == 0     # prefix, not a guess


def test_the_tiers_are_ordered_best_first():
    """The number is a sort key and the page's answer to "why am I
    looking at this" — it has to mean the same thing in both."""
    assert sorted(ps.RANKS) == [0, 1, 2, 3]
    assert ps.rank("Aaron Judge", "aaron") < ps.rank("Aaron Judge", "ron")
    assert ps.rank("Aaron Judge", "ron") < ps.rank("Aaron Judge", "judge aaron")
    assert ps.rank("Aaron Judge", "judge aaron") < ps.rank("Aaron Judge", "jugde")


# --- through the real search ----------------------------------------------

def test_every_miss_ethan_named_now_finds_the_man():
    p, b = _logs(), _book()
    for q, who in (("jose ramirez", "José Ramírez"),
                   ("jokic", "Nikola Jokić"),
                   ("aja wilson", "A'ja Wilson"),
                   ("amonra", "Amon-Ra St. Brown"),
                   ("st brown", "Amon-Ra St. Brown"),
                   ("judge aaron", "Aaron Judge"),
                   ("mahomez", "Patrick Mahomes"),
                   ("jugde", "Aaron Judge"),
                   ("kaue", "Kauê Fernandes"),
                   ("topuriaa", "Ilia Topuria")):
        assert _first(q, db_path=p, ufc_path=b) == who, q


def test_a_real_miss_still_comes_back_empty():
    assert ps.search("zzzzzz", db_path=_logs(), ufc_path=_book()) == []


def test_the_exact_name_outranks_the_guess_across_leagues():
    """A guessed spelling from the league that happens to go first must
    never sit above the man whose name was actually typed."""
    p, b = _logs(), _book()
    hits = ps.search("judge", limit=6, prefer="nfl", db_path=p, ufc_path=b)
    assert hits[0]["player"] == "Aaron Judge"
    assert hits[0]["rank"] == 0


def test_every_hit_carries_the_rank_that_found_it():
    p, b = _logs(), _book()
    for q in ("judge", "jugde", "kaue"):
        for h in ps.search(q, db_path=p, ufc_path=b):
            assert h["rank"] in ps.RANKS, (q, h)


# --- the cost -------------------------------------------------------------

def test_an_ordinary_query_never_builds_the_name_index():
    """The index is a scan of every name a league has ever logged. It is
    for the miss — where the reader is already looking at an empty page
    and a slower answer beats none — and must not be on the path of a
    query the database can answer with its own index."""
    p = _logs()
    statlogs._NAME_INDEX.clear()
    statlogs.search("mlb", "judge", db_path=p)
    assert not statlogs._NAME_INDEX, "an exact hit paid for the full scan"
    statlogs.search("mlb", "jugde", db_path=p)
    assert "mlb" in statlogs._NAME_INDEX, "the miss never reached the index"


def test_the_index_is_cached_rather_than_rebuilt_per_keystroke():
    p = _logs()
    statlogs._NAME_INDEX.clear()
    statlogs.search("mlb", "jugde", db_path=p)
    stamp = statlogs._NAME_INDEX["mlb"][0]
    statlogs.search("mlb", "jugdee", db_path=p)
    assert statlogs._NAME_INDEX["mlb"][0] == stamp, "rebuilt on every letter"
    assert statlogs.NAME_INDEX_TTL >= 300


# --- what the page says about it ------------------------------------------

def test_the_page_says_when_it_is_showing_a_corrected_spelling():
    js = open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8").read()
    body = _fn(js, "async function renderPlayers(")
    assert "const guessed = hits.length && hits.every((m) => (m.rank || 0) >= 3);" in body
    assert "Closest matches" in body
    # Tail of the sentence, not its head: the scoped search (2026-09-01)
    # put the league's name in front — "no MLB name we hold is spelled
    # exactly…" — and the honesty this pins lives in the rest.
    assert "we hold is spelled exactly" in body


def test_a_name_typed_backwards_is_not_called_a_guess():
    """Rank 2 is every word you typed starting a word of the name. That
    is his name, in the other order — apologising for it would be
    apologising for finding exactly the right man."""
    js = open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8").read()
    i = js.index("const guessed = hits.length")
    assert ">= 3" in js[i:i + 90] and ">= 2" not in js[i:i + 90]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
