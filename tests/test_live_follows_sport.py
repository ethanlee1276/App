"""The Live tab shows the sport whose button you pressed.

Ethan, 2026-09-05: "the live page is showing live mlb bets and games on
the CFB button, it should be corilated to the sport you have selected."

Two things put baseball under the CFB button. The league chip on the
live board defaulted to "all" and survived every sport switch, so the
tab opened on a mixed slate whichever button had been pressed. And the
sweat zone reads `sweat.json`, which engine/sweat.py builds from the MLB
journal alone — and drew it on every league's tab.

Both are source pins: the fix is a few lines of a 30,000-line file and
the failure is a layout that no unit renders.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    """The body up to the next declaration — plain or async — or the end
    of the file. `renderLiveBoard` is near the bottom of app.js with
    only `async function`s after it, and a slice that looks for
    "\nfunction " alone raises there."""
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


def test_the_chip_follows_the_sport_button():
    body = _fn("renderLiveBoard")
    assert "if (_liveChipSport !== state.sport) {" in body
    assert '_liveChip = LIVE_FEEDS[state.sport] ? state.sport : "all";' in body
    # The follow happens BEFORE the filter that uses the chip.
    assert body.index("_liveChipSport = state.sport") < body.index("const shown = ")


def test_a_league_without_a_live_feed_lands_on_all():
    """UFC has no scoreboard here; its Live tab must not filter to a
    league that can never have a card."""
    body = _fn("renderLiveBoard")
    assert 'LIVE_FEEDS[state.sport] ? state.sport : "all"' in body


def test_the_choice_survives_until_the_sport_changes():
    assert "let _liveChipSport = null;" in APP
    body = _fn("renderLiveBoard")
    # The click handler still sets the chip directly; the follow only
    # fires when the sport differs from the one the chip was chosen under.
    assert "_liveChip = b.dataset.chip; renderLiveBoard();" in body


def test_a_dark_league_says_so_instead_of_an_empty_grid():
    body = _fn("renderLiveBoard")
    assert 'const nothingHere = _liveChip !== "all" && !shown.length' in body
    assert "games in progress" in body and "choose All" in body
    assert "${nothingHere}${shelved}" in body, "built and never placed"


def test_the_sweat_renders_only_on_the_sport_it_was_built_from():
    body = _fn("renderSweatZone")
    assert 'if (d.sport && d.sport !== state.sport) { host.innerHTML = ""; return; }' in body
    # The guard sits after the file is loaded and before anything renders.
    assert body.index("d.sport !== state.sport") < body.index("const picks = ")


def test_the_sweat_file_names_its_sport():
    src = (ROOT / "engine" / "sweat.py").read_text()
    assert '"sport": "mlb"' in src


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
