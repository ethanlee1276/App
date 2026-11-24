"""Kinds of pick the record says we oversell go on paper: recorded, graded,
never posted.

Ethan, 2026-11-15, on the NFL board's picks fifteen or more points above
the market (step BK: we said 76%, they hit 36%): "we should only be
recording paper bets and not posting the bets so we can still learn ...
that should be automated and not asking me. if any bets is like that we
should switch them to paper and stop posting them till we learn and get
them better".

WHAT A KIND IS. The Most Likely board's picks in one league, of one market
(or every market), at one distance above the price: the chance we show
against the price's own de-vigged chance, the gap the journal keeps in
`edge` for this board (ledger.log_most_likely). Four bands — 15+ points
above, 5 to 15 above, within 5, below — and the whole market as a fifth.

THE TEST, on the board's own graded record (category ``board``, every pick
it posted, and ``held``, the ones it held back; one row a pick): a kind
with MIN_N settled picks over the last WINDOW_DAYS is tested the way the
loss miner tests a slice (wins against the chances we stated), and goes on
paper when it ran HOT by HOLD_GAP_PTS points or HOLD_GAP_REL of the claim
and survives false-discovery control over every kind tested. The bar is
twice the miner's five points because this takes a pick off the board,
not only its stake; a kind that merely loses is the record's corrections'
business (Ethan, 2026-10-04: "I don't wanna take picks off because they
are going bad").

WHAT HAPPENS TO A HELD PICK. It leaves the board as a held-back pick does
(likelyboard.held_reason), so it is journaled under ``held`` and graded
like every other — the record keeps learning on it, which is the half of
the request a refusal could not meet. A pick already posted keeps its seat
until its game; only new ones wait.

THE RELEASE. A kind comes back by itself once the picks it held since the
hold began run honest: RELEASE_N settled, running hot by under
RELEASE_GAP_PTS. Nobody is asked.

THE STANDING HOLD. The measurement that started this (BK) was made on
prices the journal does not keep, so it is written here as a hold from
2026-11-15 on every league's picks 15+ points above the price; it releases
by the same test as any other.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from pathlib import Path

from . import modelstate as _modelstate

DEFAULT_PATH = Path(_modelstate.path("paperhold.json"))

#: The one board's books: what it posted, and what it held back.
FAMILY = ("board", "held")
#: A kind with fewer settled picks than this is not tested.
MIN_N = 40
#: How far back the test reads, so a kind is judged on how it picks now.
WINDOW_DAYS = 90
#: Running hot by this many points, or this share of the claim, holds it.
HOLD_GAP_PTS = 10.0
HOLD_GAP_REL = 0.25
#: The false-discovery rate across every kind tested.
ALPHA = 0.10
#: Its paper picks since the hold, settled, before it can come back…
RELEASE_N = 30
#: …running hot by under this many points.
RELEASE_GAP_PTS = 5.0

#: WHERE A PICK CAME FROM, AS A KIND OF ITS OWN (step AEE, 24 November 2026). The kinds above are a market at a
#: distance from the price; the board's own learning (engine/boardlearn) splits its record by the maker of each pick
#: too, and one maker ran hot past every bar while the market kinds held only part of it: the "bolder than the
#: books" picks (engine/boldcheck: our number ten points or more past the books', kept because a measured step or
#: his own games explained it) hit 122 of 237 on the NFL board where we said about 76%, and 501 of 900 on college's
#: where we said about 68%, while every other maker held up. A bold pick 15 or more points over was on paper since
#: 15 November; one 10 to 15 over still posted. So "every league's bold picks" is a kind, tested and released by the
#: same rule as every other, a pick read as bold where the journal's ``bold`` book holds the same bet.
MAKERS = ("bold",)
MAKER_WORDS = {"bold": "bolder than the books"}
#: The journal's book that marks a bet bold (ledger category).
BOLD_CATEGORY = "bold"

#: (key, low, high, words): our chance minus the price's, in probability.
BANDS = (("15+", 0.15, None, "15 or more points above the price"),
         ("5-15", 0.05, 0.15, "5 to 15 points above the price"),
         ("near", -0.05, 0.05, "within 5 points of the price"),
         ("below", None, -0.05, "below the price"))
ALL = "all"
WORDS = {k: w for k, _, _, w in BANDS}
WORDS[ALL] = "at any price"

STANDING = (
    {"sport": "*", "market": "*", "band": "15+", "since": "2026-11-15", "source": "standing",
     "said": 0.76, "hit": 0.36,
     "why": "picks this far above the books' price said 76% and hit 36% on our NFL board"},
)


def band(gap) -> str | None:
    """The band of a gap (our chance minus the price's), or None."""
    try:
        g = float(gap)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(g):
        return None
    for key, lo, hi, _ in BANDS:
        if (lo is None or g >= lo) and (hi is None or g < hi):
            return key
    return None


def gap_of(row: dict):
    """A board row's gap: the chance it shows against the market's — the
    books' field de-vigged where three or more quote both sides
    (``market_prob``, likelyboard.trust_price, or ``field_prob`` where this
    module read it), else its own price de-vigged (``implied_prob`` on a
    Most Likely row). The journal keeps the same two (``fair_consensus``,
    else ``edge``), so a kind is measured on the gap it is held on."""
    try:
        p = float(row["model_prob"])
    except (KeyError, TypeError, ValueError):
        return None
    for k in ("market_prob", "field_prob", "implied_prob"):
        try:
            return p - float(row[k])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _day(r) -> _dt.date | None:
    for k in ("game_day", "date", "ts"):
        v = str(r.get(k) or "")[:10]
        try:
            return _dt.date.fromisoformat(v)
        except ValueError:
            continue
    return None


def rows_from_ledger(conn) -> list[dict]:
    """Every settled pick of the one board, once: posted ahead of held back."""
    q = ("SELECT sport, market, side, line, player, date, game_day, ts, hit_prob, edge, fair_consensus, "
         "status, category "
         f"FROM bets WHERE category IN ({','.join('?' * len(FAMILY))}) AND status IN ('won','lost')")
    seen: dict = {}
    bold = bold_keys(conn)
    for r in conn.execute(q, FAMILY).fetchall():
        r = dict(r)
        try:
            p = float(r["hit_prob"])
        except (TypeError, ValueError):
            continue
        if not 0.0 < p < 1.0:
            continue
        key = (str(r["sport"]).lower(), r["date"], r["player"], r["market"], str(r["side"]).upper(), r["line"])
        if key in seen and seen[key]["category"] == "board":
            continue
        gap = r["edge"]
        if r["fair_consensus"] is not None:
            # The over's chance on every row that carries it.
            try:
                fc = float(r["fair_consensus"])
                gap = p - (1.0 - fc if str(r["side"]).upper() in ("UNDER", "NO") else fc)
            except (TypeError, ValueError):
                pass
        seen[key] = {"sport": key[0], "market": r["market"], "prob": p, "won": int(r["status"] == "won"),
                     "band": band(gap), "day": _day(r), "category": r["category"]}
        if _bet_key(r) in bold:
            seen[key]["maker"] = "bold"
    return list(seen.values())


def _bet_key(r) -> tuple:
    """One bet across the journal's books: league, game day (the settle key where none), player, market, side —
    the match engine/likelyctx.journal makes, so a bold pick is read as the board's learning reads it."""
    return (str(r["sport"] or "").lower(), r["game_day"] or r["date"], r["player"], r["market"],
            str(r["side"] or "").upper())


def bold_keys(conn) -> set:
    """Every bet the journal's ``bold`` book holds (`_bet_key`); empty where it cannot be read."""
    try:
        return {_bet_key(dict(r)) for r in conn.execute(
            "SELECT sport, date, game_day, player, market, side FROM bets WHERE category=?", (BOLD_CATEGORY,))}
    except Exception:                                        # noqa: BLE001
        return set()


def _test(rows: list) -> dict | None:
    """Wins against the chances we stated (losspatterns._slice_test)."""
    n = len(rows)
    if not n:
        return None
    wins = sum(r["won"] for r in rows)
    said = sum(r["prob"] for r in rows)
    var = sum(r["prob"] * (1.0 - r["prob"]) for r in rows)
    if var <= 0:
        return None
    z = (wins - said) / math.sqrt(var)
    return {"n": n, "said": round(said / n, 4), "hit": round(wins / n, 4),
            "gap_pts": round((said - wins) / n * 100.0, 1), "z": round(z, 3),
            "p": min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0)))))}


def _in(kind: dict, r: dict) -> bool:
    return ((kind["sport"] in ("*", r["sport"])) and (kind["market"] in ("*", r["market"]))
            and (kind["band"] == ALL or kind["band"] == r["band"])
            and (not kind.get("maker") or r.get("maker") == kind["maker"]))


def _hot(t: dict) -> bool:
    rel = (t["gap_pts"] / 100.0) / t["said"] if t.get("said") else 0.0
    return t["gap_pts"] > 0 and (t["gap_pts"] >= HOLD_GAP_PTS or rel >= HOLD_GAP_REL)


def measure(rows: list, today: _dt.date | None = None) -> dict:
    """Every kind big enough to test, and the ones that go on paper."""
    today = today or _dt.date.today()
    cut = today - _dt.timedelta(days=WINDOW_DAYS)
    recent = [r for r in rows if r["day"] is None or r["day"] >= cut]
    kinds: dict = {}
    for r in recent:
        ks = [(r["sport"], r["market"], r["band"], ""), (r["sport"], "*", r["band"], ""),
              (r["sport"], r["market"], ALL, "")]
        if r.get("maker") in MAKERS:
            ks.append((r["sport"], "*", ALL, r["maker"]))
        for k in ks:
            if k[2] is None:
                continue
            kinds.setdefault(k, []).append(r)
    tested = []
    for (sport, market, b, mk), rs in sorted(kinds.items(), key=lambda kv: str(kv[0])):
        if len(rs) < MIN_N:
            continue
        t = _test(rs)
        if t:
            t.update(sport=sport, market=market, band=b, **({"maker": mk} if mk else {}))
            tested.append(t)
    # Benjamini–Hochberg over every kind tested, the miner's control: the
    # largest rank whose p clears its share of ALPHA, and all below it.
    m = len(tested)
    order = sorted(tested, key=lambda t: t["p"])
    cut_i = 0
    for i, t in enumerate(order, 1):
        if t["p"] <= ALPHA * i / max(1, m):
            cut_i = i
    survivors = {id(t) for t in order[:cut_i]}
    held = [dict(t) for t in tested if id(t) in survivors and t["z"] < 0 and _hot(t)]
    return {"tested": len(tested), "kinds": tested, "held": held}


def _key(k: dict) -> str:
    return f"{k['sport']}|{k['market']}|{k['band']}" + (f"|{k['maker']}" if k.get("maker") else "")


def refresh(conn, path=None, today: _dt.date | None = None) -> dict:
    """The settle pass's step: measure, carry each hold's start, release the
    kinds whose paper picks since have run honest, and save."""
    today = today or _dt.date.today()
    prev = load(path)
    rows = rows_from_ledger(conn)
    found = measure(rows, today)
    was = {h["key"]: h for h in prev.get("holds") or []}
    released = {h["key"]: h for h in prev.get("released") or []}
    holds: dict = {}
    for k in list(STANDING) + found["held"]:
        key = _key(k)
        h = dict(was.get(key) or {})
        h.update({kk: k[kk] for kk in ("sport", "market", "band", "maker") if kk in k})
        h.setdefault("since", k.get("since") or today.isoformat())
        h["source"] = k.get("source") or h.get("source") or "measured"
        for kk in ("said", "hit", "n", "z", "gap_pts", "why"):
            if kk in k:
                h[kk] = k[kk]
        h["key"] = key
        # A KIND THAT CAME BACK stays back on the record that held it: the
        # window still holds the picks that ran hot before the release, so
        # only picks after the release can put it on paper again. The
        # standing hold, once released, is never put back by its own words.
        rel = released.get(key)
        if rel:
            if k.get("source") == "standing":
                continue
            after = [r for r in rows if _in(h, r) and r["day"] and r["day"].isoformat() > str(rel["released_on"])]
            t = _test(after) if len(after) >= MIN_N else None
            if not (t and t["z"] < 0 and _hot(t)):
                continue
            h["since"] = today.isoformat()
            released.pop(key, None)
        holds[key] = h
    # The release test: the picks each hold put on paper, since it began.
    for key, h in list(holds.items()):
        since = str(h.get("since") or "")
        after = [r for r in rows if _in(h, r) and r["day"] and r["day"].isoformat() >= since]
        t = _test(after)
        h["since_n"] = t["n"] if t else 0
        if t:
            h["since_said"], h["since_hit"] = t["said"], t["hit"]
        if t and t["n"] >= RELEASE_N and t["gap_pts"] < RELEASE_GAP_PTS:
            released[key] = {**h, "released_on": today.isoformat(),
                             "after": {"n": t["n"], "said": t["said"], "hit": t["hit"]}}
            holds.pop(key)
    out = {"measured_on": today.isoformat(), "records": len(rows), "tested": found["tested"],
           "holds": sorted(holds.values(), key=lambda h: h["key"]),
           "released": sorted(released.values(), key=lambda h: h["key"])}
    save(out, path)
    return out


_cache: dict = {}


def load(path=None) -> dict:
    p = Path(DEFAULT_PATH if path is None else path)
    try:
        m = p.stat().st_mtime
    except OSError:
        return {}
    key = (str(p), m)
    if key not in _cache:
        try:
            raw = json.loads(p.read_text())
        except (OSError, ValueError):
            raw = {}
        _cache.clear()
        _cache[key] = raw if isinstance(raw, dict) else {}
    return _cache[key]


def save(out: dict, path=None) -> Path:
    p = Path(DEFAULT_PATH if path is None else path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, sort_keys=True))
    tmp.replace(p)
    return p


def holds(path=None) -> list:
    """The kinds on paper now: the saved holds, and the standing hold until
    a saved pass has released it."""
    state = load(path)
    out = list(state.get("holds") or [])
    have = {h.get("key") for h in out} | {h.get("key") for h in state.get("released") or []}
    for k in STANDING:
        key = _key(k)
        if key not in have:
            out.append({**k, "key": key})
    return out


def reason(sport: str, market: str, gap, path=None, maker: str | None = None) -> str | None:
    """Why a Most Likely pick at this gap (``gap_of``), from this maker (``bold``, or None), goes on paper, or None."""
    r = {"sport": str(sport or "").lower(), "market": market, "band": band(gap), "maker": maker}
    # The most specific hold that covers the pick says why: its maker first, its own market before every market,
    # its band before any price, the standing hold last.
    ordered = sorted(holds(path), key=lambda h: (not h.get("maker"), h.get("sport") == "*", h.get("market") == "*",
                                                 h.get("band") == ALL))
    for h in ordered:
        if r["band"] is None and h.get("band") != ALL:
            continue
        if not _in({"sport": h.get("sport"), "market": h.get("market"), "band": h.get("band"),
                    "maker": h.get("maker")}, r):
            continue
        if h.get("source") == "standing" or h.get("why"):
            what = h.get("why")
        elif h.get("maker"):
            what = (f"our {str(h.get('sport') or '').upper()} picks {MAKER_WORDS.get(h['maker'], h['maker'])} said "
                    f"{float(h.get('said') or 0):.0%} and hit {float(h.get('hit') or 0):.0%} over "
                    f"{int(h.get('n') or 0)}")
        else:
            scope = "" if h.get("market") == "*" else " " + str(h.get("market") or "").replace("_", " ")
            what = (f"our {str(h.get('sport') or '').upper()}{scope} picks {WORDS.get(h.get('band'), '')} "
                    f"said {float(h.get('said') or 0):.0%} and hit {float(h.get('hit') or 0):.0%} over "
                    f"{int(h.get('n') or 0)}")
        # Card text, for every member: "our rule", nothing from the runbook.
        return (f"on paper, not posted: {what} — our rule records them without posting them until "
                f"{RELEASE_N} run honest")
    return None


def stamp(rows: list, sport: str, result: dict | None = None, path=None) -> int:
    """Mark each board row a hold catches (``paper_hold``, the reason) and
    give every row its gap (``price_gap``). With the build's ``result``, a
    row the price rule did not field (every league but the NFL) gets the
    books' field read here (``field_prob``) where three or more books quote
    both sides. A posted pick keeps its seat. Returns how many were marked."""
    quotes = None
    if result is not None:
        try:
            from .likelyboard import book_quotes
            quotes = book_quotes(result, rows)
        except Exception:                                    # noqa: BLE001
            quotes = None
    n = 0
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if quotes and r.get("market_prob") is None and r.get("kind") != "game":
            try:
                from .likelyboard import market_chance
                got = market_chance(r, quotes)
            except Exception:                                # noqa: BLE001
                got = None
            if got:
                r["field_prob"], r["field_books"] = round(float(got[0]), 4), got[1]
        g = gap_of(r)
        if g is not None:
            r["price_gap"] = round(g, 4)
        why = None if r.get("locked") else reason(sport, r.get("market"), g, path,
                                                  maker="bold" if r.get("bold") else None)
        if why:
            r["paper_hold"] = why
            n += 1
        else:
            r.pop("paper_hold", None)
    return n


#: What the heartbeat says of each kind on paper.
KIND_FIELDS = ("sport", "market", "band", "maker", "said", "hit", "n")


def verdict(out: dict) -> dict:
    """The settle pass's line for the heartbeat: kinds on paper and back, by
    league, and each kind on paper (`kinds`: league, market, band, the chance
    we said, the hit rate, the count; 2026-11-15) — the Sunday check names
    them, and their detail is otherwise only in the box's own state file."""
    from collections import Counter
    holds = (out or {}).get("holds") or []
    on = Counter(str(h.get("sport") or "?") for h in holds)
    back = Counter(str(h.get("sport") or "?") for h in (out or {}).get("released") or [])
    kinds = [{k: h.get(k) for k in KIND_FIELDS if h.get(k) is not None} for h in holds]
    return {"records": (out or {}).get("records"), "tested": (out or {}).get("tested"),
            "on_paper": dict(sorted(on.items())), "back": dict(sorted(back.items())),
            "kinds": sorted(kinds, key=lambda k: (str(k.get("sport")), str(k.get("market")), str(k.get("band"))))}
