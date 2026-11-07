"""Each play's moment: how much it moved the game, on Real's 0–10 scale.

Ethan, 2026-10-25, sending Real's first screen: a walk-off homer's card
carries a 9.8 in its corner, the batter's and the pitcher's lines so far
and "15th homer this season". This is the number in the corner, and the
two facts under it that Real does not print: the win chance before and
after the play, and whether it tied the game, put a side ahead or ended
it.

THE NUMBER IS THE WIN CHANCE IT MOVED, where a feed gives one. ESPN's
game summary carries a `winprobability` list (the home side's chance
after each play, keyed by the play's id) for football and basketball, and
MLB's own feed gives the same per at-bat (`homeTeamWinProbability`, keyed
by `atBatIndex`). A play's swing is the change from the play before, and
the rating squeezes it onto 0–10 so the biggest swings crowd the top:

    rating = 9.9 × (1 − e^(−|swing| / 18))

  a swing of 80 points (a walk-off) → 9.8   30 → 8.0   10 → 4.2   2 → 1.0

WHERE NO FEED GIVES ONE (hockey, or a payload without the list) it is a
reading of the play itself — what happened, how late, how close —
`_by_kind`, on the same scale, and the row carries no `wp` so the page
never prints a win chance it does not have.

THE TAG IS ARITHMETIC ON THE SCORE, never the feed's words: the score
before and after, and for baseball the inning and half (in the bottom of
the ninth or later, the home side taking the lead ends the game by rule),
and for hockey a goal past regulation.

Nothing here is a prediction of ours: every number is the feed's, or the
score's.
"""

from __future__ import annotations

import math

#: The squeeze above: the swing, in points, that lands at ~6.3.
SCALE = 18.0
CAP = 9.9
#: Where a reading of the play itself tops out, with no win chance on file.
HEURISTIC_CAP = 9.0
#: A play rated this or higher is a big play wherever "big" is asked
#: (the Live tab's feed, the chat's Big plays), whatever kind it is.
BIG = 4.5


def espn_win_chances(payload: dict) -> dict[str, float]:
    """``{play id: the home side's win chance after it, 0–100}`` from an
    ESPN summary's `winprobability` list. Empty when there is none."""
    out: dict[str, float] = {}
    for w in (payload or {}).get("winprobability") or []:
        if not isinstance(w, dict):
            continue
        pid, pct = str(w.get("playId") or ""), w.get("homeWinPercentage")
        if pid and isinstance(pct, (int, float)) and 0 <= pct <= 1:
            out[pid] = round(float(pct) * 100, 1)
    return out


def mlb_win_chances(entries) -> dict[int, float]:
    """``{atBatIndex: home win chance after it, 0–100}`` from MLB's
    `/game/{pk}/winProbability` list (top-level; the index on the entry or
    under its `about`)."""
    out: dict[int, float] = {}
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict):
            continue
        ab = e.get("atBatIndex")
        if ab is None:
            ab = (e.get("about") or {}).get("atBatIndex")
        pct = e.get("homeTeamWinProbability")
        if isinstance(ab, int) and isinstance(pct, (int, float)) and 0 <= pct <= 100:
            out[ab] = round(float(pct), 1)
    return out


def _score(row: dict):
    a, h = row.get("away_score"), row.get("home_score")
    return (a, h) if isinstance(a, int) and isinstance(h, int) else None


def _lead(score) -> int:
    return 0 if score is None else (score[1] > score[0]) - (score[1] < score[0])


def _late(row: dict, league: str) -> float:
    per = row.get("period") or 0
    if league == "mlb":
        inn = row.get("inning") or 0
        return 1.5 if inn >= 9 else 1.3 if inn >= 7 else 1.0
    if league == "nhl":
        return 1.3 if per >= 3 else 1.0
    return 1.4 if per >= 4 else 1.0


_CLOSE = {"mlb": 2, "nhl": 1, "nba": 6, "wnba": 6, "nfl": 8, "cfb": 8}


def _by_kind(row: dict, league: str) -> float:
    """The play's own weight where no win chance is on file."""
    e = str(row.get("event") or "").lower()
    kind = row.get("kind")
    if kind == "football":
        base = (5.5 if row.get("scoring") and "touchdown" in e else
                5.0 if row.get("turnover") or "safety" in e else
                3.0 if row.get("scoring") else
                3.5 if abs(int(row.get("yards") or 0)) >= 20 and not row.get("penalty") else
                2.5 if "sack" in e else 1.0)
    elif kind == "atbat":
        rbi = int(row.get("rbi") or 0)
        base = (5.5 + 0.5 * max(0, rbi - 1) if "home run" in e else
                4.0 + 0.5 * rbi if rbi else
                3.0 if "double play" in e else
                2.0 if "strikeout" in e or row.get("hit") else 1.0)
    elif kind == "hoops":
        base = (2.5 if row.get("scoring") and int(row.get("points") or 0) == 3 else
                2.5 if "dunk" in e else
                2.0 if any(w in e for w in ("block", "steal", "technical", "flagrant")) else 1.0)
    else:
        base = 6.0 if kind == "goal" or "goal" in e else 2.0 if "penalty" in e else 1.0
    after = _score(row)
    close = after is not None and abs(after[1] - after[0]) <= _CLOSE.get(league, 3)
    return base * _late(row, league) * (1.2 if close else 1.0)


def enrich(rows: list[dict], league: str, chances: dict | None = None, key=None) -> list[dict]:
    """Rate every row in place, oldest first; returns the rows.

    `chances` maps a play's key (`key(row)`, its id by default) to the
    home side's win chance after it. Each row gains `rating`, and where
    the feed gave one `wp` (home, after) and `wpa` (the change, signed
    for the home side); a play that tied the game, put a side ahead or
    ended it gains `swing`."""
    chances = chances or {}
    key = key or (lambda r: r.get("id"))
    prev_wp = None
    prev_score = None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        wp = chances.get(key(row))
        if isinstance(wp, (int, float)):
            row["wp"] = wp
            if prev_wp is not None:
                row["wpa"] = round(wp - prev_wp, 1)
            prev_wp = wp
        score = _score(row)
        swing = ""
        if score is not None and prev_score is not None and score != prev_score:
            before, after = _lead(prev_score), _lead(score)
            if (league == "mlb" and row.get("half") == "B" and (row.get("inning") or 0) >= 9
                    and after > 0 and before <= 0):
                swing = "walkoff"
            elif league == "nhl" and (row.get("period") or 0) >= 4 and after != 0:
                swing = "walkoff"
            elif after == 0 and before != 0:
                swing = "tying"
            elif after != 0 and after != before and prev_score != (0, 0):
                # The game's first score puts a side ahead too, and is not
                # what "go-ahead" means to anybody watching.
                swing = "go_ahead"
        if swing:
            row["swing"] = swing
        if score is not None:
            prev_score = score
        if "wpa" in row:
            r = CAP * (1 - math.exp(-abs(row["wpa"]) / SCALE))
        else:
            # A reading, not a measurement: it stops short of the top of
            # the scale, which only a swing the feed measured (or a
            # walk-off) reaches.
            r = min(HEURISTIC_CAP, _by_kind(row, league)
                    + (1.0 if swing == "go_ahead" else 0.7 if swing == "tying" else 0.0))
        if swing == "walkoff":
            r = max(r, 9.5)
        row["rating"] = round(min(CAP, max(0.1, r)), 1)
    return rows
