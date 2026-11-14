"""Historical comps — the outside view on tonight's number.

Every projection here is an INSIDE view: build a mean from the player's
own windows, shade it, wrap a distribution around it, integrate past the
line. That distribution's SHAPE is an assumption — a variance floor and
a normal-ish tail — and prop models die on exactly that assumption long
before they die on the mean.

This module answers the same question from the outside, with no model in
the loop at all: *when a player in this form state faced this number,
how often did he actually clear it?* It walks the ingested game logs,
reconstructs each past game's trailing form as it stood BEFORE that game
was played, and reports the empirical exceedance rate for the band
tonight's player sits in. No distribution is assumed; the record just
gets counted.

Two things that makes possible:

* **A second opinion with a real denominator.** "The 214 closest comps
  went 46% over" is a different kind of evidence from "the model says
  57%", and when they disagree by a wide margin on a big sample, the
  disagreement itself is the signal worth reading.
* **A check on the tails.** Comps are where a model that quietly prices
  a 0.5-line like a normal curve gets caught.

Deliberately NOT a price input in this version. It ships as evidence on
the card and a warning when it materially disagrees, exactly the way the
incentive tracker and the rest watch ship — a new signal earns its way
into pricing by being measured first, not by being trusted first. The
blind-spot miner can then convict or clear it on our own record.

Rules it inherits from the rest of the engine:

* **Per-sport, per-market isolation.** An index is keyed by both and
  never pools. A hit rate blended across leagues describes no league.
* **Past-only.** A comp is reconstructed from games strictly before the
  one it describes, so a spot never learns from its own outcome; the
  ``before`` cutoff extends the same guarantee to a replayed date.
* **A minimum sample.** Below ``MIN_COMPS`` the band reports nothing
  rather than a number that would read as evidence.

Standard library only; reads the history DB the ingests already fill.
"""

from __future__ import annotations

import array

#: Trailing games that define a player's "form state". Ten matches the
#: form module's longest ordinary window, so the conditioning statistic
#: is one the rest of the engine already thinks in.
WINDOW = 10

#: A comp needs a full window behind it, or its form is not a form.
MIN_HISTORY = WINDOW

#: How wide a form band counts as "a similar spot", as a fraction of the
#: form itself. Relative rather than absolute because 15% of a 1.2-hit
#: bat and 15% of a 260-yard passer are the same KIND of difference.
FORM_BAND = 0.15

#: …with an absolute floor, so rare-event markets (a 0.15 home-run rate)
#: get a usable band instead of a hairline.
BAND_FLOOR = 0.05

#: Below this many comps the band is noise wearing a percentage. Same
#: order as the blind-spot miner's MIN_N, and for the same reason.
MIN_COMPS = 50

#: How far the comps must sit from the model's own probability before the
#: disagreement is worth a warning. Under this they broadly agree, and a
#: chip on every card is a chip nobody reads.
DIVERGENCE = 0.10


def _band(form: float, band: float = FORM_BAND) -> tuple[float, float]:
    """The form window counted as 'similar', relative with a floor."""
    half = max(abs(form) * band, BAND_FLOOR)
    return form - half, form + half


def spot_index(conn, sport: str, market: str, window: int = WINDOW,
               min_history: int = MIN_HISTORY) -> list[tuple]:
    """``[(sort_key, player, trailing_form, value), ...]`` for one market.

    One row per historical player-game that had a full window behind it.
    ``trailing_form`` is the mean of the player's previous ``window``
    games — computed from games strictly BEFORE this one, so a spot can
    never see its own result. ``sort_key`` is ``(season, period)``, which
    is chronological for both an ISO-dated sport and a week-labelled one.
    """
    rows = conn.execute(
        "SELECT player, season, period, game_id, value FROM player_game_logs "
        "WHERE sport=? AND market=? AND value IS NOT NULL "
        "ORDER BY player, season, period, game_id", (sport, market))
    out: list[tuple] = []
    prior: dict[str, list[float]] = {}
    for r in rows:
        player = r["player"]
        hist = prior.setdefault(player, [])
        if len(hist) >= min_history:
            recent = hist[-window:]
            out.append(((r["season"], str(r["period"])), player,
                        sum(recent) / len(recent), float(r["value"])))
        hist.append(float(r["value"]))
    return out


def comp_record(index: list[tuple], line: float, form: float,
                band: float = FORM_BAND, before=None,
                min_n: int = MIN_COMPS, player: str | None = None) -> dict | None:
    """The empirical record of comparable past spots, or None below the bar.

    Always reported from the OVER's point of view — ``hit_rate`` is how
    often the result cleared ``line``. Callers holding an under are
    responsible for taking the complement, which :func:`decorate` does;
    getting that backwards is the classic way to grade every under in a
    report upside down.

    Pushes (an exact-integer line the result lands on) are counted and
    excluded from the rate, the way the journal counts them.
    """
    lo, hi = _band(form, band)
    over = under = push = own = 0
    for key, name, f, value in index:
        if f < lo or f > hi:
            continue
        if before is not None and key >= before:
            continue
        if value > line:
            over += 1
        elif value < line:
            under += 1
        else:
            push += 1
            continue
        if player and name == player:
            own += 1
    decided = over + under
    if decided < min_n:
        return None
    return {"n": decided, "over": over, "under": under, "push": push,
            "hit_rate": round(over / decided, 4), "line": line,
            "form": round(form, 3), "form_lo": round(lo, 3),
            "form_hi": round(hi, 3), "own": own}


class _BandIndex:
    """One market's spots sorted by trailing form, for `comp_record`'s
    counts without its walk.

    EVERY SPOT, FOR EVERY PROP (2026-11-08). `decorate` asked `comp_record`
    once per priced prop, and each walked its market's whole index — every
    past player-game since the logs begin — to keep the ones inside a ±15%
    form band: about six hundred walks of tens of thousands of spots on an
    NFL Sunday, 10.7 of the pricing stage's 48 seconds at 09:16. Sorted by
    form, a band is a slice found by bisection; the slice is cut into
    blocks whose values are kept sorted, so a whole block's over, under and
    push are three bisects and only the two edge blocks are walked. A
    player's own spots sit in their own form-sorted list. Every number is a
    count, so the record is `comp_record`'s, to the digit. A replay's
    ``before`` cutoff, and a band that is not a number, are handed to
    `comp_record` itself."""

    BLOCK = 256

    def __init__(self, index: list[tuple]):
        self._spots = sorted(index, key=lambda s: s[2])
        self._cols = None
        self.forms = [s[2] for s in self._spots]
        self.values = [s[3] for s in self.spots]
        b = self.BLOCK
        self.blocks = [sorted(self.values[i:i + b]) for i in range(0, len(self.values), b)]
        self.own: dict = {}
        for _key, name, f, value in self._spots:
            fs, vs = self.own.setdefault(name, ([], []))
            fs.append(f)
            vs.append(value)

    # A KEPT COPY IN COLUMNS (engine/logcache, 2026-11-09). College's comps
    # read each market's whole history on every build, 11.5 seconds at 08:35
    # on 9 November; kept between builds as tuples a market's index was 16.5
    # MB and 0.15 seconds to load, as columns of floats 9.6 MB and 0.015.
    # The spot tuples `comp_record` walks for a replay's cutoff come back
    # only when one is asked for, rebuilt from the same columns (each name,
    # season and date stored once), so every count is the same to the digit.
    @property
    def spots(self) -> list:
        if self._spots is None:
            names, seasons, periods = self._cols
            self._spots = [((s, p), n, f, v) for n, s, p, f, v
                           in zip(names, seasons, periods, self.forms, self.values)]
        return self._spots

    def __getstate__(self) -> dict:
        pool: dict = {}
        names, seasons, periods = [], [], []
        for key, name, _f, _v in self.spots:
            names.append(pool.setdefault(name, name))
            seasons.append(pool.setdefault(("s", key[0]), key[0]))
            periods.append(pool.setdefault(("p", key[1]), key[1]))
        flat = array.array("d")
        for block in self.blocks:
            flat.extend(block)
        return {"forms": array.array("d", self.forms), "values": array.array("d", self.values),
                "blocks": flat, "n": len(self.forms),
                "own": {n: (array.array("d", fs), array.array("d", vs))
                        for n, (fs, vs) in self.own.items()},
                "names": names, "seasons": seasons, "periods": periods}

    def __setstate__(self, st: dict) -> None:
        self.forms, self.values = st["forms"], st["values"]
        b, flat = self.BLOCK, st["blocks"]
        self.blocks = [flat[i:i + b] for i in range(0, len(flat), b)]
        self.own = st["own"]
        self._cols = (st["names"], st["seasons"], st["periods"])
        self._spots = None

    def record(self, line: float, form: float, band: float = FORM_BAND, before=None,
               min_n: int = MIN_COMPS, player: str | None = None) -> dict | None:
        import bisect
        lo, hi = _band(form, band)
        if before is not None or not lo <= hi:
            return comp_record(self.spots, line, form, band=band, before=before,
                               min_n=min_n, player=player)
        i0, i1 = bisect.bisect_left(self.forms, lo), bisect.bisect_right(self.forms, hi)
        over = under = push = 0
        b, n = self.BLOCK, len(self.values)
        i = i0
        while i < i1:
            k = i // b
            block_end = min((k + 1) * b, n)
            if i == k * b and block_end <= i1:
                # The whole block is in the band: count it off its sorted values.
                vals = self.blocks[k]
                lt, le = bisect.bisect_left(vals, line), bisect.bisect_right(vals, line)
                under += lt
                push += le - lt
                over += len(vals) - le
                i = block_end
                continue
            stop = min(block_end, i1)
            for v in self.values[i:stop]:
                if v > line:
                    over += 1
                elif v < line:
                    under += 1
                else:
                    push += 1
            i = stop
        own = 0
        if player and player in self.own:
            fs, vs = self.own[player]
            j0, j1 = bisect.bisect_left(fs, lo), bisect.bisect_right(fs, hi)
            own = sum(1 for v in vs[j0:j1] if v != line)
        decided = over + under
        if decided < min_n:
            return None
        return {"n": decided, "over": over, "under": under, "push": push,
                "hit_rate": round(over / decided, 4), "line": line,
                "form": round(form, 3), "form_lo": round(lo, 3),
                "form_hi": round(hi, 3), "own": own}


def _form_of(rec: dict) -> float | None:
    """Tonight's form state, in the same statistic the index was built on:
    the mean of the player's most recent ``WINDOW`` games."""
    vals = rec.get("recent_values") or []
    vals = [v for v in vals[:WINDOW] if v is not None]
    if len(vals) < 3:
        # Too thin to place in a band; a comp set found by a two-game
        # average describes a coincidence, not a spot.
        return None
    return sum(vals) / len(vals)


def _kept_index(conn, sport: str, market: str) -> "_BandIndex":
    """One market's band index, kept until the sport's logs change
    (engine/logcache): its whole history, so every season counts. A replay
    (``before``) builds its own, as it always did."""
    from . import logcache
    return logcache.memo(conn, "comps_" + str(market).replace("-", "_"), sport, None,
                         lambda: _BandIndex(spot_index(conn, sport, market)), code=__file__)


def decorate(recommendations: list[dict], conn, sport: str,
             before=None, min_n: int = MIN_COMPS) -> dict:
    """Attach the comp record to every prop card that has one.

    Adds ``rec["comps"]`` (from the OVER's side, as stored) plus a reason
    line, and a warning when the comps disagree with the model's own
    probability by more than :data:`DIVERGENCE` — sided correctly for the
    pick actually being made.

    Returns a small summary for the board's own diagnostics.
    """
    indexes: dict[str, _BandIndex] = {}
    matched = diverged = 0
    for r in recommendations:
        market = r.get("market")
        line = r.get("line")
        if not market or line is None:
            continue
        form = _form_of(r)
        if form is None:
            continue
        if market not in indexes:
            try:
                indexes[market] = (_kept_index(conn, sport, market) if before is None
                                   else _BandIndex(spot_index(conn, sport, market)))
            except Exception:                      # noqa: BLE001
                indexes[market] = _BandIndex([])
        # The band counted off a form-sorted index (`_BandIndex`): the same
        # record `comp_record` gives, without walking every past spot.
        rec = indexes[market].record(float(line), form, band=FORM_BAND, before=before,
                                     min_n=min_n, player=r.get("player"))
        if not rec:
            continue
        r["comps"] = rec
        matched += 1
        # Side the comps to the bet actually being made before comparing.
        side = str(r.get("side") or "OVER").upper()
        comp_p = rec["hit_rate"] if side == "OVER" else 1 - rec["hit_rate"]
        r["comps"]["side_rate"] = round(comp_p, 4)
        model_p = r.get("hit_prob")
        r.setdefault("reasons", []).append(
            f"Comps: {rec['n']:,} past spots with this line and a similar "
            f"{WINDOW}-game form ({rec['form_lo']:.2f}–{rec['form_hi']:.2f}) "
            f"went {comp_p:.0%} to the {side.lower()}")
        if model_p is not None and abs(comp_p - float(model_p)) >= DIVERGENCE:
            diverged += 1
            r.setdefault("warnings", []).append(
                f"Comps disagree: the model says {float(model_p):.0%} but "
                f"{rec['n']:,} similar past spots went {comp_p:.0%} to the "
                f"{side.lower()}. The comps assume no distribution — they "
                f"just count what happened — so a gap this wide is usually "
                f"the model's tail shape, not bad luck")
    return {"matched": matched, "diverged": diverged,
            "markets": sorted(indexes), "min_n": min_n, "window": WINDOW}
