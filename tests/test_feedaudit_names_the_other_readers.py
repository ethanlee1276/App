"""A field the API reads is not a field nobody reads.

Ethan asked which numbers the build computes that "nobody ever sees",
and `feedaudit` answers it by searching four front-end files: app.js,
visuals.js, index.html, sw.js. That is the right search for the question
— the API filtering on a field does not put it in front of anybody — but
the REPORT said "named by no page" and then listed names the server
names, which reads as "nothing reads this" to whoever is asked to act on
it.

THE NUMBERS. On this box the report called 81 fields unread and three of
them were named by `server.py` or `boardlint.py`. Ethan's droplet run
produced 312; the same proportion is a dozen or so lines somebody is
asked to classify or delete with the one fact that settles it missing.

WHY A MARK AND NOT A WIDER SEARCH. Folding those files into `_readers`
would shrink the list and answer a different question. The field is
still invisible; it is just not dead. Two different findings with two
different fixes, so the report now says which it is.

Run through the gate's env.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import feedaudit                                  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _report(data, blob=""):
    """The audit over a feed handed in, against a page blob handed in."""
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "probe.json"), "w") as f:
            json.dump(data, f)
        # `audit` returns (lines, leads) — the CLI joins them. Treating
        # the tuple as a string is how a first draft of this file got
        # three green-looking assertions that were testing repr().
        lines, _leads = feedaudit.audit(data_dir=d, blob=blob)
        return "\n".join(lines)


# --- the mark -----------------------------------------------------------------
def test_a_field_only_the_api_names_is_flagged_not_called_unread():
    """`min_confidence` is the real case: no page shows it, `server.py`
    reads it, and before 2026-09-16 the report listed it beside fields
    genuinely nothing touches."""
    out = _report({"config": {"min_confidence": 6.0}})
    assert "min_confidence" in out
    assert "also in server.py" in out, out


def test_a_field_nothing_anywhere_names_carries_no_mark():
    """The mark has to distinguish, or it is decoration."""
    out = _report({"config": {"zzz_invented_here_only": 1.0}})
    assert "zzz_invented_here_only" in out
    assert "also in" not in out.split("zzz_invented_here_only")[1].split("\n")[0]


def test_a_field_a_page_does_show_is_not_in_the_report_at_all():
    """The mark is for fields that failed the page search — one that
    passes it should never reach this part of the report."""
    out = _report({"config": {"shown_thing": 1.0}}, blob='data.config.shown_thing')
    assert "shown_thing" not in out, out


# --- and the search behind it -------------------------------------------------
def test_the_off_page_consumers_are_real_files():
    """A name in `OFF_PAGE` that does not exist is a silent hole: the
    mark would never appear for anything that file reads."""
    missing = [rel for rel in feedaudit.OFF_PAGE
               if not os.path.isfile(os.path.join(ROOT, rel))]
    assert not missing, f"OFF_PAGE names files that are not here: {missing}"
    assert len(feedaudit.OFF_PAGE) >= 3


def test_the_page_search_is_still_the_page_search():
    """The fix must not have quietly widened `_readers`. If the API's
    files ever end up in there, the report starts calling API-only
    fields "shown" and the whole question goes soft."""
    import inspect
    src = inspect.getsource(feedaudit._readers)
    for rel in feedaudit.OFF_PAGE:
        assert rel not in src, (
            f"{rel} became a 'page' — the report now answers a different "
            "question than the one it prints")


def test_the_legend_explains_the_mark():
    """A mark nobody can decode is worse than none: it reads as noise on
    a report somebody is being asked to act on line by line."""
    out = _report({"config": {"min_confidence": 6.0}})
    assert "[also in <file>]" in out, "the mark is unexplained"
    assert "do not cut them" in out


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
