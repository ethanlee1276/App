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


# The scoreboard is a SUMMARY shape and carries no statistics — not
# during a bout and not after one, which a probe run mid-card proved by
# showing an already-finished fight with no stats block either. Numbers
# live on the fuller records below. Tried in order; the first that
# answers wins, and the probe reports which one it was.
def _stat_sources(event_id: str, comp_id: str) -> list[tuple[str, str, str]]:
    """[(label, url, cache-name)] — where per-fighter stats might live."""
    from ..sources.espnmma import CORE

    site = "https://site.web.api.espn.com/apis/site/v2/sports/mma/ufc"
    return [
        ("summary(event)", f"{site}/summary?event={event_id}",
         f"mma_sum_ev_{event_id}.json"),
        ("summary(competition)", f"{site}/summary?competition={comp_id}",
         f"mma_sum_comp_{comp_id}.json"),
        ("core(competition)",
         f"{CORE}/events/{event_id}/competitions/{comp_id}",
         f"mma_core_comp_{comp_id}.json"),
    ]


# A real boxscore nests further than feels reasonable —
# boxscore → players → [] → statistics → [] → athletes → [] is seven
# levels before a fighter's numbers appear, and a shallower cap silently
# returned nothing at all. The guard is a NODE BUDGET rather than a depth
# limit: it bounds the work without having to guess how deep is deep
# enough, which is the guess that was wrong.
_WALK_BUDGET = 20000


def _walk_for_stats(node, depth: int = 0, budget: list | None = None
                    ) -> list[dict]:
    """Every competitor-ish object carrying stats, anywhere in a payload.

    Deliberately a walk rather than a path. ESPN nests MMA statistics
    differently across these three endpoints, and a hard-coded path that
    is right today is a blank body diagram the week it moves. Anything
    with a name and something that parses as a target count is a
    candidate; `build` decides what to do with them.
    """
    found: list[dict] = []
    if budget is None:
        budget = [_WALK_BUDGET]
    if depth > 14 or budget[0] <= 0:
        return found
    budget[0] -= 1
    if isinstance(node, dict):
        if (node.get("athlete") or node.get("fighter")
                or node.get("displayName") or node.get("labels")):
            stats = parse_fighter_stats(node)
            if stats["targets"] or stats["totals"]:
                found.append(node)
        for v in node.values():
            found += _walk_for_stats(v, depth + 1, budget)
    elif isinstance(node, list):
        for v in node:
            found += _walk_for_stats(v, depth + 1, budget)
    return found


def fetch_bout_stats(event_id: str, comp_id: str) -> tuple[list[dict], str]:
    """(competitor entries carrying stats, which source answered)."""
    from ..sources.espnmma import _get_json

    for label, url, cache in _stat_sources(event_id, comp_id):
        try:
            payload = _get_json(url, cache, ttl=10)
        except Exception:  # noqa: BLE001 — try the next one
            continue
        hits = _walk_for_stats(payload)
        if hits:
            return hits, label
    return [], ""


def _merge_stats(bout: dict, entries: list[dict]) -> bool:
    """Fold fetched stats into a bout parsed from the scoreboard.

    Matched by NAME, because the two payloads do not agree on ordering
    and getting a fighter's numbers onto his opponent is the one error
    here that would look completely normal.
    """
    from ..sources.oddsapi import normalize_name

    by_name = {}
    for e in entries:
        n = normalize_name(_name_of(e))
        if n:
            by_name.setdefault(n, parse_fighter_stats(e))
    if not by_name:
        return False

    changed = False
    for f in bout["fighters"]:
        got = by_name.get(normalize_name(f["name"]))
        if not got or not (got["targets"] or got["totals"]):
            continue
        f["landed"] = got["targets"] or f["landed"]
        f["totals"] = got["totals"] or f["totals"]
        changed = True
    if not changed:
        return False

    if len(bout["fighters"]) == 2:
        a, b = bout["fighters"]
        a["absorbed"], b["absorbed"] = dict(b["landed"]), dict(a["landed"])
    for f in bout["fighters"]:
        f["absorbed_total"] = sum(f["absorbed"].values())
        f["landed_total"] = sum(f["landed"].values())
    bout["has_targets"] = any(f["landed"] for f in bout["fighters"])
    return True


def refresh(date: str | None = None) -> dict:
    """The live payload, following through to wherever the stats are.

    Only LIVE bouts are followed. A 14-fight card would otherwise be 14
    extra requests every twelve seconds to re-read numbers that stopped
    changing hours ago.
    """
    payload = fetch(date)
    blob = build(payload)
    event_id = ""
    for ev in (payload.get("events") or []):
        event_id = str(ev.get("id") or "")
        break
    if not event_id:
        return blob

    sources = set()
    for bout in blob["bouts"]:
        if not bout["status"]["live"] or bout["has_targets"]:
            continue
        entries, src = fetch_bout_stats(event_id, bout["id"])
        if entries and _merge_stats(bout, entries):
            sources.add(src)

    if sources:
        blob["stat_source"] = ", ".join(sorted(sources))
        # The note was written for a card with no numbers anywhere; if the
        # deeper read found them, it is no longer true.
        if any(b["has_targets"] for b in blob["bouts"] if b["status"]["live"]):
            blob["note"] = ""
    return blob


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
    lines.append(f"\nscoreboard: {blob['status']}  "
                 f"live bouts: {blob.get('live_count', 0)}")

    # The scoreboard carries no statistics at all — proved by a probe run
    # mid-card that showed an already-FINISHED bout with no stats block
    # either. So the only question that matters is whether the deeper
    # records have them, and this is where that gets answered.
    event_id = str((events[0] or {}).get("id") or "") if events else ""
    live_bouts = [b for b in blob["bouts"] if b["status"]["live"]]
    if not event_id:
        lines.append("no event id — cannot follow to the stats endpoints")
        return lines
    if not live_bouts:
        lines.append("\nNo bout in progress, so nothing to follow. Re-run "
                     "this while a fight is on — that is the only moment "
                     "this question has an answer.")
        return lines

    lines.append(f"\nFollowing the deeper records for {len(live_bouts)} live "
                 f"bout(s) — the scoreboard never carries stats:")
    answered = False
    for bout in live_bouts:
        who = " vs ".join(f["name"] for f in bout["fighters"])
        lines.append(f"  {who}")
        for label, url, cache in _stat_sources(event_id, bout["id"]):
            try:
                from ..sources.espnmma import _get_json
                data = _get_json(url, cache, ttl=10)
            except Exception as exc:  # noqa: BLE001
                lines.append(f"    {label:22} unreachable ({str(exc)[:60]})")
                continue
            hits = _walk_for_stats(data)
            if not hits:
                lines.append(f"    {label:22} reachable, no stats in it")
                continue
            answered = True
            lines.append(f"    {label:22} ✅ {len(hits)} entr(ies) with stats")
            for h in hits[:4]:
                st = parse_fighter_stats(h)
                lines.append(f"      {_name_of(h) or '?'}: "
                             f"targets {st['targets'] or '(none)'}  "
                             f"totals {st['totals'] or '(none)'}")
            break                       # first source that answers wins

    if answered:
        lines.append("\nThe body diagram can be drawn from this. The live "
                     "page follows the same path automatically.")
    else:
        lines.append(
            "\nNone of the deeper records carry per-fighter statistics for "
            "this bout either. That is the real answer: ESPN does not "
            "publish live strike-by-target for this card, and no amount of "
            "waiting or re-reading changes it. The page will say so rather "
            "than draw an empty body. If the stats appear AFTER the bout "
            "ends, a post-fight diagram is still worth having — say the "
            "word and it becomes a round-by-round recap instead of a live "
            "one.")
    return lines
