"""An expected starting quarterback is read off the headlines we already pull.

Ethan, 2026-09-28: the site learned the Bears' quarterback from the depth
chart; his research had "Keenum expected to start" from reporters hours
earlier. engine/newsqb reads that from the ESPN feed the news build already
fetches, and engine/qbchange.changes takes it behind the depth chart and
ahead of "second quarterback by volume". The card says "per ESPN".

Run directly: `python3 tests/test_the_news_names_the_starter.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import newsqb as N, qbchange as Q                  # noqa: E402

NOW = 1_790_600_000.0
QB = {"teams": {"CHI": {"starter": "Caleb Williams", "backup": "Tyson Bagent"},
                "PHI": {"starter": "Jalen Hurts", "backup": "Tanner McKee"}},
      "passing": {"Caleb Williams": (600.0, 4500.0), "Tyson Bagent": (120.0, 700.0),
                  "Case Keenum": (60.0, 400.0), "Jalen Hurts": (500.0, 3900.0)},
      "usual": {}}


def _h(title, age_h=2.0, source="ESPN"):
    return {"title": title, "source": source, "epoch": NOW - age_h * 3600, "link": ""}


def test_the_phrases_a_beat_reporter_uses_and_the_ones_that_mean_no():
    rooms = dict(QB); rooms["teams"] = dict(rooms["teams"], CHI={"starter": "Caleb Williams", "backup": "Case Keenum"})
    got = N.expected_starters([_h("Case Keenum expected to start for Bears vs. Eagles")], rooms, NOW)
    assert got == {"CHI": {"name": "Case Keenum", "title": "Case Keenum expected to start for Bears vs. Eagles",
                           "source": "ESPN", "epoch": NOW - 7200}}, got
    for t in ("Bears name Tyson Bagent the starter Monday night", "Tyson Bagent will start with Williams out",
              "Bagent gets the start", "Tyson Bagent to make his first start of the season"):
        assert N.expected_starters([_h(t)], QB, NOW).get("CHI", {}).get("name") == "Tyson Bagent", t
    for t in ("Tyson Bagent not expected to start", "Caleb Williams won't start vs. Eagles",
              "Caleb Williams ruled out; backup Tyson Bagent questionable", "Bears expected to start fast"):
        assert "CHI" not in N.expected_starters([_h(t)], QB, NOW), t


def test_newest_wins_and_old_news_is_ignored():
    got = N.expected_starters([_h("Tyson Bagent will start", age_h=30), _h("Caleb Williams will start", age_h=2)], QB, NOW)
    assert got["CHI"]["name"] == "Caleb Williams"
    assert "CHI" not in N.expected_starters([_h("Tyson Bagent will start", age_h=24 * 5)], QB, NOW)


def test_the_change_finder_takes_the_reported_man_behind_the_chart():
    Out = type("I", (), {})
    hurt = Out(); hurt.team, hurt.player, hurt.status = "CHI", "Caleb Williams", "OUT"
    room = dict(QB); room["teams"] = dict(room["teams"], CHI={"starter": "Caleb Williams", "backup": "Tyson Bagent"})
    news = {"CHI": {"name": "Case Keenum", "source": "ESPN", "title": "Case Keenum expected to start", "epoch": NOW}}
    # No chart: the reported man, ahead of the backup by volume.
    ch = Q.changes(room, [hurt], None, news_qb=news)["CHI"]
    assert ch["replacement"] == "Case Keenum" and ch["reported"]["source"] == "ESPN"
    assert Q.headline(ch) == "Caleb Williams (OUT) — Case Keenum expected to start (per ESPN)"
    assert Q.card(ch)["reported"]["source"] == "ESPN"
    # The chart names someone else: the chart wins, and nothing is "reported".
    ch = Q.changes(room, [hurt], {"CHI": "Tyson Bagent"}, news_qb=news)["CHI"]
    assert ch["replacement"] == "Tyson Bagent" and ch["reported"] is None
    assert Q.headline(ch) == "Caleb Williams (OUT) — Tyson Bagent starts"
    # No news: as before.
    assert Q.changes(room, [hurt], None)["CHI"]["replacement"] == "Tyson Bagent"


def test_the_build_reads_the_news_file_and_never_fails_on_it():
    src = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert "_nq.expected_starters(_nq.load_headlines(), carry_report.get(\"qb\") or {})" in src
    assert "news_qb=_news_qb" in src
    assert N.load_headlines("/nonexistent/news.json") == []


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
