"""Every ranking we can legitimately read, one row per player.

Ethan, 2026-08-15: "add where we show every books ranking side by side".

WHAT "EVERY BOOK" CAN HONESTLY MEAN HERE, because the answer is smaller
than the question and pretending otherwise would be the whole failure.

Fantasy rankings are published by sites, not sportsbooks, and almost none
of them can be read the way an odds feed can:

  * FANTASYPROS is the obvious one — it IS a consensus of a hundred
    analysts — and its rankings are behind an API key with a paid tier,
    with scraping forbidden by its terms. Not readable.
  * ESPN, YAHOO and CBS publish rankings inside their fantasy products.
    Reading them means either a registered OAuth app (Yahoo) or session
    cookies pasted out of a logged-in browser (ESPN). This repo does not
    take credentials, and a session cookie is a credential.
  * NFL.com's fantasy API is effectively closed.

So this module ships the sources that are genuinely free, public and
already on disk, and is built as a REGISTRY so a new one is a function
rather than a rewrite:

  * OURS — the VORP board from `fantasy_draft.build_draft_kit`.
  * SLEEPER — `search_rank` from the players blob the site already
    downloads daily for rosters and injuries. It is Sleeper's own draft
    ordering, it costs no extra request, and millions of drafts are run
    off it.
  * ADP — the live pick order in YOUR draft, once picks start. National
    ADP is a guess about your league; this is your league.
  * IMPORTED — any list you can export yourself. Pasting a CSV you
    already have access to is not scraping, and it is the honest route to
    the sources above.

WHAT THE TABLE IS FOR, WHICH IS NOT THE RANKING. Four columns of roughly
the same order is wallpaper. The USE is the DISAGREEMENT: the player our
board has 30 spots above Sleeper's is either our edge or our bug, and
either way that row is the one worth looking at. `consensus` therefore
sorts by spread, not by rank.

A PLAYER MISSING FROM A SOURCE IS MISSING, NOT LAST. Scoring an absence
as rank 999 would make every rookie look like the biggest disagreement on
the board — rookies are absent from our board BY CONSTRUCTION, since it
is last season's usage run forward. Absences are None and are excluded
from the spread rather than counted as a hostile opinion.

Standard library only. No fetches — every source is handed in.
"""

from __future__ import annotations

import re
import unicodedata

#: Sources in the order the table shows them. `key` is what the payload
#: and the tests use; `label` is what the page prints.
SOURCES = (
    ("ours", "Our board"),
    ("sleeper", "Sleeper"),
    ("adp", "Your draft"),
    ("imported", "Imported"),
)

#: A player needs a rank from at least this many sources before a
#: disagreement between them means anything. One source disagreeing with
#: nothing is not a disagreement.
MIN_SOURCES = 2

#: Rows the table carries. Enough to scroll a draft board, short of the
#: 600-player tail nobody ranks.
TABLE_LIMIT = 200

_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")
_PUNCT = re.compile(r"[.'’`\-]")


def normalize(name: str) -> str:
    """Join key for a player name, matching the page's `ffNorm` exactly.

    The two must agree or the table silently half-populates: the browser
    matches Sleeper ids to names with `ffNorm`, and this file matches our
    board to the same names. `tests/test_fantasy_ranks.py` pins the pair
    against each other rather than trusting that they were written the
    same way twice.
    """
    s = str(name or "").lower()
    # Accents, exactly as the page does it: decompose, then drop the
    # combining marks. Without this "José" keys differently here than in
    # the browser and his row silently half-populates — one column filled
    # from our board, the other blank, looking like a source that never
    # ranked him.
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _PUNCT.sub(" ", s)
    s = _SUFFIX.sub("", s)
    return " ".join(s.split())


def squash(name: str) -> str:
    """A looser key: `normalize` with every space and mark removed.

    WHY A SECOND KEY. `normalize` matches the page exactly, which means it
    inherits the page's one weakness: an apostrophe becomes a SPACE, so
    "Ja'Marr Chase" keys as `ja marr chase` and "JaMarr Chase" keys as
    `jamarr chase`, and the two never meet. Between our sources that is
    harmless — they all spell him the same way — but an imported list is
    whatever some other site exported, and apostrophes are exactly what
    exports disagree about (Ja'Marr, JaMarr, De'Von, D'Andre, Amon-Ra).

    So the primary key stays page-compatible and this is the fallback used
    to fold two spellings onto one row. Changing `ffNorm` itself would
    touch the roster and injury joins that already depend on it, which is
    a much bigger blast radius than this table is worth.
    """
    return normalize(name).replace(" ", "")


def _canonical(sources: dict) -> dict:
    """``{key: canonical key}`` folding spellings that squash the same.

    Source order decides the winner, and it is the order in `SOURCES` —
    our board first — so the canonical spelling is the one the rest of the
    site already uses rather than whichever file was read first.
    """
    canon: dict = {}
    by_squash: dict = {}
    for src, _label in SOURCES:
        for key in (sources.get(src) or {}):
            sq = squash(key)
            if sq in by_squash:
                canon[key] = by_squash[sq]
            else:
                by_squash[sq] = key
                canon[key] = key
    return canon


def _fold(ranks: dict, canon: dict) -> dict:
    """Re-key one source's ranks onto the canonical spellings."""
    out: dict = {}
    for key, rank in (ranks or {}).items():
        out.setdefault(canon.get(key, key), rank)
    return out


# --- one source at a time ---------------------------------------------------
def from_board(kit: dict) -> dict:
    """Our VORP board → ``{normalized name: rank}``.

    Rank is position in the board, which is VORP order — not points. That
    is the whole argument of the draft kit and the reason this column can
    disagree usefully with a points-ordered list.
    """
    out: dict = {}
    for i, row in enumerate((kit or {}).get("board") or []):
        key = normalize(row.get("player"))
        if key and key not in out:
            out[key] = i + 1
    return out


def from_sleeper(players: dict, positions=("QB", "RB", "WR", "TE")) -> dict:
    """Sleeper's players blob → ``{normalized name: rank}`` by search_rank.

    `search_rank` is Sleeper's own ordering of every player, and it is the
    order their draft board shows by default. Absent or sentinel values
    (Sleeper uses a very large number for "unranked") are dropped rather
    than sorted to the end, because unranked is not rank 9,999,999.
    """
    rows = []
    for p in (players or {}).values():
        if not isinstance(p, dict):
            continue
        pos = (p.get("position") or "").upper()
        if positions and pos not in positions:
            continue
        # A RETIRED PLAYER KEEPS HIS SEARCH RANK. Sleeper does not tidy
        # `search_rank` when a career ends, so an inactive player can
        # still carry a draftable-looking number — and this ordering
        # feeds draftmarket.place_missing, which put Tom Brady BACK on
        # the 2026 board the moment the usage side dropped him. Explicit
        # false only: an absent flag keeps the row, the same
        # join-failure-never-erases rule the kit drop follows.
        if p.get("active") is False:
            continue
        rank = p.get("search_rank")
        if not isinstance(rank, (int, float)) or rank <= 0 or rank >= 100000:
            continue
        name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        key = normalize(name)
        if key:
            rows.append((float(rank), key))
    rows.sort()
    out: dict = {}
    for i, (_, key) in enumerate(rows):
        if key not in out:
            out[key] = i + 1
    return out


def from_picks(picks: list) -> dict:
    """A live draft's picks → ``{normalized name: pick number}``.

    THE ONLY ADP THAT IS ABOUT YOUR LEAGUE. A national average tells you
    what strangers did; this is what the eleven people you are actually
    drafting against have done, in order, tonight.

    Sleeper numbers picks from 1; where `pick_no` is missing the position
    in the list is used, which is the same thing for a complete feed.
    """
    out: dict = {}
    for i, p in enumerate(picks or []):
        meta = (p or {}).get("metadata") or {}
        name = " ".join(x for x in (meta.get("first_name"),
                                    meta.get("last_name")) if x)
        key = normalize(name)
        if not key or key in out:
            continue
        no = p.get("pick_no")
        out[key] = int(no) if isinstance(no, (int, float)) and no > 0 else i + 1
    return out


def parse_import(text: str) -> dict:
    """A pasted or CSV ranking → ``{normalized name: rank}``.

    THE ROUTE THAT DOES NOT NEED ANYONE'S PASSWORD. A list you can already
    see — a FantasyPros export, your league's own board, a friend's tiers
    — pasted in, is the honest way to get a source this repo cannot fetch.

    Deliberately forgiving about shape, because the point is that it
    accepts whatever the other site exported:

      * ``1,Ja'Marr Chase`` / ``1. Ja'Marr Chase`` / ``1 Ja'Marr Chase``
      * ``Ja'Marr Chase`` on its own — order in the file IS the rank
      * quoted CSV cells, a header row, blank lines and comments

    A leading number is trusted when present, because an export with gaps
    (a keeper list numbered 1, 2, 5) means those gaps.
    """
    out: dict = {}
    seen = 0
    for raw in str(text or "").splitlines():
        line = raw.strip().strip(",")
        if not line or line.startswith("#"):
            continue
        cells = [c.strip().strip('"').strip("'") for c in line.split(",")]
        cells = [c for c in cells if c]
        if not cells:
            continue
        rank = None
        head = cells[0]
        m = re.match(r"^(\d{1,3})[.)]?$", head)
        if m:
            rank = int(m.group(1))
            cells = cells[1:]
        else:
            m = re.match(r"^(\d{1,3})[.)]?\s+(.*)$", head)
            if m:
                rank = int(m.group(1))
                cells = [m.group(2)] + cells[1:]
        if not cells:
            continue
        name = cells[0]
        # A header row ("rank,player,team") has no digits and no space in
        # a name-shaped cell; cheapest reliable tell is that it normalizes
        # to a single known column word.
        if normalize(name) in ("player", "name", "rank", "overall"):
            continue
        key = normalize(name)
        if not key or key in out:
            continue
        seen += 1
        out[key] = rank if rank is not None else seen
    return out


# --- putting them beside each other -----------------------------------------
def _median(vals: list) -> float:
    v = sorted(vals)
    n = len(v)
    if not n:
        return 0.0
    mid = n // 2
    return float(v[mid]) if n % 2 else (v[mid - 1] + v[mid]) / 2.0


def consensus(sources: dict, limit: int = TABLE_LIMIT,
              names: dict | None = None) -> list[dict]:
    """``{source key: {name: rank}}`` → one row per player, side by side.

    Each row carries every source's rank (None where that source does not
    list him), the CONSENSUS (median of the ranks that exist), and the
    SPREAD between the highest and lowest opinion. Sorted by consensus so
    the table reads as a board; `disagreements` below re-sorts by spread,
    which is the view worth acting on.

    ``names`` maps the normalized key back to a display name — the sources
    only agree on the key, and whichever spelling arrived first would
    otherwise win by accident.
    """
    names = names or {}
    # Fold spellings that differ only in punctuation onto one row before
    # anything is compared — otherwise an imported "JaMarr Chase" becomes
    # a second row that every other source appears not to rank.
    canon = _canonical(sources or {})
    sources = {src: _fold(sources.get(src) or {}, canon)
               for src, _label in SOURCES}
    names = {canon.get(k, k): v for k, v in names.items()}
    keys: set = set()
    for ranks in sources.values():
        keys |= set(ranks or {})
    rows = []
    for key in keys:
        per = {}
        for src, _label in SOURCES:
            r = (sources.get(src) or {}).get(key)
            per[src] = int(r) if isinstance(r, (int, float)) else None
        have = [r for r in per.values() if r is not None]
        if not have:
            continue
        rows.append({
            "key": key,
            "player": names.get(key) or key.title(),
            "ranks": per,
            "sources": len(have),
            "consensus": round(_median(have), 1),
            "best": min(have),
            "worst": max(have),
            "spread": max(have) - min(have) if len(have) >= MIN_SOURCES else None,
        })
    rows.sort(key=lambda r: (r["consensus"], r["player"]))
    return rows[:limit]


def disagreements(rows: list[dict], limit: int = 20) -> list[dict]:
    """The rows where the sources argue most — the point of the table.

    Only players ranked by at least `MIN_SOURCES`, because a spread needs
    two opinions. Each row is labelled with WHO is high and WHO is low, so
    the reader can decide whose argument they believe rather than being
    handed an average that hides the fight.
    """
    out = []
    for r in rows:
        # A spread of zero is agreement, and naming a "high source" and a
        # "low source" for it prints an argument that is not happening.
        if not r.get("spread") or r["sources"] < MIN_SOURCES:
            continue
        per = {k: v for k, v in r["ranks"].items() if v is not None}
        high = min(per, key=lambda k: per[k])       # smallest rank = highest
        low = max(per, key=lambda k: per[k])
        out.append({**r, "high_source": high, "low_source": low})
    out.sort(key=lambda r: (-r["spread"], r["consensus"]))
    return out[:limit]


def coverage(sources: dict) -> list[dict]:
    """How many players each source ranks, and whether it is present.

    A column that is silently empty looks exactly like a source that
    ranks everyone the same as us. This is what lets the page say "Sleeper
    ranked 412, your draft has 0 so far, nothing imported" instead of
    drawing four columns and filling two.
    """
    return [{"key": key, "label": label,
             "players": len((sources or {}).get(key) or {}),
             "present": bool((sources or {}).get(key))}
            for key, label in SOURCES]


def build(kit: dict | None = None, players: dict | None = None,
          picks: list | None = None, imported: str | None = None,
          limit: int = TABLE_LIMIT) -> dict:
    """The whole side-by-side payload. Every argument is optional.

    Called with nothing it returns an honest empty table rather than
    raising — the page renders during an offseason build with no draft and
    no import, and that is a real state rather than an error.
    """
    sources = {
        "ours": from_board(kit or {}),
        "sleeper": from_sleeper(players or {}),
        "adp": from_picks(picks or []),
        "imported": parse_import(imported or ""),
    }
    names: dict = {}
    for row in (kit or {}).get("board") or []:
        key = normalize(row.get("player"))
        if key:
            names.setdefault(key, row.get("player"))
    for p in (players or {}).values():
        if not isinstance(p, dict):
            continue
        name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
        key = normalize(name)
        if key and name:
            names.setdefault(key, name)
    for p in picks or []:
        meta = (p or {}).get("metadata") or {}
        name = " ".join(x for x in (meta.get("first_name"),
                                    meta.get("last_name")) if x)
        key = normalize(name)
        if key and name:
            names.setdefault(key, name)
    rows = consensus(sources, limit=limit, names=names)
    return {
        "sources": coverage(sources),
        "rows": rows,
        "disagreements": disagreements(rows),
        "note": ("Ranks are compared only where a source actually lists the "
                 "player — an absence is blank, not last, or every rookie "
                 "would read as the board's biggest argument."),
    }
