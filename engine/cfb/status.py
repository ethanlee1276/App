"""Quarterback confirmations — the one fact this sport won't hand you.

§2.3 is the strictest rule in the college spec: *no side, total or
QB-adjacent bet is graded final while the starting QB is uncertain —
publish conditionals instead.* The starter-to-backup gap is routinely
worth 4–7 points, which is larger than almost any edge the model will ever
find, so a play made without it isn't a slightly worse play. It's a
coin-flip wearing a number.

**And there is no feed.** College football has no league-mandated injury
report. Some conferences publish availability, most don't; the real
information is beat writers at Thursday practice. Scraping that and
pretending the parse is reliable would be worse than useless, because it
would look identical to knowing.

So this works the way UFC weigh-ins do: the board publishes every
qualifying play as a **conditional** — "IF the starter plays" — with the
number, the edge and the book all stated, and one command promotes it to a
real play once the human has checked:

    python3 launch.py --confirm-qb "Toledo" --starter "Tucker Gleason"

Two properties matter. A confirmation is scoped to a DATE, so last week's
answer can never authorise this week's bet; and a team that has been
positively reported as starting a backup is recorded too — that is a
different thing from silence, and it makes the game a candidate rather
than a hold.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

STORE_FILE = Path("data") / "cfb_qb_status.json"

CONFIRMED = "confirmed"      # the listed starter is playing
BACKUP = "backup"            # positively reported: the starter is OUT
UNKNOWN = "unknown"          # no information — the default, and a hold


def _key(team: str) -> str:
    return (team or "").strip().upper()


def load_store(path: Path | str | None = None) -> dict:
    p = Path(path or STORE_FILE)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record(team: str, game_date: str, state: str = CONFIRMED,
           starter: str = "", note: str = "",
           path: Path | str | None = None) -> dict:
    """Write one team's QB state for one game date."""
    if state not in (CONFIRMED, BACKUP, UNKNOWN):
        raise ValueError(f"unknown QB state {state!r}")
    p = Path(path or STORE_FILE)
    store = load_store(p)
    rec = {"state": state, "starter": starter, "note": note,
           "date": game_date,
           "recorded_at": _dt.datetime.now().isoformat(timespec="seconds")}
    store.setdefault(_key(team), {})[game_date] = rec
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2, sort_keys=True))
    return rec


def state_for(team: str, game_date: str, store: dict) -> dict:
    """This team's QB state for THIS game. Silence is not confirmation."""
    rec = (store.get(_key(team)) or {}).get(game_date)
    if not rec:
        return {"state": UNKNOWN, "starter": "", "note": "",
                "recorded_at": ""}
    return rec


def annotate_game(game: dict, store: dict) -> dict:
    """Attach QB state to a game dict, setting the model's ``qb_confirmed``.

    Both teams have to be confirmed: a game is one price, and the backup
    quarterback on the other sideline reprices it just as hard.
    """
    date = game.get("date") or (game.get("kickoff") or "")[:10]
    home = state_for(game.get("home", ""), date, store)
    away = state_for(game.get("away", ""), date, store)
    known = [s for s in (home, away) if s["state"] != UNKNOWN]
    unknown_teams = [t for t, s in ((game.get("home", ""), home),
                                    (game.get("away", ""), away))
                     if s["state"] == UNKNOWN]

    out = dict(game)
    out["qb_status"] = {"home": home, "away": away}
    out["qb_confirmed"] = not unknown_teams
    if unknown_teams:
        out["qb_uncertain_team"] = " and ".join(t for t in unknown_teams if t)
    # A positively-reported backup is INFORMATION, not a hold — it is one of
    # the few edges an unwatched market genuinely misprices, and refusing to
    # look at it would throw away the sport's biggest lever.
    out["qb_downgrade"] = [t for t, s in ((game.get("home", ""), home),
                                          (game.get("away", ""), away))
                           if s["state"] == BACKUP]
    out["qb_checked_at"] = max((s.get("recorded_at", "") for s in known),
                               default="")
    return out


def certainty(game: dict, assume_confirmed: bool = False) -> float:
    """0–1 information certainty for the §9 grade.

    Quarterback status is worth 0.2 here rather than the lion's share, even
    though it is the biggest single fact in the sport — because §2.3
    already makes it a GATE. Charging it the full 20% weight on top of the
    gate would push every unconfirmed game so far down the board that the
    conditional list, which is the entire point of the rule, would come out
    empty.

    Roster participation only counts against a game in the December window.
    Outside it, "opt-outs unverified" isn't a live risk and docking for it
    would penalise every September Saturday for a bowl-season problem.

    ``assume_confirmed`` answers the question the conditional asks: *what
    would this grade if the pending news came back clean?* It grants
    exactly the credit the pending conditions are withholding and no
    more — otherwise a conditional advertises a grade that confirming it
    could never actually produce.
    """
    from .model import december_window

    st = game.get("qb_status") or {}
    states = [(st.get("home") or {}).get("state", UNKNOWN),
              (st.get("away") or {}).get("state", UNKNOWN)]
    score = 0.5
    if all(s != UNKNOWN for s in states) or assume_confirmed:
        score += 0.2
    december = december_window(game.get("kickoff", ""))
    if not december or game.get("participation_verified") or assume_confirmed:
        score += 0.15
    if game.get("weather_checked"):
        score += 0.15
    return round(min(1.0, score), 3)


def summary(games: list[dict]) -> dict:
    """What the page says about how much of tonight's board is confirmed."""
    total = len(games)
    confirmed = sum(1 for g in games if g.get("qb_confirmed"))
    return {"games": total, "qb_confirmed": confirmed,
            "unconfirmed": total - confirmed,
            "note": ("Every play on an unconfirmed game publishes as a "
                     "conditional — the number and the edge are real, the bet "
                     "waits on the starter. Confirm with "
                     "`python3 launch.py --confirm-qb \"TEAM\"`.")}
