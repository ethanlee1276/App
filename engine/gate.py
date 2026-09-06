"""What is behind the paywall, and why it cannot be walked around.

Ethan, 2026-08-16: *"now we need to introduce the paywall for the site."*
Picks paid, the record free, $20 a month.

THE BYPASS THIS EXISTS TO PREVENT
---------------------------------
Caddy serves `web/data/*.json` straight off disk — that is the whole
reason the site is fast, and it means the app never sees those requests.
A paywall enforced in JavaScript would therefore be decorative: the first
thing anybody who wanted the picks for free would try is

    curl https://qellysbook.com/data/recommendations.json

…and they would have the entire board. Hiding a `<div>` does not hide a
file.

So the rule here is stronger than a check. **The file on the public path
IS the free version.** The build writes the redacted copy to `web/data/`
and the full copy to `data/built/`, which is outside the web root and
which Caddy has no route to. A curl against the public path returns
exactly what a signed-out visitor sees, because the paid fields were
never written there. The bypass cannot exist, rather than being guarded
against — there is no code path that leaks, because there is no copy to
leak.

Subscribers get the full board from `/api/board/<name>`, which is served
by the app, where the session cookie and the `subscriptions` row are
both in reach.

WHY FIELDS AND NOT FILES
------------------------
The obvious design — paid files, free files — does not survive contact
with the data. `recommendations.json` carries the free schedule (`games`,
`playoff_picture`, `fatigue`) in the same object as the paid picks
(`recommendations`, `game_bets`, `long_shots`, `market_scan`). Gating the
file would take tonight's slate down with the picks, and splitting every
build's output into two files would be a rewrite of eight pipelines.
Stripping keys is the smaller and more honest change.

WHAT A LOCKED BOARD SAYS
------------------------
`redact()` leaves a `locked` block behind: the name of each withheld
field and HOW MANY rows were in it. A visitor is told "14 picks behind
the subscription", not shown an empty page that looks like a slate with
nothing on it. This site's whole argument is that it does not misrepresent
its own output, and "no picks tonight" when there are fourteen would be
exactly that — with the added cost that an empty board is a worse
advertisement than a locked one.

THE RECORD IS NEVER REDACTED. It is the evidence the subscription is
sold on, and a proof nobody can read persuades nobody.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The served tree. `server.py` reads QB_WEB_DIR the same way and for the
#: same reason, and this follows it so the private half cannot be left
#: behind pointing at a different checkout.
#:
#: NOTHING IN PRODUCTION SETS IT — it is how the three server tests stand
#: a real server up on a temp copy of web/ — so with it unset this is
#: ROOT/web and the line below is exactly the constant it replaces.
_WEB = Path(os.environ.get("QB_WEB_DIR", "").strip() or (ROOT / "web"))

#: Where the FULL boards live: outside web/, so Caddy cannot route to them
#: even by accident. `web/data/` holds the redacted copies.
#:
#: A SIBLING OF THE SERVED TREE, not a fixed path under this checkout.
#: `seal` used to write here while READING a directory it was handed, so
#: a server told to serve a temp tree wrote that tree's private copies
#: into the developer's own `data/built/` — and `full_board` then read
#: them back out of it. The two ends cancelled, which is why it went
#: unnoticed, and they stop cancelling the moment a file is already
#: there: `seal` declines to overwrite an existing full copy, so
#: whichever fixture landed first stayed, and every later reader got it.
#: Found on this checkout, where `board_source("web/data/recommendations
#: .json")` returned a three-pick fixture from tests/test_paywall_bypass
#: instead of a board — the exact substitution `board_source` exists to
#: prevent, listed in its own docstring.
FULL_DIR = _WEB.parent / "data" / "built"

#: Fields that ARE the product. Present in the sport boards, stripped for
#: anyone without a live subscription.
#:
#: `market_scan` is here and it is worth saying why, because it looks like
#: raw market data rather than a pick: it is the arbitrage and middling
#: scan, which is a derived opinion about which prices are wrong. That is
#: the product under a different name.
PAID_KEYS = (
    "recommendations",
    "game_bets",
    "long_shots",
    "longshot_watch",
    # THE MAIN BOARD, which is the product under its own name — who we
    # think will actually hit. Ranked by likelihood rather than edge, and
    # every bit as much the thing somebody is paying for.
    "most_likely",
    # THE SAME BOARD UNDER A SECOND NAME, and it leaked. `board_shelves`
    # groups the likelihood rows by market for the page's layout, which
    # means it carries a COPY of every row `most_likely` holds — player,
    # market, price and probability. Stripping one and not the other
    # emptied the board a reader sees and handed the identical rows back
    # in the next key down.
    #
    # This is the third time this file has been taught the same lesson
    # (predmarkets, then UFC's `picks`/`pass_list`), and the comment
    # below already names it: key-stripping only protects boards whose
    # keys were anticipated. A new view of a paid board is a new key.
    "board_shelves",
    "market_scan",
    "correlation",
    "parlays",
    # THE PARLAY ZONE'S SECOND POOL, added the day the screen learned to
    # run over Most Likely as well (2026-09-06). `parlays` above and
    # `most_likely` twenty lines up are both paid; a screen over one,
    # published under a key nobody added here, would hand a paid board's
    # rows back for free in ticket form.
    #
    # THE FOURTH TIME THIS FILE HAS BEEN TAUGHT IT — predmarkets, UFC's
    # picks/pass_list, board_shelves, now this. The lesson each time is
    # the same one the comment above already states: a new VIEW of a paid
    # board is a new KEY, and key-stripping only protects the keys
    # somebody remembered.
    "likely_parlays",
    "edge_board",
    "futures",
    # UFC NAMES ITS PICKS DIFFERENTLY, AND THAT WAS A LIVE HOLE. Found
    # 2026-08-22 with QB_PAYWALL=1 on the box: engine/ufc/model.py returns
    # its board under `picks`, `pass_list` and `near_misses`, none of
    # which any entry above matched — so `curl /data/ufc.json` returned
    # every fighter, price and stake to anyone who asked.
    #
    # This is the failure PAID_FILES was added to catch for predmarkets
    # ("key-stripping only protects boards whose keys were anticipated"),
    # and UFC slipped through the same gap from the other side: it is not
    # wholly paid — the card, the weigh-ins and the fight order are free
    # facts — so only its pick keys can go.
    "picks",
    "pass_list",
    "near_misses",
    # MLB'S OWN NAMES FOR THE SAME TWO THINGS, found by looking for the
    # UFC hole's siblings. `near_miss` rows carry player, side, line,
    # odds, book, edge, hit_prob and grade — that is a pick with a
    # sentence about why it was not taken, which is still the product.
    # `priced_out` is worse: it is filtered straight out of
    # `recommendations`, so its rows ARE recommendation rows.
    "near_miss",
    "priced_out",
    # TONIGHT'S OPEN POSITIONS. Every row carries player, market, side,
    # line, the price we took and the stake — which is tonight's card
    # with "already placed" written on it, and worth exactly as much to
    # somebody who has not paid.
    #
    # It costs a free visitor nothing: renderLivePicks only runs inside
    # the main board render, and the main board is behind the wall
    # already, so the only reader losing these is a `curl` of the public
    # file. The Record page — settled picks, graded, in the past — is
    # untouched and stays free, because that is the evidence, not the
    # product.
    "live_picks",
)

#: PAID KEYS THAT BELONG TO ONE BOARD ONLY.
#:
#: `PAID_KEYS` above is applied to every mixed board, which is right for
#: `recommendations` and wrong for `coins`: the sport boards all speak
#: roughly the same vocabulary, and a global entry for an ordinary English
#: word would strip it off any future board that happened to use the name
#: for something harmless. So a board whose product has a board-specific
#: name declares it here instead.
#:
#: ADDED 2026-08-22, answering Ethan on his own audit output: *"remeber we
#: talked about there not being a free plan and only the 3 day trial with
#: full access. so why is it should free for all of that"*. The paywall
#: page sells "The full fantasy suite — draft kit, mock draft, lineups,
#: trades" and "the meme-coin scanner" as things you pay for, and both
#: boards were in FREE_FILES, published whole. That is not a free plan by
#: policy — it is two advertised features given away by omission, which is
#: worse, because nobody decided it.
#:
#: WHAT IS *NOT* HERE IS THE POINT. Neither board is wholly paid, because
#: most of what is in them is fact rather than opinion:
#:
#:   fantasy.json   free: `usage` (snap counts, target share, air yards —
#:                  ingested stats), `rates`, `schedule`, `camp`,
#:                  `trending` (Sleeper's own adds/drops), `season`.
#:                  paid: `draft_kit` and `ranks` (our board), `buy_sell`
#:                  (buy-low/sell-high — an opinion about a player's
#:                  price), `scripts` (game scripts, sold by name on the
#:                  paywall page).
#:
#:   memecoins.json free: `n`, `gated`, `risk_gate`, `notes`, `status` —
#:                  the counts, which make the locked state say "42
#:                  scored, 18 behind the risk gate" instead of nothing.
#:                  paid: `coins` (every coin with our momentum score,
#:                  risk score and exit signals) and the `rocket`/`exits`
#:                  lists, which are the scan's two answers.
PAID_KEYS_BY_FILE = {
    "fantasy.json": ("draft_kit", "ranks", "buy_sell", "scripts"),
    "memecoins.json": ("coins", "rocket", "exits"),
}


def paid_keys_for(name: str = "") -> tuple:
    """Every key that must be stripped from this board.

    Takes a bare file name; anything else gets the global tuple, which is
    the safe direction — a caller that has lost the name over-gates
    rather than under-gates.
    """
    return PAID_KEYS + PAID_KEYS_BY_FILE.get(Path(str(name or "")).name, ())


#: Files that are paid in their entirety — no free half to preserve.
PAID_FILES = (
    "futures_cfb.json", "futures_mlb.json", "futures_nba.json",
    "futures_nfl.json", "backtest.json", "kalshi.json",
    # The live feed: every entry names a pick — an edge appearing IS a
    # recommendation — so the whole file is the model's output.
    "feed.json",
    # The sweat page: every row is a journaled pick with a live model
    # number on it.
    "sweat.json",
    # predmarkets.json is the SAME BOARD as kalshi.json under pm_build's
    # default --out, and it was nearly missed. Its picks live in `rows`,
    # which no entry in PAID_KEYS matches, so a board named this way would
    # have been published whole — the silent direction of the failure.
    # Named files are the safety net for exactly this: key-stripping only
    # protects boards whose keys were anticipated.
    "predmarkets.json",
)

#: …and the ones that must NEVER be touched, named rather than inferred.
#:
#: THE TEST FOR THIS LIST IS "IS IT A FACT OR IS IT AN OPINION", not "is
#: it nice to have". Everything here is either something that happened
#: (a score, an injury designation, a roster move, a standing, a fixture
#: list) or something already graded and published as evidence. None of
#: it is the model's output, so none of it is what the subscription
#: sells, and gating it would only make the site useless to somebody
#: deciding whether to start the trial.
#:
#: `record.json` and `memerecord.json` are here for a stronger reason
#: than that: they ARE the pitch. "Every pick graded in public, wins and
#: losses" is the only claim this site makes that a stranger can check,
#: and the paywall page's own proof block reads from record.json. A proof
#: nobody can read persuades nobody.
#:
#: WHAT WAS REMOVED FROM THIS LIST, 2026-08-22. Ethan, reading a
#: `--paywall-audit` run: *"remeber we talked about there not being a
#: free plan and only the 3 day trial with full access. so why is it
#: should free for all of that"*. He was right about two of them —
#: `fantasy.json` and `memecoins.json` were published whole while the
#: paywall page sold "The full fantasy suite" and "the meme-coin
#: scanner" as things you pay for. Both are now MIXED_FILES: the facts
#: inside them (usage, rosters, schedule, the graded record) stay free
#: and the model's output inside them is stripped. See PAID_KEYS_BY_FILE.
FREE_FILES = (
    "record.json", "memerecord.json", "injuries.json",
    # League headlines — titles and links out to their publishers, no
    # model output in the file at all (engine/sources/news.py). Facts
    # and furniture, free like the injuries beside them.
    "news.json",
    # The refresher's liveness stamp: when the last cycle finished and
    # how long cycles take on this box. Every visitor's stale bar reads
    # it, signed in or not, so gating it would break the one line on the
    # page that tells a reader whether the numbers are current.
    "heartbeat.json",
    "ufc_live.json",
    # nfl_preseason.json LEFT this list 2026-08-25 with the rest of the
    # preseason surface (Ethan: "get rid of the pre season section for
    # nfl"). Nothing builds it now; maintenance's RETIRED_BOARDS removes
    # the stale copy from web/data. Deregistered rather than kept "just
    # in case": an unknown board is treated as gated, which is the safe
    # direction if a stray copy ever reappears.
    # The fast MLB scoreboard (live_build.py). Free for the same reason it
    # is fast: it is scores and game state only, no prices — a public fact
    # the gate has no reason to redact, and the one file that must NEVER
    # wait on entitlement checks or the model. Registered here AFTER the
    # first deploy failed on it: the builder shipped without this line, the
    # dev container never runs the fast loop so the suite stayed green, and
    # the droplet — where the loop had already written the file — refused
    # the deploy. A registry is only as good as the discipline of adding to
    # it in the same commit as the thing it registers.
    "live_mlb.json",
    # THE FOUR THE MLB LINE ABOVE WARNED ABOUT, and its warning came true
    # word for word: livescore_build.py shipped on 2026-09-04 without
    # these, the dev container never runs the fast loop so the suite
    # stayed green, and the droplet — where the loop had already written
    # all four — refused the deploy with "built but unregistered". Free
    # for the same reason as live_mlb.json: scores and game state only,
    # nothing priced (tests/test_live_scoreboards.py asserts that rather
    # than taking this sentence on trust). The same file now asserts
    # every league the builder writes is registered HERE, so the next
    # league added cannot repeat this without the sandbox suite saying so.
    "live_nfl.json", "live_cfb.json", "live_nba.json", "live_wnba.json",
    "rosters_cfb.json", "rosters_mlb.json", "rosters_nba.json",
    "rosters_nfl.json", "rosters_ufc.json", "rosters_wnba.json",
    "standings_cfb.json", "standings_mlb.json", "standings_nba.json",
    "standings_nfl.json", "standings_wnba.json",
    # The book report card (engine/booksharp.payload, written by the
    # daily chores). Facts about BOOKS — early-price error vs the close,
    # who moves first — with no pick, no line and no model probability
    # in it. Shareable content is the point (roadmap #7), and a report
    # nobody can read shares nothing.
    "bookreport.json",
    # The streak game's slate. Free BY DESIGN, not by omission — it is
    # the acquisition feature, the thing a stranger plays before the
    # trial. It can be free because it contains no model output at all:
    # engine/streak.py publishes player, market, line, lock time and the
    # graded result, selects by price balance rather than edge, and
    # never writes a side, a projection or an EV. A question is a fact.
    "streak.json",
)


#: EVERY board the pipelines can produce, whether or not this machine has
#: built one. The classification test used to read `web/data/*.json` — so it
#: only ever checked the boards the DEV container happened to have, and
#: passed while the live server carried two it had never seen
#: (nfl_preseason.json and predmarkets.json). Found by deploy.sh on the
#: droplet: the second time this session a check was only as good as the
#: data underneath it.
#:
#: Listed by hand on purpose. Adding a board to a pipeline and not to this
#: tuple should be a failing test, not a silent default.
KNOWN_BOARDS = (
    "recommendations.json", "mlb_recommendations.json", "nba.json",
    "wnba.json", "cfb.json", "ufc.json",
    "futures_cfb.json", "futures_mlb.json", "futures_nba.json",
    "futures_nfl.json", "backtest.json", "kalshi.json", "predmarkets.json",
    "record.json", "injuries.json", "news.json", "fantasy.json",
    "memecoins.json",
    # memes_build.py has written this since the meme ledger shipped and
    # nothing here had ever heard of it — the third time a pipeline grew
    # a board without telling the gate. Unregistered meant `is_free` said
    # no, so it went down the MIXED path, matched none of PAID_KEYS and
    # was published whole anyway. Right answer, reached by accident.
    "memerecord.json", "heartbeat.json", "feed.json", "sweat.json",
    "streak.json", "bookreport.json", "ufc_live.json", "live_mlb.json",
    "live_nfl.json", "live_cfb.json", "live_nba.json", "live_wnba.json",
    "rosters_cfb.json", "rosters_mlb.json", "rosters_nba.json",
    "rosters_nfl.json", "rosters_ufc.json", "rosters_wnba.json",
    "standings_cfb.json", "standings_mlb.json", "standings_nba.json",
    "standings_nfl.json", "standings_wnba.json",
)

#: Boards that are neither wholly free nor wholly paid: a free schedule and
#: paid picks in one object, handled by stripping keys rather than by name.
MIXED_FILES = (
    "recommendations.json", "mlb_recommendations.json", "nba.json",
    "wnba.json", "cfb.json", "ufc.json",
    # Not sports boards, same shape of problem: a feed's facts and the
    # model's read of them in one object. Their paid keys are named in
    # PAID_KEYS_BY_FILE rather than in PAID_KEYS, because `coins` and
    # `ranks` are ordinary words and a global entry would strip them off
    # any future board that happened to use the name.
    "fantasy.json", "memecoins.json",
)

#: The switch. OFF by default, and that default is the whole reason this
#: can be built while the site is live and free.
#:
#: Wired in one step, the paywall would go dark the moment it deployed —
#: for everybody, Ethan included, because there is no Paddle account yet
#: and therefore no account that CAN be entitled. A flag means the code
#: ships, is tested, sits inert, and is switched on later on a chosen day
#: with the processor live. Off, `publish()` writes the full board to both
#: paths and nothing about the site changes.
ENV_ENABLED = "QB_PAYWALL"

#: Accounts that are entitled without paying. Comma-separated emails.
#:
#: NOT A BACK DOOR — the alternative to it is worse. Without this the only
#: route to an entitled account is a completed Paddle checkout, which
#: means Ethan cannot see his own board, cannot comp a tester, and cannot
#: honour a refund without issuing one through the processor and waiting.
#: It reads from the environment rather than the database so that it
#: cannot be granted by anything reachable from the web.
ENV_COMP = "QB_COMP_EMAILS"


def enabled() -> bool:
    return os.environ.get(ENV_ENABLED, "").strip().lower() in ("1", "true", "yes")


def comped(email: str) -> bool:
    """True for an address on the comp list. Case- and space-insensitive,
    because the list is typed by hand into a file and `Ethan@…` and
    `ethan@…` are the same mailbox."""
    who = str(email or "").strip().lower()
    if not who:
        return False
    listed = {e.strip().lower()
              for e in os.environ.get(ENV_COMP, "").split(",") if e.strip()}
    return who in listed


#: DIRECTORIES whose every JSON file is free. One so far: `pbp/`, one
#: play-by-play file per live game, named by league and event id
#: (livescore_build.write_pbp, live_build). The names cannot be listed
#: in FREE_FILES — a new game is a new name every night — and the
#: contents are what live_*.json already publishes free, in full:
#: scores and plays, nothing priced. tests/test_pbp_files.py asserts
#: that the files carry no paid key rather than taking this on trust.
FREE_DIRS = ("pbp",)


def is_free(name: str) -> bool:
    """True for a board that is published whole. Named files only — an
    unknown board is treated as gated, because the failure directions are
    not symmetric: wrongly gating a free board is a visible annoyance, and
    wrongly publishing a paid one gives the product away silently.

    A file inside one of FREE_DIRS is free by its directory: those are
    per-game files whose names are not knowable in advance."""
    p = Path(str(name))
    if p.name in FREE_FILES:
        return True
    return p.suffix == ".json" and p.parent.name in FREE_DIRS


def is_wholly_paid(name: str) -> bool:
    return Path(str(name)).name in PAID_FILES


def _size(value) -> int:
    """How many rows were withheld. Dicts and lists both appear here."""
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return 1 if value not in (None, "", 0, False) else 0


def redact(payload: dict, name: str = "") -> dict:
    """The public copy of a board: same shape, picks removed, honest about it.

    Returns a NEW dict — the caller keeps the full one to write elsewhere,
    and a function that mutated its argument would silently poison the
    copy that goes to subscribers.
    """
    if not isinstance(payload, dict):
        return {}
    if name and is_free(name):
        return dict(payload)

    if name and is_wholly_paid(name):
        # Nothing to keep. The shape is still returned so the page can
        # render its locked state rather than fail to parse.
        kept = {k: payload[k] for k in
                ("generated_at", "date", "sport", "built_at") if k in payload}
        kept["locked"] = {"whole_board": _size(payload)}
        kept["locked_reason"] = "subscription"
        return kept

    locked: dict = {}
    out = _strip(payload, paid_keys_for(name), locked)
    if locked:
        out["locked"] = locked
        out["locked_reason"] = "subscription"
    return out


def _strip(node: dict, paid, locked: dict, path: str = "") -> dict:
    """One level of the board, paid keys emptied — then the same again
    for every dict inside it.

    AT EVERY DEPTH, NOT JUST THE TOP, and that is the repair. This walk
    used to be a single `for key, value in payload.items()` loop, so a
    paid board tucked inside a non-paid container was not a paid key as
    far as it was concerned — it was a value of a free one, copied
    across whole.

    Measured 2026-09-03 on the college board: `cfb_build` publishes
    `out["cfb"] = {"near_misses": …, "pass_list": …}`, and both of those
    names ARE in PAID_KEYS. Stripped at the top, shipped in full one
    level down — twenty refused game markets with the price, the edge,
    the book and the model's number on each, sitting in the public
    `web/data/cfb.json` that every phone polls. The same keys at the top
    of the same file were correctly emptied, which is what made it
    invisible: the board looked locked.

    This is the fourth time this module has been taught the same lesson
    (predmarkets, UFC's `picks`/`pass_list`, `board_shelves`, now a
    nested container), and the comment above PAID_KEYS has named the
    cause each time — "key-stripping only protects boards whose keys
    were anticipated". Anticipating a KEY is still required; anticipating
    WHERE IN THE TREE it sits no longer is.

    DICTS ONLY, deliberately. Recursing into lists would descend into the
    rows of free keys — `games`, `team_recent`, `player_stats` — and
    empty any field that happened to share a name with a paid board,
    which is over-reach dressed as safety. A paid board is a named
    container, and named containers are dicts.

    Nested strips are reported in `locked` under a dotted path
    ("cfb.pass_list") so the honest count of what is behind the paywall
    stays honest. Top-level keys keep their bare names, which is what
    every reader of that map already expects — and every one of them
    only tests it for truthiness.
    """
    out: dict = {}
    for key, value in node.items():
        where = f"{path}.{key}" if path else key
        if key in paid:
            n = _size(value)
            if n:
                locked[where] = n
            # An empty list stays an empty list rather than becoming
            # locked: "0 picks tonight" is true and is not a paywall.
            out[key] = [] if isinstance(value, (list, tuple)) else {}
        elif isinstance(value, dict) and not _is_disclosure(key, path):
            out[key] = _strip(value, paid, locked, where)
        else:
            out[key] = value
    return out


def _is_disclosure(key: str, path: str) -> bool:
    """The `locked` block at the top of a sealed board.

    NOT BOARD CONTENT — bookkeeping ABOUT the board, `{"game_bets": 2}`,
    whose keys are deliberately the paid key names. `seal()` promises it
    is "safe at any time, safe twice", so a sealed board goes back
    through here; walking into this block would read those names as paid
    keys and empty a disclosure that is the whole point of the file, then
    re-report it as `locked.game_bets`.

    `_paid_rows` learned the same thing the hard way and its docstring
    records the hour it cost on 2026-08-20 — counted from the paid keys
    themselves and never from `locked`, "so a correctly sealed file reads
    as still leaking". Recursion is a new way to walk into it, so the
    rule is written down here rather than left implicit in a loop that
    happened not to descend.
    """
    return not path and key == "locked"


def publish(payload: dict, public_path, name: str = "") -> tuple[str, str]:
    """Write both copies. Returns (public_path, full_path).

    THE ORDER MATTERS. The full copy is written first, to a directory the
    web server cannot reach; the redacted copy goes to the public path
    last. Written the other way round, a crash between the two writes
    leaves the FULL board sitting on the public path — the exact failure
    this module exists to prevent, arriving through the back door.
    """
    public = Path(public_path)
    label = name or public.name
    built = _full_dir_for(public)
    built.mkdir(parents=True, exist_ok=True)
    full = built / label
    # Atomic on both copies (tmp + replace, same directory so the rename
    # cannot cross filesystems). The public file is what every phone polls
    # on a 15-30s clock while the refresher rewrites it every cycle — an
    # in-place write hands a poll that lands mid-write a truncated board,
    # which renders as a JSON error until the next cycle. The same lesson
    # the meme board's 20s loop and _save_profile already carry; the slow
    # loop was the one writer left telling itself it was too slow to race.
    for path, doc in ((full, payload),
                      (public, None)):
        if path is public:
            public.parent.mkdir(parents=True, exist_ok=True)
            # Paywall off: the public copy IS the full board, exactly as
            # it was before any of this existed. The full copy is still
            # written, so switching the flag on needs no rebuild — the
            # subscriber path is already populated and correct.
            doc = redact(payload, label) if enabled() else payload
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w") as fh:
            json.dump(doc, fh, indent=2)
        os.replace(tmp, path)
    return (str(public), str(full))


def _paid_rows(payload: dict, name: str) -> int:
    """How many PAID rows this payload actually still exposes.

    Counted from the paid keys themselves, NOT from the `locked` block.
    That distinction cost an hour on 2026-08-20: `locked` is a disclosure
    ("3 picks were withheld") and `redact` copies it through like any
    other key, so re-redacting an already-sealed board hands back the old
    counts and a correctly sealed file reads as still leaking.
    """
    if is_free(name):
        return 0
    if is_wholly_paid(name):
        # Sealed copies keep only the stamps plus the locked block.
        return 0 if payload.get("locked_reason") else _size(payload)
    return _count_paid(payload, paid_keys_for(name))


def _count_paid(node: dict, paid, path: str = "") -> int:
    """Paid rows at every depth — the same tree `_strip` walks.

    IT HAS TO MATCH THE STRIPPER OR IT IS WORSE THAN NOTHING. This is the
    detector behind `unsealed()`, whose docstring says "with the paywall
    on this must be empty. If it is not, the product is public and nobody
    has noticed." It counted the top level only, so the nested college
    pass list `_strip` now catches was invisible to it too: the board
    leaked twenty priced rows and this said zero.

    That is the same shape as the board lint reading the stripped public
    copy and reporting it clean (2026-09-03) — a tool whose whole job is
    to say something is wrong, answering about a different thing.
    """
    n = 0
    for key, value in node.items():
        if key in paid:
            n += _size(value)
        elif isinstance(value, dict) and not _is_disclosure(key, path):
            n += _count_paid(value, paid, f"{path}.{key}" if path else key)
    return n


def seal(web_data=None, verbose=True) -> dict:
    """Strip the paid rows out of every board ALREADY on the public path.

    THE HOLE THIS CLOSES, found 2026-08-20 by running the real server with
    QB_PAYWALL=1 and curling the picks file: it returned all 293
    recommendations. Redaction happens inside `publish()`, so turning the
    flag on does not touch one file already written — it only changes what
    the NEXT build writes. Between the flag going on and every board being
    rebuilt, the paid product sits on the public path, and any board whose
    build fails keeps its full copy there indefinitely.

    On the droplet a restart runs `refresh_all()` and most boards do get
    rewritten, which is why this was invisible: the site mostly seals
    itself by accident. "Mostly" and "by accident" are not a paywall.

    IT STRIPS, IT DOES NOT REPUBLISH. An earlier cut of this preferred the
    private copy in data/built/ as the source, which is wrong twice over:
    it changes WHICH board is public (a stale private copy would go live),
    and `publish()` writes its input to data/built/ as the full copy — so
    handing it an already-stripped board destroys the subscribers' data in
    the name of protecting it. This reads the public file, keeps a full
    copy if none exists yet, and writes the stripped version back. Safe at
    any time, safe twice, and it can only ever remove rows.
    """
    root = Path(web_data) if web_data else (ROOT / "web" / "data")
    out = {"sealed": [], "skipped": [], "free": [], "already": []}
    if not enabled():
        out["off"] = True
        return out
    for path in sorted(root.glob("*.json")):
        name = path.name
        if is_free(name):
            out["free"].append(name)
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            out["skipped"].append(name)
            continue
        if not isinstance(payload, dict):
            out["skipped"].append(name)
            continue
        exposed = _paid_rows(payload, name)
        if not exposed:
            out["already"].append(name)
            continue
        # Keep the full copy the subscriber endpoint reads, but never
        # overwrite one that is already there — it may be fresher than
        # this public file, and it is the only surviving full board.
        # ROOT-RELATIVE, the same way `publish` and `board_source`
        # resolve it, so a seal against a tree that is not this checkout
        # keeps that tree's private copies beside it.
        built = _full_dir_for(path)
        built.mkdir(parents=True, exist_ok=True)
        full_path = built / name
        if not full_path.is_file():
            tmp = full_path.with_suffix(full_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, full_path)
        stripped = redact(payload, name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(stripped))
        os.replace(tmp, path)
        out["sealed"].append({"board": name, "withheld": exposed})
        if verbose:
            print(f"  sealed {name} — {exposed} paid row(s) removed")
    return out


def unsealed(web_data=None) -> list:
    """Boards on the public path that STILL carry paid rows.

    With the paywall on this must be empty. If it is not, the product is
    public and nobody has noticed.
    """
    root = Path(web_data) if web_data else (ROOT / "web" / "data")
    bad = []
    for path in sorted(root.glob("*.json")):
        name = path.name
        if is_free(name):
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        n = _paid_rows(payload, name)
        if n:
            bad.append({"board": name, "rows": n})
    return bad


#: Fields that only ever appear on a row carrying OUR OPINION of a
#: market. A stake is the obvious one; the model's own probability and
#: its disagreement with the price are the same product with the bet
#: size left off.
#:
#: THE FIRST CUT OF THIS LOOKED ONLY FOR A STAKE, and it missed
#: `near_miss` — ten props a night with player, side, line, book price,
#: edge and hit probability, and no stake because we did not bet them.
#: A reader does not need our stake to use our number.
_PRODUCT_FIELDS = ("stake_units", "stake_fraction", "units", "stake",
                   "edge", "hit_prob", "ev")


def _looks_staked(value) -> bool:
    """Is this a list of rows carrying our opinion of a market?"""
    if not isinstance(value, list) or not value:
        return False
    for row in value[:8]:
        if isinstance(row, dict) and any(f in row for f in _PRODUCT_FIELDS):
            return True
    return False


def leaks(payload: dict, name: str) -> list:
    """Keys on this board that carry staked rows and are NOT gated.

    THE HOLE THIS EXISTS TO FIND, live on 2026-08-22 with the paywall on:
    engine/ufc/model.py returns its board under `picks`, and no entry in
    PAID_KEYS matched, so `curl /data/ufc.json` handed every fighter,
    price and stake to anybody. Key-stripping only protects boards whose
    keys somebody anticipated, and the next board will name its rows
    something else again.

    So this asks a question that does not depend on the name: does this
    list contain rows with a STAKE on them? If it does and the key is not
    paid, that is the paid product on the public path.

    Returns [] for a wholly-paid or free file — the first keeps nothing
    and the second is a deliberate decision, not an oversight.
    """
    if not isinstance(payload, dict) or is_free(name) or is_wholly_paid(name):
        return []
    paid = paid_keys_for(name)
    return sorted(k for k, v in payload.items()
                  if k not in paid and _looks_staked(v))


def full_board_file(name: str) -> "Path | None":
    """The file a board name refers to, or None if it refers to no file.

    THE WHOLE SECURITY CHECK, in one place, because there are now two
    callers: `full_board` below and the byte cache in server.py. `name`
    arrives from a URL, and a path that can climb out of FULL_DIR turns
    an entitlement check into an arbitrary file read — so a second copy
    of this is a second place for that to be got wrong.
    """
    label = str(name or "")
    if not label.endswith(".json") or Path(label).name != label:
        return None
    if label.startswith("."):
        return None
    path = FULL_DIR / label
    try:
        # Resolve and re-check: a symlink inside FULL_DIR would otherwise
        # still point wherever it liked.
        if path.resolve().parent != FULL_DIR.resolve():
            return None
    except OSError:
        return None
    return path


def _full_dir_for(public_path) -> "Path":
    """Where THIS board's private copy belongs, given its public path.

    ROOT-RELATIVE, not global, and used by both the writer and the
    reader so the two cannot drift. `arbitrate_slate` takes a root
    precisely so it can run against a tree that is not this checkout,
    and the first cut of `board_source` jumped straight to FULL_DIR — so
    a caller working in a temp tree read THIS machine's real boards
    instead of its own, which is how that function's own test failed.

    In production the answer is identical: ROOT/web/data resolves to
    ROOT/data/built, which is FULL_DIR. Anything not shaped like
    `<root>/web/data/` falls back to FULL_DIR, because there is no tree
    to be relative to.
    """
    parent = Path(public_path).parent
    parts = parent.parts
    if len(parts) >= 2 and parts[-2:] == ("web", "data"):
        return Path(*parts[:-2]) / "data" / "built"
    return FULL_DIR


def board_source(public_path) -> "Path":
    """The file to READ a board from, given where its public copy lives.

    THE MISTAKE THIS EXISTS TO STOP MAKING, three times over. Every
    internal tool that wants a board's picks was opening `web/data/` —
    which, with the paywall on, is the copy with the picks taken out.
    Not one of them raised: they all read an empty list and reported
    honestly on nothing.

      engine/parlays.arbitrate_slate  §10.2 caps the operation at one
                                      parlay per slate across all sports.
                                      `parlays` is a paid key, so every
                                      board looked parlay-less and the cap
                                      was silently not enforced at all.
      parlaycheck.py                  printed "every published ticket is
                                      internally consistent" having found
                                      no tickets to check.
      launch.py --odds-doctor         counted priced games off the public
                                      copy and reported 0 of 15.

    The private copy is the truth; the public one is a derived artifact.
    Falls back to the public path when there is no private copy — a board
    built before data/built/ existed, or a machine with the paywall off
    that has never called publish().
    """
    public = Path(public_path)
    if full_board_file(public.name) is None:
        return public                        # not a name we will resolve
    full = _full_dir_for(public) / public.name
    return full if full.is_file() else public


def full_board(name: str) -> dict | None:
    """The subscriber's copy, read from outside the web root."""
    path = full_board_file(name)
    if path is None:
        return None
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None
