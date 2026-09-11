"""Official weigh-in results, pulled instead of typed.

Recording weigh-ins by hand was the last place this system asked a person
to key in data that a feed publishes. It also made the weakest part of the
UFC board depend on somebody being awake on a Friday morning.

**What this can and cannot promise.** There is no keyless endpoint that
exists to serve weigh-in results the way a scoreboard serves scores. What
ESPN's MMA event payloads *do* carry, on some cards, is a per-competitor
weight recorded for the bout. That is the number the scale produced, and
where it is present it is exactly what we want. Where it is absent this
returns nothing and says so — an unrecorded weigh-in is a first-class
answer everywhere else in this model, and inventing one here would be far
worse than a blank.

So the reader is deliberately SHAPE-TOLERANT: it walks the event payload
looking for a competitor-attached weight under any of the field names
these payloads have been seen to use, rather than hard-coding one path
that a schema change silently breaks into permanent silence. Whatever it
finds is validated against the division limit by
:mod:`engine.ufc.weighin`, which is the same code path a hand-entered
number goes through — so an automatic result and a typed one are the same
kind of fact, graded the same way.

Run ``python3 launch.py --probe-weighins`` to see exactly what the feed
returned for the current card, field by field. If a card comes back empty,
that output is the answer to why — and ``--weigh-in`` still works for the
case a feed cannot cover: you watched the scale on the broadcast before
anyone published it.
"""

from __future__ import annotations

import datetime as _dt

from . import weighin

# Field names seen carrying a fighter's recorded bout weight. Order is
# preference: an explicitly-named weigh-in field beats a generic "weight",
# which on some payloads is the fighter's listed walk-around weight rather
# than what the scale said.
WEIGHT_FIELDS = ("weighIn", "weighin", "weightIn", "officialWeight",
                 "recordedWeight", "weight")

# A plausible fighting weight, in pounds. Anything outside this is a units
# mix-up (kilograms) or a different quantity wearing the same field name,
# and a bad weight is worse than no weight: it manufactures a "missed
# weight" red flag that blocks a real bet.
MIN_LBS, MAX_LBS = 100.0, 350.0


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().replace("lbs", "").replace("lb", "").strip())
        except ValueError:
            return None
    if isinstance(v, dict):
        for k in ("value", "weight", "displayValue"):
            if k in v:
                return _num(v[k])
    return None


def read_weight(competitor: dict) -> tuple[float | None, str]:
    """(pounds, which field it came from) for one competitor entry."""
    for field in WEIGHT_FIELDS:
        if field not in competitor:
            continue
        w = _num(competitor[field])
        if w is not None and MIN_LBS <= w <= MAX_LBS:
            return w, field
    return None, ""


def _name_of(competitor: dict) -> str:
    ath = competitor.get("athlete") or competitor.get("fighter") or {}
    for k in ("displayName", "fullName", "name", "shortName"):
        v = ath.get(k) if isinstance(ath, dict) else None
        if v:
            return str(v)
    for k in ("displayName", "fullName", "name"):
        if competitor.get(k):
            return str(competitor[k])
    return ""


def scan_event(event: dict) -> list[dict]:
    """Every (name, weight, field, division, title_fight) the payload has.

    Walks competitions rather than assuming one shape, because the same
    league publishes fight cards under both ``competitions`` and
    ``groupings``depending on the endpoint.
    """
    out: list[dict] = []
    comps = list(event.get("competitions") or [])
    for grouping in (event.get("groupings") or []):
        comps += list(grouping.get("competitions") or [])
    for comp in comps:
        div = ((comp.get("type") or {}).get("text")
               or comp.get("division") or "")
        title = bool(comp.get("titleFight") or comp.get("isTitleFight"))
        for c in (comp.get("competitors") or []):
            name = _name_of(c)
            weight, field = read_weight(c)
            if not name or weight is None:
                continue
            out.append({"name": name, "weight": weight, "field": field,
                        "division": _division_text(div), "title_fight": title})
    return out


def _division_text(raw: str) -> str:
    """"Women's Flyweight Title Bout" → "flyweight" — the key `weighin`
    knows. Unrecognised text falls through and `evaluate` reports an
    unknown division rather than guessing a limit."""
    t = (raw or "").lower()
    for div in sorted(weighin.LIMITS, key=len, reverse=True):
        if div in t:
            return div
    return raw or ""


def fetch_card(date: str | None = None) -> dict:
    """The upcoming UFC event payload from ESPN, or raise DataUnavailable."""
    from ..sources.espnmma import _get_json

    day = date or _dt.date.today().isoformat()
    url = ("https://site.web.api.espn.com/apis/site/v2/sports/mma/ufc/"
           "scoreboard?dates=" + day.replace("-", ""))
    return _get_json(url, f"mma_scoreboard_{day}.json", ttl=1800)


# How many bouts to follow into the core API when the scoreboard's own
# competitor entries carry no weight. Enough to answer "does this feed
# have it at all", bounded so a probe is never a hundred requests.
DEEP_BOUTS = 6


def deep_scan(event_id: str, limit: int = DEEP_BOUTS) -> list[dict]:
    """Follow the core API's competitor refs, which are richer than the
    scoreboard's summary entries.

    The scoreboard is a *summary* shape — it carries enough to draw a card
    and no more. If a weigh-in weight is published anywhere in this feed
    it is on the fuller competitor record, so "the scoreboard has no
    weights" is not the same finding as "ESPN has no weights", and the
    difference is worth one request per bout to establish.
    """
    from ..sources.espnmma import _get_json, CORE

    out: list[dict] = []
    try:
        comps = _get_json(f"{CORE}/events/{event_id}/competitions",
                          f"mma_ev_{event_id}_comps.json", ttl=1800)
    except Exception:  # noqa: BLE001 — a probe reports, it does not raise
        return out
    for item in (comps.get("items") or [])[:limit]:
        ref = (item.get("$ref") or "").replace("http://", "https://")
        if not ref:
            continue
        cid = ref.rstrip("/").split("/")[-1].split("?")[0]
        try:
            comp = _get_json(ref, f"mma_comp_{cid}.json", ttl=1800)
        except Exception:  # noqa: BLE001
            continue
        div = _division_text((comp.get("type") or {}).get("text") or "")
        title = bool(comp.get("titleFight") or comp.get("isTitleFight"))
        for c in (comp.get("competitors") or []):
            entry = c
            cref = (c.get("$ref") or "").replace("http://", "https://")
            if cref and not any(f in c for f in WEIGHT_FIELDS):
                try:
                    entry = _get_json(
                        cref, f"mma_cptr_{cid}_{c.get('id', '')}.json",
                        ttl=1800)
                except Exception:  # noqa: BLE001
                    entry = c
            weight, field = read_weight(entry)
            out.append({"name": _name_of(entry) or _name_of(c),
                        "weight": weight, "field": field,
                        "keys": sorted(k for k in entry
                                       if "weigh" in k.lower()),
                        "division": div, "title_fight": title})
    return out


def refresh(date: str | None = None, store_path=None,
            today: str | None = None) -> dict:
    """Pull the card and record every weigh-in it carries.

    Returns a summary the launcher prints. Recording is idempotent — the
    same weight written twice is the same stored fact — and it never
    overwrites a *newer* hand-entered result for the same fighter on the
    same day, because both go through :func:`weighin.record` and the last
    write for a fighter wins by design.
    """
    payload = fetch_card(date)
    events = payload.get("events") or []
    if not events:
        return {"recorded": 0, "made": 0, "missed": 0, "source": "espn",
                "note": "no UFC event in the feed for this date"}

    found: list[dict] = []
    for ev in events:
        found += scan_event(ev)

    if not found:
        return {"recorded": 0, "made": 0, "missed": 0, "source": "espn",
                "note": "card found but it carries no weigh-in weights yet "
                        "— they publish the morning before the fights"}

    made = missed = 0
    for row in found:
        res = weighin.record(row["name"], row["weight"], row["division"],
                             title_fight=row["title_fight"],
                             path=store_path, today=today)
        if res["state"] == "made":
            made += 1
        elif res["state"] == "missed":
            missed += 1
    return {"recorded": len(found), "made": made, "missed": missed,
            "source": "espn", "note": ""}


def probe(date: str | None = None) -> list[str]:
    """What the feed actually returned, field by field.

    The point of a probe is that a blank board should never be a mystery.
    If weigh-ins are not appearing, this says whether the card was found,
    which competitors it carried, and which weight fields — if any — were
    on them.
    """
    lines: list[str] = []
    try:
        payload = fetch_card(date)
    except Exception as exc:  # noqa: BLE001 — the probe reports, never raises
        return [f"feed unreachable: {exc}"]

    events = payload.get("events") or []
    lines.append(f"events in feed: {len(events)}")
    for ev in events:
        lines.append(f"  {ev.get('name') or ev.get('shortName') or ev.get('id')}")
        comps = list(ev.get("competitions") or [])
        for g in (ev.get("groupings") or []):
            comps += list(g.get("competitions") or [])
        lines.append(f"    bouts: {len(comps)}")
        for comp in comps[:3]:
            for c in (comp.get("competitors") or []):
                keys = [k for k in WEIGHT_FIELDS if k in c]
                w, field = read_weight(c)
                lines.append(
                    f"      {_name_of(c) or '?'}: "
                    + (f"{w} lbs from {field!r}" if w is not None else
                       f"no usable weight (weight-ish keys present: "
                       f"{keys or 'none'})"))
        if len(comps) > 3:
            lines.append(f"      … {len(comps) - 3} more bout(s) not shown")
    hits = sum(len(scan_event(ev)) for ev in events)
    lines.append(f"\nusable weigh-in weights on the scoreboard: {hits}")

    # The scoreboard is a summary shape. Before concluding anything, look
    # in the fuller record — "the summary has no weights" and "ESPN has no
    # weights" are different findings.
    deep_hits = 0
    if not hits and events:
        eid = str(events[0].get("id") or "")
        lines.append(f"\nfollowing the core API for event {eid} "
                     f"(the fuller competitor record)…")
        rows = deep_scan(eid)
        if not rows:
            lines.append("  core API returned no competitors either")
        for r in rows[:8]:
            if r["weight"] is not None:
                deep_hits += 1
                lines.append(f"  {r['name']}: {r['weight']} lbs "
                             f"from {r['field']!r}")
            else:
                lines.append(f"  {r['name']}: no weight"
                             + (f" (weigh-ish keys: {r['keys']})"
                                if r["keys"] else ""))
        lines.append(f"  usable weights in the core API: {deep_hits}")

    if hits or deep_hits:
        return lines

    # Which of the two reasons is it? The probe used to leave that hanging,
    # which made it a diagnostic you still had to guess after.
    when = str(events[0].get("date") or "")[:10] if events else ""
    day = date or _dt.date.today().isoformat()
    lines.append("")
    if when and when > day:
        lines.append(
            f"VERDICT: the card is {when} and today is {day}. Fighters weigh "
            f"in the MORNING BEFORE the card, so there is nothing published "
            f"yet and nothing wrong. Re-run this on {when} (or the day "
            f"before) to find out whether the feed actually carries them — "
            f"until then this tells you nothing either way.")
    else:
        lines.append(
            "VERDICT: the card is today or already past and BOTH the "
            "scoreboard and the fuller core record carry no weights. That "
            "is the real answer: this feed does not publish weigh-in "
            "results, and no amount of waiting will change it. Use "
            "`python3 launch.py --weigh-in \"Name\" 155.5` for a fight you "
            "care about, or leave it — see below.")
    lines.append(
        "\nEither way this does NOT hold the board back. Camp is now scored "
        "from layoff, activity and gym (engine/ufc/camp.py), and a missing "
        "weigh-in drops out of the grade instead of marking the fight down. "
        "The one thing a recorded weigh-in still does that nothing else can "
        "is catch a MISS, which gates that fight outright — so if you see "
        "the scale on the broadcast before anyone publishes it: "
        "`python3 launch.py --weigh-in \"Name\" 155.5`.")
    return lines
