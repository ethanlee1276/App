"""Live fight state — strikes by target, while the fight is happening.

The UFC's broadcast body graphic is not a damage model. It is a count of
significant strikes landed to each target area — head, body, leg — and
that distinction is the whole design of this module. "Damage" is a
judgement nobody publishes; strikes to the head is a number somebody
counts. We show the number and call it what it is.

**What this can and cannot promise.** ESPN republishes MMA statistics
per competition, and during a live fight those update as the fight goes
on. Whether they update strike-by-target at broadcast latency, or only at
the end of a round, is a property of that feed that I could not test from
where this was written — there was no live card, and the network policy
in that environment blocks the host outright. So the reader is
shape-tolerant, it reports what it found rather than what it hoped for,
and ``python3 launch.py --probe-live`` prints the raw shape during a live
fight so the answer comes from the card rather than from an assumption.

Three rules the page depends on:

* **Never interpolate.** If the feed last moved 90 seconds ago, the page
  says the numbers are 90 seconds old. A smoothly-rising count that is
  really a stale one redrawn is the worst possible thing to put next to a
  fight somebody is watching.
* **Absorbed, not thrown.** The body diagram shades what a fighter has
  TAKEN, because that is what the UFC's graphic shows and what a viewer
  reads it as. A fighter's own landed strikes appear on his opponent.
* **This is not an in-play betting signal.** The pre-game model refuses
  live prices by design (docs/UFC_MODEL.md §10), and nothing here feeds
  it. A live fight page is something to watch, not something to bet.
"""

from __future__ import annotations

import datetime as _dt

# Target areas, in the order the body diagram stacks them. These are the
# three FightMetric target categories the UFC has used for years, so a
# feed carrying strike targets at all almost certainly carries these.
TARGETS = ("head", "body", "leg")

# Label spellings seen for each target across MMA stat payloads. Matched
# case-insensitively on a normalised label, longest first, so "Significant
# Strikes Head" and "SigStrHead" both land in the same bucket.
TARGET_LABELS = {
    "head": ("sigstrhead", "significantstrikeshead", "headstrikeslanded",
             "headsignificantstrikes", "strikeshead", "head"),
    "body": ("sigstrbody", "significantstrikesbody", "bodystrikeslanded",
             "bodysignificantstrikes", "strikesbody", "body"),
    "leg": ("sigstrleg", "significantstrikesleg", "legstrikeslanded",
            "legsignificantstrikes", "strikesleg", "leg"),
}

# Totals worth showing next to the diagram, same tolerant matching.
EXTRA_LABELS = {
    "sig_strikes": ("sigstrlanded", "significantstrikeslanded", "ssl",
                    "sigstr"),
    "sig_attempted": ("sigstrattempted", "significantstrikesattempted",
                      "ssa"),
    "takedowns": ("takedownslanded", "tdl", "takedowns"),
    "knockdowns": ("knockdowns", "kd"),
    "control": ("controltime", "ctrl", "groundcontroltime"),
}

# Older than this and the page stops calling it live. A fight moves in
# seconds; a minute-old count sitting under a "LIVE" badge is a lie with a
# green dot on it.
STALE_S = 75


def _norm(label: str) -> str:
    return "".join(ch for ch in str(label).lower() if ch.isalnum())


def _match(label: str, table: dict) -> str | None:
    n = _norm(label)
    if not n:
        return None
    # Longest spellings first: "head" would otherwise swallow
    # "headstrikeslanded" and lose the more specific match.
    for key, spellings in table.items():
        for sp in sorted(spellings, key=len, reverse=True):
            if n == sp:
                return key
    for key, spellings in table.items():
        for sp in sorted(spellings, key=len, reverse=True):
            if sp in n:
                return key
    return None


def _num(v):
    """A count from whatever shape the feed used. '12 of 30' -> 12."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, dict):
        for k in ("value", "displayValue", "landed"):
            if k in v:
                return _num(v[k])
        return None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s:
            return None
        # "12 of 30" / "12/30" — the landed half is the first number.
        for sep in (" of ", "/", "-"):
            if sep in s:
                s = s.split(sep)[0].strip()
                break
        # Control time arrives as "4:31"; keep it as seconds.
        if ":" in s:
            try:
                m, sec = s.split(":")[:2]
                return int(m) * 60 + int(sec)
            except ValueError:
                return None
        try:
            return int(float(s))
        except ValueError:
            return None
    return None


def parse_fighter_stats(entry: dict) -> dict:
    """One competitor's numbers, from any of the shapes this feed uses.

    Walks label/value pairs wherever they appear rather than indexing a
    fixed position, because a stats payload that adds a column would
    otherwise shift every number one to the left — silently, and while
    somebody is watching a fight.
    """
    out: dict = {"targets": {}, "totals": {}}

    def take(label, value):
        t = _match(label, TARGET_LABELS)
        n = _num(value)
        if n is None:
            return
        if t:
            out["targets"][t] = max(out["targets"].get(t, 0), n)
            return
        e = _match(label, EXTRA_LABELS)
        if e:
            out["totals"][e] = max(out["totals"].get(e, 0), n)

    # Shape A: {"statistics": [{"name"/"label", "value"/"displayValue"}]}
    for block in (entry.get("statistics") or entry.get("stats") or []):
        if isinstance(block, dict):
            label = (block.get("name") or block.get("label")
                     or block.get("abbreviation") or block.get("shortDisplayName"))
            if label is not None:
                take(label, block.get("value", block.get("displayValue")))
            # Shape B: a category wrapping its own list.
            for inner in (block.get("stats") or []):
                if isinstance(inner, dict):
                    take(inner.get("name") or inner.get("label") or "",
                         inner.get("value", inner.get("displayValue")))

    # Shape C: parallel labels[] / stats[] arrays.
    labels = entry.get("labels") or entry.get("names")
    values = entry.get("stats") or entry.get("values")
    if isinstance(labels, list) and isinstance(values, list):
        for label, value in zip(labels, values):
            take(label, value)

    return out


def _name_of(c: dict) -> str:
    ath = c.get("athlete") or c.get("fighter") or {}
    for k in ("displayName", "fullName", "shortName", "name"):
        if isinstance(ath, dict) and ath.get(k):
            return str(ath[k])
    for k in ("displayName", "fullName", "name"):
        if c.get(k):
            return str(c[k])
    return ""


def _status_of(comp: dict) -> dict:
    st = comp.get("status") or {}
    t = st.get("type") or {}
    state = str(t.get("state") or "").lower()
    return {
        "state": state,                       # pre / in / post
        "live": state == "in",
        "detail": str(t.get("shortDetail") or t.get("detail") or ""),
        "round": st.get("period") or st.get("round") or 0,
        "clock": str(st.get("displayClock") or st.get("clock") or ""),
    }


def bout_from_competition(comp: dict) -> dict:
    """One bout: who, what round, and each corner's strikes by target."""
    status = _status_of(comp)
    fighters = []
    for c in (comp.get("competitors") or []):
        stats = parse_fighter_stats(c)
        fighters.append({
            "name": _name_of(c),
            "order": c.get("order"),
            "winner": bool(c.get("winner")),
            "landed": stats["targets"],       # what HE landed
            "totals": stats["totals"],
        })
    # The diagram shows what each fighter ABSORBED, which is the other
    # corner's landed strikes. Doing this here rather than in the page
    # keeps the one easy-to-invert idea in a place with a test on it.
    if len(fighters) == 2:
        a, b = fighters
        a["absorbed"] = dict(b["landed"])
        b["absorbed"] = dict(a["landed"])
    else:
        for f in fighters:
            f["absorbed"] = {}
    for f in fighters:
        f["absorbed_total"] = sum(f["absorbed"].values())
        f["landed_total"] = sum(f["landed"].values())
    return {
        "id": str(comp.get("id") or ""),
        "division": ((comp.get("type") or {}).get("text") or ""),
        "status": status,
        "fighters": fighters,
        "has_targets": any(f["landed"] for f in fighters),
    }


def build(payload: dict, now: str | None = None) -> dict:
    """The live-card payload the page renders."""
    stamp = now or _dt.datetime.now().isoformat(timespec="seconds")
    events = payload.get("events") or []
    if not events:
        return {"status": "no_card", "bouts": [], "generated_at": stamp,
                "note": "No UFC event in the feed right now."}

    ev = events[0]
    comps = list(ev.get("competitions") or [])
    for g in (ev.get("groupings") or []):
        comps += list(g.get("competitions") or [])
    bouts = [bout_from_competition(c) for c in comps]
    live = [b for b in bouts if b["status"]["live"]]
    done = [b for b in bouts if b["status"]["state"] == "post"]

    note = ""
    if not live:
        note = ("No bout is in progress. This page fills itself in while a "
                "fight is happening — there is nothing to show between "
                "them, and inventing something would be worse.")
    elif not any(b["has_targets"] for b in live):
        # The honest failure mode, stated rather than drawn as zeros.
        note = ("The fight is live but this feed is not publishing strikes "
                "by target for it. The body diagram needs head/body/leg "
                "counts; without them it would be a picture of nothing. "
                "Run `python3 launch.py --probe-live` to see exactly what "
                "the feed is sending.")

    return {
        "status": "live" if live else ("card" if bouts else "no_card"),
        "event": str(ev.get("name") or ev.get("shortName") or ""),
        "event_date": str(ev.get("date") or "")[:10],
        "bouts": bouts, "live_count": len(live), "final_count": len(done),
        "generated_at": stamp, "note": note,
        "stale_after_s": STALE_S,
        "disclaimer": ("Significant strikes landed to each target area, as "
                       "published by the feed — not a damage score, and not "
                       "a betting signal. The pre-game model refuses live "
                       "prices by design."),
    }


def fetch(date: str | None = None) -> dict:
    """Today's MMA scoreboard. Cached for seconds, not hours — this is the
    one feed on the site where a stale read is worse than no read."""
    from ..sources.espnmma import _get_json

    day = date or _dt.date.today().isoformat()
    url = ("https://site.web.api.espn.com/apis/site/v2/sports/mma/ufc/"
           "scoreboard?dates=" + day.replace("-", ""))
    return _get_json(url, f"mma_live_{day}.json", ttl=10)


def refresh(date: str | None = None) -> dict:
    return build(fetch(date))


def probe(date: str | None = None) -> list[str]:
    """What the feed is actually sending for a live fight.

    Written for the one moment it matters: a fight is on, the diagram is
    blank, and the question is whether the feed carries target data at all
    or whether we are reading it wrong. This prints every stat label it
    finds, so the answer is visible rather than inferred.
    """
    lines: list[str] = []
    try:
        payload = fetch(date)
    except Exception as exc:  # noqa: BLE001 — a probe reports, never raises
        return [f"feed unreachable: {exc}"]

    events = payload.get("events") or []
    lines.append(f"events: {len(events)}")
    for ev in events:
        lines.append(f"  {ev.get('name') or ev.get('id')}  "
                     f"({str(ev.get('date') or '')[:16]})")
        comps = list(ev.get("competitions") or [])
        for g in (ev.get("groupings") or []):
            comps += list(g.get("competitions") or [])
        for comp in comps:
            st = _status_of(comp)
            names = [_name_of(c) for c in (comp.get("competitors") or [])]
            flag = "LIVE" if st["live"] else st["state"].upper() or "?"
            lines.append(f"    [{flag:4}] {' vs '.join(n or '?' for n in names)}"
                         + (f"  R{st['round']} {st['clock']}" if st["live"] else ""))
            for c in (comp.get("competitors") or []):
                raw = []
                for block in (c.get("statistics") or c.get("stats") or []):
                    if isinstance(block, dict):
                        lab = (block.get("name") or block.get("label")
                               or block.get("abbreviation") or "?")
                        raw.append(f"{lab}={block.get('displayValue', block.get('value'))}")
                if isinstance(c.get("labels"), list):
                    raw += [f"{a}={b}" for a, b in
                            zip(c["labels"], c.get("stats") or [])]
                parsed = parse_fighter_stats(c)
                lines.append(f"      {_name_of(c) or '?'}")
                lines.append(f"        raw: {', '.join(raw[:12]) or '(no stats block)'}")
                lines.append(f"        parsed targets: {parsed['targets'] or '(none)'}"
                             f"  totals: {parsed['totals'] or '(none)'}")

    blob = build(payload)
    lines.append(f"\nstatus: {blob['status']}  live bouts: {blob.get('live_count', 0)}")
    if blob["note"]:
        lines.append(blob["note"])
    if not any(b["has_targets"] for b in blob["bouts"]):
        lines.append(
            "\nNo head/body/leg counts anywhere on this card. If a fight is "
            "LIVE above and the raw lines show stats but none of them name a "
            "target area, this feed publishes totals only — the diagram "
            "cannot be drawn from it and the page will say so rather than "
            "draw an empty body. If the raw lines are empty during a live "
            "fight, the feed publishes stats only after the bout.")
    return lines
