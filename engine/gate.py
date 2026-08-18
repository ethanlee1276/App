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

#: Where the FULL boards live: outside web/, so Caddy cannot route to them
#: even by accident. `web/data/` holds the redacted copies.
FULL_DIR = ROOT / "data" / "built"

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
    "market_scan",
    "correlation",
    "parlays",
    "edge_board",
    "futures",
)

#: Files that are paid in their entirety — no free half to preserve.
PAID_FILES = (
    "futures_cfb.json", "futures_mlb.json", "futures_nba.json",
    "futures_nfl.json", "backtest.json", "kalshi.json",
    # predmarkets.json is the SAME BOARD as kalshi.json under pm_build's
    # default --out, and it was nearly missed. Its picks live in `rows`,
    # which no entry in PAID_KEYS matches, so a board named this way would
    # have been published whole — the silent direction of the failure.
    # Named files are the safety net for exactly this: key-stripping only
    # protects boards whose keys were anticipated.
    "predmarkets.json",
)

#: …and the ones that must NEVER be touched, named rather than inferred.
#: `record.json` is the evidence the subscription is sold on. The rest is
#: what makes the site worth visiting when you have not paid: scores,
#: schedules, injuries, standings, rosters, the fantasy tools and the
#: meme-coin tracker.
FREE_FILES = (
    "record.json", "injuries.json", "fantasy.json", "memecoins.json",
    "ufc_live.json",
    # Schedule and scores for the five weeks of preseason. Free
    # because it is structurally priceless — board_payload()
    # refuses to put a number on a starter who plays a series and
    # a half, and keeping the fixture list free is what stops that
    # refusal reading as a paywall.
    "nfl_preseason.json",
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
    "rosters_cfb.json", "rosters_mlb.json", "rosters_nba.json",
    "rosters_nfl.json", "rosters_ufc.json", "rosters_wnba.json",
    "standings_cfb.json", "standings_mlb.json", "standings_nba.json",
    "standings_nfl.json", "standings_wnba.json",
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
    "record.json", "injuries.json", "fantasy.json", "memecoins.json",
    "ufc_live.json", "nfl_preseason.json", "live_mlb.json",
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


def is_free(name: str) -> bool:
    """True for a board that is published whole. Named files only — an
    unknown board is treated as gated, because the failure directions are
    not symmetric: wrongly gating a free board is a visible annoyance, and
    wrongly publishing a paid one gives the product away silently."""
    return Path(str(name)).name in FREE_FILES


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

    out, locked = {}, {}
    for key, value in payload.items():
        if key in PAID_KEYS:
            n = _size(value)
            if n:
                locked[key] = n
            # An empty list stays an empty list rather than becoming
            # locked: "0 picks tonight" is true and is not a paywall.
            out[key] = [] if isinstance(value, (list, tuple)) else {}
        else:
            out[key] = value
    if locked:
        out["locked"] = locked
        out["locked_reason"] = "subscription"
    return out


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
    FULL_DIR.mkdir(parents=True, exist_ok=True)
    full = FULL_DIR / label
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


def full_board(name: str) -> dict | None:
    """The subscriber's copy, read from outside the web root.

    Refuses anything that is not a bare filename. `name` arrives from a
    URL, and a path that can climb out of FULL_DIR turns an entitlement
    check into an arbitrary file read.
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
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None
