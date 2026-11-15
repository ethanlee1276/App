"""The game reports read in plain words (2026-11-15).

Ethan sent the NE at DET report's red zone with two phrases circled —
"(23rd of 32, 1st the stingiest)" and "(0% below the league), both
adjusted for opponents" — and wrote: "Also I wanna add that the wording in
these reports are confusing and doesn't make sense or is hard to read".

So every league's report (engine/gamereport.finish, which engine/
leaguereport shares) now:

  * says a rank from its near end — "the 8th-best rate in the league",
    "the 10th-worst" — never "23rd of 32, 1st the stingiest";
  * says a number near the league "about average", never "0% below";
  * says "the most" for "the 1st-most" and first to ninth in words;
  * names the player a caveat is about ("though Matthew Golden has only 4
    catches…"), drops a ", a game" a missing number leaves behind, and
    writes its jargon out (the box, line yards, goals saved above
    expected, the game script's names, signed park factors).

    python3 tests/test_the_reports_read_in_plain_words.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R                       # noqa: E402
from engine.nhl import scan as NS                        # noqa: E402


def _nfl():
    import test_the_game_report_reads_like_the_research as T
    return T._report()


def _cfb():
    import test_the_college_game_report as T
    return T._report()[1]


def test_the_plain_pass_says_ranks_and_averages_as_a_reader_does():
    assert R.plain("DET gives up the 1st-most passing yards") == "DET gives up the most passing yards"
    assert R.plain("GB gives up the 2nd-most touchdowns and the 6th-fewest yards") == \
        "GB gives up the second-most touchdowns and the sixth-fewest yards"
    assert R.plain("the 10th-worst rate") == "the 10th-worst rate", "10th and up stay as numbers"
    assert R.plain("runs 7.4 plays a game (0% below the league)") == "runs 7.4 plays a game (about average)"
    assert R.plain("tight ends (109 a game) (over 5 games)") == "tight ends (109 a game, over 5 games)"
    assert R.plain("Jahmyr Gibbs (RB) 18% of the targets,  a game.") == "Jahmyr Gibbs (RB) 18% of the targets."
    assert R.plain("two  spaces") == "two spaces"
    # Names and codes are never touched — only sentences.
    out = R.plain_all([{"type": "p", "key": "the 1st-most", "text": "the 1st-most", "player": "A  B"}])
    assert out == [{"type": "p", "key": "the 1st-most", "text": "the most", "player": "A  B"}], out


def test_the_red_zone_ethan_circled_reads_plainly():
    rep = _nfl()
    rz = next(s for s in rep["sections"] if s["key"] == "redzone")
    text = " ".join(rz["blocks"][0]["items"])
    for gone in ("of 32", "stingiest", "0% below", "0% above", "red-zone trips", "adjusted for opponents)"):
        assert gone not in text, (gone, text)
    assert "GB scores a touchdown on 54% of its trips inside the 20 (the eighth-worst rate in the league)." in text
    assert "DET's defense gives up a touchdown on 80% of them (the third-worst)." in text
    assert ("GB runs about 10 plays a game inside the opponent's 20 (9% more than an average team); "
            "DET's defense allows about 9.8 (6% more than an average team). Both are adjusted for the "
            "teams they've played.") in text
    # Within 5% of the league is "about average".
    assert R._than_average(0.03) == "about average" and R._than_average(-0.2) == "20% fewer than an average team"
    assert R._place(25, 32) == "the 8th-worst" and R._place(1, 32) == "the best" and R._place(32, 32) == "the worst"


def test_no_report_in_any_league_says_the_old_shorthand():
    import test_every_league_gets_a_game_report as L
    nba, meta = L._nba_board()
    reps = [_nfl(), _cfb(), L._attach(L._mlb_board(), "mlb")[0], L._attach(nba, "nba", meta=meta)[0],
            L._attach(L._nhl_board(), "nhl")[0]]
    assert [r["sport"] for r in reps] == ["nfl", "cfb", "mlb", "nba", "nhl"], [r["sport"] for r in reps]
    for rep in reps:
        text = R.to_text(rep)
        for bad in (r"\bthe 1st-", r"\bthe [2-9](?:nd|rd|th)-", r"\(0% (?:above|below)", r",\s{2,}a game",
                    r"Reading it:", r"Across \w+'s key players", r"rush runs through", r"allowed a carry",
                    r"goals saved above expected", r"plays [+−±]\d", r"[+−]\d+% (?:strikeouts|runs)",
                    r"Inactives post", r"The pens:", r"is moot", r"everyone eats", r"Fixed dome: identical",
                    r"two weeks of prep", r"oldest scheduling angle", r"arrive together", r"If he sits —",
                    r"to share out", r"protection weakens", r"8\+ in the box", r"stacks the box",
                    r"interception-worthy", r"over expected a carry", r"\w+: (?:Off a bye|Rest edge|Short week):"):
            assert not re.search(bad, text), (bad, rep.get("title"), re.search(bad, text).group(0))


def test_a_caveat_names_the_player_it_is_about():
    assert R._with_name("Matthew Golden", "only 4 catches in his last 2 games") == \
        "Matthew Golden has only 4 catches in his last 2 games"
    assert R._with_name("Matthew Golden", "Golden has 4 catches in his last 2") == \
        "Golden has 4 catches in his last 2", "a reason that names him already stands"
    assert R._with_name("Matthew Golden", "DET gives up the most passing yards") == \
        "DET gives up the most passing yards", "no 'his', nothing to name"
    text = R.to_text(_nfl())
    assert "though Matthew Golden has only 4 catches in his last 2 games" in text


def test_the_schedule_the_script_and_the_simulation_are_sentences():
    assert R.rest_words("DET", "GB", "Off a bye: 14 days of rest and two weeks to prepare") == \
        "DET comes off a bye: 14 days of rest and two weeks to prepare"
    assert R.rest_words("DET", "GB", "Rest edge: 14 days to the opponent's 7") == "DET has the rest edge: 14 days to GB's 7"
    assert R.rest_words("DET", "GB", "Something new") == "DET: Something new"
    assert R.script_words("Everyone eats") == "a high-scoring, close game, good for both offenses"
    assert R.script_words("Favorite runs, dog throws").startswith("a high-scoring game with a clear favorite")
    assert R.script_lean_words("DET favored in a shootout — everyone eats.") == \
        "DET favored in a high-scoring game that's good for both offenses."
    assert R.confidence_words("high — favorites this size win ~79%") == \
        " (high confidence: favorites this size win about 79% of the time)"
    assert R.confidence_words("moderate") == " (moderate confidence)"
    assert R.confidence_words("coin flip — don't project a script off this") == " (a coin flip, so don't lean on it)"
    # The game plan keeps its own words: script_sign still reads them.
    from engine.gameplan import script_sign
    assert script_sign("favored in a shootout — everyone eats", "rec_yds") == 1
    text = R.to_text(_nfl())
    assert "We simulated this game 4,000 times, drive by drive" in text
    assert "Of the simulated games, 45% are decided by 8 points or fewer and 36% by 14 or more." in text
    assert ("Officials: the referee is named late in the week. We tested 7,340 games, and the referee told us "
            "nothing the closing line didn't already, so the crew isn't part of this report.") in text


def test_a_goalie_is_said_without_a_sign():
    assert NS.gsax_words(4.2) == "has stopped 4.2 more goals than expected lately"
    assert NS.gsax_words(-3.4) == "has let in 3.4 more goals than expected lately"
    assert NS.gsax_words(0.02) == "has stopped about as many goals as expected lately"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=5)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
