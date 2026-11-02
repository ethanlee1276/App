"""Ten books cost one region; the eleventh doubles every call.

Ethan, 2026-11-02: "cut the books to 10. obv keep the main books everyone
uses the draft kings and fanduel and thescore bet and mgm and shit like
that". The API bills every call per MARKET per region, and a call that
names its books (`bookmakers`) is billed one region for every ten of them.
From 2026-09-15 the list was seventeen, on the belief that naming books
only FILTERS a response already paid for; on 2026-10-30 the API reported
~99,400 credits used in October against ~55,000 in our own ledger, about
the two regions seventeen books make.

What these hold:

  * the list is ten books at most (`oddsapi.BOOKS_PER_REGION`), with no
    key twice;
  * the main US books stay — DraftKings, FanDuel, BetMGM, Caesars,
    Fanatics, theScore Bet, Hard Rock, BetRivers — and Pinnacle stays as
    the sharp reference the fair prices are measured against, never a
    ticket;
  * the ledger's estimate (`oddsapi._classify`) counts every ten books
    named as a region, so a longer list shows up as a doubled estimate;
  * every paid call still asks for one region, and every book asked for
    has a name to print;
  * the reason is written beside the list.

This file used to be test_books_are_free.py, which held the opposite claim.

Run directly: `python3 tests/test_ten_books_cost_one_region.py`
"""

import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget                                 # noqa: E402
from engine.sources import oddsapi                            # noqa: E402

URL = ("https://api.the-odds-api.com/v4/sports/basketball_nba/events/e1/odds"
       "?apiKey=k&regions=us&markets=player_points,player_rebounds,h2h&oddsFormat=american")


def test_the_list_is_ten_books_at_most_and_names_none_twice():
    """THE LOAD-BEARING FACT. One book past ten is a second region on every
    call, for every sport — and in a diff it looks like adding a word."""
    assert oddsapi.BOOKS_PER_REGION == 10
    books = oddsapi.DEFAULT_BOOKS
    assert len(books) <= oddsapi.BOOKS_PER_REGION, (
        f"{len(books)} books asked for: every call is billed "
        f"{-(-len(books) // oddsapi.BOOKS_PER_REGION)} regions. Drop one, or "
        f"budget the doubled bill first and say so here.")
    assert len(set(books)) == len(books), "a book is asked for twice"


def test_the_main_books_stay_and_pinnacle_is_the_reference():
    """Ethan's list: the books everyone uses, and the sharp book the fair
    prices are measured against (the NBA and NHL anchors, Sharp money)."""
    books = set(oddsapi.DEFAULT_BOOKS)
    for key in ("draftkings", "fanduel", "betmgm", "williamhill_us", "fanatics",
                "hardrockbet", "betrivers"):
        assert key in books, key
    assert books & {"espnbet", "thescorebet", "thescore"}, "theScore Bet is gone"
    assert "pinnacle" in books and oddsapi.SHARP_BOOKS == {"pinnacle"}
    for gone in ("ballybet", "betparx", "fliff", "windcreek", "novig", "prophetx"):
        assert gone not in books, gone
        assert oddsapi.BOOK_TITLES.get(gone), f"{gone}: old tickets still need its name"


def test_the_ledger_counts_every_ten_books_as_a_region():
    """`_classify` is the ledger's estimate beside what the API billed
    (`x-requests-last`). It reads the books off the URL actually sent."""
    name = "odds_event_nba_e1_abcd1234.json"
    ten = ",".join(oddsapi.DEFAULT_BOOKS)
    assert oddsapi._classify(f"{URL}&bookmakers={ten}", name)[2] == 3, "three markets, ten books: one region"
    seventeen = ten + ",ballybet,betparx,fliff,windcreek,novig,prophetx,thescore"
    assert oddsapi._classify(f"{URL}&bookmakers={seventeen}", name)[2] == 6, "seventeen books: two regions"
    assert oddsapi._classify(URL, name)[2] == 3, "no books named: the regions asked for"
    body = inspect.getsource(oddsapi._classify)
    assert "bookmakers" in body and "BOOKS_PER_REGION" in body


def test_the_pacer_meters_markets_and_one_region():
    """The pacer's per-event figure is built from MARKETS, one region — true
    while the list is ten books at most, which the first test holds."""
    src = inspect.getsource(oddsbudget)
    assert "per MARKET per region" in src, "the module no longer states what it is billed on"
    i = src.index("per MARKET per region")
    assert "multiplies the event count" in src[i:i + 600]
    sig = inspect.signature(oddsbudget.affordable_events)
    assert "book" not in str(sig).lower(), sig


def test_every_book_we_ask_for_has_a_name_to_print():
    """A key with no title renders as a raw slug on a card — the failure
    that made "Moneyline · best" ship (see `likely`'s note on it)."""
    for key in oddsapi.DEFAULT_BOOKS:
        assert key in oddsapi.BOOK_TITLES, key
        assert oddsapi.BOOK_TITLES[key].strip(), key


def test_the_sharp_set_is_not_a_place_to_park_a_hunch():
    """`engine/booksharp` exists because "received wisdom about which
    book is sharp is the single most repeated claim in this industry and
    the least often checked". Naming a book sharp is a PRICING claim: it
    decides which number other prices are judged against, and
    `odds.is_sharp_book` also stops that book being quoted as the
    ticket. Growing this set belongs to a measurement, not to a commit
    message."""
    assert oddsapi.SHARP_BOOKS == {"pinnacle"}, (
        "a book was named sharp — if booksharp measured it, update this "
        "test and say which run; if not, that is the claim this guards")


def test_a_bettable_book_is_never_also_the_sharp_reference():
    """The two roles are exclusive by construction: the reference must
    never be quoted as the price to take, so anything in the sharp set
    that a reader could click would be a ticket nobody can buy."""
    from engine.odds import is_sharp_book
    bettable = [b for b in oddsapi.DEFAULT_BOOKS if b not in oddsapi.SHARP_BOOKS]
    assert len(bettable) >= 8, "fewer than eight books a reader can bet"
    for key in bettable:
        assert not is_sharp_book(key), key
    for key in oddsapi.SHARP_BOOKS:
        assert is_sharp_book(key), key


def test_the_reason_is_written_beside_the_list():
    """The comment above DEFAULT_BOOKS is what a future reader needs before
    adding an eleventh book "for free"."""
    src = inspect.getsource(oddsapi)
    i = src.index("DEFAULT_BOOKS = [")
    head = src[max(0, i - 3200):i]
    assert "TEN BOOKS, BECAUSE TEN IS ONE REGION'S PRICE" in head
    assert "Ethan, 2026-11-02" in head and "MIN_CONSENSUS_BOOKS" in head
    assert "test_ten_books_cost_one_region" in head


# --- the one-word change that would double the bill -------------------------
def test_every_paid_call_asks_for_exactly_one_region():
    """THE OTHER MOST EXPENSIVE WORD IN THE CODEBASE, guarded.

    REGIONS are the other half of `markets x regions`: a second region
    DOUBLES every call, for every sport, forever. Some books live in the
    API's `us2` region, and the obvious move to fetch one is to add `us2` —
    one word that turns a 100k month into a 200k one. (A call that names
    its books is billed for them instead; the first test holds that half.)
    """
    src = inspect.getsource(oddsapi)
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().strip().startswith("#"))
    asked = re.findall(r'"regions":\s*"([^"]+)"', code)
    assert asked, "no call asks for a region at all"
    for spec in asked:
        names = [r for r in spec.split(",") if r.strip()]
        assert names == ["us"], (
            f'a paid call asks for regions={spec!r}. Each extra region '
            f'MULTIPLIES the credit cost of that call — see this test. If '
            f'this is deliberate, budget it first and update the pin.')


def test_the_cost_rule_is_markets_times_regions_and_the_code_says_so():
    """`_classify` reads both off the URL actually sent rather than
    assuming. If it ever stops multiplying, the guards above protect a
    number that no longer drives the bill."""
    body = inspect.getsource(oddsapi._classify)
    assert "regions" in body and "markets" in body and "*" in body, body[:300]


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
