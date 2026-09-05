"""The sweat page's engine: live win probability on the fast clock.

Ethan's roadmap, item 2: "for every journaled bet, show live win
probability updating as the game goes... watching a parlay's % tick up
pitch-by-pitch is the reason people never close FanDuel."

THE MATH ALREADY EXISTED AND RODE THE WRONG CLOCK. engine/livepicks has
computed per-bet live probabilities since mid-August — hitter rates over
remaining plate appearances, pitcher props settled the moment the
starter leaves — but it runs inside mlb_build, the 8-minute board
rebuild. A win probability that updates every eight minutes is the exact
latency bug live_build.py was created to fix for scores. This module
runs the SAME assembly (one function, so the two surfaces cannot
disagree) on live_build's clock: 12 seconds while games are on.

WHAT IT ADDS BEYOND CADENCE:

  * History. Each pick's probability is banked as it moves, thinned to
    the points that matter (≥45s apart or a ≥2-point jump), so the page
    can draw the sweat rather than just state it.
  * Parlays. Open tickets from the parlay ledger get a live joint
    probability — the PRODUCT of their legs' live numbers, labelled as
    exactly that. The pregame modeled_joint priced the correlation
    between legs; conditioning on the live game state re-tangles them in
    ways nothing here has a sample of, so the product is shipped beside
    the pregame joint as an approximation that says its name, not a
    correlation claim.

THE FEED IS PAID: every row names a pick, so sweat.json reaches the
public path through gate.publish like every board.

Reads the SERVED board for context (recommendations, long shots, games)
rather than rebuilding anything — the whole point is to be cheap enough
for a 12-second clock. Board context going stale mid-slate is fine: a
projection does not move during a game; the live inputs are re-fetched
fresh here every cycle.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

STATE_PATH = Path("data/sweatstate.json")
OUT_PUBLIC = Path("web/data/sweat.json")
#: History thinning: a point is banked when this long has passed since
#: the last one, or the probability jumped this far.
HIST_MIN_GAP_S = 45
HIST_MIN_JUMP = 0.02
HIST_CAP = 300


def _key(r: dict) -> str:
    return f"{r.get('player', '')}|{r.get('market', '')}|{r.get('category', 'main')}"


# --- history ---------------------------------------------------------------

def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def bank_history(state: dict, rows: list[dict], now: str) -> dict:
    """Roll each live pick's probability into its history — pure.

    Thinned, not raw: the fast loop fires every 12 seconds and a full
    game of that is a thousand points saying "still 62%". A point earns
    its place by being far enough in time from the last one, or far
    enough in probability. Settled and vanished picks are dropped so the
    state file cannot grow all season.
    """
    ts = now
    keep_keys = set()
    out = dict(state or {})
    for r in rows:
        p = r.get("live_prob")
        k = _key(r)
        keep_keys.add(k)
        if p is None:
            continue
        h = list((out.get(k) or {}).get("h") or [])
        take = True
        if h:
            last_t, last_p = h[-1]
            try:
                gap = (_dt.datetime.fromisoformat(ts)
                       - _dt.datetime.fromisoformat(last_t)).total_seconds()
            except ValueError:
                gap = HIST_MIN_GAP_S
            take = gap >= HIST_MIN_GAP_S or abs(p - last_p) >= HIST_MIN_JUMP
        if take:
            h.append([ts, round(float(p), 3)])
        out[k] = {"h": h[-HIST_CAP:]}
    return {k: v for k, v in out.items() if k in keep_keys}


# --- parlays ---------------------------------------------------------------

def parlay_rows(tickets: list[dict], picks: list[dict]) -> list[dict]:
    """Open tickets with their legs' live numbers joined on — pure.

    A leg matches a pick on (player, market, side, line). A leg with no
    live number leaves the ticket's joint None — a product over a
    missing factor is not a probability, and 62% × nothing is nothing.
    """
    from .sources.oddsapi import normalize_name
    idx = {}
    for r in picks:
        idx[(normalize_name(r.get("player", "")), r.get("market", ""),
             r.get("side", ""), float(r.get("line") or 0))] = r
    out = []
    for t in tickets:
        legs = []
        joint = 1.0
        complete = True
        for leg in t.get("legs") or []:
            pick = idx.get((normalize_name(leg.get("player", "")),
                            leg.get("market", ""), leg.get("side", ""),
                            float(leg.get("line") or 0)))
            p = (pick or {}).get("live_prob")
            settled = str(leg.get("status") or "open")
            if settled == "won":
                p = 1.0
            elif settled == "lost":
                p = 0.0
            legs.append({"player": leg.get("player", ""),
                         "market": leg.get("market", ""),
                         "side": leg.get("side", ""),
                         "line": leg.get("line"),
                         "status": settled,
                         "live_prob": p,
                         "pregame_prob": leg.get("p_final"),
                         "current": (pick or {}).get("current"),
                         "phase": (pick or {}).get("phase")})
            if p is None:
                complete = False
            else:
                joint *= float(p)
        out.append({
            "id": t.get("id"), "book": t.get("book", ""),
            "n_legs": t.get("n_legs"), "stake_units": t.get("stake_units"),
            "quoted_dec": t.get("quoted_dec"),
            "pregame_joint": t.get("modeled_joint"),
            # The label is the honesty: a product of conditionals, not a
            # correlation-priced joint. See the module header.
            "live_joint": round(joint, 4) if complete and legs else None,
            "joint_basis": "product",
            "legs": legs,
        })
    return out


def open_tickets(conn, sport: str, dates: tuple) -> list[dict]:
    from . import parlayledger
    parlayledger.ensure_schema(conn)
    qmarks = ",".join("?" * len(dates))
    tickets = [dict(r) for r in conn.execute(
        f"SELECT id, date, book, n_legs, stake_units, quoted_dec, "
        f"modeled_joint FROM parlays WHERE status='open' AND sport=? "
        f"AND date IN ({qmarks})", (sport, *dates))]
    for t in tickets:
        t["legs"] = [dict(r) for r in conn.execute(
            "SELECT player, market, side, line, odds, p_final, status "
            "FROM parlay_legs WHERE parlay_id=? ORDER BY leg_no", (t["id"],))]
    return tickets


# --- the cycle -------------------------------------------------------------

def build(today: str | None = None, quiet: bool = True,
          now: str | None = None) -> dict | None:
    """One sweat cycle: the served board's context + fresh live inputs
    through the SAME assembly the board uses, plus history and parlays.

    Returns the doc it published, or None when there was nothing to do
    (no board, or no open bets). Every fetch failure degrades to a
    thinner doc rather than no doc — scores keep flowing around us and
    the page falls back to the board's own slower tracker if we vanish.
    """
    from . import gate, ledger
    from .livepicks import assemble_live_picks
    from .mlb.livestats import (current_pitchers, parse_live_stats,
                                parse_situation)
    from .mlb.sources.live import fetch_live
    from .mlb.sources.statslogs import fetch_boxscore, fetch_linescore

    day = today or _dt.date.today().isoformat()
    board = _load(gate.board_source(Path("web/data/mlb_recommendations.json")))
    if not board or board.get("locked"):
        return None
    games = board.get("games") or []
    if not games:
        return None

    # Fresh live state over the board's games — the board's own live
    # blocks are as old as the last slow build.
    try:
        live_map = fetch_live(day)
    except Exception:                                     # noqa: BLE001
        live_map = {}
    progress: dict = {}
    pitching: set = set()
    n_live = 0
    for g in games:
        pair = frozenset((g.get("home"), g.get("away")))
        st = (live_map.get((pair, int(g.get("game_number") or 1)))
              or live_map.get(pair))
        if st is None:
            continue
        pk = None
        for k, v in live_map.items():
            if v is st and isinstance(k, int):
                pk = k
                break
        g["live"] = {"state": st.state, "home_score": st.home_score,
                     "away_score": st.away_score, "period": st.period,
                     "outs": st.outs, "bases": st.bases}
        if st.state not in ("live", "final") or not pk:
            continue
        if st.state == "live":
            n_live += 1
        try:
            box = fetch_boxscore(pk)
            progress.update(parse_live_stats(box))
            if st.state == "live":
                pitching |= current_pitchers(box)
        except Exception:                                 # noqa: BLE001
            pass
        if st.state == "live":
            try:
                g["live"]["situation"] = parse_situation(fetch_linescore(pk))
            except Exception:                             # noqa: BLE001
                pass

    conn = ledger.connect()
    cols = ("player, market, side, line, odds, stake_units, date, "
            "category, hit_prob")
    # 'likely' rides the same clock since 2026-09-05 (Ethan: two panels on
    # the Live page, edge and Most Likely). A likely prop finds its
    # projection the way every row does — `assemble_live_picks` keys the
    # recommendation map on player and market, and every analyzed prop is
    # on that list whether or not it was recommended. The page splits the
    # two by the `category` every row already carries.
    where = ("status='open' AND sport='mlb' "
             "AND category IN ('main','longshot','likely')")
    dates = (day,
             (_dt.date.fromisoformat(day) - _dt.timedelta(days=1)).isoformat(),
             (_dt.date.fromisoformat(day) + _dt.timedelta(days=1)).isoformat())
    open_bets = [dict(r) for r in conn.execute(
        f"SELECT {cols} FROM bets WHERE {where} AND date IN (?,?,?)", dates)]
    if not open_bets:
        conn.close()
        return None

    try:
        from .rosters import identity_map
        from . import db as _db
        hconn = _db.connect()
        ident = identity_map(hconn, "mlb")
        hconn.close()
    except Exception:                                     # noqa: BLE001
        ident = {}
    rows = assemble_live_picks(open_bets, board.get("recommendations") or [],
                               games, progress,
                               board.get("long_shots") or [], ident, pitching)

    now = now or _dt.datetime.now().isoformat(timespec="seconds")
    state = _load(STATE_PATH) or {}
    state = bank_history(state, rows, now)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(STATE_PATH)
    for r in rows:
        r["history"] = (state.get(_key(r)) or {}).get("h") or []

    # PARLAY LEGS ARE NOT NECESSARILY JOURNALED AS SINGLES — a ticket's
    # legs live in the parlay ledger, not the bets table — so joining
    # them only against journaled picks left every un-journaled leg
    # without a number. Each leg becomes a pseudo-bet through the SAME
    # assembly, so a leg's live probability is computed by exactly the
    # machinery a single would get.
    tickets = open_tickets(conn, "mlb", dates)
    conn.close()
    leg_bets = [{"player": leg.get("player", ""),
                 "market": leg.get("market", ""),
                 "side": leg.get("side", ""), "line": leg.get("line"),
                 "odds": leg.get("odds"), "stake_units": 0,
                 "date": t.get("date", day), "category": "parlay",
                 "hit_prob": leg.get("p_final")}
                for t in tickets for leg in t.get("legs") or []]
    leg_rows = assemble_live_picks(
        leg_bets, board.get("recommendations") or [], games, progress,
        board.get("long_shots") or [], ident, pitching) if leg_bets else []
    parlays = parlay_rows(tickets, rows + leg_rows)

    doc = {"generated_at": now, "sport": "mlb", "n_live": n_live,
           "picks": rows, "parlays": parlays}
    gate.publish(doc, OUT_PUBLIC, "sweat.json")
    if not quiet:
        live_n = sum(1 for r in rows if r.get("live_prob") is not None)
        print(f"  sweat: {len(rows)} pick(s), {live_n} with a live number, "
              f"{len(parlays)} parlay(s), {n_live} game(s) live")
    return doc
