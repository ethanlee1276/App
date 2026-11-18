"""A day is said in words wherever a reader meets one (2026-11-18, step YE).

The Streak's "Survived 2026-11-17." (step YD) had company: the Record's
recent results ("2026-11-14 3–1"), its "Last slate (2026-11-14)", the era
note's "(2026-09-27)", the fantasy player card's "Upcoming game" and the
proof page's days each printed the date as the database keeps it. Each now
says it the way every other page does (app.js formatGameDate: "Sat, Nov 14"),
keeping the stored text when it is not a date.

    python3 tests/test_a_day_is_said_in_words.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
REC = (JS / "record.js").read_text(encoding="utf-8")
MORE = (JS / "more.js").read_text(encoding="utf-8")
ACCT = (JS / "account.js").read_text(encoding="utf-8")


def test_each_day_goes_through_the_sites_own_words():
    for src, said in ((APP, "escapeHtml(formatGameDate(up.date) || up.date)"),
                      (APP, "escapeHtml(formatGameDate(r.date) || r.date)"),
                      (APP, "`Last slate (${escapeHtml(formatGameDate(lastPt.date) || lastPt.date)})`"),
                      (REC, "escapeHtml(formatGameDate(era.since) || era.since)"),
                      (MORE, "escapeHtml(formatGameDate(d.date) || d.date)"),
                      (ACCT, "escapeHtml(formatGameDate(d) || d)")):
        assert said in src, said
    for raw in ("${escapeHtml(up.date)}", "<span>${escapeHtml(r.date)}</span>", "Last slate (${escapeHtml(lastPt.date)})",
                "(${escapeHtml(era.since)})", "<summary>${escapeHtml(d.date)} — ", "Survived ${escapeHtml(me.last_day)}"):
        assert raw not in APP + REC + MORE + ACCT, raw


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
