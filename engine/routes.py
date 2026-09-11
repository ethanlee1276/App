"""Real addresses for the things this site already renders.

Ethan, 2026-08-25: *"Give the site places — entity pages and real URLs …
Static-friendly: these can all be rendered from the JSON you already
publish; server.py just needs routes."*

WHAT A CLEAN URL IS HERE
------------------------
`/player/juan-soto` is a **front door**, not a second router. The app
routes with the hash fragment and will keep doing so: one router, one
place where a view is chosen, and no risk of the two disagreeing about
what is on screen. What a clean path adds is the three things a hash
cannot do:

  * it survives being pasted into a text message, where a preview is
    fetched by a scraper that runs no JavaScript — so the OG tags have
    to be in the HTML the server hands back, per entity;
  * it can be typed and it can be indexed;
  * it names the entity rather than the app's internal id, so a link
    that outlives one rebuild still points at the same player.

So the server answers these paths with the ordinary app document, its
preview block swapped for this entity's, plus a `__QB_ROUTE__` hint that
tells the app which hash route to open. The app normalises the address
to that hash once it has booted. Nothing here re-implements a view.

THE GATE APPLIES TO PREVIEW TEXT, AND THAT IS THE ONE RULE TO NOT LOSE
----------------------------------------------------------------------
Every board here is read through `gate.board_source`, which means the
PRIVATE copy — the one that still has picks in it with the paywall on.
It has to be: the public copy has its picks stripped, so resolving
against it would make a permalink work for exactly the picks nobody
would pay for and 404 for the rest.

So this module can see the product, and must not print it. `pick_meta`
names the PLAYER, the MARKET and the MATCHUP — never the side, never the
line, never the projection, the edge, the price or the stake. A preview
card that reads "Juan Soto OVER 0.5 home runs, +11% edge" is the paid
board, published to anyone who can guess a slug, one row at a time. Nor
does the document carry the row: the app fetches the board through the
same entitled endpoint it always did, and a signed-out reader who opens
a pick link gets the locked state, exactly as if they had found the row
on the board itself.

Facts about who is playing whom are free everywhere else on this site;
the opinion is what is sold. That split is the whole gate, and it holds
here too.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from engine import gate

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

#: The sport boards, by the code the app uses for `state.sport`.
BOARD_FILES = {
    "nfl": "recommendations.json",
    "mlb": "mlb_recommendations.json",
    "nba": "nba.json",
    "wnba": "wnba.json",
    "cfb": "cfb.json",
}

#: Search order when a two-segment URL does not say which league it means.
#: `/player/juan-soto` is the shape Ethan asked for, and it carries no
#: sport — so the resolver looks through the boards in this order and
#: takes the first hit. In season the busiest league is first, which is
#: both the common case and the cheapest one.
SPORT_ORDER = ("mlb", "nfl", "cfb", "nba", "wnba")

SITE = "https://qellysbook.com"

#: Sections that get a real path. The value is the app's own view name
#: (or sport code), so this table cannot invent a destination that does
#: not exist — tests/test_routes.py checks every one of them against
#: VIEW_ORDER in app.js.
#:
#: Deliberately NOT every view. `#checkout`, `#paywall` and `#signup` are
#: steps inside a flow, not places, and a shareable link to somebody
#: else's half-finished checkout is a support ticket waiting to happen.
SECTIONS = {
    # sports — these switch the league and land on its board
    "mlb":  ("sport", "mlb", "MLB", "Tonight’s MLB board: player props priced against the book, with the projection and the form behind each one."),
    "nfl":  ("sport", "nfl", "NFL", "The NFL board: player props, game bets and long shots, each with the model’s number beside the price it was found at."),
    "nba":  ("sport", "nba", "NBA", "The NBA board: player props priced against the book, with the projection behind each one."),
    "wnba": ("sport", "wnba", "WNBA", "The WNBA board: player props priced against the book, with the projection behind each one."),
    "cfb":  ("sport", "cfb", "College football", "The college football board: player props, game bets and touchdown long shots."),
    "ufc":  ("view", "ufc", "UFC", "The fight card, the weigh-ins and what the model makes of each bout."),
    # sections
    "record":    ("view", "record", "Track record", "Every pick graded in public — wins, losses and closing-line value, with the sample size beside every number."),
    "live":      ("view", "live", "Live", "Tonight’s games as they happen, beside the picks that ride on them."),
    "tonight":   ("view", "tonight", "Tonight", "Everything on tonight’s slate in one place."),
    "streak":    ("view", "streak", "Streak", "The free daily streak game: pick the side, run the streak, no stake and no subscription."),
    "feed":      ("view", "alerts", "The feed", "What changed since the last rebuild: edges appearing and dying, lines moving, cards posted."),
    "scanner":   ("view", "scanner", "Scanner", "Stale prices, arbitrage and the book report card — where the market disagrees with itself."),
    "longshots": ("view", "longshots", "Long shots", "The big-price board: home runs, touchdowns and the players most likely to score whatever their price."),
    "futures":   ("view", "futures", "Futures", "Season-long markets priced against the model."),
    "injuries":  ("view", "injuries", "Injuries", "Every designation that moves a number, by league."),
    "weather":   ("view", "weather", "Weather", "Wind, rain and roof state for tonight’s games — and which totals they actually move."),
    "standings": ("view", "standings", "Standings", "League tables, kept current."),
    "rosters":   ("view", "rosters", "Rosters", "Who is on which roster, with depth and designation."),
    "players":   ("view", "players", "Players", "Search any player in any league we ingest: game logs, form windows and tonight’s priced markets."),
    "mybets":    ("view", "mybets", "My Bets", "Your journal — what you took, at what price, and how it settled."),
    "bankroll":  ("view", "bankroll", "Bankroll", "Stake sizing and the bankroll curve."),
    "lab":       ("view", "lab", "The lab", "What the model is made of, measured against itself."),
    "intel":     ("view", "intel", "Intel", "Prediction markets, book divergence and where the venues disagree."),
    "fantasy":   ("view", "fantasy", "Fantasy", "Draft kit, lineups, waivers and trades, built on the same usage data as the board."),
    "about":     ("view", "about", "About", "What this is, who builds it, and what it refuses to do."),
    "methodology": ("view", "methodology", "Methodology", "How every number on the board is made: the five steps, what is fitted against results, what is still an assumption, and what we deliberately do not model."),
    "status":    ("view", "status", "Status", "When each board last rebuilt, what the odds and lineup feeds are doing, and how long a full cycle takes."),
    # /changelog lands on the Methodology page, which carries it as a
    # section with that id. A log of what changed IS the methodology's
    # history, and a page of its own would be a page with one list on it.
    "changelog": ("view", "methodology", "Changelog", "What shipped, what was fixed, what was measured and refused — and the dates the model's own numbers changed."),
    "why":       ("view", "why", "Why us", "The argument for this model, with its own record as the evidence."),
}


# --- slugs -------------------------------------------------------------------

def slugify(text) -> str:
    """A URL segment from a name.

    Accents are folded rather than dropped — José Ramírez has to reach
    `jose-ramirez`, because that is what somebody typing his name into an
    address bar will produce, and a slug nobody can type is a slug nobody
    shares.
    """
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s


def game_slug(game: dict) -> str:
    """`ne-sea-0909` — away, home, month and day.

    The month and day are what stop a slug being ambiguous over a season:
    the same two teams meet again, and a link to the wrong meeting is a
    link to the wrong lineups, the wrong weather and the wrong prices.
    The YEAR is left off on purpose — it makes the address longer and no
    less unique inside a season, and a link that has aged past a year has
    aged past the board it points at anyway.
    """
    if not isinstance(game, dict):
        return ""
    away = slugify(game.get("away"))
    home = slugify(game.get("home"))
    date = str(game.get("date") or "")
    md = date[5:7] + date[8:10] if len(date) >= 10 else ""
    n = game.get("game_number") or 1
    if not away or not home:
        return ""
    out = f"{away}-{home}-{md}" if md else f"{away}-{home}"
    return f"{out}-g{n}" if int(n or 1) > 1 else out


def pick_slug(row: dict) -> str:
    """`juan-soto-home-runs` — the player and the market, and nothing else.

    THE SIDE AND THE LINE ARE DELIBERATELY ABSENT. They are the pick.
    Putting them in the address publishes the board in the share text
    itself, before anybody has clicked anything — the link would read
    `/pick/juan-soto-home-runs-over-0-5` in every group chat it is
    forwarded to. One row per player per market is what the boards
    actually build, so this identifies the pick without stating it.
    """
    if not isinstance(row, dict):
        return ""
    player = slugify(row.get("player"))
    market = slugify(row.get("market") or row.get("market_label"))
    if not player or not market:
        return ""
    return f"{player}-{market}"


# --- reading the published JSON ----------------------------------------------

def _load(path: Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _board(sport: str, web: Path = WEB) -> dict:
    """One sport's board, ALWAYS the private copy where there is one.

    One rule for the whole module rather than a judgement at each call
    site. `web/data/` has its picks stripped once the paywall is on, so
    reading it would make a pick permalink resolve for exactly the picks
    nobody would pay for and break for the rest — and it would drop a
    priced player out of `find_player` the day he became worth linking
    to. `gate.board_source` falls back to the public path when no
    private copy exists.

    The safety is therefore in what gets PRINTED, not in what gets read:
    see the module docstring, and `pick_meta` below.
    """
    name = BOARD_FILES.get(sport)
    if not name:
        return {}
    return _load(gate.board_source(Path(web) / "data" / name))


def _roster(sport: str, web: Path = WEB) -> dict:
    return _load(Path(web) / "data" / f"rosters_{sport}.json")


def find_player(slug: str, web: Path = WEB) -> dict | None:
    """Who this slug means, from the rosters and boards already published.

    The rosters are FREE files carrying every player in every league we
    ingest, which makes them the right source: a player page has to work
    for a bench bat nobody priced tonight, not only for whoever is on the
    board.
    """
    slug = slugify(slug)
    if not slug:
        return None
    for sport in SPORT_ORDER:
        board = _board(sport, web)
        for row in board.get("recommendations") or []:
            if isinstance(row, dict) and slugify(row.get("player")) == slug:
                return {"player": row.get("player"), "team": row.get("team"),
                        "position": row.get("position"), "sport": sport,
                        "opponent": row.get("opponent")}
        teams = (_roster(sport, web).get("teams") or {})
        for _abbr, block in teams.items():
            for p in (block or {}).get("players") or []:
                if slugify(p.get("player")) == slug:
                    return {"player": p.get("player"), "team": p.get("team"),
                            "position": p.get("position"), "sport": sport,
                            "opponent": ""}
    return None


def find_game(slug: str, web: Path = WEB) -> dict | None:
    slug = slugify(slug)
    if not slug:
        return None
    for sport in SPORT_ORDER:
        for g in _board(sport, web).get("games") or []:
            if isinstance(g, dict) and game_slug(g) == slug:
                out = dict(g)
                out["sport"] = sport
                return out
    return None


def find_pick(slug: str, web: Path = WEB) -> dict | None:
    """The row a pick permalink points at.

    Returns the whole row — the caller needs the matchup off it — and
    the only caller is `pick_meta`, which prints three fields of it.
    Nothing else in the repo calls this, and nothing else should: a
    second caller is a second place to leak the board.
    """
    slug = slugify(slug)
    if not slug:
        return None
    for sport in SPORT_ORDER:
        board = _board(sport, web)
        for key in ("recommendations", "long_shots", "longshot_watch"):
            for row in board.get(key) or []:
                if isinstance(row, dict) and pick_slug(row) == slug:
                    out = dict(row)
                    out["sport"] = sport
                    return out
    return None


# --- previews ----------------------------------------------------------------

def _title(text: str) -> str:
    return f"{text} · Qellys Book"


def player_meta(slug: str, web: Path = WEB) -> dict:
    who = find_player(slug, web)
    if not who:
        return {"title": _title("Player"),
                "description": "Game logs, form windows and tonight’s priced "
                               "markets for any player in any league we ingest.",
                "hash": f"player/{slugify(slug)}", "sport": ""}
    bits = [b for b in (who.get("position"), who.get("team")) if b]
    where = " · ".join(str(b) for b in bits)
    return {
        "title": _title(str(who.get("player") or "Player")),
        "description": (f"{who.get('player')}{' — ' + where if where else ''}. "
                        "Game logs, form windows and every market priced on "
                        "tonight’s board, with the model’s number beside the "
                        "book’s."),
        "hash": f"player/{who['sport']}/{slugify(who.get('player'))}",
        "sport": who["sport"],
    }


def game_meta(slug: str, web: Path = WEB) -> dict:
    g = find_game(slug, web)
    if not g:
        return {"title": _title("Game"),
                "description": "Lineups, weather, the park and every prop "
                               "priced on the game.",
                "hash": f"game/{slugify(slug)}", "sport": ""}
    label = f"{g.get('away')} at {g.get('home')}"
    when = str(g.get("date") or "")
    total = g.get("total")
    line = []
    if g.get("favorite") and g.get("spread") is not None:
        line.append(f"{g['favorite']} {g['spread']}")
    if total is not None:
        line.append(f"total {total}")
    return {
        "title": _title(label),
        "description": (f"{label}{', ' + when if when else ''}"
                        f"{' — ' + ', '.join(line) if line else ''}. "
                        "Lineups, weather, the venue and every prop priced "
                        "on the game."),
        "hash": f"game/{g['sport']}/{game_slug(g)}",
        "sport": g["sport"],
    }


def pick_meta(slug: str, web: Path = WEB) -> dict:
    """The preview for a pick permalink — WITHOUT the pick.

    Player, market, matchup. No side, no line, no price, no projection,
    no edge, no stake. See the module docstring: this function can see
    the paid board and its whole job is to describe it without quoting
    it. tests/test_routes.py holds the line by feeding it a row with
    every product field set and reading the output back.
    """
    row = find_pick(slug, web)
    if not row:
        return {"title": _title("A pick"),
                "description": "One pick from the board, with the game log, "
                               "the form ladder and the price it was found at.",
                "hash": f"pick/{slugify(slug)}", "sport": ""}
    who = str(row.get("player") or "")
    market = str(row.get("market_label") or row.get("market") or "").strip()
    opp = str(row.get("opponent") or "")
    matchup = f"{row.get('team')} vs {opp}" if opp else str(row.get("team") or "")
    return {
        "title": _title(f"{who} — {market}" if market else who),
        "description": (f"{who}{', ' + matchup if matchup else ''}: our "
                        f"{market.lower() if market else 'prop'} card, with the "
                        "game log, the form ladder and the price behind it."),
        "hash": f"pick/{row['sport']}/{pick_slug(row)}",
        "sport": row["sport"],
    }


def section_meta(name: str) -> dict:
    kind, target, label, desc = SECTIONS[name]
    return {
        "title": _title(label),
        "description": desc,
        "hash": target if kind == "sport" else target,
        "sport": target if kind == "sport" else "",
    }


def resolve(path: str, web: Path = WEB) -> dict | None:
    """A URL path → what to render, or None when this is not our route.

    None means "not a route", and the caller must fall through to the
    static handler — which is what serves the real files and the real
    404. A route that swallowed unknown paths would turn every typo into
    a soft landing on the board, which is the thing a 404 page exists to
    stop.
    """
    p = "/" + str(path or "").strip("/")
    if p == "/":
        return None
    segs = [s for s in p.strip("/").split("/") if s]
    if len(segs) == 1:
        name = segs[0].lower()
        if name in SECTIONS:
            out = section_meta(name)
            out["kind"] = "section"
            out["canonical"] = f"{SITE}/{name}"
            return out
        return None
    if len(segs) != 2:
        return None
    kind, slug = segs[0].lower(), segs[1]
    if kind == "player":
        out = player_meta(slug, web)
    elif kind == "game":
        out = game_meta(slug, web)
    elif kind == "pick":
        out = pick_meta(slug, web)
    else:
        return None
    out["kind"] = kind
    out["canonical"] = f"{SITE}/{kind}/{slugify(slug)}"
    return out


# --- the document ------------------------------------------------------------

#: The block in index.html this module rewrites, marked in the file
#: itself rather than matched by pattern. A regex over `<meta property=…>`
#: would quietly start matching a tag somebody adds later, and the first
#: sign of that is a share preview with the wrong title on it.
META_OPEN = "<!-- QB:META -->"
META_CLOSE = "<!-- /QB:META -->"


def _esc(text: str) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def meta_block(route: dict) -> str:
    """The head block for one entity: title, canonical, OG, Twitter.

    The IMAGE stays the site card. A per-entity image is roadmap item 6
    and needs a renderer; a wrong image is worse than a general one, and
    a missing one makes the link unfurl as a bare grey box.

    ITS URL IS ABSOLUTE HERE and relative in index.html, which is not
    the inconsistency it looks like. index.html is served at `/`, where
    a relative image keeps working from localhost and from a tailnet
    address with no second copy of the tag. These documents are served
    at two-segment paths, and a scraper is not a browser: most of them
    resolve a relative image against the page URL without reading the
    `<base>` tag, so `og-card-v2.png` at /player/juan-soto is fetched
    from /player/ and the link unfurls with no picture at all.
    """
    title = _esc(route.get("title") or "Qellys Book")
    desc = _esc(route.get("description") or "")
    url = _esc(route.get("canonical") or SITE)
    img = f"{SITE}/og-card-v2.png"
    return "\n".join([
        META_OPEN,
        f"  <title>{title}</title>",
        f'  <link rel="canonical" href="{url}" />',
        f'  <meta property="og:url" content="{url}" />',
        f'  <meta name="description" content="{desc}" />',
        '  <meta property="og:type" content="website" />',
        '  <meta property="og:site_name" content="Qellys Book" />',
        f'  <meta property="og:title" content="{title}" />',
        f'  <meta property="og:description" content="{desc}" />',
        f'  <meta property="og:image" content="{img}" />',
        '  <meta property="og:image:width" content="1200" />',
        '  <meta property="og:image:height" content="630" />',
        '  <meta property="og:image:alt" content="Qellys Book — the QB crown mark beside an overhead plan of Coors Field" />',
        '  <meta name="twitter:card" content="summary_large_image" />',
        f'  <meta name="twitter:title" content="{title}" />',
        f'  <meta name="twitter:description" content="{desc}" />',
        f'  <meta name="twitter:image" content="{img}" />',
        META_CLOSE,
    ])


def document(route: dict, index_html: str) -> str:
    """The app document with this entity's preview block in its head.

    One document, not a shell that redirects. A separate landing page
    would flash, would need its own copy of the styles to not look
    broken for the half-second it exists, and would break the back
    button — three costs for nothing, when the app is perfectly able to
    open the right view if it is simply told which one.
    """
    if META_OPEN in index_html and META_CLOSE in index_html:
        head = index_html.index(META_OPEN)
        tail = index_html.index(META_CLOSE) + len(META_CLOSE)
        index_html = index_html[:head] + meta_block(route) + index_html[tail:]
    hint = json.dumps({"hash": route.get("hash") or "",
                       "sport": route.get("sport") or "",
                       "kind": route.get("kind") or ""})
    # `</` escaped so the payload can never close the script element it
    # rides in — the one injection a JSON blob in a <script> still has.
    hint = hint.replace("</", "<\\/")
    tag = f'<script>window.__QB_ROUTE__ = {hint};</script>\n</head>'
    return index_html.replace("</head>", tag, 1)
