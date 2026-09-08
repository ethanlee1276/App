"""The college talent card left the home page, and says what it carries.

Ethan, 2026-09-08, with the card circled at the top of the college home
page in week three: "do we really still need to show this on CFB still
and was all that data actually being used."

Two answers, both pinned here.

WHERE IT SHOWS. The card is a build-status readout — which of the four
inputs arrived, what the slope was fitted on — and it sat above the
board saying the same thing every day. The in-force card lives on the
Status page now, beside the other feed readouts, for the league in
view. The home page keeps only the warning that no prior is in force,
and only while a prior would still carry ten percent or more of the
rating; a missing five percent in November is not worth a banner.

WHAT IT SAYS. "It carries ~25% of a Week-1 projection" was the
schedule, printed in week three. `talent.current_weight` is the
reading: the median weight `blend_rating` actually gives the prior over
the teams that have one, with the median games played, and the build
publishes both. The card prints them, and says how unequally the four
inputs are used and that the layer's value against the close has never
been measured — `gamerank`'s college walk leaves it out.

Run directly: `python3 tests/test_talent_card_in_season.py`
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil as _shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
MODEL_DOC = open(os.path.join(ROOT, "docs", "CFB_MODEL.md"), encoding="utf-8").read()
CHECKS = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()

from engine.cfb import talent as T                              # noqa: E402
from engine.teamrates import TeamRating                         # noqa: E402


def _fn(name):
    i = APP.index(name)
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


# --- the reading -------------------------------------------------------------
def _rating(games):
    return TeamRating(net=0.0, off=0.0, def_=0.0, games=games)


def test_the_reading_is_the_median_weight_over_the_teams_with_a_prior():
    """Five teams with a prior: one unplayed (1.0), four at two and three
    games. The median is the two-game weight; a mean would be dragged
    toward the unplayed team's 1.0, a number no team is at."""
    ratings = {"A": _rating(0), "B": _rating(2), "C": _rating(2),
               "D": _rating(3), "E": _rating(3), "Z": _rating(3)}
    prior = {"A": 4.0, "B": 1.0, "C": -1.0, "D": 2.0, "E": 0.5}   # Z has none
    r = T.current_weight(ratings, prior)
    assert r["weighted_teams"] == 5
    assert r["weight_now"] == T.prior_weight(2) == 0.21, r
    assert r["games_median"] == 2, r
    mean = sum(T.prior_weight(n) for n in (0, 2, 2, 3, 3)) / 5
    assert abs(mean - r["weight_now"]) > 0.1, "the reading is a mean"


def test_returning_production_moves_the_reading_the_way_it_moves_the_blend():
    ratings = {"A": _rating(2), "B": _rating(2), "C": _rating(2)}
    prior = {"A": 1.0, "B": 1.0, "C": 1.0}
    low = T.current_weight(ratings, prior, {t: {"overall": 0.2} for t in prior})
    high = T.current_weight(ratings, prior, {t: {"overall": 0.8} for t in prior})
    assert low["weight_now"] < 0.21 < high["weight_now"], (low, high)
    assert low["weight_now"] == round(T.prior_weight(2, 0.2), 3)


def test_a_team_with_a_prior_and_no_rating_row_counts_as_unplayed():
    r = T.current_weight({}, {"A": 1.0, "B": 2.0})
    assert r == {"weight_now": 1.0, "games_median": 0, "weighted_teams": 2}


def test_no_prior_is_no_reading():
    assert T.current_weight({"A": _rating(3)}, {}) == \
        {"weight_now": None, "games_median": None, "weighted_teams": 0}


def test_the_build_publishes_the_reading_and_a_schedule_figure_before_it():
    fn = BUILD[BUILD.index("def attach_talent("):BUILD.index("def build_plays(")]
    assert "report.update(T.current_weight(ratings, prior, returning))" in fn
    # Before any fetch — so the no-key and no-rows paths carry it too —
    # the report says where the season is and what the schedule would
    # give a prior there; the page gates the warning on it.
    head = fn[:fn.index("raw_talent = cfbd.fetch_talent(year)")]
    assert '"games_median": _games_med' in head
    assert '"weight_now": T.prior_weight(_games_med)' in head


# --- where the card shows ---------------------------------------------------
def test_the_home_page_keeps_only_the_warning_and_only_while_it_matters():
    body = _fn("function renderTalent(")
    body = body[:body.index("\n}") + 2]          # the function, not the comment after it
    assert "talentStillMatters(t) ? talentWarnHTML(t) : \"\"" in body
    assert "talentCardHTML" not in body, "the in-force card is back on the home page"
    assert 'iconMark("check")' not in body
    assert body.rstrip().endswith('host.innerHTML = "";\n}'), \
        "an in-force prior draws something on the home page"


def test_the_status_page_carries_the_card_for_the_league_in_view():
    body = _fn("async function renderStatus(")
    assert 'state.sport === "cfb" && d.talent' in body
    assert "talentCardHTML(d.talent)" in body
    assert "The college talent prior" in body


def test_the_card_says_what_the_prior_carries_and_how_the_inputs_are_used():
    card = _fn("function talentCardHTML(")
    assert "talentWeightLine(t)" in card
    assert "~25% of a Week-1 projection" not in card, "the schedule is printed as a reading"
    assert "the recruiting composite IS the prior" in card
    assert "unmeasured" in card and "leave the prior out" in card
    line = _fn("function talentWeightLine(")
    assert "t.weight_now" in line and "t.games_median" in line
    assert "5% floor by the tenth game" in line


def test_the_docs_say_the_layers_value_is_unmeasured():
    for line in MODEL_DOC.splitlines():
        if line.startswith("| §5 Preseason prior"):
            assert "unmeasured" in line and "current_weight" in line, line
            break
    else:
        raise AssertionError("the §5 row vanished")
    assert "## 8b. The college talent card left the home page" in CHECKS
    assert "weight_now" in CHECKS and "games_median" in CHECKS


# --- the card, run --------------------------------------------------------
if not _shutil.which("node"):
    print("SKIP node is not installed; the arithmetic half of this file "
          "executes the card rather than reading it.")

_HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
function grab(name, end) {
  const i = src.indexOf(name);
  if (i < 0) throw new Error("missing: " + name);
  const j = src.indexOf(end, i);
  return src.slice(i, j + end.length);
}
var escapeHtml = (s) => String(s == null ? "" : s);
var iconMark = (n) => `[${n}]`;
eval([grab("function talentStillMatters(", "\n}"),
      grab("function talentWeightLine(", "\n}"),
      grab("function talentWarnHTML(", "\n}"),
      grab("function talentCardHTML(", "\n}")].join("\n"));
const out = {};
const t = { available: true, teams_with_prior: 105, weight_now: 0.21, games_median: 2,
  layers: { talent: 107, blue_chip: 229, returning: 106, portal: 256 },
  fit: { fitted: true, points_per_sd: 2.508, samples: 406, r: 0.206 }, missing_layers: [] };
let html = talentCardHTML(t);
out.says_weight = html.includes("<b>21%</b>") && html.includes("median 2 games played");
out.no_schedule = !html.includes("~25%");
out.check = html.includes("[check]") && !html.includes("[warn]");
out.one_game = talentWeightLine({ weight_now: 0.23, games_median: 1 }).includes("median 1 game played");
out.schedule_when_unknown = talentWeightLine({}).includes("~25% of a Week-1 projection");
out.matters = [talentStillMatters({ weight_now: 0.21 }), talentStillMatters({ weight_now: 0.10 }),
               talentStillMatters({ weight_now: 0.05 }), talentStillMatters({}), talentStillMatters(null)];
const w = talentCardHTML({ available: false, note: "nothing arrived", empty_layers: ["talent"] });
out.warn = w.includes("[warn]") && w.includes("--warn") && !w.includes("--good")
  && w.includes("nothing arrived") && w.includes("not the same");
out.none = talentCardHTML(null);
console.log(JSON.stringify(out));
"""


def _run():
    node = _shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(_HARNESS)
        path = fh.name
    try:
        res = subprocess.run([node, path, os.path.join(ROOT, "web", "js", "app.js")],
                             capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def test_the_card_prints_the_reading_and_the_warning_stays_a_warning():
    r = _run()
    if r is None:
        return
    assert r["says_weight"] and r["no_schedule"] and r["check"], r
    assert r["one_game"] and r["schedule_when_unknown"]
    assert r["matters"] == [True, True, False, True, True], r["matters"]
    assert r["warn"] and r["none"] == ""


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
