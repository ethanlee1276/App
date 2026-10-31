"""A number a language model writes onto the site must be in its data.

Audit 2026-09-30, P0-3: the nightly postmortem and weekly brief reach the
public Record page, the explainer reaches every pick page, and Ask answers
"what's your record" — all guarded only by a prompt line. `engine.numcheck`
is the check; these tests hold it, and each lane that calls it, to the
rules the audit named.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import numcheck                                           # noqa: E402

PACK = {"date": "2026-09-29", "sports": ["mlb", "nfl"],
        "by_sport": {"mlb": {"graded": 17, "won": 13, "lost": 4, "pushed": 0,
                             "net_units": 2.13,
                             "picks": [{"player": "Aaron Judge", "line": 1.5,
                                        "odds": -110, "hit_prob": 0.524}]},
                     "nfl": {"graded": 5, "won": 2, "lost": 3, "pushed": 0,
                             "net_units": -1.4, "picks": []}}}


def _scrub(text):
    return numcheck.scrub(text, PACK)


def test_a_record_the_pack_does_not_hold_loses_its_sentence():
    kept, dropped = _scrub("MLB went 14-3 on the night. The overs carried it.")
    assert kept == "The overs carried it."
    assert dropped and dropped[0]["numbers"] == ["14-3"]


def test_the_packs_own_record_stands():
    kept, dropped = _scrub("MLB went 13-4 on the night.")
    assert kept == "MLB went 13-4 on the night." and not dropped


def test_the_nights_total_across_sports_stands():
    """13-4 and 2-3 beside each other are a 15-7 night; a column that says
    so is adding the pack, not inventing."""
    kept, dropped = _scrub("A 15-7 night overall.")
    assert not dropped


def test_a_percent_matches_the_fraction_it_came_from():
    kept, dropped = _scrub("Judge was a 52.4% shot.")
    assert not dropped
    kept, dropped = _scrub("Judge was a 57.4% shot.")
    assert dropped


def test_units_match_at_the_precision_shown():
    assert not _scrub("MLB finished +2.1u.")[1]
    assert not _scrub("MLB finished +2.13u.")[1]
    assert _scrub("MLB finished +2.4u.")[1]


def test_prices_and_lines_match():
    assert not _scrub("Judge over 1.5 at -110 was the call.")[1]
    assert _scrub("Judge over 2.5 at -135 was the call.")[1]


def test_a_sentence_with_no_numbers_is_untouched():
    text = "Losses are losses. The market faded us early and was right."
    assert _scrub(text) == (text, [])


def test_counting_words_years_and_days_are_not_claims():
    assert not _scrub("Two of the 3 losses came on Sept. 29, 2026.")[1]
    assert not _scrub("On 2026-09-29 the board ran.")[1]


def test_a_team_name_with_digits_is_not_a_number():
    assert not _scrub("The 49ers covered.")[1]


def test_a_game_score_the_pack_never_carried_is_dropped():
    """The postmortem pack holds no scores. A score in the column came from
    nowhere the site can stand behind."""
    assert _scrub("The Bills won 27-24.")[1]


def test_dropped_sentences_are_logged_with_the_pack_key():
    p = Path(tempfile.mkdtemp()) / "drops.jsonl"
    _, dropped = _scrub("MLB went 14-3.")
    numcheck.log_drops("postmortem", "2026-09-29", dropped, path=p)
    row = json.loads(p.read_text().splitlines()[0])
    assert row["kind"] == "postmortem" and row["key"] == "2026-09-29"
    assert row["numbers"] == ["14-3"] and "14-3" in row["sentence"]


def test_ask_checks_only_what_it_says_about_our_record():
    ok = numcheck.allowed({"our_record": {"won": 40, "lost": 30, "roi": 0.051}})
    text = ("At -110 you need to win 52.4% to break even. "
            "Our record is 41-30 with a 5.1% ROI.")
    kept, dropped = numcheck.scrub(text, None, ok=ok,
                                   only=numcheck.about_our_record)
    assert kept == "At -110 you need to win 52.4% to break even."
    assert dropped and "41-30" in dropped[0]["numbers"]


# --- the lanes ---------------------------------------------------------------
class _Canned:
    """Stands in for `prose._call`: no paid request in a test."""

    def __init__(self, out):
        self.out = out

    def __call__(self, system, prompt, schema, kind, timeout=180.0):
        return self.out


def _ledger_with_a_night():
    from engine import ledger
    conn = ledger.connect(":memory:")
    for i, (sport, status) in enumerate([("mlb", "won")] * 3 + [("mlb", "lost")]):
        conn.execute(
            "INSERT INTO bets (sport,date,game_day,player,market,side,line,odds,"
            "status,stake_units,pnl_units,category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sport, "2026-09-29", "2026-09-29", f"P{i}", "hits", "OVER", 0.5,
             -110, status, 1.0, 0.91 if status == "won" else -1.0, "main"))
    conn.commit()
    return conn


def test_the_postmortem_drops_an_invented_record_before_it_is_stored():
    from engine import prose
    conn = _ledger_with_a_night()
    saved, saved_drops = prose._call, numcheck.DROPS_PATH
    tmp = Path(tempfile.mkdtemp())
    numcheck.DROPS_PATH = tmp / "drops.jsonl"
    prose._call = _Canned({
        "headline": "MLB goes 4-0",
        "overall": "MLB went 3-1 on the night. It was a good night.",
        "by_sport": [{"sport": "mlb", "note": "MLB went 9-1. Variance."}]})
    try:
        e = prose.write_postmortem(conn, "2026-09-29", tmp / "pm.json")
    finally:
        prose._call, numcheck.DROPS_PATH = saved, saved_drops
    assert "4-0" not in e["headline"] and e["headline"], \
        "a headline that fails the check is replaced, never published"
    assert e["overall"] == "MLB went 3-1 on the night. It was a good night."
    assert e["by_sport"]["mlb"] == "Variance."
    assert (tmp / "drops.jsonl").exists()


def test_the_brief_is_checked_the_same_way():
    import inspect
    from engine import prose
    src = inspect.getsource(prose.write_brief)
    assert "_checked(" in src


def test_the_explainer_is_checked_against_the_picks_own_facts():
    from engine import explainer as ex
    import inspect
    assert "numcheck" in inspect.getsource(ex.explain)


def test_ask_checks_its_record_claims_against_the_turns_facts():
    import inspect
    from engine import askbot
    src = inspect.getsource(askbot.ask)
    assert "numcheck.scrub(" in src and "about_our_record" in src
    assert "tool_outputs" in inspect.getsource(askbot.converse)


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items())
           if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
