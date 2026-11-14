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

    def emit(kind, key, sport="mlb", **fields):
        e = {"id": _eid(kind, key), "ts": now, "sport": sport,
             "kind": kind}
        e.update(fields)
        events.append(e)

    # -- last night, fully graded, ONE RECAP PER SPORT ---------------
    # Ethan, 2026-09-14, the NFL board's morning strip reading "LAST
    # NIGHT 1-1 +1.53u": "It seems like it displays MLBs grade for the
    # night no matter what sport is selected." It did — the recap summed
    # the whole journal and every moment was stamped mlb, so the
    # football page wore baseball's line. `recap` is now a mapping of
    # sport → line (a bare line still means mlb), each sport recapped
    # once by its own marker, and the event carries the sport so the
    # page can show its own.
    #
    # MONOTONIC, not just "different": a marker holds one date per
    # sport, and a plain != would re-announce an OLDER night the moment
    # anything handed one in. Recapped nights only move forward.
    recaps = ({} if not recap else {"mlb": recap} if "date" in recap
              else dict(recap))
    by = dict(state.get("recapped_by") or {})
    if state.get("recapped") and "mlb" not in by:
        by["mlb"] = state["recapped"]              # the marker before sports
    # THE LINE, BESIDE THE DATE. Ethan, 2026-09-14, the NFL strip still
    # reading 18-39 after the Record page said 13-12: the recap had fired
    # once for Sunday with Sunday's numbers as they stood, and a night
    # only announces once. But a night's line CAN change after it is
    # announced — sixteen rows graded two days late, and a strip that
    # counted the wrong book was corrected — and the feed kept the first
    # figure. So the same night re-announces when its line has moved,
    # under the same event id, which replaces the old event in the feed
    # rather than adding a second. Older nights still never come back.
    lines = dict(state.get("recapped_line") or {})
    for sp, r in sorted(recaps.items()):
        if not (r and r.get("date")):
            continue
        line = [int(r.get("w", 0)), int(r.get("l", 0)), int(r.get("p", 0)),
                round(float(r.get("net_u", 0.0)), 2)]
        marker = str(by.get(sp) or "")
        fresh = r["date"] > marker
        moved = r["date"] == marker and list(lines.get(sp) or []) != line
        if ((fresh or moved)
                and (r.get("w", 0) + r.get("l", 0) + r.get("p", 0)) > 0
                and not r.get("open", 0)):
            # mlb keeps its pre-sport event id so a deploy does not
            # re-announce a night the feed already carries.
            emit("settle_recap", r["date"] if sp == "mlb" else f"{sp}|{r['date']}",
                 sport=sp, date=r["date"],
                 w=line[0], l=line[1], p=line[2], net_u=line[3])
            by[sp] = r["date"]
            lines[sp] = line
    state["recapped_by"] = by
    state["recapped_line"] = lines
    state["recapped"] = by.get("mlb", state.get("recapped", ""))

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


def last_night(conn, today: str, sport: str | None = None) -> dict | None:
    """Yesterday's line from the journal: {date, w, l, p, net_u, open}.

    By GAME DAY (`ledger.day_expr`), so football — journaled under a
    week label with the calendar in `game_day` — has a night at all.
    ``sport`` narrows it to one league; without it the line pools every
    league, which is what the digest's subject wants and what the
    board's strip must never show.
    """
    from .ledger import day_expr, BOOK
    y = (_dt.date.fromisoformat(today) - _dt.timedelta(days=1)).isoformat()
    # THE SAME BOOK THE RECORD PAGE COUNTS. Ethan, 2026-09-14, the NFL
    # Record tab reading 26 graded while the board's strip read 18-39:
    # since 2026-08-24 the strip had summed the edge book PLUS the
    # anytime-touchdown longshot board — the measurement-only bucket the
    # record never mixes in — and had left paper rows out. Forty-odd
    # touchdown flags made a −2.2u Sunday read −3.07u on the board.
    marks = ",".join("?" * len(BOOK))
    q = ("SELECT SUM(status='won') w, SUM(status='lost') l, "
         "SUM(status='push') p, COALESCE(SUM(pnl_units),0) u, "
         f"SUM(status='open') o FROM bets WHERE {day_expr()}=? "
         f"AND category IN ({marks})")
    args: list = [y, *BOOK]
    if sport:
        q += " AND sport=?"
        args.append(sport)
    row = conn.execute(q, args).fetchone()
    if row is None:
        return None
    return {"date": y, "w": row["w"] or 0, "l": row["l"] or 0,
            "p": row["p"] or 0, "net_u": round(row["u"] or 0.0, 2),
            "open": row["o"] or 0}


#: How far back a sport's last graded slate may be and still be its
#: strip. A football league plays once a week; Sunday's line is the
#: right thing to show on Thursday.
RECAP_LOOKBACK_DAYS = 7


def last_graded_night(conn, today: str, sport: str,
                      lookback: int = RECAP_LOOKBACK_DAYS) -> dict | None:
    """The sport's NEWEST fully graded day inside the lookback.

    Ethan, 2026-09-15: "now only mlb has the last nights bar, nothing
    else does." `last_nights` asked each sport about YESTERDAY only,
    and a recap fires only once a day is fully graded. Baseball plays
    every night and grades by morning, so it always had one. Football
    plays Saturday or Sunday and its props graded on Tuesday — by which
    time Sunday was no longer yesterday, so its recap was never computed
    and the strip stayed empty for the whole week. Walk back from
    yesterday and take the first day that is graded through; a day with
    a bet still open is skipped, not shown half-done.
    """
    day = _dt.date.fromisoformat(today)
    for back in range(1, lookback + 1):
        r = last_night(conn, (day - _dt.timedelta(days=back - 1)).isoformat(),
                       sport=sport)
        if not r:
            continue
        if r["open"]:
            continue
        if (r["w"] + r["l"] + r["p"]) > 0:
            return r
    return None


def last_nights(conn, today: str) -> dict:
    """``{sport: line}`` — every tracked sport's newest fully graded day
    inside the lookback. The strip on each board shows its own."""
    from .ledger import TRACKED_SPORTS
    out: dict = {}
    for sp in TRACKED_SPORTS:
        r = last_graded_night(conn, today, sp)
        if r:
            out[sp] = r
    return out


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
        recap = last_nights(conn, today)
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
