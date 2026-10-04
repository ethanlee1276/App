"""Park and wind, on the pick they bear on — in the model's own words.

Ethan, 2026-08-20: "push injuries/weather signals into the board rather
than beside it."

Both signals already existed and both sat somewhere other than the card.
The injury feed was a box NEXT TO the board; the park factor and the wind
went straight into the journal and were never shown at all. A reader
looking at a home-run over on a 14mph night out to center could not learn
that from the card, even though every one of our own settled bets is
sliced on exactly that fact.

THE BANDS ARE PORTS, NOT NEW THRESHOLDS, and that is what this file
defends. engine/losspatterns.py convicts on "wind out hard" and "boosting
park"; the card now prints the same cuts. If someone tunes a number on
either side, the page and the model start describing one night in two
vocabularies — the page saying calm where the miner says windy — and
nobody would notice, because both would still look reasonable. So this
runs BOTH implementations over the same grid and demands identical
answers, rather than reading either one.

Football bands on wind SPEED (there is no center field to blow out of;
magnitude is what leans on the passing game). Baseball bands on SIGNED
wind against the park's real bearing, because direction is the physics of
a fly ball. Indoors has no wind dimension at all — the park band says
"roof closed/dome" and a second chip would double-count it.

THE TONE IS ABOUT THE PICK, NOT THE WEATHER. The same 14mph blowing out
is good news for a home-run OVER and bad news for the UNDER, so the chip
cannot be coloured by the wind alone. And because the projection ALREADY
carries the park and the wind, a green chip must never read as edge the
price has not noticed — the tooltip says so on every one.

Run directly: `python3 tests/test_envband.py`
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# NODE IS REQUIRED HERE AND IS NOT A RUNTIME DEPENDENCY OF THE SITE. These
# assertions RUN both implementations rather than read them, which is the
# entire reason the file exists — a regex over thresholds would pass while
# the two functions disagreed about which side of `<` a boundary sits on.
# The droplet has no Node, so this SKIPs there rather than failing a
# deploy over a dev tool the server does not need.
import shutil as _shutil                                    # noqa: E402
if not _shutil.which("node"):
    print("SKIP node is not installed; this file executes the band ports "
          "against engine/losspatterns.py. `apt install -y nodejs`")
    print("\n0 tests passed.")
    raise SystemExit(0)

from engine.losspatterns import park_band, wind_band        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    """One function declaration, brace-matched.

    Reading to the next `\\n}` truncates at the first nested block, which
    is how an earlier helper in this repo silently tested a third of the
    function it named."""
    i = APP.index(f"function {name}(")
    j = APP.index("{", i)
    depth = 0
    for k in range(j, len(APP)):
        if APP[k] == "{":
            depth += 1
        elif APP[k] == "}":
            depth -= 1
            if depth == 0:
                return APP[i:k + 1]
    raise AssertionError(f"{name} has unbalanced braces")


def _const(name):
    """A top-level `const NAME = [...];` line, taken verbatim so the market
    lists under test are the ones the site ships."""
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";", i) + 1]


_STUBS = """
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function escapeAttr(s) { return escapeHtml(s); }
function icon(n) { return `<i data-i="${n}"></i>`; }
function iconMark(n) { return icon(n); }
function injWhen(ts) { return ts ? "today" : "\\u2014"; }
function injTone(status) {
  const s = (status || "").toLowerCase();
  if (/(^|\\b)(out|injured reserve|ir\\b)/.test(s)) return "var(--bad)";
  if (/(doubtful|questionable|day-to-day)/.test(s)) return "var(--warn)";
  return "var(--text-dim)";
}
let INJ = null;
function injFind(sport, player) { return INJ; }
const state = { sport: "mlb" };
"""


def _run(script):
    src = _STUBS + "\n".join(
        [_const(n) for n in ("ENV_AERIAL", "ENV_POWER")]
        + [_fn(n) for n in ("windBand", "parkBand", "envChip", "pickInjuryNote")]
    ) + "\n" + script
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


# ---------------------------------------------------------------- ports

def test_the_wind_bands_are_the_miners_wind_bands():
    """Both implementations, same grid, no exceptions. A boundary that
    drifts from `<` to `<=` on one side only is invisible to inspection
    and obvious here."""
    speeds = [None] + [round(x * 0.5 - 30, 1) for x in range(121)]
    sports = ["nfl", "cfb", "mlb", None]
    grid = [[w, roofed, sp] for w in speeds
            for roofed in (True, False) for sp in sports]
    got = _run("const g = " + json.dumps(grid) + ";"
               "console.log(JSON.stringify(g.map(([w, r, s]) =>"
               " windBand(w, r, s))));")
    want = [wind_band(w, roofed, sp) for w, roofed, sp in grid]
    for (w, roofed, sp), a, b in zip(grid, want, got):
        assert a == b, f"wind={w} roofed={roofed} sport={sp}: py {a!r} != js {b!r}"


def test_the_park_bands_are_the_miners_park_bands():
    idxs = [None] + [round(0.50 + x * 0.01, 2) for x in range(101)]
    grid = [[i, roofed] for i in idxs for roofed in (True, False)]
    got = _run("const g = " + json.dumps(grid) + ";"
               "console.log(JSON.stringify(g.map(([i, r]) => parkBand(i, r))));")
    want = [park_band(i, roofed) for i, roofed in grid]
    for (i, roofed), a, b in zip(grid, want, got):
        assert a == b, f"hr={i} roofed={roofed}: py {a!r} != js {b!r}"


def test_indoors_has_no_wind_dimension_in_either_language():
    """The park band already says the roof is shut. A wind band on top of
    it would double-count one fact in two chips."""
    assert wind_band(14.0, True, "mlb") is None
    got = _run("console.log(JSON.stringify([windBand(14, true, 'mlb'),"
               " windBand(14, true, 'nfl'), parkBand(1.4, true)]));")
    assert got == [None, None, "roof closed/dome"]


# ---------------------------------------------------------------- chip

def _chip(rec, sport="mlb"):
    return _run(f"state.sport = {json.dumps(sport)};"
                f"console.log(JSON.stringify(envChip({json.dumps(rec)})));")


def test_the_neutral_band_draws_nothing():
    """An env chip on every card is an env chip nobody reads."""
    assert _chip({"market": "home_runs", "side": "OVER",
                  "park_hr": 1.00, "wind_out": 1.0, "roofed": False}) == ""


def test_a_market_the_weather_does_not_reach_says_nothing():
    """A closed roof does not change a strikeout number and a crosswind
    does not change a rushing line."""
    assert _chip({"market": "strikeouts", "side": "OVER", "park_hr": 1.30,
                  "wind_out": 14.0, "roofed": False}) == ""
    assert _chip({"market": "rush_yds", "side": "OVER", "wind_out": 22.0,
                  "roofed": False}, sport="nfl") == ""


def test_the_same_wind_is_green_on_the_over_and_amber_on_the_under():
    """THE POINT OF THE COLOUR. Fourteen out to center helps a home-run
    over and hurts the under; a chip coloured by the weather alone would
    tell half the board the opposite of the truth."""
    r = {"market": "home_runs", "park_hr": 1.00, "wind_out": 14.0,
         "roofed": False}
    over = _chip({**r, "side": "OVER"})
    under = _chip({**r, "side": "UNDER"})
    assert "chip up" in over and "chip down" not in over, over
    assert "chip down" in under and "chip up" not in under, under
    assert "14 mph out" in over and "14 mph out" in under


def test_wind_blowing_in_flips_both_readings():
    r = {"market": "total_bases", "park_hr": 1.00, "wind_out": -12.0,
         "roofed": False}
    assert "chip down" in _chip({**r, "side": "OVER"})
    assert "chip up" in _chip({**r, "side": "UNDER"})
    assert "12 mph in" in _chip({**r, "side": "OVER"})


def test_football_reads_wind_against_the_over_whichever_way_it_blows():
    """No center field to blow out of: wind is a tax on the passing game,
    so the sign carries no information and the magnitude carries all of
    it. Both directions must read the same way."""
    for w in (22.0, -22.0):
        r = {"market": "pass_yds", "wind_out": w, "roofed": False}
        assert "chip down" in _chip({**r, "side": "OVER"}, sport="nfl")
        assert "chip up" in _chip({**r, "side": "UNDER"}, sport="cfb")
        assert "22 mph wind" in _chip({**r, "side": "OVER"}, sport="nfl")


def test_a_closed_roof_is_one_chip_and_carries_no_direction():
    out = _chip({"market": "home_runs", "side": "OVER", "park_hr": 1.30,
                 "roofed": True, "wind_out": None})
    assert out.count("<span") == 1, out
    assert "Roof closed" in out
    assert "chip up" not in out and "chip down" not in out, \
        "a shut roof was coloured as if it favoured a side"


def test_the_park_is_printed_as_the_percentage_not_the_index():
    """1.22 means nothing to a reader; +22% HR does."""
    out = _chip({"market": "home_runs", "side": "OVER", "park_hr": 1.22,
                 "wind_out": 0.0, "roofed": False})
    assert "Park +22% HR" in out, out
    out = _chip({"market": "home_runs", "side": "OVER", "park_hr": 0.86,
                 "wind_out": 0.0, "roofed": False})
    assert "Park −14% HR" in out, out


def test_every_chip_says_the_projection_already_carries_it():
    """A green chip that reads as edge the price has not noticed would be
    a lie told by styling. The model prices the park and the wind."""
    outs = [
        _chip({"market": "home_runs", "side": "OVER", "park_hr": 1.22,
               "wind_out": 14.0, "roofed": False}),
        _chip({"market": "home_runs", "side": "OVER", "park_hr": 1.22,
               "roofed": True}),
        _chip({"market": "pass_yds", "side": "OVER", "wind_out": 20.0,
               "roofed": False}, sport="nfl"),
    ]
    for out in outs:
        assert out
        for chip in out.split("<span")[1:]:
            assert "already inside the projection" in chip, chip


def test_the_chip_names_the_band_the_miner_would_file_it_under():
    """One vocabulary. The reader sees the word our own settled bets are
    sliced on, so the page and the model cannot describe one night
    differently."""
    out = _chip({"market": "home_runs", "side": "OVER", "park_hr": 1.22,
                 "wind_out": 14.0, "roofed": False})
    assert "boosting park" in out and "wind out hard" in out, out


# ------------------------------------------------------------- injury

def _note(rec, inj, sport="nfl"):
    return _run(f"state.sport = {json.dumps(sport)};"
                f"INJ = {json.dumps(inj)};"
                f"console.log(JSON.stringify(pickInjuryNote({json.dumps(rec)})));")


def test_a_healthy_player_gets_no_note():
    assert _note({"player": "A Back", "warnings": []}, None) == ""


def test_the_note_names_the_designation_and_the_injury():
    out = _note({"player": "A Back", "warnings": []},
                {"status": "Questionable", "injury": "hamstring",
                 "date": "2026-08-19", "return_date": ""})
    assert "Questionable" in out and "hamstring" in out
    assert "A Back" in out
    assert "var(--warn)" in out, "the designation is not toned"


def test_mlb_says_it_better_so_we_stand_down():
    """MLB's IL warnings come off the transactions wire, not off ESPN's
    page. Printing both would put one fact on the card twice in two
    wordings, and the weaker source would be the one people read."""
    rec = {"player": "A Hitter",
           "warnings": ["On the injured list (since 2026-08-11) — never a "
                        "pick until activated"]}
    assert _note(rec, {"status": "Out", "injury": "elbow",
                       "date": "2026-08-11"}, sport="mlb") == ""


def test_the_note_does_not_pretend_the_projection_knew():
    """The whole reason to print it: every game in the sample was played
    by a healthy man."""
    out = _note({"player": "A Back", "warnings": []},
                {"status": "Out", "injury": "knee", "date": "2026-08-19"})
    assert "games he played healthy" in out, out


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
    # run_tests.py counts a file's tests by reading "N tests passed" off
    # this line. "all good" matches nothing, so this file scored zero and
    # was still drawn green — say the number instead.
    print(f"\n{ran} tests passed." if not fails else f"{fails} failed")
    sys.exit(1 if fails else 0)
