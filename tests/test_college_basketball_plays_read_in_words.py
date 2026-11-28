"""College basketball's live plays read in words, and the Live tab's card keeps its few rows for plays (23 November).

The Live tab's college basketball card read ESPN's play codes as written ("SF · Ben Oosterbaan — LayUpShot +2",
"NEV · Elijah Price — MadeFreeThrow miss"), where the NBA's read as phrases ("Driving Floating Jump Shot"), and a
dead ball's run of substitutions and its dead-ball rebound filled half of the card's six rows. A code now reads as
its words (engine/sources/espnplays.event_label) and the card leaves bookkeeping rows to the game's own page
(espnplays.card_noise).

Run directly: `python3 tests/test_college_basketball_plays_read_in_words.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.sources import espnplays as E            # noqa: E402


def test_a_code_reads_as_its_words_and_a_phrase_is_left_alone():
    assert E.event_label("LayUpShot") == "Layup"
    assert E.event_label("MadeFreeThrow") == "Free Throw" and E.event_label("MissedFreeThrow") == "Free Throw"
    assert E.event_label("JumpShot") == "Jump Shot" and E.event_label("DunkShot") == "Dunk"
    assert E.event_label("OfficialTVTimeOut") == "TV Timeout"
    for phrase in ("Driving Floating Jump Shot", "Defensive Rebound", "Three Point Jump Shot", "Jumpball",
                   "Lost Ball Turnover", "Substitution"):
        assert E.event_label(phrase) == phrase, phrase
    assert E.event_label("") == "Play" and E.event_label(None) == "Play"


def test_the_card_leaves_bookkeeping_to_the_games_own_page():
    rows = [{"kind": "hoops", "event": e} for e in ("Layup", "Substitution", "Dead Ball Rebound", "Defensive Rebound",
                                                    "Timeout")]
    assert [r["event"] for r in rows if not E.card_noise(r)] == ["Layup", "Defensive Rebound", "Timeout"]
    assert not E.card_noise({"kind": "hockey", "event": "Substitution"}), "basketball's rule"
    src = (ROOT / "livescore_build.py").read_text(encoding="utf-8")
    assert 'g["plays"] = [r for r in every if not espnplays.card_noise(r)][-PLAYS_PER_GAME:]' in src
    assert 'doc["plays"] = espnplays.hoops_plays(payload, league, 0, sides=sides)' in src, "the page keeps them all"


def test_hockeys_card_drops_stoppages_and_its_rows_say_the_shot():
    rows = [{"kind": "hockey", "event": e} for e in ("Shot", "Stoppage", "Face Off", "Missed", "Goal")]
    assert [r["event"] for r in rows if not E.card_noise(r)] == ["Shot", "Face Off", "Missed", "Goal"]
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'const ICE_WORDS = { Missed: "Missed Shot", Blocked: "Blocked Shot", "Face Off": "Faceoff" };' in js, \
        "inside the row's own function (the tests that lift it out carry it along)"
    assert "const label = ice ? (ICE_WORDS[p.event] || p.event) : p.event;" in js
    assert '${who}${who ? " — " : ""}${escapeHtml(label)}' in js
    assert E.event_label("Missed") == "Missed" and E.event_label("Blocked") == "Blocked", \
        "the data keeps the feed's words (Call It reads them)"


def test_a_college_play_row_carries_the_words():
    payload = {"plays": [{"id": "1", "type": {"text": "LayUpShot"}, "period": {"number": 2},
                          "clock": {"displayValue": "0:57"}, "team": {"id": "9"}, "scoringPlay": True,
                          "shootingPlay": True, "scoreValue": 2, "participants": []}]}
    row = E.hoops_plays(payload, "cbb", 0, sides={"9": "SF"})[0]
    assert row["event"] == "Layup" and row["points"] == 2 and row["team"] == "SF"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
