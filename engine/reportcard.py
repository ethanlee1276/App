"""Your report card's one server half: the close on the bets you logged.

Ethan, 2026-10-15, from the brainstorm he asked to have built ("do every
one for every sport"): a betting report card in My Bets — your hit rate
against what your prices needed, and your closing-line value against our
closes. The hit rate needs nothing but your own log and is worked out on
the page (js/extras.js). The close does not: a bet you typed in by hand
has a price and a description, and the price the market settled at is on
our side, in the journal, for the picks we published.

WHAT THIS DOES. For each logged bet the page sends ({id, sport, date,
desc}), it looks for ONE journaled pick of ours on that sport and day
whose player (or team) is named in the description, whose side is the
side the words say, whose number is in the words, and — when more than
one market is left — whose market's own name is in the words. A bet that
leaves no pick, or more than one, gets nothing back: an answer is a close
we are sure of, never a guess at one.

WHAT IT NEVER DOES. It answers only from SETTLED picks (won, lost, push)
that carry a closing price, so it cannot be used to ask what is open
tonight; it returns the close and the pick it came from, nothing else
from the row; it writes nothing and keeps nothing it was sent. The page
sends only when the reader presses the button that says so, because My
Bets otherwise never leaves the browser.
"""

from __future__ import annotations

import re

#: At most this many bets per ask; the page sends the settled ones only.
MAX_BETS = 300
#: The fields kept from each bet the page sends, and their lengths.
_ID, _SPORT, _DESC = 40, 8, 160
SPORTS = ("nfl", "cfb", "mlb", "nba", "wnba", "nhl", "ufc")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUM = re.compile(r"(?<![\d.])[+-]?\d+(?:\.\d+)?(?![\d.])")


def _text(desc: str) -> str:
    """The description, lower-cased with accents and apostrophes folded the
    way `normalize_name` folds a name, but with a number's decimal point
    kept: "Over 1.5" must still read 1.5. Padded with spaces so a word is
    found whole."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(desc or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("'", "").replace("\u2019", "").replace("\u02bc", "")
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    s = re.sub(r"[^a-z0-9.+ ]", " ", s)
    return " " + re.sub(r"\s+", " ", s).strip() + " "


def _words(label: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", str(label or "").lower()) if len(w) > 2]


def _numbers(text: str) -> set[float]:
    out = set()
    for m in _NUM.finditer(text):
        try:
            out.add(abs(float(m.group(0))))
        except ValueError:
            pass
    return out


def _named(row, text: str) -> bool:
    """The pick's player is in the words, or — for a game line, where the
    journal's `player` is the team — the team's last word is."""
    from engine.sources.oddsapi import normalize_name
    who = normalize_name(str(row["player"] or ""))
    if not who:
        return False
    if f" {who} " in text:
        return True
    if row["market"] in ("moneyline", "spread", "total", "team_total"):
        last = who.split()[-1]
        return len(last) > 2 and f" {last} " in text
    return False


def _side_fits(row, text: str) -> bool:
    side = str(row["side"] or "").strip().lower()
    if side in ("over", "under"):
        short = "o" if side == "over" else "u"
        return f" {side} " in text or bool(re.search(rf"\s{short}\s?\d", text))
    if side in ("yes", "no"):
        return side != "no" or " no " in text
    return True


def _line_fits(row, nums: set[float]) -> bool:
    line = row["line"]
    if line is None or row["market"] == "moneyline":
        return True
    try:
        return abs(float(line)) in nums
    except (TypeError, ValueError):
        return False


def _market_fits(row, text: str) -> bool:
    from engine import markets
    words = _words(markets.label(row["market"])) or _words(row["market"])
    return bool(words) and all(f" {w}" in text for w in words)


def clean(bets) -> list[dict]:
    """The bets as the page sent them, cut to the fields and lengths this
    reads, with anything malformed dropped."""
    out = []
    for b in (bets if isinstance(bets, list) else [])[:MAX_BETS]:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or "")[:_ID]
        sport = str(b.get("sport") or "").strip().lower()[:_SPORT]
        date = str(b.get("date") or "")[:10]
        desc = str(b.get("desc") or "")[:_DESC]
        if bid and sport in SPORTS and _DATE.match(date) and desc.strip():
            out.append({"id": bid, "sport": sport, "date": date, "desc": desc})
    return out


def closes(conn, bets) -> dict:
    """{bet id: {"close", "player", "market", "side", "line", "label"}} for
    each bet that matches exactly one settled, closed pick of ours."""
    from engine import markets
    found: dict = {}
    day_rows: dict = {}
    for b in clean(bets):
        key = (b["sport"], b["date"])
        if key not in day_rows:
            day_rows[key] = conn.execute(
                "SELECT DISTINCT player, market, side, line, closing_odds FROM bets "
                "WHERE sport=? AND (date=? OR game_day=?) AND closing_odds IS NOT NULL "
                "AND status IN ('won','lost','push')", (b["sport"], b["date"], b["date"])).fetchall()
        text = _text(b["desc"])
        nums = _numbers(text)
        hits = [r for r in day_rows[key]
                if _named(r, text) and _side_fits(r, text) and _line_fits(r, nums)]
        if len(hits) > 1:
            hits = [r for r in hits if _market_fits(r, text)]
        # One close per (player, market, side, line): two categories that
        # journaled the same pick closed at the same price.
        picks = {(r["player"], r["market"], str(r["side"] or "").upper(), r["line"]): r for r in hits}
        if len(picks) != 1:
            continue
        r = next(iter(picks.values()))
        found[b["id"]] = {"close": int(r["closing_odds"]), "player": r["player"], "market": r["market"],
                          "side": r["side"], "line": r["line"], "label": markets.label(r["market"])}
    return found
