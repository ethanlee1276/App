"""Are we ahead of the market on injury news, or behind it?

Ethan, 2026-09-19: *"figure out what data we need to source and what we
can use to make all of our edge bets and all of our most likely bets
better."*

THE CHEAPEST DATA IS THE DATA ALREADY ON DISK, and `engine.datause`'s
table audit found one table read by nothing at all: `injury_events`.
It is written every night by `engine.newstape` — player, team, status,
`posted_at` from the feed and `first_seen` from us — and no model, no
gate and no page has ever selected a row from it. A nightly that runs,
a feed we pay for, and a column nobody reads.

WHY THIS ONE IS WORTH THE TROUBLE. Injury news is one of the few edges
in this sport that is documented, repeatable and mechanical rather than
predictive: when a starter is ruled out, the number moves, and the money
is made in the window between the filing and the move. We do not have to
out-forecast anyone. We have to be early, and being early is a fact we
can measure rather than a claim we can make.

AND WE CAN MEASURE IT WITHOUT BUYING ANYTHING. `odds_history` is
timestamped (`taken_at`) and carries `player`, so a player's own prop
quotes can be lined up against the moment his status changed. That makes
the question arithmetic:

    for each injury filing, did that player's line move AFTER we first
    saw the news — and by how much, and how long did we have?

WHAT THE ANSWER MEANS, both ways, because only one of them is a signal:

  * moves land AFTER `first_seen`, with a usable gap — we see the news
    before the market finishes pricing it, and the gap is the edge. The
    size of the move is the size of the prize.
  * moves land BEFORE `first_seen` — the market already knew. Our feed
    is a newspaper, not a wire, and no amount of modelling fixes that;
    the fix is a faster source, which is a purchase, not a patch.

NOTHING HERE BETS. This is the information test from
`docs/THE_INFORMATION_TEST.md` applied to a store we already keep:
measure first, and let the number decide whether a signal is ever
wired. A negative answer is as useful as a positive one and costs the
same to produce.
"""

from __future__ import annotations

import datetime as _dt

#: The smallest line change that counts as a move.
#:
#: Half a point on a prop is the tick most books quote in, so anything
#: under it is the same number wearing a rounding error. Counting those
#: would report a move on every quote and make the lead time meaningless.
MOVE_EPS = 0.5

#: How far either side of a filing to look for quotes.
#:
#: Wide enough to hold the pre-news baseline and the market's reaction,
#: narrow enough that the next day's news is not attributed to this one.
WINDOW_HOURS = 24

#: A ceiling on the quotes pulled for one filing.
#:
#: A day of one player's props across every book is tens of rows, not
#: thousands. The cap is there so a pathological key — a name that
#: matches half the board, a feed that stamped everything at midnight —
#: costs one bounded read instead of the whole table.
MAX_QUOTES = 5_000

#: Statuses worth measuring. A player downgraded to OUT or DOUBTFUL is
#: the case the market has to reprice; "probable" is noise that moves
#: nothing, and including it would bury the signal in filings that were
#: never going to matter.
MOVING_STATUSES = ("out", "doubtful", "questionable")

#: One filing's quotes, in one bounded read.
#:
#: Named at module level so `tests/test_query_plans.py` can put THIS
#: string through EXPLAIN QUERY PLAN rather than a copy of it. A test
#: that checks a query it wrote itself proves only that the test is
#: indexed.
QUOTE_SQL = ("SELECT taken_at, line FROM odds_history "
             "WHERE sport=? AND taken_at BETWEEN ? AND ? "
             "AND player=? AND line IS NOT NULL "
             "LIMIT ?")

#: Do we EVER quote this man, at any hour?
#:
#: Asked only when the window came back empty, to separate "the books do
#: not price him" from "they price him, but we hold nothing near the
#: news". One is a coverage fact and one is a timing fact.
NAME_SQL = ("SELECT 1 FROM odds_history "
            "WHERE sport=? AND player=? LIMIT 1")


def _norm(name) -> str:
    """The books' spelling of a man, which is the one on disk.

    `engine.sources.oddsapi.parse_event_lines` keys every prop by
    `normalize_name(player)`, so that is what `odds_history` holds.
    Imported lazily: this module is a measurement and must not drag an
    API client in at import time.
    """
    try:
        from .sources.oddsapi import normalize_name
        return normalize_name(str(name or ""))
    except Exception:                                         # noqa: BLE001
        return str(name or "").strip().lower()



def _parse(ts) -> _dt.datetime | None:
    """A timestamp from either store, or None. Never raises: these are
    feed strings and a bad one must cost its own row, not the pass."""
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                d = _dt.datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return d.replace(tzinfo=None)


def classify(first_seen, quotes) -> dict | None:
    """One filing against one player's quote history.

    ``quotes`` is ``[(taken_at, line), …]`` in any order. Returns None
    when there is not enough on both sides of the filing to say
    anything — which is the honest answer far more often than not, and
    counting those as "no move" would quietly claim we were early.

    Returned:
      ``moved``        the line differs across the filing by >= MOVE_EPS
      ``move``         signed size of that difference
      ``lead_minutes`` filing -> the first quote that shows the move.
                       NEGATIVE means the market moved first and we are
                       reading yesterday's paper.
    """
    seen = _parse(first_seen)
    if seen is None:
        return None
    rows = []
    for ts, line in quotes or ():
        t, ln = _parse(ts), line
        if t is None or ln is None:
            continue
        if abs((t - seen).total_seconds()) > WINDOW_HOURS * 3600:
            continue
        rows.append((t, float(ln)))
    if not rows:
        return None
    rows.sort()
    before = [r for r in rows if r[0] <= seen]
    after = [r for r in rows if r[0] > seen]
    if not before or not after:
        return None

    base = before[-1][1]
    # THE FIRST QUOTE THAT ACTUALLY DIFFERS, not the last one in the
    # window. A line that drifts back before the close still moved, and
    # the lead time we care about is to the FIRST chance to bet it.
    hit = next((r for r in after if abs(r[1] - base) >= MOVE_EPS), None)
    if hit is None:
        return {"moved": False, "move": 0.0, "lead_minutes": None,
                "base": base, "quotes_before": len(before),
                "quotes_after": len(after)}

    # AND WHETHER THE MARKET BEAT US TO IT. If the line had already
    # moved off its earlier level before the filing, the news was priced
    # before we saw it — the lead is negative and the "edge" is a
    # reconstruction of somebody else's.
    lead = (hit[0] - seen).total_seconds() / 60.0
    if len(before) > 1:
        earliest = before[0][1]
        if abs(base - earliest) >= MOVE_EPS:
            pre = next(r for r in before if abs(r[1] - earliest) >= MOVE_EPS)
            lead = (pre[0] - seen).total_seconds() / 60.0
    return {"moved": True, "move": round(hit[1] - base, 2),
            "lead_minutes": round(lead, 1), "base": base,
            "quotes_before": len(before), "quotes_after": len(after)}


def summarise(rows) -> dict:
    """The verdict over many filings.

    `ahead` is the share of MOVES we saw first. It is deliberately not a
    share of all filings: a filing whose line never moved says nothing
    about our speed, and folding those in would flatter whichever answer
    happened to have more quiet news in it.
    """
    usable = [r for r in rows if r]
    moves = [r for r in usable if r["moved"]]
    leads = sorted(r["lead_minutes"] for r in moves
                   if r["lead_minutes"] is not None)
    ahead = [l for l in leads if l > 0]
    sizes = sorted(abs(r["move"]) for r in moves)

    def med(xs):
        if not xs:
            return None
        n = len(xs)
        return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2, 1)

    return {
        "filings": len(rows),
        "usable": len(usable),
        "moved": len(moves),
        "ahead": len(ahead),
        "ahead_rate": round(len(ahead) / len(leads), 4) if leads else None,
        "median_lead_minutes": med(leads),
        "median_move": med(sizes),
    }


def measure(hist_conn, sport: str | None = None, since: str | None = None,
            statuses=MOVING_STATUSES) -> dict:
    """Run it over the stores. Read-only; nothing here writes."""
    q = ("SELECT sport, player, status, posted_at, first_seen "
         "FROM injury_events WHERE 1=1")
    args: list = []
    if sport:
        q += " AND sport=?"; args.append(sport)
    if since:
        q += " AND COALESCE(first_seen, posted_at) >= ?"; args.append(since)
    out: dict = {}
    blind: dict = {}
    for ev in hist_conn.execute(q, args).fetchall():
        st = str(ev["status"] or "").strip().lower()
        if statuses and not any(s in st for s in statuses):
            continue
        seen = _parse(ev["first_seen"] or ev["posted_at"])
        if seen is None:
            # Parsed BEFORE the quote lookup, not after. A filing with no
            # readable stamp can never be classified, and querying for it
            # is a full window scan bought for nothing.
            continue
        # BOUNDED BY `taken_at`, WHICH IS WHAT MAKES THIS FINISH.
        #
        # `odds_history`'s primary key is (sport, taken_at, event_id,
        # player, market, book), so `sport=? AND player=?` cannot use it
        # — `taken_at` sits between them, and SQLite falls back to
        # scanning the table. One scan per filing over months of quotes,
        # a few thousand times: Ethan's first run on the droplet was
        # still going after thirteen minutes and had to be killed.
        #
        # Adding the time bounds makes the leading two columns of the
        # index usable, so each lookup is a range scan over one day
        # instead of a walk through every quote we have ever stored. The
        # window is the one `classify` would keep anyway, so nothing that
        # could have counted is lost.
        lo = (seen - _dt.timedelta(hours=WINDOW_HOURS)).isoformat(sep=" ")
        hi = (seen + _dt.timedelta(hours=WINDOW_HOURS)).isoformat(sep=" ")
        # THE TWO STORES SPELL HIM DIFFERENTLY. `injury_events` keeps the
        # feed's display name; `odds_history` keeps the books' menu run
        # through `normalize_name` at parse time. So the join is
        # "A.J. Terrell Jr." against "a j terrell" — 0 of 708 NFL players
        # matched on the droplet, which is why this reported zero usable
        # filings in every sport and looked like a quiet season.
        name = _norm(ev["player"])
        quotes = hist_conn.execute(
            QUOTE_SQL, (ev["sport"], lo, hi, name, MAX_QUOTES)).fetchall()
        if quotes:
            got = classify(ev["first_seen"] or ev["posted_at"],
                           [(q2["taken_at"], q2["line"]) for q2 in quotes])
            out.setdefault(ev["sport"], []).append(got)
            if got is None:
                # QUOTED INSIDE THE WINDOW, BUT ONLY ON ONE SIDE of the
                # filing, so there is no before-price to compare against
                # and `classify` refuses it. Counted, because on
                # 2026-09-19 mlb printed 18 filings over buckets summing
                # to 16 and the missing two were exactly these — a report
                # whose own columns do not reconcile is a report that
                # teaches the reader to distrust all of it.
                blind.setdefault(ev["sport"], [0, 0, 0])[2] += 1
            continue
        # NOTHING IN THE WINDOW — AND WHICH KIND OF NOTHING MATTERS.
        # "we never quote this man" and "we quote him, but never near the
        # news" are different problems with different fixes, and the first
        # version of this report could not tell them apart. It printed
        # "0 with quotes either side" for both and sent me looking in the
        # wrong place twice.
        ever = hist_conn.execute(NAME_SQL, (ev["sport"], name)).fetchone()
        out.setdefault(ev["sport"], []).append(None)
        blind.setdefault(ev["sport"], [0, 0, 0])[0 if ever is None else 1] += 1
    res = {}
    for sp, rows in out.items():
        s = summarise(rows)
        (s["never_quoted"], s["quoted_elsewhen"],
         s["one_sided"]) = blind.get(sp, (0, 0, 0))
        res[sp] = s
    return res


#: The index this measurement cannot run without.
#:
#: `idx_odds_hist_lookup` leads (sport, market, player, taken_at) because
#: the pricing models read one market at a time. This one asks for every
#: quote on a man around a moment, naming no market, so it needs the twin
#: that leads (sport, player, taken_at) — see `engine/db.py`.
REQUIRED_INDEX = "idx_odds_hist_player"


def index_ready(conn) -> bool:
    """Is the index this read depends on actually built?

    `homecheck` opens the history READ-ONLY, which is correct — a check
    must be safe to run mid-cycle — but it also means this process
    cannot create the index it needs. Without the check, a fresh deploy
    reads exactly like the bug it fixed: a command that sits there.

    A measurement that cannot be fast should say so in a second rather
    than be slow for five minutes and explain nothing.
    """
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (REQUIRED_INDEX,)).fetchone() is not None
    except Exception:                                         # noqa: BLE001
        return False


def report(hist_conn, sport: str | None = None, since: str | None = None) -> str:
    # REFUSE RATHER THAN CRAWL. The guard is here and not in `measure`
    # because `measure` is arithmetic over rows and is tested against a
    # connection that has no schema at all; this is a fact about the
    # store a reader is pointed at.
    if not index_ready(hist_conn):
        return "\n".join([
            "", "=" * 70,
            "  ARE WE AHEAD OF THE MARKET ON INJURY NEWS?", "=" * 70,
            f"  not measured — {REQUIRED_INDEX} is not built yet.",
            "",
            "  Without it this read falls back to the primary key, whose",
            "  range over (sport, taken_at) is every quote taken that day",
            "  — every player, every market, every book — once per injury",
            "  filing. That is the five minutes, and refusing is faster",
            "  than proving it again.",
            "",
            "  The nightly builds it on its next writable connect. To do",
            "  it now:",
            "",
            "      python3 -c \"from engine import db; db.connect().close()\"",
            "", ])
    res = measure(hist_conn, sport=sport, since=since)
    lines = ["", "=" * 70,
             "  ARE WE AHEAD OF THE MARKET ON INJURY NEWS?", "=" * 70]
    if not res:
        lines += ["  no injury filings matched any stored quotes.",
                  "  `injury_events` may be empty, or the props for these "
                  "players were never harvested."]
    for sp, s in sorted(res.items()):
        lines.append(
            f"  {sp:5} {s['filings']:5} filings · {s['usable']:4} with quotes "
            f"either side · {s['moved']:4} moved the line")
        if not s["usable"]:
            # WHICH KIND OF NOTHING. Printed because the first version of
            # this report said only "0 with quotes either side", which is
            # true of a name mismatch, a coverage gap and a timing gap
            # alike — and on 2026-09-19 it was the first of those in every
            # sport, with nothing on the page to say so.
            never = s.get("never_quoted", 0)
            elsewhen = s.get("quoted_elsewhen", 0)
            one = s.get("one_sided", 0)
            lines.append(
                f"        {never} never quoted by any book · {elsewhen} "
                f"quoted, but never within {WINDOW_HOURS}h of the news"
                + (f" · {one} quoted on one side only" if one else ""))
            if never >= elsewhen:
                lines.append(
                    "        the books do not price these men, or we spell "
                    "them differently — a coverage or naming gap, not a "
                    "verdict on our speed")
            else:
                lines.append(
                    "        we price these men but hold no quote when the "
                    "news breaks — the edge may be real and is not being "
                    "recorded")
            continue
        if not s["moved"]:
            lines.append("        no measurable moves — nothing to conclude yet")
            continue
        lines.append(
            f"        we were first on {s['ahead']}/{s['moved']} "
            f"({(s['ahead_rate'] or 0) * 100:.0f}%)   "
            f"median lead {s['median_lead_minutes']} min   "
            f"median move {s['median_move']}")
    lines += ["",
              "  A POSITIVE median lead is the edge: minutes between our",
              "  filing and the market's move, at a price still on the board.",
              "  A NEGATIVE one means the market moved first and the feed is",
              "  a newspaper — which no model can fix, only a faster source.",
              "",
              "  Nothing here bets. Measure first.", ""]
    return "\n".join(lines)
