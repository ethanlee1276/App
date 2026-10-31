"""Lighthouse runs in the nightly session, and a slower night is a number.

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 15 (tools/lighthouse_check.py). Lighthouse itself is too slow for
the gate (three runs, a minute each), so the nightly session runs it; what
these hold is the arithmetic that decides "slower":

  - the five numbers are read out of a Lighthouse report where Lighthouse
    puts them, and three runs give their median;
  - it is slower only past the slack (score 10 down, paint or interactive
    30% later, blocked 50% and 150 ms worse, shift past 0.1) — one
    wandering point is not a regression;
  - the baseline is committed and dated, and the code it measures is served
    as the box serves it (trimmed, compressed), not as 2.4 MB of raw script;
  - with no Chromium or no npx it says so and passes: the environment, not
    the page;
  - accessibility, best practices and SEO are scored in the same runs
    (2026-10-25): any point below the baseline fails the night, with the
    failing audits named (they do not wander the way timings do).

    python3 tests/test_lighthouse_runs_nightly.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import lighthouse_check as LC  # noqa: E402

BASE = {"score": 67, "lcp_ms": 6195, "tbt_ms": 327, "cls": 0.016, "tti_ms": 6566, "fcp_ms": 1367, "si_ms": 3066}


def _report(score, lcp, tbt, cls, tti):
    return {"categories": {"performance": {"score": score}},
            "audits": {"largest-contentful-paint": {"numericValue": lcp}, "total-blocking-time": {"numericValue": tbt},
                       "cumulative-layout-shift": {"numericValue": cls}, "interactive": {"numericValue": tti},
                       "first-contentful-paint": {"numericValue": 1300.4}, "speed-index": {"numericValue": 3000.6}}}


def test_the_numbers_come_out_of_the_report_and_the_median_of_three():
    runs = [LC.numbers(_report(.66, 6100.2, 300, .016, 6500)), LC.numbers(_report(.70, 5900, 280, .015, 6400)),
            LC.numbers(_report(.52, 9900, 900, .02, 9000))]
    assert runs[0] == {"score": 66, "lcp_ms": 6100, "tbt_ms": 300, "cls": 0.016, "tti_ms": 6500, "fcp_ms": 1300, "si_ms": 3001}
    m = LC.median(runs)
    assert m["score"] == 66 and m["lcp_ms"] == 6100 and m["tbt_ms"] == 300, "one bad run does not set the night"


def test_slower_means_clearly_past_the_slack():
    assert LC.verdict(dict(BASE), BASE) == []
    assert LC.verdict(dict(BASE, score=58, lcp_ms=7500, tbt_ms=470, tti_ms=8000), BASE) == [], "inside the slack"
    worse = LC.verdict(dict(BASE, score=55, lcp_ms=8200, tbt_ms=520, cls=0.14, tti_ms=8700), BASE)
    assert len(worse) == 5 and worse[0] == "score 55 (baseline 67)", worse
    assert any(w.startswith("largest paint 8.2 s") for w in worse) and any("layout shift 0.140" in w for w in worse)
    assert LC.verdict(dict(BASE, tbt_ms=470), dict(BASE, tbt_ms=100)) == ["blocked 470 ms (baseline 100 ms)"], \
        "a small baseline still needs 150 ms more"


def test_the_baseline_is_committed_and_the_code_is_served_as_the_box_serves_it():
    base = json.loads((ROOT / "tools" / "lighthouse_baseline.json").read_text())
    assert set(BASE) <= set(base) and base["measured"] and base["lighthouse"] == LC.VERSION
    src = (ROOT / "tools" / "lighthouse_check.py").read_text()
    assert "shrink.trimmed(rel, src) if rel in shrink.FILES" in src and '("Content-Encoding", "gzip")' in src
    assert f'"lighthouse@{{VERSION}}"' in src and "--only-categories=performance,accessibility,best-practices,seo" in src
    assert "from test_the_first_screen_holds_still import _board" in src, "the same board the first-screen test loads"


def test_the_other_categories_fail_on_any_point_down_and_name_the_audits():
    rep = _report(.70, 6000, 300, .016, 6400)
    rep["categories"].update({
        "accessibility": {"score": .96, "auditRefs": [{"id": "heading-order", "weight": 3}, {"id": "skip-link", "weight": 3},
                                                       {"id": "label-content-name-mismatch", "weight": 0}]},
        "best-practices": {"score": .96, "auditRefs": []}, "seo": {"score": 1, "auditRefs": []}})
    rep["audits"].update({"heading-order": {"score": 0, "title": "Heading elements are not in order"},
                          "skip-link": {"score": 1, "title": "Skip links are focusable"},
                          "label-content-name-mismatch": {"score": 0, "title": "Weightless"}})
    n = LC.numbers(rep)
    assert (n["a11y"], n["bp"], n["seo"]) == (96, 96, 100)
    assert "accessibility 96 · best practices 96 · SEO 100" in LC.line(n)
    base = dict(BASE, a11y=100, bp=96, seo=100)
    assert LC.worse(dict(n), base) == ["accessibility 96 (baseline 100)"], "one point down is reported"
    assert LC.worse(dict(n, a11y=100), base) == [] and LC.worse(dict(n, a11y=100, bp=100), base) == []
    assert LC.worse(n, BASE) == [], "an old baseline without the categories judges only the timings"
    assert LC.failing(rep, "accessibility") == ["Heading elements are not in order"], "only audits that count, and failed"
    assert "a11y" not in LC.numbers(_report(.7, 1, 1, 0, 1)), "a performance-only run carries no category"
    assert LC.median([LC.numbers(_report(.7, 1, 1, 0, 1)), n])["a11y"] == 96


def test_no_browser_or_no_npx_is_the_environment_not_the_page():
    old = dict(os.environ)
    try:
        os.environ["CHROME_PATH"] = "/nonexistent/chrome"
        assert LC.main([]) == 0
    finally:
        os.environ.clear()
        os.environ.update(old)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
