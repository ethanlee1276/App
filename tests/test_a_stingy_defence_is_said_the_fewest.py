"""A stingy defence is said from its own end of the table: "the 3rd-fewest",
never "the 30th-most" (engine/defensevs.rank_words, matchup_card, effect;
web/js/app.js matchupCardHTML).

Ethan's free fantasy page, 12 November 2026, Jayden Daniels before the
Commanders at the Giants: "NYG allow 189.2 passing yards a game, the
30th-most (league 233.5), over 8 games". True, and backwards to read: the
Giants give up the third-fewest. The tough-matchup line under a prop
already said it that way; the card's own sentence, its second line and the
page's rank chip ("30th-most of 32") did not. What these hold:

  * a rank in the top half is said as the most, one in the bottom half as
    the fewest, counted from that end;
  * the card's sentence and its second line both say it so;
  * the page's chip on a prop says it the same way.

Run directly: `python3 tests/test_a_stingy_defence_is_said_the_fewest.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import defensevs as D                                    # noqa: E402

#: The Giants as the fantasy page read them that morning.
NYG = {"qb_pass_yds": {"pg": 189.2, "league": 233.5, "rank": 30, "of": 32, "games": 8},
       "qb_pass_td": {"pg": 1.8, "league": 1.5, "rank": 10, "of": 32, "games": 8}}


def test_each_half_is_said_from_its_own_end():
    assert D.rank_words(30, 32) == "3rd-fewest"
    assert D.rank_words(32, 32) == "1st-fewest"
    assert D.rank_words(3, 32) == "3rd-most"
    assert D.rank_words(16, 32) == "16th-most" and D.rank_words(17, 32) == "16th-fewest"
    # A short table (basketball's early weeks) and one with no size.
    assert D.rank_words(1, 3) == "1st-most" and D.rank_words(2, 3) == "2nd-most"
    assert D.rank_words(3, 3) == "1st-fewest"
    assert D.rank_words(5, 0) == "5th-most"


def test_the_card_says_the_giants_give_up_the_third_fewest():
    card = D.matchup_card("NYG", NYG, "qb_pass_yds", "qb_pass_td")
    assert card["text"] == ("NYG allow 189.2 passing yards a game, the 3rd-fewest (league 233.5), "
                            "over 8 games; 1.8 passing TDs a game (10th-most)"), card["text"]
    # The numbers the page draws from are unchanged.
    assert (card["rank"], card["of"]) == (30, 32)
    stingy_td = dict(NYG, qb_pass_td={"pg": 0.9, "league": 1.5, "rank": 31, "of": 32, "games": 8})
    assert D.matchup_card("NYG", stingy_td, "qb_pass_yds", "qb_pass_td")["text"].endswith(
        "; 0.9 passing TDs a game (2nd-fewest)")
    last = dict(NYG["qb_pass_yds"], last_season=True)
    assert D.matchup_card("NYG", {"qb_pass_yds": last}, "qb_pass_yds")["text"] == (
        "NYG allowed 189.2 passing yards a game last season, the 3rd-fewest (league 233.5); "
        "no game yet this season")


def test_no_card_sentence_says_a_bottom_half_rank_as_the_most():
    for rank in range(1, 33):
        r = {"qb_pass_yds": {"pg": 200.0, "league": 233.5, "rank": rank, "of": 32, "games": 8}}
        text = D.matchup_card("NYG", r, "qb_pass_yds")["text"]
        if rank > 16:
            assert f"the {D._ord(33 - rank)}-fewest" in text and "-most" not in text, text
        else:
            assert f"the {D._ord(rank)}-most" in text, text


def test_the_page_chip_says_it_the_same_way():
    src = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "const rankWords = (rank, of) => (of && rank > Math.floor((of + 1) / 2))" in src
    assert "`${muOrd(of - rank + 1)}-fewest of ${of}`" in src
    assert '${rankWords(x.rank, x.of)}</span></div>`;' in src
    assert "${muOrd(x.rank)}-most of ${x.of}" not in src, "the chip's old wording is gone"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
