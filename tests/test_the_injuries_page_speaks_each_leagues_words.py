"""The injuries page speaks each league's words, and its headlines are news
(USEREYES1, 18 November 2026).

Walk 7 read the NHL's injuries page as a visitor:

  * the "Out tier" tile said "out, IR, long-term IL", baseball's injured list;
  * the footer pointed hockey readers at "the NFL's practice-level detail";
  * each team row said its count twice: "Toronto Maple Leafs · 9 out · 9";
  * "Around the league" opened with "Today's top games to watch, best bets,
    odds: Jazz vs. Clippers, Illinois vs. Duke and more" (CBS's every-sport
    roundup, filed under hockey), and the NFL's, the NBA's and college
    basketball's lists carried "Use BetMGM bonus code CBSSPORTS to get $1,500
    bonus bets ..." — a sportsbook's sign-up offer as a headline.

What these hold: each league's own words for the out tier, the NFL's note
only on the NFL's page, a team's count only where it adds to its tiers, and
no promotion or every-sport roundup among a league's headlines.

    python3 tests/test_the_injuries_page_speaks_each_leagues_words.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.sources import news                               # noqa: E402

MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")


def _fn(name):
    i = MORE.index(f"function {name}(")
    return MORE[i:MORE.index("\n}\n", i) + 3]


def test_the_out_tier_is_said_in_the_leagues_words():
    page = _fn("renderInjuries")
    assert '"out, IR, long-term IL"' not in page
    assert 'nhl: "out, IR, long-term IR"' in page and 'mlb: "out, the injured list"' in page
    assert 'nfl: "out, IR, PUP"' in page


def test_the_nfl_note_is_only_on_the_nfls_page():
    page = _fn("renderInjuries")
    i = page.index("practice-level detail")
    assert 'sport === "nfl" ? ` The NFL’s' in page[i - 120:i], page[i - 120:i]


def test_a_teams_count_shows_only_where_it_adds():
    block = _fn("injTeamBlock")
    assert "rows.length !== out + maybe" in block
    assert '${tiers}<span class="inj-team-n">${rows.length}</span>' not in block


def test_a_promotion_or_a_roundup_is_not_news():
    for ad in ("Use BetMGM bonus code CBSSPORTS to get $1,500 bonus bets for Pistons-Spurs, Duke-Illinois, NBA on Tuesday",
               "Use DraftKings promo code to get $200 bonus, free NBA League Pass for Spurs-Pistons, Duke-Illinois on Tuesday",
               "Kalshi promo code CBSSPORTS55: Claim $55 bonus for Duke-Illinois, Spurs-Pistons, NBA, college football Tuesday",
               "Use FanDuel promo code to get $200 in bonus bets for college football, Spurs-Pistons, Duke-Illinois on Tuesday",
               "Today's top games to watch, best bets, odds: Jazz vs. Clippers, Illinois vs. Duke and more",
               "Today’s top games to watch, best bets, odds: Wizards vs. Pacers and more"):
        assert not news.is_news(ad), ad
    for real in ("Hurricanes vs. Kraken NHL odds, picks: Carolina looks to keep rolling in rare Thursday matinee from Finland",
                 "NFL schedule flex: League moves Week 12 'Sunday Night Football' matchup, shifts afternoon games",
                 "NBA MVP Rankings: Luka Dončić, Victor Wembanyama in a two-horse race",
                 "College basketball picks, schedule: Predictions for Michigan State vs. Tennessee, more Top 25 games Tuesday"):
        assert news.is_news(real), real


def test_the_feed_drops_what_is_not_news():
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Use BetMGM bonus code CBSSPORTS to get $1,500 bonus bets</title>
  <link>https://example.com/ad</link><pubDate>Tue, 17 Nov 2026 14:00:00 GMT</pubDate></item>
<item><title>Makar out two weeks with a lower-body injury</title>
  <link>https://example.com/makar</link><pubDate>Tue, 17 Nov 2026 13:00:00 GMT</pubDate></item>
</channel></rss>"""
    keep = (news.FEEDS, news.fetch_text)
    try:
        news.FEEDS = {"nhl": [("Test", "https://example.com/feed")]}
        news.fetch_text = lambda *a, **k: rss
        got = news.fetch_sport("nhl")
    finally:
        news.FEEDS, news.fetch_text = keep
    assert [r["title"] for r in got] == ["Makar out two weeks with a lower-body injury"], got


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
