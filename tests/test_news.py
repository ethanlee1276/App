"""Headlines only, from feeds offered for syndication — the news section.

Ethan, 2026-09-02: "We should add a section for sports news. Figure out
what we are allowed to pull and display on the site." The answer lives
in engine/sources/news.py: TITLES + SOURCE + LINK OUT from
publisher-offered RSS, never article text or images — and the parser
enforces it structurally by refusing to even read the description tag.

Run directly: `python3 tests/test_news.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.sources import news

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Star back at practice</title>
  <link>https://example.com/a</link>
  <description>FULL ARTICLE TEXT THAT MUST NEVER SHIP</description>
  <pubDate>Tue, 02 Sep 2026 14:00:00 GMT</pubDate></item>
<item><title>Trade rumor swirls</title>
  <link>https://example.com/b</link>
  <pubDate>Tue, 02 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>No link, no row</title><link></link></item>
<item><title></title><link>https://example.com/c</link></item>
</channel></rss>"""


def test_titles_links_and_dates_parse_and_junk_rows_drop():
    got = news.parse_rss(RSS, "ESPN")
    assert [r["title"] for r in got] == ["Star back at practice",
                                        "Trade rumor swirls"]
    assert got[0]["link"] == "https://example.com/a"
    assert got[0]["source"] == "ESPN"
    assert got[0]["epoch"] > got[1]["epoch"] > 0


def test_article_text_is_structurally_unreachable():
    """The rights answer, enforced: the parser never reads the
    description tag, so no field of any published row can carry the
    publisher's article text — a future page cannot leak what the
    pipeline never held."""
    got = news.parse_rss(RSS, "ESPN")
    for row in got:
        for v in row.values():
            assert "FULL ARTICLE TEXT" not in str(v)
        assert set(row) == {"title", "link", "source", "published", "epoch"}
    with open(os.path.join(ROOT, "engine", "sources", "news.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert 'findtext("description")' not in src
    assert 'findtext("content' not in src


def test_bad_xml_returns_empty_not_a_crash():
    assert news.parse_rss("not xml at all", "X") == []
    assert news.parse_rss("<rss><channel></channel></rss>", "X") == []


def test_every_site_sport_with_a_league_has_a_feed():
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba", "ufc"):
        assert news.FEEDS.get(sport), sport
        for source, url in news.FEEDS[sport]:
            assert url.startswith("https://"), url
            assert source, "attribution requires a source name"


def test_the_loop_builds_it_and_the_page_links_out_safely():
    with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as f:
        assert "news_build.py" in f.read()
    assert os.path.exists(os.path.join(ROOT, "news_build.py"))
    with open(os.path.join(ROOT, "web", "js", "app.js"),
              encoding="utf-8") as f:
        js = f.read()
    assert "function newsSectionHTML(sport, news)" in js
    at = js.index("function newsSectionHTML")
    body = js[at:js.index("\nasync function renderInjuries", at)]
    assert 'rel="noopener noreferrer"' in body
    assert 'target="_blank"' in body
    assert "r.description" not in body and "r.summary" not in body
    assert "Around the league" in body
    assert "escapeHtml(r.title)" in body, "titles render as text, never HTML"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
