"""The league headlines reach the page (the 2026-10-30 audit).

The news section on Injuries & News has drawn nothing since it shipped:
web/data/news.json on the box was written once, on 2026-09-01, with no
headlines, and never again. The feed read sent the site's own User-Agent,
which ESPN answers 403 (engine/sources/fetch.py records it), so every
league failed; and the build, finding every feed down, returned without
writing — keeping an empty file and no reason.

Guarded here: the read sends urllib's own agent as every other ESPN read
does; every league with a board has a feed, and a second publisher beside
ESPN; a failing feed says why, in the file; a league whose feeds fail keeps
its last headlines in the file and the page never shows one older than four
days.

    python3 tests/test_the_news_feeds_answer.py
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.sources import fetch, news                        # noqa: E402

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Chiefs activate their tight end</title><link>https://example.com/a</link>
<pubDate>Thu, 29 Oct 2026 18:00:00 GMT</pubDate><description>NOT READ</description></item>
</channel></rss>"""


def test_the_read_sends_urllibs_own_agent():
    asked = []
    real = news.fetch_text
    news.fetch_text = lambda url, key, ttl=None, user_agent=None: asked.append(user_agent) or RSS
    try:
        rows = news.fetch_sport("nfl")
    finally:
        news.fetch_text = real
    assert asked and all(a is fetch.DEFAULT_AGENT for a in asked), "ESPN answers the site's own agent 403"
    assert rows and rows[0]["title"] == "Chiefs activate their tight end"
    assert "NOT READ" not in json.dumps(rows), "the description is never read"


def test_every_league_with_a_board_has_two_publishers():
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba", "nhl", "ufc"):
        feeds = news.FEEDS.get(sport) or []
        assert len({name for name, _ in feeds}) >= 2, sport
        assert all(u.startswith("https://") for _, u in feeds), sport


def test_a_failing_feed_says_why():
    def boom(url, key, ttl=None, user_agent=None):
        if "espn" in url:
            raise fetch.DataUnavailable("HTTP Error 403: Forbidden")
        return "<rss><channel></channel></rss>"
    real = news.fetch_text
    news.fetch_text = boom
    try:
        out = news.build_all()
    finally:
        news.fetch_text = real
    assert out["sports"] == {}
    assert "403" in out["errors"]["nfl"]["ESPN"]
    assert out["errors"]["nhl"]["CBS Sports"] == "the feed answered with no headlines"


def test_the_build_keeps_a_quiet_leagues_headlines_and_writes_why():
    import news_build
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "news.json"
        old_row = {"title": "Old news", "link": "https://example.com/o", "source": "ESPN",
                   "published": "", "epoch": 1}
        out.write_text(json.dumps({"generated_at": "2026-09-01T06:38:47", "sports": {"nba": [old_row]}}))
        fresh = {"generated_at": "2026-10-30T01:00:00", "policy": "p",
                 "sports": {"nfl": [dict(old_row, title="New")]},
                 "errors": {"nba": {"ESPN": "HTTPError: 403"}}}
        real, argv = news_build.news.build_all, sys.argv
        news_build.news.build_all = lambda: json.loads(json.dumps(fresh))
        sys.argv = ["news_build.py", "--out", str(out)]
        try:
            news_build.main()
        finally:
            news_build.news.build_all, sys.argv = real, argv
        got = json.loads(out.read_text())
    assert got["generated_at"] == "2026-10-30T01:00:00", "the file is rewritten every run"
    assert got["sports"]["nfl"][0]["title"] == "New"
    assert got["sports"]["nba"] == [old_row], "a quiet league keeps what it had"
    assert got["errors"] == {"nba": {"ESPN": "HTTPError: 403"}}, "and the file says why"


def test_the_page_never_shows_a_headline_older_than_four_days():
    src = (ROOT / "web" / "js" / "more.js").read_text()
    i = src.index("const NEWS_MAX_AGE_S")
    j = src.index("\n}\n", src.index("function newsSectionHTML(")) + 3
    now = int(time.time())
    news_doc = {"sports": {"nfl": [
        {"title": "Fresh", "link": "https://example.com/f", "source": "ESPN", "epoch": now - 3600},
        {"title": "Stale", "link": "https://example.com/s", "source": "ESPN", "epoch": now - 9 * 86400}],
        "nba": [{"title": "Gone", "link": "https://example.com/g", "source": "ESPN", "epoch": now - 30 * 86400}]}}
    js = f"""
    const escapeHtml = (s) => String(s), safeHref = (s) => s;
    {src[i:j]}
    console.log(JSON.stringify([newsSectionHTML("nfl", {json.dumps(news_doc)}),
                                newsSectionHTML("nba", {json.dumps(news_doc)})]));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    nfl, nba = json.loads(out.stdout)
    assert "Fresh" in nfl and "Stale" not in nfl
    assert nba == "", "a league whose only headlines are old draws no section"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
