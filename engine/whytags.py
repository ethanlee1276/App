"""Why a bet actually won or lost — the human tag beside the measured one.

MLB_MODEL §11 and UFC_MODEL §11 both park the same half: the journal
carries a MEASURED cause (`engine/causes.py` writes `loss_cause` —
blowout, short run, variance — from the box score) and a process verdict
via CLV, but nothing lets the person watching the game write down what
the machine cannot see. The pitcher was squeezed all night; the corner
threw in a towel the judges disagreed with; the wind flipped at 7pm.

A CONTROLLED VOCABULARY, NOT FREEFORM, and that choice is the design.
Freeform tags are how every trends tab dies: "ump", "umpire", "bad zone"
and "squeezed" are four spellings of one cause, and a slice of one is a
slice of none. Each sport gets a fixed menu, mineable by construction,
with a free-text NOTE beside the tag for the detail — the note is for
reading, the tag is for counting.

The menus were built from what actually beats bets in each sport, and
every entry answers "what would I do differently": a `bad-read` needs a
model fix, a `late-scratch` needs the lineup gate checked, `variance`
needs nothing. That is §11's whole point — the fix for a bad bet depends
on which failure it was.

NOTHING HERE PRICES ANYTHING. Tags are evidence for the reader and, once
enough accumulate, for the loss miner — a tagged dimension it can slice.
"""

from __future__ import annotations

#: Per-sport menus. `shared` applies everywhere and is checked last, so a
#: sport can shadow nothing. Every tag is kebab-case and short because it
#: will be typed by hand at a terminal.
SHARED = {
    "variance": "the read was fine, the coin came up tails",
    "bad-read": "the model (or I) misjudged it — the only tag that means "
                "the MODEL needs fixing",
    "stale-price": "the number was right earlier; I bet it after the "
                   "market had moved",
    "late-news": "information landed after the bet that no process "
                 "would have caught",
}
MENUS = {
    "mlb": {
        "late-scratch": "starter/lineup change after the bet",
        "early-hook": "the manager pulled him before the number had a "
                      "chance",
        "bullpen-game": "the start dissolved into a bullpen night",
        "ump-zone": "the zone squeezed or widened the whole night",
        "weather-flip": "wind/rain changed after pick time",
        "blowout-script": "the game script removed the at-bats/innings",
    },
    "ufc": {
        "early-finish": "the fight ended before the read could matter",
        "judges": "scorecards disagreed with the fight most people saw",
        "weight-cut": "the cut showed — flat from the first round",
        "short-notice-showed": "the replacement fought like one",
        "injury-in-fight": "an injury mid-fight decided it",
        "gameplan": "the corner brought a different fight than the tape",
    },
    "nfl": {
        "late-scratch": "inactive/role change after the bet",
        "script-flip": "the game script inverted the usage",
        "weather-flip": "conditions changed after pick time",
        "injury-in-game": "he left the game early",
    },
}


def menu_for(sport: str) -> dict:
    return {**MENUS.get(str(sport or "").lower(), {}), **SHARED}


def valid(sport: str, tag: str) -> bool:
    return str(tag or "").strip().lower() in menu_for(sport)


def tag_bet(conn, bet_id: int, tag: str, note: str = "") -> dict:
    """Write the tag onto one SETTLED bet. Returns what was written.

    Settled only: §11 is a post-mortem layer, and tagging an open bet is
    predicting — the one thing a why-tag must never be, or the tags stop
    being observations and start being the model grading itself early.
    """
    row = conn.execute("SELECT id, sport, player, market, status FROM bets "
                       "WHERE id=?", (int(bet_id),)).fetchone()
    if row is None:
        raise ValueError(f"no bet with id {bet_id}")
    if row["status"] not in ("won", "lost", "push"):
        raise ValueError(
            f"bet {bet_id} is {row['status']} — tags are a post-mortem, "
            f"and tagging an open bet is predicting")
    t = str(tag).strip().lower()
    if not valid(row["sport"], t):
        opts = ", ".join(sorted(menu_for(row["sport"])))
        raise ValueError(f"{t!r} is not in {row['sport']}'s menu: {opts}")
    conn.execute("UPDATE bets SET why_tag=?, why_note=? WHERE id=?",
                 (t, str(note or "").strip() or None, int(bet_id)))
    conn.commit()
    return {"id": row["id"], "sport": row["sport"], "player": row["player"],
            "market": row["market"], "tag": t,
            "note": str(note or "").strip()}


def tag_counts(conn, sport: str | None = None) -> dict:
    """How the tagged record splits — the §11 readout."""
    q = ("SELECT sport, why_tag, status, COUNT(*) AS n FROM bets "
         "WHERE why_tag IS NOT NULL")
    args: list = []
    if sport:
        q += " AND sport=?"
        args.append(sport)
    out: dict = {}
    for r in conn.execute(q + " GROUP BY sport, why_tag, status", args):
        key = f"{r['sport']}:{r['why_tag']}"
        d = out.setdefault(key, {"won": 0, "lost": 0, "push": 0})
        d[r["status"]] = r["n"]
    return out
