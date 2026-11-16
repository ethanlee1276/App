"""Every bet a game report posts, in one list, and its own book on the record
(2026-11-16).

Ethan, 2026-11-16: "all bets and parlays made from the game reports should be
categorized as 'report' bets under each sport on the record page and also we
should have a page like the most likely bets page but all game report parlays
and bets."

A report posts its bets in three places, each graded on a finished game's page
already (engine/gameresults): its picks card ("Our picks for this game"), its
matchup reads' picks, and its breakout candidates' and fades' picks. Its
parlays are the game's three-leg tickets and scorer pairs (engine/gameparlays),
on the record since 14 November (engine/parlayledger, `two_leg.game`).

`bets_of(sections, rows)` reads the bets a finished report shows, each matched
to the board row it came from (its price, its book, our chance) and tagged with
where the report shows it (SOURCES). gamereport.finish keeps them on the report
under PRIVATE, and `attach(result)` lifts them onto the board as KEY, each pick
once a game, paid as the picks are (engine/gate.PAID_KEYS). The Report Picks
page lists them game by game beside the game's parlays (js/reportpicks.js).
`journal(conn, board, sport)` writes them to the record under CATEGORY the way
the Most Likely book is written (ledger.log_most_likely: one row a pick, a flat
0.1 unit, the chance the page showed, never a game under way, never a pick
without a real price), from the pass that journals every board's parlays
(parlayledger.journal_built_boards).

A LENS ON PICKS OTHER BOOKS HOLD. A card pick is a Most Likely pick too, so
this book is shown on its own (the Record page's Report section, with the
reports' parlays beside it) and is in no headline, no chip count and no other
book's total: ledger.RECOMMENDED_CATEGORIES leaves it out.
"""
from __future__ import annotations

KEY = "report_bets"
CATEGORY = "report"
#: Where a report shows a pick, in the order a reader meets them.
SOURCES = ("card", "read", "breakout", "fade")
#: Each one in the report's own words.
SOURCE_WORDS = {"card": "Our picks", "read": "Matchup read", "breakout": "Breakout candidate",
                "fade": "Fade"}
#: The key a finished report carries its bets under until `attach` lifts them.
PRIVATE = "_bets"
#: What a row keeps: what the page shows and what the record journals.
FIELDS = ("player", "team", "opponent", "market", "market_label", "bet_type", "side", "line", "odds",
          "book", "model_prob", "kind", "matchup", "home", "away", "game_date", "position", "headshot",
          "tier_label", "lane")


def key(b: dict) -> tuple:
    """A pick as the page grades it (engine/gameresults.bet_of): who, which
    club, the market, the side and the line."""
    from .gameresults import norm
    line = (b or {}).get("line")
    try:
        line = None if line in (None, "") else round(float(line), 2)
    except (TypeError, ValueError):
        line = None
    return (norm((b or {}).get("player") or ""), str((b or {}).get("team") or ""),
            str((b or {}).get("market") or "").lower(), str((b or {}).get("side") or "").lower(), line)


def pool(card_rows, reads) -> dict:
    """{key: board row} for every pick a report can show: its card's rows,
    then each read's Most Likely pick and matchup pick, with the read's name,
    club, face and position under them where the pick leaves them off."""
    from .gameresults import bet_of
    out: dict = {}

    def put(row):
        b = bet_of(row)
        if b:
            out.setdefault(key(b), row)
    for r in card_rows or []:
        if isinstance(r, dict):
            put(r)
    for r in reads or []:
        if not isinstance(r, dict):
            continue
        for k in ("pick", "matchup_pick"):
            p = r.get(k)
            if isinstance(p, dict) and p:
                put(dict(p, player=p.get("player") or r.get("player"), team=p.get("team") or r.get("team"),
                         headshot=p.get("headshot") or r.get("headshot"),
                         position=p.get("position") or r.get("pos")))
    return out


def source_of(section_key: str, item: dict) -> str:
    """Where the report shows a pick: its card, a breakout candidate's or a
    fade's case (engine/breakouts.card: "up", "down"), else a matchup read."""
    if section_key == "card":
        return "card"
    v = str((item or {}).get("verdict") or "")
    return "breakout" if v == "up" else "fade" if v == "down" else "read"


def bets_of(sections, rows: dict | None = None) -> list:
    """Every bet a finished report shows, once each, in the order it shows
    them: the board row it came from (else the bet itself) and ``sources``,
    each place the report shows it. A bet with no price stays on the list,
    the page shows it, and the record passes it by."""
    rows = rows or {}
    seen: dict = {}
    for s in sections or []:
        if not isinstance(s, dict):
            continue
        for blk in s.get("blocks") or []:
            if not isinstance(blk, dict):
                continue
            for it in blk.get("items") or []:
                b = it.get("bet") if isinstance(it, dict) else None
                if not isinstance(b, dict) or not b.get("market"):
                    continue
                k, src = key(b), source_of(s.get("key"), it)
                if k in seen:
                    if src not in seen[k]["sources"]:
                        seen[k]["sources"].append(src)
                    continue
                row = rows.get(k) or b
                out = {f: row[f] for f in FIELDS if row.get(f) not in (None, "")}
                for f in ("player", "team", "market", "side", "line"):
                    if f not in out and b.get(f) not in (None, ""):
                        out[f] = b[f]
                if b.get("game"):
                    # A game bet: the record keys it off its club (ledger.game_row_keys).
                    out["kind"] = "game"
                out["sources"] = [src]
                seen[k] = out
    return list(seen.values())


def attach(result: dict) -> int:
    """KEY on the board: every report's bets (PRIVATE, lifted off each report
    so the reports carry them no more), each with its game, each pick once a
    game. Returns how many; a board with none carries no KEY."""
    if not isinstance(result, dict):
        return 0
    out = []
    for r in result.get("game_reports") or []:
        if not isinstance(r, dict):
            continue
        bets = r.pop(PRIVATE, None) or []
        for b in bets:
            if isinstance(b, dict):
                out.append(dict(b, game=r.get("game") or f"{r.get('away')}@{r.get('home')}",
                                home=b.get("home") or r.get("home"), away=b.get("away") or r.get("away")))
    if out:
        result[KEY] = out
    else:
        result.pop(KEY, None)
    return len(out)


def journal(conn, board: dict, sport: str) -> int:
    """Every report bet on the board, journaled under CATEGORY the Most Likely
    way (ledger.log_most_likely: a pick already in the book is not written
    twice, a game under way is passed by, a pick needs a real price). The
    board's private copy is the one read (engine/gate: KEY is paid). Returns
    rows written."""
    rows = [b for b in (board or {}).get(KEY) or [] if isinstance(b, dict)]
    if not rows or not sport:
        return 0
    from . import ledger
    return ledger.log_most_likely(conn, {"sport": sport, "date": board.get("date") or "",
                                         "games": board.get("games") or [], "most_likely": rows},
                                  depth=None, category=CATEGORY, grade_label="Report pick")
