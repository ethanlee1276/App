"""Anchored daily moments: the day's rhythm, published as feed events.

Ethan's roadmap, item 3: "Structure the day so there are 4-5 known times
to check in, each with its own payload... ~9am 'The Card': today's board
+ last night's settle recap. Two dopamine hits in one visit."

NOTHING HERE IS SCHEDULED. Each moment fires when the thing it announces
actually happens — the card when the board first stands, the recap when
last night's grading finishes, first pitch when a game actually goes
live, the ump when the crew actually posts. The pipeline's own rhythm IS
the schedule; announcing at 9am a card that built at 9:40 would be the
feed lying about the one thing a feed is for.

EACH MOMENT FIRES ONCE. The state file remembers what has been said for
which date, because the loop passes this way every sixty seconds and
"The card is up" forty times before noon is an alarm clock nobody asked
for. Events ride the same feed as item 1's diffs — same file, same gate,
same page — so the day's rhythm and the market's churn read as one
stream, newest first.

  settle_recap   last night fully graded: "went 7-4, +3.2u". Waits for
                 the LAST open bet of that date to close — a recap of a
                 half-graded night would restate itself hourly with
                 different numbers, which is a correction, not a moment.
  card_posted    today's board first stands with recommended picks.
  ump_assigned   a plate umpire appears on a game, with his measured K
                 tilt when we have one — announced hours before first
                 pitch, which is why it is news.
  first_pitch    the day's first live game: "the sweat is on".
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from . import feedstate as _feedstate

STATE_PATH = Path(_feedstate.path("moments.json"))

#: The ump tilt worth a sentence, either side of neutral. Under it the
#: profile is noise wearing a name.
UMP_TILT = 0.03


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _eid(kind: str, key: str) -> str:
    import hashlib
    return hashlib.sha1(f"moment|{kind}|{key}".encode()).hexdigest()[:12]


def derive(board: dict, live_games: list, recap: dict | None,
           state: dict, today: str, now: str,
           autopsy: dict | None = None) -> tuple[list, dict]:
    """Events due right now, plus the state that remembers them — pure.

    ``recap`` is last night's ledger summary ({date, w, l, p, net_u,
    open}) or None; ``live_games`` the fast scoreboard's rows; ``board``
    the served slate; ``autopsy`` the newest nightly postmortem entry
    ({date, headline}) or None. The caller owns all I/O.
    """
    state = dict(state or {})
    if state.get("date") != today:
        # A new day forgets yesterday's announcements — except the
        # markers keyed by the night they describe: the recap and the
        # autopsy both only ever move forward.
        state = {"date": today, "umps": {},
                 "recapped": state.get("recapped", ""),
                 "autopsied": state.get("autopsied", "")}
    events: list = []

    def emit(kind, key, **fields):
        e = {"id": _eid(kind, key), "ts": now, "sport": "mlb",
             "kind": kind}
        e.update(fields)
        events.append(e)

    # -- last night, fully graded ------------------------------------
    # MONOTONIC, not just "different": the marker holds one date, and a
    # plain != would re-announce an OLDER night the moment anything
    # handed one in. Recapped nights only move forward (ISO dates sort).
    if (recap and recap.get("date")
            and recap["date"] > str(state.get("recapped") or "")
            and (recap.get("w", 0) + recap.get("l", 0) + recap.get("p", 0)) > 0
            and not recap.get("open", 0)):
        emit("settle_recap", recap["date"], date=recap["date"],
             w=recap.get("w", 0), l=recap.get("l", 0), p=recap.get("p", 0),
             net_u=round(float(recap.get("net_u", 0.0)), 2))
        state["recapped"] = recap["date"]

    # -- the autopsy -------------------------------------------------
    # The roadmap's late-night anchor and #6's celebration in one: when
    # the nightly postmortem lands (engine/prose.py — the honest "what
    # we got wrong and why" the Results page publishes), the feed says
    # so, headline attached. Same monotonic marker discipline as the
    # recap: a date only announces once and only ever moves forward.
    if (autopsy and autopsy.get("date")
            and autopsy["date"] > str(state.get("autopsied") or "")):
        emit("autopsy_posted", autopsy["date"], date=autopsy["date"],
             headline=str(autopsy.get("headline") or "")[:120])
        state["autopsied"] = autopsy["date"]

    # -- the card ----------------------------------------------------
    recs = [r for r in (board or {}).get("recommendations") or []
            if r.get("recommended")]
    if recs and not state.get("card_posted"):
        best = max(recs, key=lambda r: r.get("ev_per_unit") or 0)
        games = {(g.get("home"), g.get("away"))
                 for g in (board or {}).get("games") or []}
        emit("card_posted", today, n_picks=len(recs),
             n_games=len(games),
             best={"player": best.get("player", ""),
                   "label": best.get("market_label", ""),
                   "side": best.get("side", ""),
                   "line": best.get("line"),
                   "ev": best.get("ev_per_unit")})
        state["card_posted"] = True

    # -- ump assignments ---------------------------------------------
    for g in (board or {}).get("games") or []:
        ump = (g.get("plate_umpire") or "").strip()
        if not ump:
            continue
        gkey = f"{g.get('away')}@{g.get('home')}#{g.get('game_number') or 1}"
        if state["umps"].get(gkey) == ump:
            continue
        kf = g.get("ump_k_factor")
        tilt = None
        if kf is not None and abs(float(kf) - 1.0) >= UMP_TILT:
            tilt = "over" if float(kf) > 1.0 else "under"
        emit("ump_assigned", f"{today}|{gkey}", ump=ump,
             home=g.get("home"), away=g.get("away"),
             k_tilt=tilt, k_factor=kf)
        state["umps"][gkey] = ump

    # -- first pitch -------------------------------------------------
    n_live = sum(1 for g in live_games or []
                 if ((g.get("live") or {}).get("state")) == "live")
    if n_live and not state.get("first_pitch"):
        emit("first_pitch", today, n_live=n_live,
             n_open=int((board or {}).get("open_tonight") or 0)
             or len([1 for r in (board or {}).get("live_picks") or []]))
        state["first_pitch"] = True

    return events, state


def last_night(conn, today: str) -> dict | None:
    """Yesterday's line from the journal: {date, w, l, p, net_u, open}."""
    y = (_dt.date.fromisoformat(today) - _dt.timedelta(days=1)).isoformat()
    row = conn.execute(
        "SELECT SUM(status='won') w, SUM(status='lost') l, "
        "SUM(status='push') p, COALESCE(SUM(pnl_units),0) u, "
        "SUM(status='open') o FROM bets WHERE date=? "
        "AND category IN ('main','longshot')", (y,)).fetchone()
    if row is None:
        return None
    return {"date": y, "w": row["w"] or 0, "l": row["l"] or 0,
            "p": row["p"] or 0, "net_u": round(row["u"] or 0.0, 2),
            "open": row["o"] or 0}


def run(quiet: bool = True, today: str | None = None,
        now: str | None = None) -> int:
    """One pass: derive due moments and publish them into the feed."""
    from . import feed, gate, ledger

    today = today or _dt.date.today().isoformat()
    now = now or _dt.datetime.now().isoformat(timespec="seconds")
    try:
        board = json.loads(
            gate.board_source(Path("web/data/mlb_recommendations.json"))
            .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        board = {}
    try:
        live_games = (json.loads(
            Path("web/data/live_mlb.json").read_text(encoding="utf-8"))
            .get("games") or [])
    except (OSError, ValueError):
        live_games = []
    conn = ledger.connect()
    try:
        recap = last_night(conn, today)
    finally:
        conn.close()
    # The newest nightly postmortem, straight from the prose store —
    # reading the store beats re-parsing record.json for one field.
    autopsy = None
    try:
        from .prose import POSTMORTEM_PATH
        entries = json.loads(Path(POSTMORTEM_PATH).read_text(
            encoding="utf-8"))
        if isinstance(entries, list) and entries:
            autopsy = max((e for e in entries if isinstance(e, dict)
                           and e.get("date")),
                          key=lambda e: e["date"], default=None)
    except (OSError, ValueError):
        autopsy = None
    events, state = derive(board, live_games, recap, _load_state(),
                           today, now, autopsy=autopsy)
    _save_state(state)
    if events:
        feed.publish(events, now=now)
        if not quiet:
            print(f"  moments: {', '.join(e['kind'] for e in events)}")
    return len(events)
