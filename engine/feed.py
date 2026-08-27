"""The live feed: every rebuild diffed into events worth opening the app for.

Ethan, 2026-08-24: "The board rebuilds every 60s and the site shows only
the latest snapshot. Diff consecutive builds and publish the diff as a
live activity feed... every entry is a reason someone opened the app at
2:47pm."

He is right that it is nearly free. The detectors that notice these
moments have existed for weeks — the board stamps move_delta and steam,
lineupwatch knows the release moment, the gates decide `recommended`
every cycle — and every one of them threw its answer away sixty seconds
later when the next build overwrote the file. This module is the memory:
a compact digest of each build is kept, the next build is diffed against
it, and the differences accumulate in a rolling public feed.

WHAT COUNTS AS AN EVENT, and the one rule under all of them: an event is
a CHANGE THE BOARD ALREADY BELIEVES, never a re-derivation. "Edge
appeared" is the board's own `recommended` flag turning on — the same
gates, thresholds and vetoes that decide the card decide the feed, so
the two can never disagree about what qualifies.

  edge_appeared   a prop the gates now recommend (new, or newly cleared)
  edge_died       one they recommended last build and refuse now — with
                  the reason read off the diff: the line moved, the price
                  moved, or the prop left the board entirely
  line_move       a priced prop's line changed; when the model's own
                  projection HELD while the book moved, the event says
                  which way the edge went — that sentence is the whole
                  reason line moves are worth publishing
  price_move      the odds moved ≥ 2 implied points with the line still
  released        held props (model-only, no book line) got priced — the
                  lineup-drop moment, summarized as one event per build
                  because fourteen separate rows is noise, not news

COLD START IS SILENT. The first scan of a board has nothing to diff
against; it stores the digest and emits nothing. A feed that greets its
first reader with two hundred "appeared" rows is announcing its own
deployment, not the market.

THE FEED IS PAID. Every entry names a pick — an edge appearing IS a
recommendation — so feed.json is in gate.PAID_FILES and reaches the
public path through gate.publish() like every other board: full copy for
subscribers, locked stub outside the wall.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

from .odds import american_to_prob

STATE_DIR = Path("data/feedstate")
FEED_PUBLIC = Path("web/data/feed.json")
MAX_EVENTS = 250
MAX_AGE_H = 48
#: A price move worth publishing, in implied-probability points.
PRICE_MOVE_PTS = 0.02
#: Below this many releases in one build they are still one event —
#: a release is only news as a WAVE (the lineup-drop moment).
RELEASE_MIN = 1

#: A starter down this much on the four-seam is the red flag the MLB
#: model doc calls out ("a drop of 1+ mph"). The event fires when a row
#: FIRST crosses it — velocity is measured once per start, so there is
#: no churn to debounce, only the moment the number lands.
VELO_FLAG = -1.0

#: Stale-line events per build. The scanner can hold a dozen stale
#: quotes at once; the feed announces the widest few and the Scanner
#: page holds the full table — a wall of near-identical alerts is how a
#: feed stops being read.
STALE_MAX_PER_BUILD = 3


def _key(r: dict) -> str:
    return f"{r.get('player', '')}|{r.get('market', '')}"


def digest(board: dict) -> dict:
    """One build, compacted to what the next diff needs."""
    out: dict = {}
    for r in board.get("recommendations") or []:
        k = _key(r)
        if not k.strip("|"):
            continue
        out[k] = {
            "player": r.get("player", ""),
            # WHOSE GAME IT IS. Carried so a reader can watch a team
            # rather than a name — "anything in the Bengals game" is the
            # second most common thing anybody wants told about, and the
            # feed had no field that could answer it. One key, off a row
            # that already holds it.
            "team": (r.get("team") or "").upper(),
            "opponent": (r.get("opponent") or "").upper(),
            "market": r.get("market", ""),
            "label": r.get("market_label", "") or r.get("market", ""),
            "side": r.get("side", ""),
            "line": r.get("line"),
            "odds": r.get("odds"),
            "book": r.get("book", ""),
            "proj": r.get("projection"),
            "ev": r.get("ev_per_unit"),
            "edge": r.get("edge"),
            "rec": bool(r.get("recommended")),
            "priced": r.get("has_market") is not False,
            # §5's velocity tell (MLB pitcher props) — None elsewhere.
            "velo": r.get("velo_delta"),
        }
    return out


def _eid(kind: str, key: str, ts: str, extra: str = "") -> str:
    raw = f"{kind}|{key}|{ts[:16]}|{extra}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _imp(odds) -> float | None:
    try:
        return american_to_prob(int(odds))
    except Exception:                                     # noqa: BLE001
        return None


def diff(prev: dict, cur: dict, sport: str, ts: str) -> list[dict]:
    """Events between two digests — pure, and the heart of the feature."""
    events: list[dict] = []
    released: list[dict] = []

    def base(kind, c, key, **extra):
        e = {"id": _eid(kind, key, ts, str(extra.get("to", ""))),
             "ts": ts, "sport": sport, "kind": kind,
             "player": c["player"], "label": c["label"],
             "team": c.get("team", ""), "opponent": c.get("opponent", ""),
             "side": c["side"], "line": c["line"],
             "book": c["book"], "odds": c["odds"]}
        e.update(extra)
        return e

    state_changed: set = set()
    for key, c in cur.items():
        p = prev.get(key)
        if p is None:
            # New to the board mid-day. Only its edges are events —
            # every board rebuild adds and drops fringe rows.
            if c["rec"]:
                events.append(base("edge_appeared", c, key,
                                   ev=c["ev"], edge=c["edge"]))
            continue
        if c["rec"] and not p["rec"]:
            state_changed.add(key)
            events.append(base("edge_appeared", c, key,
                               ev=c["ev"], edge=c["edge"]))
        elif p["rec"] and not c["rec"]:
            state_changed.add(key)
            if c["line"] != p["line"] and c["line"] is not None:
                why = "line_moved"
            else:
                pi, ci = _imp(p["odds"]), _imp(c["odds"])
                why = ("price_moved" if pi is not None and ci is not None
                       and abs(ci - pi) >= PRICE_MOVE_PTS else "gates")
            events.append(base("edge_died", c, key, reason=why,
                               frm=p["line"], to=c["line"]))
        if c["priced"] and not p["priced"]:
            released.append(c)
            continue
        if not (c["priced"] and p["priced"]):
            continue
        if key in state_changed:
            # The appeared/died event already carries the move that
            # caused it — a second row for the same change is noise.
            continue
        if (c["line"] is not None and p["line"] is not None
                and c["line"] != p["line"]):
            # The model-held sentence: the book moved, our projection
            # did not, so the gap between them changed by the move.
            held = (c["proj"] is not None and p["proj"] is not None
                    and abs(float(c["proj"]) - float(p["proj"])) < 1e-9)
            events.append(base("line_move", c, key,
                               frm=p["line"], to=c["line"],
                               proj=c["proj"], model_held=held,
                               edge=c["edge"], rec=c["rec"]))
        else:
            pi, ci = _imp(p["odds"]), _imp(c["odds"])
            if (pi is not None and ci is not None
                    and abs(ci - pi) >= PRICE_MOVE_PTS):
                events.append(base("price_move", c, key,
                                   frm=p["odds"], to=c["odds"],
                                   imp_delta=round(ci - pi, 3),
                                   edge=c["edge"], rec=c["rec"]))

    # The velocity red flag — the last of the roadmap's five promised
    # event kinds ("starter down 1.4mph on the four-seam"). Fires on the
    # build where the number FIRST crosses the flag line: warm-up
    # readings land once per start, so prev-missing → cur-flagged is the
    # moment the engine learned it. Old state files predate the `velo`
    # key, so `.get` — their first pass may announce a currently-flagged
    # starter once, which is true today rather than stale.
    for key, c in cur.items():
        cv = c.get("velo")
        if cv is None or float(cv) > VELO_FLAG:
            continue
        p = prev.get(key)
        pv = p.get("velo") if p else None
        if pv is not None and float(pv) <= VELO_FLAG:
            continue                    # already announced when it landed
        events.append(base("velocity_flag", c, key,
                           delta=round(float(cv), 1), rec=c["rec"]))

    for key, p in prev.items():
        if key not in cur and p["rec"]:
            events.append(base("edge_died", p, key, reason="left_board"))

    if len(released) >= RELEASE_MIN:
        top = sorted(released, key=lambda r: (r["ev"] or 0), reverse=True)
        events.append({
            "id": _eid("released", sport, ts, str(len(released))),
            "ts": ts, "sport": sport, "kind": "released",
            "n": len(released),
            "players": [f"{r['player']} ({r['label']})" for r in top[:4]],
        })
    return events


def _stale_key(row: dict) -> str:
    return "|".join(str(row.get(k, "")) for k in
                    ("player", "market", "book", "side", "line"))


def stale_diff(prev_keys: set, stale_rows: list, sport: str,
               ts: str) -> tuple[list[dict], list[str]]:
    """(events for NEWLY stale quotes, all current keys) — pure.

    The roadmap's sniper ("this book hasn't moved yet"): the Scanner page
    has always held the full stale table, but a table is where you look
    when you already suspect something — the feed is where the MOMENT a
    book falls behind the field becomes a sentence with a timestamp.
    Only quotes that were NOT stale last build fire; a book that stays
    behind for an hour is one event, not sixty. Pre-game only — an
    in-play "stale" quote is just a book pausing its live trading.
    """
    rows = [r for r in stale_rows or []
            if not r.get("live") and not r.get("started")]
    cur_keys = [_stale_key(r) for r in rows]
    fresh = [r for r, k in zip(rows, cur_keys) if k not in prev_keys]
    fresh.sort(key=lambda r: -(float(r.get("edge") or 0)))
    events = []
    for r in fresh[:STALE_MAX_PER_BUILD]:
        events.append({
            "id": _eid("stale_line", _stale_key(r), ts,
                       str(r.get("odds", ""))),
            "ts": ts, "sport": sport, "kind": "stale_line",
            "player": r.get("player", ""), "bet": r.get("bet", ""),
            "book": r.get("book", ""), "side": r.get("side", ""),
            "line": r.get("line"), "odds": r.get("odds"),
            "gap": round(float(r.get("edge") or 0), 3),
            "consensus": r.get("consensus"),
        })
    return events, cur_keys


# --- the state and the public file -----------------------------------------

def _state_path(sport: str) -> Path:
    return STATE_DIR / f"{sport}.json"


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def scan(sport: str, board_path, now: str | None = None) -> list[dict]:
    """Diff one board against its stored digest; roll the state forward.

    Returns the new events (possibly []). The first sight of a board
    stores its digest and returns nothing — see the module header.
    """
    board = _load_json(Path(board_path))
    if not board or board.get("locked"):
        return []
    ts = now or _dt.datetime.now().isoformat(timespec="seconds")
    cur = digest(board)
    if not cur and not board.get("recommendations"):
        # An empty slate is a fact, not a wave of edge_died events —
        # but only when the board itself says so. A missing file above
        # returned [] without touching state.
        pass
    stale_rows = (board.get("market_scan") or {}).get("stale") or []
    sp = _state_path(sport)
    prev_doc = _load_json(sp)
    prev_stale = set((prev_doc or {}).get("stale") or [])
    stale_events, stale_keys = stale_diff(prev_stale, stale_rows, sport, ts)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = sp.with_suffix(".tmp")
    tmp.write_text(json.dumps({"ts": ts, "digest": cur,
                               "stale": stale_keys}), encoding="utf-8")
    tmp.replace(sp)
    if prev_doc is None:
        return []                       # cold start is silent
    return diff(prev_doc.get("digest") or {}, cur, sport, ts) + stale_events


def prune(events: list[dict], now: str | None = None) -> list[dict]:
    ts = now or _dt.datetime.now().isoformat(timespec="seconds")
    try:
        cutoff = (_dt.datetime.fromisoformat(ts)
                  - _dt.timedelta(hours=MAX_AGE_H)).isoformat()
    except ValueError:
        cutoff = ""
    keep = [e for e in events if str(e.get("ts", "")) >= cutoff]
    keep.sort(key=lambda e: str(e.get("ts", "")), reverse=True)
    return keep[:MAX_EVENTS]


def publish(new_events: list[dict], now: str | None = None) -> int:
    """Merge new events into the rolling public feed, through the gate."""
    from . import gate
    ts = now or _dt.datetime.now().isoformat(timespec="seconds")
    prior = _load_json(gate.board_source(FEED_PUBLIC)) or {}
    seen = {e.get("id") for e in prior.get("events") or []}
    merged = (prior.get("events") or []) + [
        e for e in new_events if e.get("id") not in seen]
    doc = {"generated_at": ts, "events": prune(merged, now=ts)}
    gate.publish(doc, FEED_PUBLIC, "feed.json")
    return len(doc["events"])


def scan_all(boards: dict, quiet: bool = True,
             now: str | None = None) -> int:
    """One pass over every board: {sport: path}. Called from the launch
    loop's refresh sweep, same shape as _seal_forecasts — a sweep cannot
    be forgotten by the next sport somebody adds."""
    fresh: list[dict] = []
    for sport, path in boards.items():
        try:
            fresh += scan(sport, path, now=now)
        except Exception as exc:                          # noqa: BLE001
            if not quiet:
                print(f"  feed: {sport} scan failed — "
                      f"{type(exc).__name__}: {exc}")
    if fresh:
        n = publish(fresh, now=now)
        if not quiet:
            print(f"  feed: {len(fresh)} new event(s), {n} on the wire")
    return len(fresh)
