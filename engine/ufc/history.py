"""Every fight a fighter had: the fight history chart (kind "fights").

Ethan, 2026-10-13: "Yes do all of them and don't stop till they are all
done, then make sure they are all routed correctly like nfl." The list he
said yes to had UFC fight history and finish times on it.

WHAT THE RECORD HAS. ESPN's MMA records, which the dossiers are already
drafted from (engine/sources/espnmma.fight_log): each bout he has had —
the date, the opponent, won, lost or neither (a draw or no contest), how
it ended (KO/TKO, submission or decision), the round and the time in it,
how long the fight lasted, the rounds scheduled, the division, and the
per-fight numbers both men put up where ESPN tracked the bout
(significant strikes landed and thrown, takedowns landed and tried,
knockdowns, submission attempts).

ITS OWN TABLE, NOT THE DOSSIER. A dossier is the model's input and a
human may have reviewed it (an auto red flag confirmed or deleted); a
re-draft to add a history would have reset that review. So the history
lives in `ufc_fights`, read from the same cached ESPN responses, and
nothing in it moves a price.

`fill` reads a few fighters at a time (the scheduler's UFC tick does the
upcoming card's, launch.py); `chart` is what the page draws.
"""

from __future__ import annotations

import datetime as _dt

#: Fighters read per call: each is ~60 small, cached requests.
PER_TICK = 4
#: A fighter's history is read again after this many days.
STALE_DAYS = 3
#: The fights kept per fighter (the dossier's own window).
WINDOW = 15
ROUND_S = 300.0
#: His photo, by the ESPN athlete id his fights were read under: the
#: league's own headshot address, as the NFL's faces are.
FACE = "https://a.espncdn.com/i/headshots/mma/players/full/{aid}.png"
COLS = ["fighter", "fighter_id", "comp_id", "event_id", "date", "opp", "opp_id", "result", "method",
        "rnd", "clock", "secs", "rounds", "division", "ssl", "ssa", "tdl", "tda", "kd", "sm",
        "o_ssl", "o_ssa", "o_tdl", "o_tda", "o_kd", "o_sm"]
STATS = ("ssl", "ssa", "tdl", "tda", "kd", "sm")


def _clock(secs) -> str:
    if secs is None:
        return ""
    s = int(round(float(secs)))
    return f"{s // 60}:{s % 60:02d}"


def rows(name: str, aid: str, fights: list[dict]) -> list[dict]:
    """The `ufc_fights` rows for one fighter's `fight_log`."""
    out = []
    for f in fights:
        res = "W" if f.get("winner") is True else "L" if f.get("winner") is False else "D"
        method = f.get("method") or ""
        rounds = int(f.get("rounds") or 3)
        if method == "DEC":
            rnd, clock = rounds, ROUND_S
        else:
            rnd, clock = f.get("period"), f.get("clock")
        own, opp = f.get("own_row") or {}, f.get("opp_row") or {}
        row = {"fighter": name, "fighter_id": str(aid), "comp_id": str(f.get("comp_id") or ""),
               "event_id": str(f.get("event_id") or ""),
               "date": f["date"].isoformat() if hasattr(f.get("date"), "isoformat") else (f.get("date") or ""),
               "opp": f.get("opp_name") or "", "opp_id": str(f.get("opp_id") or ""), "result": res,
               "method": method, "rnd": int(rnd) if rnd else None, "clock": _clock(clock) if rnd else "",
               "secs": round(float(f.get("duration_s") or 0.0), 1), "rounds": rounds,
               "division": f.get("division_text") or ""}
        for k in STATS:
            row[k] = own.get(k)
            row[f"o_{k}"] = opp.get(k)
        if row["comp_id"]:
            out.append(row)
    return out


def fetch(name: str, today: _dt.date | None = None):
    """``(athlete id, fights)`` for a fighter off ESPN, or None when ESPN
    cannot find him."""
    from ..sources import espnmma as E
    aid = E.find_athlete_id(name)
    if not aid:
        return None
    _own, fights, _total = E.fight_log(aid, today or _dt.date.today(), WINDOW, names=True)
    return aid, fights


def owed(conn, names, today: _dt.date | None = None) -> list[str]:
    """The fighters on the card whose history is missing or stale."""
    today = today or _dt.date.today()
    out = []
    for n in names:
        row = conn.execute("SELECT fetched FROM ufc_fighters_read WHERE fighter=?", (n,)).fetchone()
        try:
            fresh = row and (today - _dt.date.fromisoformat(row[0])).days < STALE_DAYS
        except (TypeError, ValueError):
            fresh = False
        if not fresh:
            out.append(n)
    return out


def fill(conn, names, today: _dt.date | None = None, limit: int = PER_TICK, fetch_fn=None) -> dict:
    """Read up to ``limit`` owed fighters' histories into `ufc_fights`.
    Returns ``{"read", "fights", "missing", "left"}``. A fighter ESPN
    cannot find is remembered as read (with no fights) until he is stale
    again, so he does not hold up the rest of the card."""
    from .. import db
    today = today or _dt.date.today()
    fetch_fn = fetch_fn or (lambda n: fetch(n, today))
    todo = owed(conn, names, today)
    out = {"read": 0, "fights": 0, "missing": 0, "left": max(0, len(todo) - limit)}
    for n in todo[:limit]:
        try:
            got = fetch_fn(n)
        except Exception:                                          # noqa: BLE001 — one fighter, never the card
            got = None
        aid, fights = got if got else ("", [])
        if not got:
            out["missing"] += 1
        new = rows(n, aid, fights)
        if new:
            # His fights as ESPN has them now: a bout it re-dated or
            # dropped does not linger.
            conn.execute("DELETE FROM ufc_fights WHERE fighter=?", (n,))
            out["fights"] += db.upsert_ufc_fights(conn, new)
        conn.execute("INSERT OR REPLACE INTO ufc_fighters_read (fighter, fighter_id, fetched, fights) "
                     "VALUES (?,?,?,?)", (n, str(aid), today.isoformat(), len(new)))
        conn.commit()
        out["read"] += 1
    return out


# --- what the page draws ------------------------------------------------------
def resolve(conn, player: str) -> str:
    """The stored spelling of a fighter's name, or ""."""
    from ..carries import _fold
    q = (player or "").strip()
    if not q:
        return ""
    row = conn.execute("SELECT fighter FROM ufc_fights WHERE fighter=? LIMIT 1", (q,)).fetchone()
    if row:
        return row[0]
    want = _fold(q).replace(" ", "")
    hits = [f for (f,) in conn.execute("SELECT DISTINCT fighter FROM ufc_fights")
            if _fold(f).replace(" ", "") == want] if want else []
    return hits[0] if len(hits) == 1 else ""


def _pct(n, d):
    return round(n / d, 3) if d else None


def _line(fs: list[dict]) -> dict:
    """His record over these fights and how they ended."""
    n = len(fs)
    w = [f for f in fs if f["result"] == "W"]
    lo = [f for f in fs if f["result"] == "L"]
    by = lambda xs, m: sum(1 for f in xs if f["method"] == m)  # noqa: E731
    dist = [f for f in fs if f["method"] == "DEC"]
    secs = [f["secs"] for f in fs if f["secs"]]
    return {"n": n, "w": len(w), "l": len(lo), "d": n - len(w) - len(lo),
            "ko_w": by(w, "KO/TKO"), "sub_w": by(w, "SUB"), "dec_w": by(w, "DEC"),
            "ko_l": by(lo, "KO/TKO"), "sub_l": by(lo, "SUB"), "dec_l": by(lo, "DEC"),
            "finish_w": _pct(by(w, "KO/TKO") + by(w, "SUB"), len(w)),
            "distance": _pct(len(dist), n),
            "r1": sum(1 for f in fs if f["method"] in ("KO/TKO", "SUB") and f["rnd"] == 1),
            "avg_secs": round(sum(secs) / len(secs), 1) if secs else None}


def _stats(f: dict) -> list:
    """That fight's numbers, his beside his opponent's, where ESPN
    tracked the bout."""
    out = []
    for key, name, att in (("ssl", "Significant strikes", "ssa"), ("tdl", "Takedowns", "tda"),
                           ("kd", "Knockdowns", None), ("sm", "Submission attempts", None)):
        me, them = f.get(key), f.get(f"o_{key}")
        if me is None and them is None:
            continue
        out.append({"key": key, "name": name, "me": me, "opp": them,
                    "me_att": f.get(att) if att else None, "opp_att": f.get(f"o_{att}") if att else None})
    return out


def chart(conn, player: str, season=None) -> dict:
    """Everything the fight history draws for one fighter: ``{player,
    sport, seasons, season, position, face, games: [{id, date, opp, home,
    result, method, rnd, clock, secs, rounds, division, stats}],
    season_line, by_method, by_rounds, by_finish}``, fights newest first.
    ``{}`` when none is on file."""
    try:
        name = resolve(conn, player)
    except Exception:                                              # noqa: BLE001 — no table yet
        return {}
    if not name:
        return {}
    cur = conn.execute(f"SELECT {', '.join(COLS)} FROM ufc_fights WHERE fighter=? "
                       "ORDER BY date DESC, comp_id DESC", (name,))
    fights = [dict(zip(COLS, r)) for r in cur.fetchall()]
    if not fights:
        return {}
    games = [{"id": f["comp_id"], "date": f["date"], "opp": f["opp"] or "his opponent", "home": True,
              "team": "", "result": f["result"], "method": f["method"], "rnd": f["rnd"], "clock": f["clock"],
              "secs": f["secs"], "rounds": f["rounds"], "division": f["division"], "stats": _stats(f),
              "line": {"n": 1}} for f in fights]
    by_method = [{"key": m, "name": label, "w": sum(1 for f in fights if f["result"] == "W" and f["method"] == m),
                  "l": sum(1 for f in fights if f["result"] == "L" and f["method"] == m)}
                 for m, label in (("KO/TKO", "KO/TKO"), ("SUB", "Submission"), ("DEC", "Decision"))]
    by_rounds = [dict(_line([f for f in fights if f["rounds"] == r]), rounds=r)
                 for r in (3, 5) if any(f["rounds"] == r for f in fights)]
    finish = {}
    for f in fights:
        k = "Decision" if f["method"] == "DEC" else f"Round {f['rnd']}" if f["rnd"] else "Unknown"
        finish[k] = finish.get(k, 0) + 1
    by_finish = [{"name": k, "n": v} for k, v in sorted(finish.items(), key=lambda kv: (kv[0] == "Decision", kv[0]))]
    aid = next((f["fighter_id"] for f in fights if f["fighter_id"]), "")
    return {"player": name, "sport": "ufc", "seasons": [0], "season": 0,
            "position": (fights[0]["division"] or "").title(), "team": "",
            "face": FACE.format(aid=aid) if aid.isdigit() else "",
            "games": games, "season_line": _line(fights), "by_method": by_method,
            "by_rounds": by_rounds, "by_finish": by_finish}
