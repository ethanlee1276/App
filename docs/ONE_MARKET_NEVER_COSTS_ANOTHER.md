# One market never costs another

Ethan, 2026-09-14, after the Monday board showed one moneyline and no
props for the Chiefs game:

> Anytime we're working on the most likely bets or edge bets for NFL or
> any sport, I need you to make sure that issue we just ran into is not
> happening anymore. If I'm having an issue seeing a certain category of
> props, to make those props show you should not be affecting another
> category of props.

This is a standing rule. Work on one market — buying it, pricing it,
shelving it, fixing it — must leave every other market's rows exactly
where they were. The three places that rule was, or could be, broken are
listed with what now enforces each. `tests/test_market_independence.py`
pins all three; add to it before adding a fourth place.

## What happened

The passing-TD key went on the NFL request on the morning of 09-14. The
event odds cache file is named by the market list, so every NFL event's
payload was suddenly filed under a name no cached rebuild would look for.
The one fallback (the list without the ladders, from the 09-07 ladder
deploy) had changed too. Every prop fell to a proxy price; both NFL
boards refused all of them as "no real book price"; the moneyline
survived only because the game lines come from a separate pull. Fixing
one category of props blanked every other category for most of a day.

## The enforcement points

1. **The request.** A cached rebuild serves the newest payload on disk
   for the event under ANY name (`oddsapi.newest_event_cache`, counted as
   `name_fallback`), dated by that file's own age. A market joining or
   leaving the request can never hide the last paid pull's prices for the
   markets that did not change.

2. **A refused key.** `fetch_event_odds` drops a key the API refuses and
   retries the event without it, once per process (`REJECTED_MARKETS`).
   Every key bought on documentation rather than a returned call is in
   `UNPROVEN_MARKETS`, so a refusal that names nothing drops those and
   keeps the proven rest. One bad key costs one call, never the event.

3. **The board's seats.** `likely._cut_players` keeps each market's best
   `PER_MARKET` rows as seats no other market can take; `LIMIT` is the
   back-fill target, not a cap on them. It used to cut the kept rows back
   to `LIMIT` in probability order across markets, which never bound at
   five markets and would have taken passing yards' seats the day the
   sixth market joined.

## What is shared on purpose

The Edge board's exposure caps (`correlation.apply_exposure_caps`: 5u a
game, 15u a slate, one factor across every funded pick) are a bankroll
rule measured on 888 settled bets. A new market's picks do draw on the
same slate cap, and a pick scaled under the minimum stake comes off the
board. That is money, not display, and it stays as measured unless
Ethan says otherwise; it is named here so nobody mistakes it for the
rule above being broken.

## The check before touching any market

* Does the change alter the odds request? Then the cache name changes:
  confirm the newest-file fallback covers it (it does for any list).
* Is the key proven against the API from a returned call? If not, it
  goes in `UNPROVEN_MARKETS`.
* Does the market rank (`likely.rankable`) and have a shelf
  (`boards.SHELVES_BY_SPORT`)? A market that ranks without a shelf lands
  in "Other markets"; a shelf without a ranking stays empty by rule.
* Does the number of rankable markets times `PER_MARKET` exceed `LIMIT`?
  It may; the seats are per market and the test says so.
* Run `tests/test_market_independence.py` and the sport's ladder test.
