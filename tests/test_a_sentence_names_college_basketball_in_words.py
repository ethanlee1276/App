"""A sentence names college basketball in words (USEREYES1, 18 November 2026).

The Record page's chips and tabs came to say NCAAB (step XF), but a sentence
built on the server still upper-cased the league's code: a college game's
pressure card said "No closing lines on file for CBB games", a college
Most Likely game line "the book's de-vigged price sorts CBB winners", and
Ask's notes "no games on tonight's boards for CBB". What these hold:

  * the pressure note, the Most Likely ranking note and Ask's notes say
    "college basketball" (and "college football"), and a pro league's code as
    before ("for NBA", "in the NHL").

    python3 tests/test_a_sentence_names_college_basketball_in_words.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import askbot as A, likely, pressure                            # noqa: E402


def test_asks_notes_say_the_league_in_words():
    assert (A._lg("cbb"), A._lg("cfb"), A._lg("nba")) == ("college basketball", "college football", "NBA")
    assert (A._lg_in("cbb"), A._lg_in("nhl")) == ("college basketball", "the NHL")
    src = (ROOT / "engine" / "askbot.py").read_text(encoding="utf-8")
    assert 'f" for {sport.upper()}"' not in src and 'f" in the {sport.upper()}"' not in src


def test_the_ranking_note_and_the_pressure_note_say_it_in_words():
    assert likely._LG["cbb"] == "college basketball"
    src = (ROOT / "engine" / "likely.py").read_text(encoding="utf-8")
    assert "sorts {sport.upper()} winners" not in src
    psrc = (ROOT / "engine" / "pressure.py").read_text(encoding="utf-8")
    assert 'f"No closing lines on file for {league} games, so "' in psrc
    assert '{"cbb": "college basketball", "cfb": "college football"}.get(sport, sport.upper())' in psrc
    assert pressure is not None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
