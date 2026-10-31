"""The game page before kickoff says each thing once (2026-10-25).

Ethan: "when you click on a game before it starts in the this week's
stadium and you're reading all the information, I feel like there's a lot
of repeated information that doesn't need to be there as well, so that can
kind of get work done and condense without losing any information."

What repeated, and where each fact now lives:
  * every card's matchup and kickoff     -> the page's header
  * every card's game-script sentence    -> the Game scripts section (the
                                            card keeps the script's name and
                                            what it did to this pick)
  * every card's wind and cold lines     -> the header's weather panel (the
                                            card keeps its verdict line)
  * five count tiles, mostly zeros       -> the jump chips' own counts; the
                                            props analysed in the props empty
                                            state
  * Key insights' injury list            -> the report's injuries section and
                                            the plan's who-is-out step
  * "no props clear" and "N props held"  -> one empty state

Run directly: `python3 tests/test_the_game_page_says_each_thing_once.py`
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
DETAIL = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\nfunction ", i + 10)]


def test_the_game_page_tells_its_cards_where_they_are():
    body = _fn(DETAIL, "renderGamePage")
    assert "CARD_GAME = g;" in body
    helper = _fn(APP, "cardInGame")
    assert 'state.view !== "game"' in helper, "on any other page a card is unchanged"
    assert "r.home === g.home && r.away === g.away" in helper and "propInGame(r, g)" in helper


def test_a_card_on_its_own_game_page_drops_the_copies_and_keeps_its_own():
    card = _fn(APP, "likelyCard")
    assert '${home ? "" : `${sub}${when' in card, "no matchup and kickoff under the name"
    assert "startedChip(r)" in card and "reserveChip(r)" in card, "the card's own chips stay"
    # The script: its name and what it did to this pick; the line and the
    # lean are the Game scripts section's.
    assert "(gs.applied ? ` · ${escapeHtml(gs.applied)}.` : \"\")" in card
    # The weather: the detail lines go, the verdict stays.
    assert "WEATHER_DETAIL.test(String(x).trim())" in card
    m = re.search(r"const WEATHER_DETAIL = /(.*)/i;", APP)
    rx = re.compile(m.group(1), re.I)
    for detail in ("Wind 16 mph — measured in 12–18 mph games", "26°F — cold on its own measured no clear effect"):
        assert rx.search(detail), detail
    for keep in ("Weather works against this side", "Soft run defence — +10% vs average",
                 "Game script: favoured by 6 — +6% TD equity for a RB"):
        assert not rx.search(keep), keep
    shot = _fn(APP, "longShotCard")
    assert "cardInGame(r) ? \"\" : `<div class=\"subtitle\">" in shot


def test_the_count_tiles_and_the_third_injury_list_are_gone():
    body = _fn(DETAIL, "renderGamePage")
    assert "gp-stats" not in body and '<div class="k">Props analyzed</div>' not in body
    assert "if (!gameReportFor(g) && !gamePlanFor(g)) (g.injuries || [])" in body


def test_one_empty_state_for_the_props():
    body = _fn(DETAIL, "renderGamePage")
    assert 'plural(props.length, "prop was", "props were")} analyzed here and held' in body
    assert "props.length > shown.length && shown.length ?" in body, "the held note only beside picks it is not repeating"


def test_the_scan_prints_each_rate_once():
    """The real CIN @ BAL page, 2026-10-25: the ranks table carried third
    downs and the red zone, and the raw table under it printed the same four
    rates again. Each rate now sits in its ranks row, with its unadjusted
    rank beside it when that differs."""
    assert 'const TAPE_RAW = { off: { third_down: "third_off", redzone: "rz_off" },' in DETAIL
    assert 'def: { third_down: "third_def", redzone: "rz_def" } };' in DETAIL
    cell = _fn(DETAIL, "tapeCell")
    assert "raw.rank && raw.rank !== now ? ` · ${ordinal(raw.rank)} raw` : \"\"" in cell
    nums = _fn(DETAIL, "seasonNumbersHTML")
    assert "!drawn.has(k)" in nums, "the raw table keeps what only it has"
    tape = _fn(DETAIL, "scanTapeHTML")
    assert "seasonNumbersHTML(scan, away, home, drawn)" in tape
    assert "if (key && (rawOf(away, side, k) || rawOf(home, side, k))) drawn.add(key);" in tape, \
        "a rate leaves the raw table only where the ranks table drew it"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
