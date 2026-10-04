"""Measured causes for lost bets — the postmortem's evidence layer.

The nightly diary's prompt has always asked its writer to "note when a
loss looks like variance" while handing it nothing to reason from —
an invitation to invent. This module computes the verdict BEFORE the
writer ever sees the night: every settled loss gets tagged with the
most specific measurable circumstance the ingested results support,
and the prose lane narrates tags instead of guessing causes. Same
contract as the whole LLM lane: arithmetic decides, prose describes.

Three tags, most specific first, all from data the pipeline already
stores:

* ``blowout (N-pt final)`` — the game's final margin cleared the
  sport's garbage-time threshold. Scripts die in blowouts: starters
  sit, trailing teams stop running, pace evaporates. The margin comes
  off the ingested ``games`` scores via the player's own result row
  (its ``game_id``), so the journal needs no team column.
* ``short run (A of B min)`` — hoops only: the player logged under
  ``SHORT_RUN_FRAC`` of projected minutes (both already journaled on
  the bet row at pick and settle time). Foul trouble, an early exit, a
  coach's hook — the possession half of the projection never showed.
* ``variance`` — no stored circumstance explains the loss; the pick
  just missed. An honest default, not a shrug: it is the tag that
  lets a reader trust the other two.

A blowout outranks short minutes (garbage time is WHY the minutes were
short). UFC losses tag ``variance`` — no scores table, no minutes,
nothing measurable, which is itself the honest reading. NULL in the
column only ever means "not yet swept": the sweep writes a tag for
every settled loss it visits, and a regrade that flips a loss to a win
clears the stale tag on the next pass. Settled history is never
restated — the tag annotates the row, it never touches the grade.
"""

from __future__ import annotations

# Final-margin thresholds where the game script is dead and the tape
# stops resembling the game that was priced. Units are the sport's own
# (runs for MLB, points elsewhere).
BLOWOUT_MARGIN = {"nfl": 17, "cfb": 21, "nba": 20, "wnba": 16, "mlb": 6}

# Under this share of projected minutes the rotation read failed, not
# the shooting model.
SHORT_RUN_FRAC = 0.75

HOOPS = ("nba", "wnba")


def _col(b, name):
    """Optional column off a sqlite3.Row or plain dict fixture."""
    try:
        return b[name] if name in b.keys() else None
    except (AttributeError, TypeError):
        return None


def _final_margin(hconn, b) -> float | None:
    """The final margin of THIS bet's game, or None without clean evidence.

    The bet's own result row (found exactly the way the settler found it,
    doubleheader legs included) names the ``game_id``; the ingested games
    row supplies the score. One ambiguous or missing link → None.
    """
    from .ledger import _hist_where, _leg_row
    from .sources.oddsapi import normalize_name

    where, wargs = _hist_where(b)
    rows = hconn.execute(
        f"SELECT player, game_id FROM player_game_logs WHERE {where} "
        f"AND market=? AND player=?",
        (*wargs, b["market"], b["player"])).fetchall()
    if not rows:
        target = normalize_name(b["player"])
        rows = [r for r in hconn.execute(
                    f"SELECT player, game_id FROM player_game_logs "
                    f"WHERE {where} AND market=?", (*wargs, b["market"]))
                if normalize_name(r["player"]) == target]
    if len(rows) > 1:
        picked = _leg_row(rows, _col(b, "leg"))
        rows = [picked] if picked is not None else rows
    if len(rows) != 1:
        return None
    g = hconn.execute(
        f"SELECT home_score, away_score FROM games WHERE {where} "
        f"AND game_id=?", (*wargs, rows[0]["game_id"])).fetchone()
    if not g or g["home_score"] is None or g["away_score"] is None:
        return None
    return abs(float(g["home_score"]) - float(g["away_score"]))


def cause_of(hconn, b) -> str:
    """The measured cause for one settled loss (see module docstring)."""
    threshold = BLOWOUT_MARGIN.get(b["sport"])
    if threshold:
        try:
            margin = _final_margin(hconn, b)
        except Exception:                          # noqa: BLE001
            margin = None                # evidence unreachable ≠ evidence
        if margin is not None and margin >= threshold:
            unit = "run" if b["sport"] == "mlb" else "pt"
            return f"blowout ({margin:.0f}-{unit} final)"

    if b["sport"] in HOOPS:
        try:
            proj = _col(b, "proj_minutes")
            act = _col(b, "actual_minutes")
            proj = float(proj) if proj is not None else None
            act = float(act) if act is not None else None
        except (TypeError, ValueError):
            proj = act = None
        if proj and act is not None and act < SHORT_RUN_FRAC * proj:
            return f"short run ({act:.0f} of {proj:.0f} min)"

    return "variance"


def backfill(lconn, hconn) -> int:
    """Tag every settled loss that lacks a cause; clear tags a regrade
    orphaned. Runs inside the settle passes, so fresh losses are tagged
    in the same pass that graded them. Idempotent; returns rows written.
    """
    lconn.execute("UPDATE bets SET loss_cause=NULL "
                  "WHERE loss_cause IS NOT NULL AND status != 'lost'")
    n = 0
    for b in lconn.execute("SELECT * FROM bets WHERE status='lost' "
                           "AND loss_cause IS NULL").fetchall():
        lconn.execute("UPDATE bets SET loss_cause=? WHERE id=?",
                      (cause_of(hconn, b), b["id"]))
        n += 1
    lconn.commit()
    return n
