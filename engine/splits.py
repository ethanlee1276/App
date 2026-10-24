"""The public betting percentages: the share of the bets and of the money on each side, at a sportsbook.

    python3 -m engine.splits --probe          # one request, the reply's shape (needs the key)
    python3 -m engine.splits                  # this week's splits as the report will say them

Ethan, 2026-10-24: "yes build all of D" — the public betting percentages
first on that list. The research docs quote them ("72% of the bets on KC");
the site had only the prediction markets' money (engine/crowd).

THE SOURCE IS LICENSED, NOT SCRAPED. The pages that print these numbers
(Action Network, VSiN, the books' own) do not offer them for reuse. SharpAPI
sells them through an API: DraftKings' and Circa's handle (the money) and
ticket (the bets) shares, every five minutes. Its docs disagree on whether
splits need the Pro plan (listed at $229 a month) or come with every plan,
free included; a free key settles it with one `--probe`. OFF until the key
is set, with deploy/setenv.sh and never in a file:

    sudo ./deploy/setenv.sh SHARPAPI_KEY

THE REPLY IS READ BY SHAPE. Their docs (blocked from where this was
written) name `handle_pct` and `bets_pct` per side, 0-1, per market, with a
`fetched_at`. `parse` finds every block carrying either, wherever it sits,
names its market by the key above it and its book by the nearest `book`,
and reads 0-100 as well as 0-1. A shape it cannot read gives no splits, never
wrong ones, and `--probe` prints the reply's keys for the fix.

WHERE IT GOES. `betting_splits` on the board, a top-level paid key
(engine/gate.PAID_KEYS; licensed data is not given away), {"AWAY@HOME":
{book: {market: {"bets": {side: share}, "money": {side: share}}}}}; the
game report's market section says it. Every reading is appended to
data/cache/splits_history.jsonl, so whether fading the public pays can be
measured on our own record once a season is kept. Until then it moves no
number, and the report says who the public backs is context.

Standard library only.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

ENV = "SHARPAPI_KEY"
URL = "https://api.sharpapi.io/api/v1/splits?league={league}"
#: One request a league per this long: the feed refreshes every five
#: minutes, and the free plan allows twelve a minute.
TTL = 600
HISTORY = os.path.join("data", "cache", "splits_history.jsonl")
#: The book whose splits the report leads with: the biggest public book.
LEAD_BOOK = "DraftKings"
MARKETS = {"moneyline": "moneyline", "ml": "moneyline", "h2h": "moneyline",
           "spread": "spread", "spreads": "spread", "point_spread": "spread",
           "total": "total", "totals": "total", "over_under": "total"}
SIDES = ("home", "away", "over", "under")
BETS_KEYS = ("bets_pct", "bet_pct", "tickets_pct", "ticket_pct", "bets", "tickets")
MONEY_KEYS = ("handle_pct", "money_pct", "handle", "money")


def _cache_path(league: str) -> str:
    from .sources.fetch import CACHE_DIR
    return os.path.join(str(CACHE_DIR), f"splits_{league}.json")


def fetch(league: str, key: str | None = None, ttl: int = TTL, now: float | None = None):
    """The league's reply, cached for ``ttl``; None with no key. The key
    rides in a header, never the URL, so no log line can carry it."""
    key = key if key is not None else os.environ.get(ENV, "")
    if not key:
        return None
    path, now = _cache_path(league), now or time.time()
    try:
        if now - os.path.getmtime(path) < ttl:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    except (OSError, ValueError):
        pass
    req = urllib.request.Request(URL.format(league=league),
                                 headers={"X-API-Key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(path + ".tmp", path)
    return payload


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sides(block) -> dict:
    """{side: share 0-1} from one block, or {} when it is not a set of
    shares: a negative, a number past 100, or two sides that do not add
    up to the whole (within PAIR_SLACK). Percent points read as shares
    when any side is past 1."""
    if not isinstance(block, dict):
        return {}
    raw = {s: _num(block.get(s)) for s in SIDES}
    raw = {s: v for s, v in raw.items() if v is not None}
    if not raw or min(raw.values()) < 0:
        return {}
    scale = 100.0 if max(raw.values()) > 1.0 else 1.0
    out = {s: round(v / scale, 4) for s, v in raw.items()}
    if max(out.values()) > 1.0:
        return {}
    for a, b in (("home", "away"), ("over", "under")):
        if a in out and b in out and abs(out[a] + out[b] - 1.0) > PAIR_SLACK:
            return {}
    return out


#: Two sides' shares may miss the whole by this much (rounding), no more.
PAIR_SLACK = 0.03


def _team(v) -> str:
    if isinstance(v, dict):
        v = v.get("name") or v.get("full_name") or v.get("abbreviation") or ""
    return str(v or "").strip()


def _events(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "events", "games", "splits", "results"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def _walk(node, market: str, book: str, out: dict) -> None:
    """Fill {book: {market: {"bets", "money"}}} from every block that
    carries a bets or money share, wherever it sits."""
    if isinstance(node, list):
        for x in node:
            _walk(x, market, book, out)
        return
    if not isinstance(node, dict):
        return
    book = str(node.get("book") or node.get("sportsbook") or node.get("bookmaker") or book)
    m = MARKETS.get(str(node.get("market") or "").lower(), market)
    bets = next((_sides(node[k]) for k in BETS_KEYS if isinstance(node.get(k), dict)), {})
    money = next((_sides(node[k]) for k in MONEY_KEYS if isinstance(node.get(k), dict)), {})
    if (bets or money) and m:
        got = out.setdefault(book or "?", {}).setdefault(m, {})
        if bets:
            got["bets"] = bets
        if money:
            got["money"] = money
    for k, v in node.items():
        if not isinstance(v, (dict, list)) or k in BETS_KEYS + MONEY_KEYS:
            continue
        child = MARKETS.get(str(k).lower())
        # A dict keyed by the book's name: {"DraftKings": {"spread": …}}.
        named = (child is None and isinstance(v, dict)
                 and any(str(x).lower() in MARKETS for x in v))
        _walk(v, child or m, str(k) if named else book, out)


def parse(payload) -> list:
    """[{"home", "away", "at", "books": {book: {market: {"bets", "money"}}}}]."""
    out = []
    for e in _events(payload):
        if not isinstance(e, dict):
            continue
        teams = e.get("teams") if isinstance(e.get("teams"), dict) else {}
        home = _team(e.get("home_team") or e.get("home") or teams.get("home"))
        away = _team(e.get("away_team") or e.get("away") or teams.get("away"))
        books: dict = {}
        _walk(e, "", "", books)
        if home and away and books:
            out.append({"home": home, "away": away, "books": books,
                        "at": str(e.get("fetched_at") or e.get("updated_at") or "")})
    return out


def _abbr(sport: str) -> dict:
    if sport != "nfl":
        return {}
    from .sources.oddsapi import TEAM_ABBR
    return {k.lower(): v for k, v in TEAM_ABBR.items()}


def match(events: list, games: list, sport: str = "nfl") -> dict:
    """{"AWAY@HOME": books} for the board's games; a full name or the
    board's own code both match."""
    names = _abbr(sport)

    def code(t):
        return names.get(t.lower(), t.upper())
    want = {(str(g.get("away") or ""), str(g.get("home") or "")) for g in games if isinstance(g, dict)}
    out = {}
    for e in events:
        k = (code(e["away"]), code(e["home"]))
        if k in want:
            out[f"{k[0]}@{k[1]}"] = dict(e["books"], _at=e.get("at") or "")
    return out


def record(got: dict, sport: str, path: str = HISTORY, now: float | None = None) -> int:
    """Append each game's reading to the history; the lines written."""
    if not got:
        return 0
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time()))
    with open(path, "a", encoding="utf-8") as fh:
        for game, books in got.items():
            fh.write(json.dumps({"sport": sport, "game": game, "taken_at": stamp, "books": books}) + "\n")
    return len(got)


def attach_to_board(result: dict, sport: str, fetcher=None, history: str = HISTORY) -> str:
    """``result["betting_splits"]`` for the board's games. Never raises."""
    try:
        payload = (fetcher or fetch)(sport)
        if payload is None:
            return f"Public betting: off — {ENV} is not set (sudo ./deploy/setenv.sh {ENV})"
        got = match(parse(payload), result.get("games") or [], sport)
        result["betting_splits"] = got
        record(got, sport, history)
        return f"Public betting: {len(got)} of {len(result.get('games') or [])} game(s)"
    except Exception as exc:                                 # noqa: BLE001
        return f"Public betting unavailable ({type(exc).__name__})"


def _lead(books: dict) -> tuple:
    for name in [LEAD_BOOK] + sorted(books):
        if name in books and isinstance(books[name], dict) and name != "_at":
            return name, books[name]
    return "", {}


def words(books: dict, home: str, away: str) -> str:
    """The report's sentence for one game, or ""."""
    book, mk = _lead(books or {})
    bits = []
    for market, what in (("spread", "to cover"), ("moneyline", "to win")):
        s = mk.get(market) or {}
        b, m = s.get("bets") or {}, s.get("money") or {}
        side = max(("home", "away"), key=lambda x: b.get(x, m.get(x, 0)))
        if b.get(side) is None and m.get(side) is None:
            continue
        team = home if side == "home" else away
        parts = [f"{b[side] * 100:.0f}% of the bets" if b.get(side) is not None else "",
                 f"{m[side] * 100:.0f}% of the money" if m.get(side) is not None else ""]
        bits.append(f"{' and '.join(p for p in parts if p)} on {team} {what}")
        break
    t = mk.get("total") or {}
    b, m = t.get("bets") or {}, t.get("money") or {}
    if b or m:
        side = max(("over", "under"), key=lambda x: b.get(x, m.get(x, 0)))
        parts = [f"{b[side] * 100:.0f}% of the bets" if b.get(side) is not None else "",
                 f"{m[side] * 100:.0f}% of the money" if m.get(side) is not None else ""]
        if any(parts):
            bits.append(f"{' and '.join(p for p in parts if p)} on the {side}")
    if not bits:
        return ""
    sharp = ""
    circa = (books or {}).get("Circa") or (books or {}).get("Circa Sports")
    if book != "Circa" and isinstance(circa, dict):
        cs = (circa.get("spread") or {}).get("money") or {}
        if cs:
            side = max(cs, key=cs.get)
            sharp = (f". At Circa, where bigger bettors play, {cs[side] * 100:.0f}% of the spread money is on "
                     f"{home if side == 'home' else away}")
    return (f"Public betting at {book}: " + "; ".join(bits) + sharp
            + ". Who the public backs is context; the line already prices it")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probe", action="store_true", help="one request; print the reply's shape")
    ap.add_argument("--league", default="nfl")
    a = ap.parse_args(argv)
    if not os.environ.get(ENV):
        print(f"  {ENV} is not set: sudo ./deploy/setenv.sh {ENV}, then run with the service's env")
        return 1
    payload = fetch(a.league, ttl=0 if a.probe else TTL)
    if a.probe:
        evs = _events(payload)
        print(f"  reply: {type(payload).__name__}"
              + (f", keys {sorted(payload)[:12]}" if isinstance(payload, dict) else "")
              + f"; {len(evs)} event(s)")
        if evs:
            print("  first event:", json.dumps(evs[0])[:1500])
    got = parse(payload)
    print(f"  read {len(got)} game(s) with splits")
    for e in got[:16]:
        print(f"    {e['away']} @ {e['home']}: {words(e['books'], e['home'], e['away']) or '(no sentence)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
