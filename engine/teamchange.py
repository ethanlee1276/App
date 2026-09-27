"""Which NFL teams are not last season's team — and on which side of the ball.

Ethan, 2026-09-27, on the Jets in the matchup scan: "any team that has a
new QB starting this season or new defense coach or offense coach or new
coach, I feel like the 2026 offense and defense should favor more for
those teams. Like maybe 75/25 or 70/30 ... Last year there defense sucked
and now it's decent this year yet we still rank it pretty low here."

The scan's unit ranks (engine/gamescan) and the red-zone rates
(engine/redzone) blend this season with last at 55/45 from two games on
(gamescan.CURRENT_SHARE). That is right for a team that is still the same
team, and too much of last season for one that is not. A side that
changed leans on this season at gamescan.CHANGED_SHARE instead.

What counts, and which side it moves:

  new head coach        both sides    the schedule (below)
  new starting QB       the offence   the schedule (below)
  new offensive coord.  the offence   data/nfl_staff_changes.json
  new defensive coord.  the defence   data/nfl_staff_changes.json

FROM DATA WHERE IT EXISTS. nflverse stamps every game with both head
coaches and both starting quarterbacks, so a head-coach or QB change is a
diff between last season's games and this season's — no list to go stale.
No free feed carries coordinators, so they are the one hand-kept input:
a team listed in the staff file for this season, and nothing guessed.

A QB change has to be a real one. Last season's QB is the one who started
the most games; this season's likewise, over the games played before the
week being priced. A tie keeps last season's man, so a backup's two
starts while the starter is hurt do not throw away a season of evidence.
Before a team has played, the QB and coach its first game is stamped with.

Never raises: no schedule, or a malformed one, is no changes — the 55/45
blend every team had before this.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

#: The hand-kept coordinator changes, by season: {"2026": {"NYJ": {"dc":
#: "Name"}}}. See the file's own note.
STAFF_FILE = Path(__file__).resolve().parents[1] / "data" / "nfl_staff_changes.json"

#: Which side of the ball each kind of change moves.
SIDES = {"hc": ("off", "def"), "qb": ("off",), "oc": ("off",), "dc": ("def",)}

#: How the card names each kind.
WORDS = {"hc": "new head coach", "qb": "new starting QB",
         "oc": "new offensive coordinator", "dc": "new defensive coordinator"}


def _team(t) -> str:
    from .offseason import _canon_team
    return _canon_team(str(t or "").strip())


def _week(r) -> int | None:
    try:
        return int(float(r.get("week")))
    except (TypeError, ValueError):
        return None


def _played(r) -> bool:
    return str(r.get("home_score") or "").strip() not in ("", "NA")


def _rows(schedules, season: int) -> list[dict]:
    out = [r for r in schedules or [] if str(r.get("season")) == str(season)]
    return sorted(out, key=lambda r: (str(r.get("gameday") or ""), _week(r) or 0))


def _this_season(schedules, season: int, before_week: int | None) -> tuple[list, list]:
    """(this season's games played before the week, its games not yet
    played) — the second is where a team with no games yet reads its
    staff and its QB from."""
    rows = _rows(schedules, season)
    played = [r for r in rows if _played(r)
              and (before_week is None or (_week(r) or 0) < before_week)]
    later = [r for r in rows if not _played(r)
             or (before_week is not None and (_week(r) or 0) >= before_week)]
    return played, later


def head_coaches(schedules, season: int, before_week: int | None = None) -> dict:
    """``{team: (last season's final coach, this season's coach)}``."""
    before: dict = {}
    for r in _rows(schedules, season - 1):
        if not _played(r):
            continue
        for side in ("home", "away"):
            c = str(r.get(f"{side}_coach") or "").strip()
            if c:
                before[_team(r.get(f"{side}_team"))] = c
    played, later = _this_season(schedules, season, before_week)
    now: dict = {}
    # The most recent game played before the week; failing that, the
    # first one still to come.
    for r in played:
        for side in ("home", "away"):
            c = str(r.get(f"{side}_coach") or "").strip()
            if c:
                now[_team(r.get(f"{side}_team"))] = c
    for r in later:
        for side in ("home", "away"):
            c = str(r.get(f"{side}_coach") or "").strip()
            if c:
                now.setdefault(_team(r.get(f"{side}_team")), c)
    return {t: (before.get(t, ""), now[t]) for t in now}


def _qb_counts(rows) -> dict:
    """{team: Counter({qb key: starts})} and each key's name."""
    counts: dict = {}
    names: dict = {}
    for r in rows:
        for side in ("home", "away"):
            name = str(r.get(f"{side}_qb_name") or "").strip()
            if not name:
                continue
            key = str(r.get(f"{side}_qb_id") or "").strip() or name.lower()
            names[key] = name
            counts.setdefault(_team(r.get(f"{side}_team")), Counter())[key] += 1
    return counts, names


def starting_qbs(schedules, season: int, before_week: int | None = None) -> dict:
    """``{team: (last season's QB, this season's QB, same man?)}`` — names,
    "" where the schedule does not say. The same man whenever last
    season's starter has started as many of this season's games as
    anyone (a tie is not a change); compared by the schedule's player id
    where it has one, so two spellings of one name are one man."""
    last, last_names = _qb_counts(r for r in _rows(schedules, season - 1) if _played(r))
    played, later = _this_season(schedules, season, before_week)
    cur, cur_names = _qb_counts(played)
    nxt, _ = _qb_counts(later)
    out: dict = {}
    for team in set(last) | set(cur) | set(nxt):
        was_key = last[team].most_common(1)[0][0] if team in last else ""
        was = last_names.get(was_key, "")
        if team in cur and cur[team]:
            top_key, top_n = cur[team].most_common(1)[0]
            if was_key and cur[team].get(was_key, 0) >= top_n:
                top_key = was_key
            now = cur_names.get(top_key, "")
        elif team in nxt and nxt[team]:
            # Not played yet: the first game still to come names him.
            first = next((r for r in later
                          if team in (_team(r.get("home_team")), _team(r.get("away_team")))), None)
            side = "home" if first and _team(first.get("home_team")) == team else "away"
            now = str((first or {}).get(f"{side}_qb_name") or "").strip()
            top_key = str((first or {}).get(f"{side}_qb_id") or "").strip() or now.lower()
        else:
            continue
        out[team] = (was, now, was_key == top_key if was_key and top_key else True)
    return out


def load_staff(season: int, path: Path | None = None) -> dict:
    """``{team: {"oc": name, "dc": name}}`` for ``season`` from the staff
    file; {} when it is missing or unreadable."""
    try:
        blob = json.loads(Path(path or STAFF_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    got = blob.get(str(season)) if isinstance(blob, dict) else None
    if not isinstance(got, dict):
        return {}
    return {_team(t): {k: str(v).strip() for k, v in (d or {}).items()
                       if k in ("oc", "dc") and str(v or "").strip()}
            for t, d in got.items() if isinstance(d, dict)}


def detect(schedules, season: int, before_week: int | None = None,
           staff: dict | None = None) -> dict:
    """``{team: {"off": [reason, ...], "def": [...]}}`` — only teams with
    a change, only the sides it moves. A reason reads "new starting QB
    (Geno Smith)"."""
    out: dict = {}

    def add(team, kind, who):
        for side in SIDES[kind]:
            out.setdefault(team, {"off": [], "def": []})[side].append(
                f"{WORDS[kind]} ({who})" if who else WORDS[kind])

    try:
        for team, (was, now) in head_coaches(schedules, season, before_week).items():
            if was and now and was.lower() != now.lower():
                add(team, "hc", now)
        for team, (was, now, same) in starting_qbs(schedules, season, before_week).items():
            if was and now and not same:
                add(team, "qb", now)
    except Exception:                                        # noqa: BLE001
        pass
    for team, roles in (staff or {}).items():
        for kind in ("oc", "dc"):
            if roles.get(kind):
                add(team, kind, roles[kind])
    return out


def nfl_changes(season: int, before_week: int | None = None, schedules=None) -> dict:
    """The live call: the cached nflverse schedule plus the staff file."""
    if schedules is None:
        try:
            from .sources.nflverse import load_schedules
            schedules = load_schedules()
        except Exception:                                    # noqa: BLE001
            schedules = []
    return detect(schedules, int(season), before_week, load_staff(int(season)))
