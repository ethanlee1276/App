"""Each fighter's path: how his fights have ended, beside how the model says this one will.

Ethan, 2026-10-15, from the brainstorm he asked to have built: UFC "fight
path". The card already carries the model's six-way read of every fight it
priced (`method`: each man by knockout, submission or decision) and, where
enough finishes are stored, the round it ends in (engine/ufc/rounds). What
it did not carry is the record behind it: how each man's own recent fights
ended — won or lost, by what and in which round — which `ufc_fights` holds
(engine/ufc/history, ESPN's records). This hangs that record on each corner
of every fight the card shows, so the page can put the two side by side.

CONTEXT ONLY. Nothing here moves a price, a grade or a stake: the record is
the dossier's own window of fights (history.WINDOW), counted, and a man
whose fights are not on file yet carries no path rather than an empty one.
"""

from __future__ import annotations

#: How a fight ended, as `ufc_fights.method` stores it, and the page's key.
METHOD_KEY = {"KO/TKO": "ko", "SUB": "sub", "DEC": "dec"}
#: The newest fights listed one by one on the card.
LAST = 5


def record(conn, name: str) -> dict | None:
    """His stored fights, counted: ``{"n", "wins": {ko, sub, dec},
    "losses": {ko, sub, dec}, "draws", "won_in": {round: n},
    "lost_in": {round: n}, "last": [[result, method, round, opp, date]]}``,
    or None when none are on file. A finish's round is where it ended; a
    decision has none. Other endings (a disqualification, a no contest)
    count in ``n`` and nowhere else."""
    from .history import WINDOW, resolve
    stored = resolve(conn, name)
    if not stored:
        return None
    rows = conn.execute("SELECT result, method, rnd, opp, date FROM ufc_fights WHERE fighter=? "
                        "ORDER BY date DESC LIMIT ?", (stored, WINDOW)).fetchall()
    if not rows:
        return None
    out = {"n": len(rows), "wins": {"ko": 0, "sub": 0, "dec": 0}, "losses": {"ko": 0, "sub": 0, "dec": 0},
           "draws": 0, "won_in": {}, "lost_in": {}, "last": []}
    for res, method, rnd, opp, date in rows:
        k = METHOD_KEY.get(method or "")
        if res == "D":
            out["draws"] += 1
        elif k and res in ("W", "L"):
            side = "wins" if res == "W" else "losses"
            out[side][k] += 1
            if k != "dec" and rnd:
                when = out["won_in" if res == "W" else "lost_in"]
                when[str(int(rnd))] = when.get(str(int(rnd)), 0) + 1
        if len(out["last"]) < LAST:
            out["last"].append([res or "", method or "", int(rnd) if rnd and k != "dec" else None, opp or "",
                                str(date or "")[:10]])
    return out


def attach(result: dict, conn) -> int:
    """Hang ``path`` on each corner (``fighters``) of every fight the card
    shows — picks and passes alike. Returns how many corners carry one."""
    n = 0
    seen: dict = {}
    for row in list(result.get("picks") or []) + list(result.get("pass_list") or []):
        if not isinstance(row, dict):
            continue
        for f in row.get("fighters") or []:
            if not isinstance(f, dict) or not f.get("name"):
                continue
            if f["name"] not in seen:
                seen[f["name"]] = record(conn, f["name"])
            if seen[f["name"]]:
                f["path"] = seen[f["name"]]
                n += 1
    return n
