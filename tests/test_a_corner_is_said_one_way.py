"""A corner is said one way, and a missing starter reads as words (step AIH, 27 November 2026).

Reading the game report again with Ethan's Bears at Lions research beside it, one corner was said four ways: "the
Lions' left cornerback D.J. Reed" in the short version, "D.J. Reed (LCB)" in the soft spot line, "Left corner" in
the corners' table and "DET's LCB corner D.J. Reed" on the player pages, with the passer rating as 126.5 in the
report and 127 on the pages. Worse, from 19 October, when a starting corner was ruled out, the matchup section
joined the scan's records as they were: "DET is without {'name': 'Terrion Arnold', 'spot': 'RCB', 'status': 'Out'}
in the secondary". Now every line says the spot in words (engine/gamescan.corner_spot), a listing in words
("on injured reserve", never "ir"), and the passer rating to the charting's one decimal.

The names below are this test's own; the numbers are made up for it.

    python3 tests/test_a_corner_is_said_one_way.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gameplan as P                                     # noqa: E402
from engine import gamereport as R                                   # noqa: E402
from engine import gamescan as G                                     # noqa: E402


def test_the_words_for_a_spot_a_listing_and_a_rating():
    assert [G.corner_spot(s) for s in ("LCB", "rcb", "NB", "S", "FS", "", None)] == [
        "left cornerback", "right cornerback", "nickel back", "safety", "free safety", "cornerback", "cornerback"]
    assert G.corner_spot("XB") == "XB", "a code with no word stays as it is"
    assert [G.status_said(s) for s in ("IR", "OUT", "Doubtful", "PUP", "SUSPENDED")] == [
        "on injured reserve", "out", "doubtful", "on the PUP list", "suspended"]
    assert [G.rating_said(r) for r in (126.5, 80.4, 92.0, 118.3, 11.0, 18.5)] == [
        "a 126.5", "an 80.4", "a 92", "a 118.3", "an 11", "an 18.5"]
    assert G.rating_num(68.0) == "68" and G.rating_num(142.84) == "142.8"


def test_a_missing_starter_is_a_sentence_never_a_record():
    room = {"corners": [{"name": "Fill In", "spot": "RCB", "next_man_up": True, "targets": 9, "rating": 88.0}],
            "missing": [{"name": "Gone Starter", "spot": "RCB", "status": "IR"},
                        {"name": "Slot Starter", "spot": "NB", "status": "OUT"}]}
    line = R.missing_corners_line("DET", room)
    assert line == ("DET is without right cornerback Gone Starter (on injured reserve) and nickel back Slot Starter "
                    "(out) in the secondary; Fill In starts at right cornerback"), line
    assert R.missing_corners_line("DET", {"missing": ["Old Style Name"]}) == \
        "DET is without Old Style Name in the secondary", "a name as the older boards stored it"
    assert R.missing_corners_line("DET", {"missing": []}) == ""


def _research_report(missing):
    import test_the_game_report_reads_like_the_research as T
    board = T._board()

    def holder(x):
        if isinstance(x, dict):
            if isinstance(x.get("coverage"), dict) and "DET" in x["coverage"]:
                return x
            for v in x.values():
                got = holder(v)
                if got is not None:
                    return got
        elif isinstance(x, list):
            for v in x:
                got = holder(v)
                if got is not None:
                    return got
        return None
    scan = holder(board)
    scan["coverage"]["DET"]["missing"] = missing
    scan["coverage"]["DET"]["corners"].append({"name": "Fill In", "spot": "RCB", "targets": 9, "rating": 88.0,
                                               "yds_per_tgt": 6.1, "td": 0, "next_man_up": True})
    return R.build(board["games"][0], board, allowed=T.ALLOWED, names=T.NAMES)


def test_the_whole_report_says_the_corners_in_words():
    rep = _research_report([{"name": "Gone Starter", "spot": "RCB", "status": "IR"}])
    text = R.to_text(rep)
    blob = json.dumps(rep, ensure_ascii=False)
    assert "{'" not in blob and "'spot'" not in blob, "no record printed as it is stored"
    assert "DET is without right cornerback Gone Starter (on injured reserve) in the secondary; Fill In starts at " \
        "right cornerback." in text, text
    assert "The soft spot in DET's coverage: left cornerback D.J. Reed — 126.5 passer rating allowed" in text
    for code in ("(LCB)", "(RCB)", "(NB)", "LCB corner", "RCB corner", "Left corner ", "Right corner "):
        assert code not in text, code
    table = next(b for s in rep["sections"] if s["key"] == "matchups" for b in s["blocks"]
                 if b.get("title") == "Lions corners")
    assert [r[1] for r in table["rows"]] == ["Left cornerback", "Nickel back", "Right cornerback"], table["rows"]


def test_the_player_pages_facts_and_notes_say_the_same():
    room = {"corners": [{"name": "Tight Corner", "spot": "LCB", "rating": 71.3, "targets": 30},
                        {"name": "Soft Corner", "spot": "RCB", "rating": 126.5, "targets": 28},
                        {"name": "Maybe Corner", "spot": "NB", "rating": 99.0, "targets": 12,
                         "status": "QUESTIONABLE"}],
            "missing": [{"name": "Gone Starter", "spot": "NB", "status": "IR"}], "weakest": "Soft Corner"}
    facts = G.read_facts("wr", "WR", "GB", "DET", usage={"games": 5, "tgt_share": 0.24, "targets_pg": 7.5},
                         allowed={}, ratings_def={}, points=24.5, line_words="", n_teams=32, room=room)
    texts = " | ".join(f["text"] for f in facts)
    assert "DET's nickel back Maybe Corner is questionable" in texts, texts
    assert "DET's starting nickel back Gone Starter is on injured reserve" in texts, texts
    read = G.player_read("Some Receiver", "GB", "DET", "WR", usage={"games": 5, "tgt_share": 0.24, "targets_pg": 7.5},
                         ratings={}, room=room, scheme=None, split=None, tackling=None, line_out=None,
                         mates_out=None, allowed={}, points=24.5)
    notes = " | ".join(read.get("notes") or [])
    assert "Gone Starter, DET's starting nickel back, is on injured reserve" in notes, notes
    assert "Soft Corner, DET's right cornerback, has allowed a 126.5 passer rating on 28 targets" in notes, notes
    every = texts + " | " + notes + " | " + " | ".join(f["text"] for f in read.get("facts") or [])
    for code in ("(LCB)", "(RCB)", "(NB)", "LCB corner", "RCB corner", "slot corner", " is ir", "127 passer"):
        assert code not in every, (code, every)


def test_the_game_plan_says_the_same():
    scan = {"coverage": {"DET": {"corners": [{"name": "Soft Corner", "spot": "RCB", "rating": 126.5, "targets": 28}],
                                 "missing": [{"name": "Gone Starter", "spot": "LCB", "status": "IR"}],
                                 "weakest": "Soft Corner"}}}
    lines = " ".join(P.matchup_lines(scan, "DET", "GB"))
    assert "DET's soft spot: right cornerback Soft Corner, who has allowed a 126.5 passer rating on 28 targets." \
        in lines, lines
    assert "DET's starting left cornerback Gone Starter is on injured reserve — the backup is the one to throw at." \
        in lines, lines


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
