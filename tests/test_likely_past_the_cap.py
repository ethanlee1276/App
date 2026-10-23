"""The likely legs the −250 cap keeps off are shown beside the board, labelled — never picks.

Ethan, 2026-10-22, at Patriots–Bears: Luther Burden III went for 84 yards in
the first quarter, all four of his research docs had him, and the board
showed nothing of his — "The app and you have to be better." Asked how the
board should treat a leg our model rates likely but the cap keeps off, he
chose to show it, labelled: legs at 70% or better priced −251 to −350
(engine/likely.PAST_CAP_HEAVIEST), never staked, never journaled.

What these hold: a leg past the cap at 70%+ is listed with its note; the
same number at a better price elsewhere is the board's, not this list's; a
leg past −350 or under 70% is not listed; another number of a prop the board
already seats is; the board itself still never carries a row heavier than
−250; and the list rides its own paid key that nothing journals or stakes.

Run directly: `python3 tests/test_likely_past_the_cap.py`
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gate                                            # noqa: E402
from engine import likely as K                                     # noqa: E402

#: The real fitted mixtures from 2026-08-30 (see tests/test_likely.py).
FITS = {"receptions": {"zero": [-0.82, 0.48], "sigma": 0.46},
        "rec_yds": {"zero": [-0.39, 0.61], "sigma": 0.60}}


def _ln(book, line, over, under):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _catches(**kw):
    """A receiver whose 4+ catches is about 73% to the fitted curve, the
    main line 4.5 near a coin flip."""
    got = {"player": "A Receiver", "team": "CHI", "opponent": "NE", "market": "receptions",
           "market_label": "Receptions", "side": "over", "line": 4.5, "book": "DraftKings",
           "odds": -128, "has_market": True, "fair_prob": 0.537, "hit_prob": 0.54, "raw_prob": 0.55,
           "projection": 5.2, "recent_values": [5, 3, 7, 4, 4, 8], "reasons": ["because"],
           "date": "2026-10-22", "game_date": "2026-10-22",
           "alt_lines": [_ln("DraftKings", 2.5, -450, 330), _ln("DraftKings", 3.5, -260, 200),
                         _ln("DraftKings", 4.5, -128, -102)],
           "alt_sharp_lines": []}
    got.update(kw)
    return got


def test_a_likely_leg_past_the_cap_is_listed_and_labelled():
    pc: list = []
    board = K.build([_catches()], sport="nfl", fits=FITS, past_cap=pc)
    assert all(int(r["odds"]) >= K.HEAVIEST_PRICE for r in board), "the board keeps its cap"
    assert len(pc) == 1, pc
    r = pc[0]
    assert (r["side"], r["line"], r["odds"], r["book"]) == ("over", 3.5, -260, "DraftKings")
    assert r["model_prob"] >= K.PAST_CAP_MIN_PROB and r["past_cap"] is True
    assert r["past_cap_note"].startswith("Past the -250 cap: we have this at ")
    assert "not a pick, never staked or journaled" in r["past_cap_note"]


def test_the_same_number_cheaper_elsewhere_is_the_boards():
    row = _catches()
    row["alt_lines"].append(_ln("FanDuel", 3.5, -240, 190))
    pc: list = []
    board = K.build([row], sport="nfl", fits=FITS, past_cap=pc)
    assert [(r["line"], r["odds"]) for r in board] == [(3.5, -240)], board
    assert pc == [], "a -240 bet is not past the cap"


def test_past_the_band_or_under_seventy_is_not_listed():
    heavy = _catches(alt_lines=[_ln("DraftKings", 3.5, -400, 290), _ln("DraftKings", 4.5, -128, -102)])
    assert K.past_cap_rows([heavy], sport="nfl", fits=FITS) == [], "past -350 is chalk"
    soft = _catches(projection=4.6)
    assert K.past_cap_rows([soft], sport="nfl", fits=FITS) == [], "under 70% is not 'likely' enough"


def test_another_number_of_a_seated_prop_is_listed_the_same_bet_is_not():
    row = _catches()
    seated = {("A Receiver", "CHI", "receptions", "over", 3.5)}
    assert K.past_cap_rows([row], sport="nfl", fits=FITS, seated=seated) == []
    other = {("A Receiver", "CHI", "receptions", "under", 5.5)}
    assert len(K.past_cap_rows([row], sport="nfl", fits=FITS, seated=other)) == 1


def test_likeliest_first_and_capped():
    rows = [_catches(player=f"P{i}", projection=5.2 + i * 0.04) for i in range(K.PAST_CAP_LIMIT + 3)]
    got = K.past_cap_rows(rows, sport="nfl", fits=FITS)
    assert len(got) == K.PAST_CAP_LIMIT
    probs = [r["model_prob"] for r in got]
    assert probs == sorted(probs, reverse=True)


def test_a_number_far_past_the_books_is_held_to_the_credibility_bar():
    # 6.4 catches makes 4+ about 85% to the curve against the book's 68%:
    # the board would refuse that gap as an error, not a find, and so does this.
    assert K.past_cap_rows([_catches(projection=6.4)], sport="nfl", fits=FITS) == []


def test_a_proxy_price_or_a_held_player_is_never_listed():
    assert K.past_cap_rows([_catches(has_market=False)], sport="nfl", fits=FITS) == []
    held = _catches(injury_status="OUT")
    assert K.past_cap_rows([held], sport="nfl", fits=FITS) == [], "the board's injury hold applies"


def test_its_own_paid_key_that_nothing_journals():
    assert "likely_past_cap" in gate.PAID_KEYS
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    assert '"likely_past_cap": _past_cap,' in pipe
    for path in ("engine/ledger.py", "nfl_build.py", "engine/likelyboard.py", "engine/potd.py",
                 "engine/parlays.py", "engine/served.py"):
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        assert "likely_past_cap" not in src and "past_cap" not in src, f"{path} reads the past-cap list"


def test_the_page_draws_it_labelled():
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "function likelyPastCapHTML()" in app and "likely_past_cap" in app
    assert "Past the −250 cap" in app and "Not staked, not journaled." in app
    assert app.count("likelyPulledHTML(likelyPulled()) + likelyPastCapHTML()") == 2, "both layouts"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
