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
import functools
import re
import unicodedata
from array import array
from bisect import bisect_right

#: Every source this box covers, in the order a tie is broken. The log
#: leagues come from statlogs; ufc is its own reader.
#: In the order of importance Ethan set on 2026-09-01 ("NFL … then CFB,
#: then MLB, then NBA, then WNBA, then UFC") — this is the tie-break
#: order when no tab preference says otherwise. Hockey (2026-10-03) sits
#: after the WNBA: Ethan, the same day, "I don't really bet it."
SOURCES = ("nfl", "cfb", "mlb", "nba", "cbb", "wnba", "nhl", "ufc")


@functools.lru_cache(maxsize=1 << 17)
def norm(s: str) -> str:
    """A name reduced to what a person is actually typing at it.

    REMEMBERED (step AGT, 25 November 2026): every roster rewrite and every name list rebuilt put the same tens of
    thousands of names through this again (Ryan Williams's college page, 7.4 s finding him on a rewritten roster,
    beside the search's own rebuild); the same name is the same answer.

    Ethan, 2026-08-23: "if you dont type the players name in exactly, they
    dont come up at all which makes it feel broken."

    Ethan is right, and the first cause is not typos — it is that the stored
    spelling carries things nobody types. "Kauê Fernandes" is on Ethan's own
    droplet right now and a search for "Kaue" could never find the fighter,
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
    # The two cheap bounds before the ratio, as difflib's own
    # get_close_matches checks them: each is at least the ratio, so a name
    # they rule out could never have passed, and most names are ruled out.
    s = difflib.SequenceMatcher(None, ql, n)
    if (s.real_quick_ratio() >= FUZZ_WHOLE and s.quick_ratio() >= FUZZ_WHOLE
            and s.ratio() >= FUZZ_WHOLE):
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


def rank(name: str, q: str, fuzzy: bool = True):
    """How well ``name`` answers ``q`` — 0 best, 3 worst, None for no.

    FOUR TIERS BECAUSE THERE ARE FOUR DIFFERENT MISSES. Exact-prefix and
    substring are what the old SQL `LIKE '%q%'` could do, and everything
    below them is what it could not: an accent or a hyphen in the stored
    spelling (fixed in `norm`, so those land in tiers 0-1 now), the words
    typed in the other order, and a plain misspelling. Each is a real way
    a person types a name they half remember, and each used to come back
    with nothing at all.
    """
    return rank_normed(norm(name), norm(q), fuzzy)


def rank_normed(n: str, ql: str, fuzzy: bool = True):
    """`rank` for a name and a query already through `norm`.

    The league search keeps every name it holds normed once (`NameIndex`),
    so a keystroke pays for the comparisons and not for eighty thousand
    accent strips. ``fuzzy=False`` stops at tier 2: the closest-spelling
    tier is for a search that found nobody by the name typed.
    """
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
    if fuzzy and _close_enough(n, toks, ql, qt):
        return 3
    return None


def no_guess_beside_an_answer(hits: list) -> list:
    """A GUESS IS NOT AN ANSWER. Ethan, 2026-11-16, with "jacoby brissett"
    typed: Jacoby Brissett came back, and eleven rostered players spelled
    nearly like that name came back with it ("Jacob Rodriguez", "Coby Bryant").
    The closest spellings (tier 3) are for a search that found nobody by
    the name typed; beside someone who has it, they are only noise to
    scroll past."""
    if any(h.get("rank", 3) < 3 for h in hits):
        return [h for h in hits if h.get("rank", 3) < 3]
    return hits


def closeness(ql: str, n: str) -> float:
    """How near a whole name (through `norm`) is to what was typed, 0 to 1:
    the order a list of guessed spellings is shown in, nearest first."""
    return difflib.SequenceMatcher(None, ql, n).ratio()


def fuzzy_hits(norms, ql: str) -> list[int]:
    """The positions in ``norms`` (names through `norm`) that `_close_enough`
    takes for a misspelling of ``ql``: the same answers, at a price a league
    of eighty thousand names can pay when a search finds nobody.

    Two savings, neither of which changes an answer. The whole-name bounds
    are taken with the query held still, so its letters are counted once
    rather than once a name (both bounds are the same whichever side is
    held), and only a name inside them pays for the ratio, in the order
    `_close_enough` computes it. And a word of a name is judged once per
    search however many names share it, the way get_close_matches judges
    it: the word as the first sequence, the typed word as the second, the
    same three checks in the same order.
    """
    if len(ql) < FUZZ_MIN:
        return []
    whole = difflib.SequenceMatcher(None)
    whole.set_seq2(ql)
    words = []
    for w in ql.split():
        if len(w) >= FUZZ_MIN:
            m = difflib.SequenceMatcher(None)
            m.set_seq2(w)
            words.append(m)
    near: dict = {}
    out = []
    for k, n in enumerate(norms):
        if not n:
            continue
        whole.set_seq1(n)
        if (whole.real_quick_ratio() >= FUZZ_WHOLE and whole.quick_ratio() >= FUZZ_WHOLE
                and difflib.SequenceMatcher(None, ql, n).ratio() >= FUZZ_WHOLE):
            out.append(k)
            continue
        for t in n.split():
            hit = near.get(t)
            if hit is None:
                hit = False
                for m in words:
                    m.set_seq1(t)
                    if (m.real_quick_ratio() >= FUZZ_TOKEN and m.quick_ratio() >= FUZZ_TOKEN
                            and m.ratio() >= FUZZ_TOKEN):
                        hit = True
                        break
                near[t] = hit
            if hit:
                out.append(k)
                break
    return out


class NameIndex:
    """Every name one source holds, normed once and searched in C.

    Ethan, 2026-11-16: "players are not showing up on the search page for
    players." On the box a college football search took 8 to 16 seconds:
    every keystroke scanned millions of log rows with `LIKE '%q%'` (no
    index can serve a leading wildcard), then put all 41,888 rostered
    college players through the spelling matcher one at a time. This keeps
    a source's names as two strings, the normed names and the same with
    their spaces taken out, so the words typed are found by `str.find`
    running over a megabyte, and only the names it lands in are ranked.

    ``rows`` are ``(name, latest season)``; the season orders names that
    match equally well, the current player before a namesake from 2021.
    Memory is about a hundred bytes a name.
    """

    __slots__ = ("names", "last", "src", "at", "sig", "_n", "_n_at", "_sq", "_sq_at")

    def __init__(self, rows, at: float = 0.0, sig=None):
        # ``src`` is where each kept name sat in ``rows``: a name that norms
        # to nothing is left out, and the caller's own list still lines up.
        names, last, src, ns, sqs = [], array("H"), array("i"), [], []
        for i, (name, season) in enumerate(rows):
            n = norm(name)
            if not n:
                continue
            names.append(name)
            src.append(i)
            try:
                last.append(max(0, min(int(season or 0), 65535)))
            except (TypeError, ValueError):
                last.append(0)
            ns.append(n)
            sqs.append(n.replace(" ", ""))
        self.names, self.last, self.src, self.at, self.sig = names, last, src, at, sig
        self._n, self._n_at = self._join(ns)
        self._sq, self._sq_at = self._join(sqs)

    @staticmethod
    def _join(parts):
        """One string, a newline after each part, and where each part starts
        (and, last, where the string ends)."""
        at, pos = array("i"), 0
        for s in parts:
            at.append(pos)
            pos += len(s) + 1
        at.append(pos)
        return "".join(s + "\n" for s in parts), at

    def __len__(self) -> int:
        return len(self.names)

    def norm_of(self, k: int) -> str:
        return self._n[self._n_at[k]:self._n_at[k + 1] - 1]

    def norms(self) -> list[str]:
        return self._n.split("\n")[:-1]

    def matching(self, ql: str) -> list[int]:
        """The names whose spaceless form holds every word typed: everything
        tiers 0 to 2 can take (each needs every word somewhere in the name)
        and a few more, found by `str.find`. The longest word is the one
        searched for, the rest checked on the names it lands in."""
        qt = ql.split()
        if not qt:
            return []
        w = max(qt, key=len)
        blob, at, out = self._sq, self._sq_at, []
        i = blob.find(w)
        while i != -1:
            k = bisect_right(at, i) - 1
            s = blob[at[k]:at[k + 1] - 1]
            if all(x in s for x in qt):
                out.append(k)
            i = blob.find(w, at[k + 1])
        return out

    def ranked(self, ql: str, fuzzy: bool = True) -> dict:
        """``{position: tier}`` for a query through `norm`: tiers 0 to 2 where
        any name has one, else (when ``fuzzy``) the closest spellings, tier 3."""
        out = {}
        for k in self.matching(ql):
            got = rank_normed(self.norm_of(k), ql, fuzzy=False)
            if got is not None:
                out[k] = got
        if out or not fuzzy:
            return out
        return {k: 3 for k in fuzzy_hits(self.norms(), ql)}


def merge(per_source: dict, q: str, limit: int, order,
          prefer: str = "") -> list[dict]:
    """Round-robin over already-ranked lists, best matches first.

    ONE ROUND PER TIER, not one round overall. A guessed spelling from a
    league that happens to go first must never sit above the player whose
    name was actually typed in the league that goes second — so every
    source offers its rank-0 hits before any source offers a rank-1, and
    so on down. Within a tier the round-robin is what keeps a short list
    from being filled by one league.

    THE TAB YOU ARE ON EMPTIES ITS SHELF FIRST. Ethan, 2026-09-01: "MLB
    players are popping up on the NFL search." They belong there — Ethan's
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


#: Each league's clubs by their full names, as the odds feed spells them
#: (engine/sources/oddsapi): the names a club's own row in the logs carries.
CLUB_TABLES = {"nfl": "TEAM_ABBR", "mlb": "MLB_TEAM_ABBR", "nba": "NBA_TEAM_ABBR",
               "wnba": "WNBA_TEAM_ABBR", "nhl": "NHL_TEAM_ABBR"}


def club_names(sport: str) -> frozenset:
    """A league's clubs' full names, normalized ({} when the table cannot be read)."""
    try:
        from .sources import oddsapi
        table = getattr(oddsapi, CLUB_TABLES.get(str(sport or "").lower(), ""), None) or {}
    except Exception:                                        # noqa: BLE001
        table = {}
    return frozenset(norm(n) for n in table)


def drop_clubs(hits: list[dict], sport: str = "") -> list[dict]:
    """A SEARCH NAMES EACH THING ONCE (SEARCHDUP1, 2026-11-18). Ethan, of "Lions"
    on the search page, which offered the Detroit Lions as a team and again as
    a player (the logs file a club's defence under its own name, "DEF"): "we
    don't need to have search results popping up twice on this page". A club
    is offered as a team, by the page's team chips; its row in the logs is not
    offered again as a player. A hit with no league is read against ``sport``."""
    out = []
    names: dict = {}
    for h in hits or []:
        sp = str(h.get("sport") or sport or "").lower()
        if sp not in names:
            names[sp] = club_names(sp)
        if norm(h.get("player") or "") in names[sp]:
            continue
        out.append(h)
    return out


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
    ufc_faces(per["ufc"], db_path)
    return drop_clubs(no_guess_beside_an_answer(merge(per, q, limit, order, prefer=prefer)))


def ufc_faces(hits: list[dict], db_path=None) -> None:
    """A fighter's face on the search row, as every league's player has one
    (2026-11-17): where the dossier keeps no ESPN id, the one the fight
    history's read kept (engine/ufc/history.faces). One connection, only
    when a fighter row has no face."""
    need = [h for h in hits if not h.get("headshot")]
    if not need:
        return
    import os
    from . import db as _db
    from .ufc import history as _hist
    path = str(db_path or _db.DEFAULT_DB)
    if not os.path.exists(path):
        return
    conn = _db.connect(path)
    try:
        got = _hist.faces(conn, [h["player"] for h in need])
    finally:
        conn.close()
    for h in need:
        h["headshot"] = got.get(h["player"], "")
