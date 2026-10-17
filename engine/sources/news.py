"""League headlines the site may legally show — titles, source, link out.

Ethan, 2026-09-02: "We should add a section for sports news. Figure out
what we are allowed to pull and display on the site."

THE ANSWER, WRITTEN WHERE THE CODE ENFORCES IT. What we display:

  * HEADLINES — short factual titles get, at most, thin copyright
    protection, and showing them with attribution and a link is the
    settled practice of every aggregator (Google News runs on it);
  * THE SOURCE'S NAME — attribution is both the legal safety margin and
    the honest thing;
  * A LINK OUT — traffic to the publisher is the exchange the whole
    arrangement rests on. Links are not copies.

And the source of the data matters as much as what we take from it:
these are RSS FEEDS THE PUBLISHERS THEMSELVES OFFER — RSS exists to be
syndicated; publishing one is an invitation to display its items.

What we deliberately do NOT take, even though the feeds carry it:

  * ARTICLE TEXT — descriptions and bodies are the publisher's
    copyrighted expression. This module does not even PARSE the
    description tag, so a future page cannot leak it by accident;
  * IMAGES — hotlinking a publisher's photos takes their bandwidth and
    their photographers' licensed work. Headlines only;
  * anything from a source that does not offer a feed.

Cached through the standard fetch layer (30-minute TTL — news is not a
scoreboard), each league failing independently, standard library only.
"""

from __future__ import annotations

import email.utils as _eut
import xml.etree.ElementTree as _ET

from .fetch import fetch_text

#: Publisher-offered RSS feeds, per site sport key. ESPN publishes one
#: per league at a stable path. More sources append as (name, url)
#: tuples — the parser is plain RSS 2.0.
FEEDS: dict[str, list[tuple[str, str]]] = {
    "nfl": [("ESPN", "https://www.espn.com/espn/rss/nfl/news")],
    "cfb": [("ESPN", "https://www.espn.com/espn/rss/ncf/news")],
    "mlb": [("ESPN", "https://www.espn.com/espn/rss/mlb/news")],
    "nba": [("ESPN", "https://www.espn.com/espn/rss/nba/news")],
    "wnba": [("ESPN", "https://www.espn.com/espn/rss/wnba/news")],
    "ufc": [("ESPN", "https://www.espn.com/espn/rss/mma/news")],
}

TTL = 1800
PER_SPORT = 12


def parse_rss(text: str, source: str) -> list[dict]:
    """RSS 2.0 items → ``[{title, link, source, published, epoch}]``.

    Title, link, and date ONLY — see the module docstring for why the
    description is never read. Tolerant of feed quirks: an item missing
    a date still ships (epoch 0 sorts it last), an unparseable feed
    returns [] rather than raising.
    """
    try:
        root = _ET.fromstring(text)
    except _ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        pub = (item.findtext("pubDate") or "").strip()
        epoch = 0
        if pub:
            try:
                epoch = int(_eut.parsedate_to_datetime(pub).timestamp())
            except (TypeError, ValueError):
                epoch = 0
        out.append({"title": title[:300], "link": link, "source": source,
                    "published": pub, "epoch": epoch})
    return out


def fetch_sport(sport: str) -> list[dict]:
    """One sport's headlines, newest first, capped at PER_SPORT."""
    rows: list[dict] = []
    for source, url in FEEDS.get(sport, ()):
        try:
            text = fetch_text(url, f"news_{sport}_{source.lower()}", ttl=TTL)
        except Exception:                                   # noqa: BLE001
            continue
        if text:
            rows.extend(parse_rss(text, source))
    rows.sort(key=lambda r: -r["epoch"])
    return rows[:PER_SPORT]


def build_all() -> dict:
    """Every sport's headlines plus the display policy, for the page."""
    import datetime as _dt
    out = {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
           # Stated in the payload so the page's wording can read it
           # rather than hard-coding a claim the engine enforces.
           "policy": ("headlines and links only, from publisher-offered "
                      "feeds — the reporting itself lives at the source"),
           "sports": {}}
    for sport in FEEDS:
        got = fetch_sport(sport)
        if got:
            out["sports"][sport] = got
    return out
