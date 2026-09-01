"""One search box, every source.

Ethan, 2026-08-23: "i want the search bar to be to search any player in
every leauge" — and, an hour later, "im not able to search ufc players."

The second is not the first with one more league added to a list. Four
leagues live in ``player_game_logs`` (engine/statlogs.py) and are found by
a SQL LIKE; fighters live in ``data/ufc_dossiers.json`` (engine/ufc/
fighters.py) and are found by reading a file. Different stores, different
readers, one answer — and this is where the answer gets assembled, so
neither reader has to know the other exists.

RANKED BY ROUND-ROBIN, NOT BY ONE BIG SORT. Every source ranks its own
hits by whatever means something to it — the log search uses
``season || '-' || period``, which is a zero-padded NFL week ('005') in
one league and an ISO date in another, and neither of those means
anything against a fighter's UFC-fight count. There is no honest way to
sort them against each other, so nothing tries: one hit is taken from
each source in turn. That needs no cross-source comparison at all, and it
guarantees every league a place in a short list rather than letting
whichever format sorts highest take the lot.

Names that START with the query go round first. ``prefer`` — the tab the
visitor is standing on — only decides who goes first within a tier. It
never removes anyone, which is the entire point of the change.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

#: Every source this box covers, in the order a tie is broken. The log
#: leagues come from statlogs; ufc is its own reader.
SOURCES = ("nfl", "mlb", "nba", "wnba", "cfb", "ufc")


def norm(s: str) -> str:
    """A name reduced to what a person is actually typing at it.

    Ethan, 2026-08-23: "if you dont type the players name in exactly, they
    dont come up at all which makes it feel broken."

    He is right, and the first cause is not typos — it is that the stored
    spelling carries things nobody types. "Kauê Fernandes" is on his own
    droplet right now and a search for "Kaue" could never find him,
    because `LIKE '%kaue%'` does not match a circumflex. Same for the
    period in "St. Brown", the hyphen in "Amon-Ra", the apostrophe in
    "O'Neal". Strip the accents, drop the punctuation, and both sides of
    the comparison are the letters a keyboard produces.
    """
    t = unicodedata.normalize("NFKD", str(s or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


#: Below this many letters a fuzzy match is a guess, not a correction:
#: at three characters half the league is within one edit.
FUZZ_MIN = 4
#: How close a whole name, and a single word of one, has to be. Tuned on
#: real misses: "jugde"/"judge" is 0.80, "mahomez"/"mahomes" is 0.86.
FUZZ_WHOLE = 0.72
FUZZ_TOKEN = 0.78


def _tokens_prefix(toks, qt) -> bool:
    """Does every word typed start some distinct word of the name?

    Order-free, so "judge aaron" and "st brown" both land. Greedy
    first-fit, longest word first — a full assignment search would be
    right and is not worth it here: the case it gets wrong is one query
    word being a prefix of another ("a aaron"), where the answer it
    gives up on is a worse match anyway.
    """
    if not qt:
        return False
    used = set()
    for w in sorted(qt, key=len, reverse=True):
        hit = next((i for i, t in enumerate(toks)
                    if i not in used and t.startswith(w)), None)
        if hit is None:
            return False
        used.add(hit)
    return True


def _close_enough(n, toks, ql, qt) -> bool:
    """A typo, rather than a different person."""
    if len(ql) < FUZZ_MIN:
        return False
    if difflib.SequenceMatcher(None, ql, n).ratio() >= FUZZ_WHOLE:
        return True
    for w in qt:
        if len(w) >= FUZZ_MIN and difflib.get_close_matches(
                w, toks, n=1, cutoff=FUZZ_TOKEN):
            return True
    return False


#: What each rank means, worst last. The number is the sort key AND the
#: page's answer to "why am I looking at this" — a result list whose best
#: hit is a 2 or a 3 says so rather than presenting a guess as the answer.
RANKS = {0: "starts with", 1: "contains", 2: "words, any order",
         3: "closest spelling"}


def rank(name: str, q: str):
    """How well ``name`` answers ``q`` — 0 best, 3 worst, None for no.

    FOUR TIERS BECAUSE THERE ARE FOUR DIFFERENT MISSES. Exact-prefix and
    substring are what the old SQL `LIKE '%q%'` could do, and everything
    below them is what it could not: an accent or a hyphen in the stored
    spelling (fixed in `norm`, so those land in tiers 0-1 now), the words
    typed in the other order, and a plain misspelling. Each is a real way
    a person types a name they half remember, and each used to come back
    with nothing at all.
    """
    n, ql = norm(name), norm(q)
    if not n or not ql:
        return None
    toks, qt = n.split(), ql.split()
    # The spaceless form too, because the punctuation people leave OUT is
    # as common as the punctuation they leave in: "oneal" for O'Neal,
    # "amonra" for Amon-Ra. `norm` turns those marks into spaces, which
    # makes the words right and the run-together spelling wrong, so both
    # are compared.
    sq_n, sq_q = n.replace(" ", ""), ql.replace(" ", "")
    if (n.startswith(ql) or sq_n.startswith(sq_q)
            or any(t.startswith(ql) for t in toks)):
        return 0
    if ql in n or sq_q in sq_n:
        return 1
    if _tokens_prefix(toks, qt):
        return 2
    if _close_enough(n, toks, ql, qt):
        return 3
    return None


def merge(per_source: dict, q: str, limit: int, order,
          prefer: str = "") -> list[dict]:
    """Round-robin over already-ranked lists, best matches first.

    ONE ROUND PER TIER, not one round overall. A guessed spelling from a
    league that happens to go first must never sit above the man whose
    name was actually typed in the league that goes second — so every
    source offers its rank-0 hits before any source offers a rank-1, and
    so on down. Within a tier the round-robin is what keeps a short list
    from being filled by one league.

    THE TAB YOU ARE ON EMPTIES ITS SHELF FIRST. Ethan, 2026-09-01: "MLB
    players are popping up on the NFL search." They belong there — his
    own 2026-08-23 ask is why the box spans leagues at all — but the
    round-robin WOVE them between the NFL names on the NFL tab, which
    reads as the search not knowing where you are standing. So within
    each tier, ``prefer`` now lists ALL of its hits before the other
    leagues take their turns. Across tiers nothing moves: a name that
    starts with what you typed still beats the tab you happen to be on.
    """
    order = [s for s in order if s in per_source]
    tiers = []
    for want in sorted(RANKS):
        tiers.append({s: [h for h in per_source[s]
                          if h.get("rank", rank(h["player"], q)) == want]
                      for s in order})
    out: list[dict] = []
    for tier in tiers:
        if prefer in tier:
            out.extend(tier[prefer][:max(0, limit - len(out))])
        depth = 0
        while len(out) < limit:
            took = False
            for s in order:
                if s == prefer:
                    continue
                lst = tier[s]
                if depth < len(lst):
                    out.append(lst[depth])
                    took = True
                    if len(out) >= limit:
                        break
            if not took:
                break
            depth += 1
    return out[:limit]


def source_order(prefer: str = "") -> list[str]:
    """SOURCES with the visitor's own league first."""
    return ([prefer] if prefer in SOURCES else []) + \
        [s for s in SOURCES if s != prefer]


def search(q: str, limit: int = 12, prefer: str = "",
           db_path=None, ufc_path=None) -> list[dict]:
    """Every player and fighter whose name contains ``q``."""
    from . import statlogs
    from .ufc import fighters
    q = (q or "").strip()
    if not q:
        return []
    order = source_order(prefer)
    # Every source fetches a full page: four empty ones must not cost the
    # fifth its results. The log leagues come back in ONE connection.
    per: dict = dict(statlogs.search_by_sport(
        q, limit, [s for s in order if s != "ufc"], db_path))
    # A store that is missing is not an error — see fighters.load.
    per["ufc"] = fighters.search(q, limit=limit, path=ufc_path)
    return merge(per, q, limit, order, prefer=prefer)
