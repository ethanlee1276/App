"""THE CONFERENCES' OWN WORD ON WHO PLAYS (decision 20, step ADB, 23 November 2026).

Ethan, 23 November: "decision 20 is a yes if it helps and get us more up to date info for the users". The ACC, the
SEC and the Big 12 have published every school's availability report for each conference game since 2025, and the
Big Ten since 2026: on the evenings before the game (the ACC and the Big 12 say Available, Probable, Questionable,
Doubtful or Out) and on game day about 90 minutes before kickoff (Available, Game Time Decision or Out). ESPN's
college injury board, the one source college read until now, is thinner and slower than that.

This module is the part that does not depend on how each conference publishes: the report's words in the engine's
statuses, a report's names in the board's spelling, the cache the box writes (data/cfb_availability.json, one
filing per school per game, newest kept), and the rule that lays a school's filing over ESPN's board:

  * a man on both: the newer word wins (a filing undated on ESPN's side loses to the school's);
  * a man the school lists Available or Probable: cleared, his props priced (counted in ``cleared``);
  * a man only ESPN lists questionable, doubtful or a game-time decision, on a school whose newer filing leaves him
    off: dropped, as an NFL club's own report drops the board's stale tag (injuries.merge_injuries, 14 November);
  * a man only ESPN lists out: kept — a school's report is about one game, the board's out is often longer;
  * a man only the school lists: added.

A school with no filing for its game keeps ESPN's board as it was. Off without a deploy:
``sudo ./deploy/setenv.sh QB_CFB_AVAIL off``.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path

from ..models import Injury

ENV = "QB_CFB_AVAIL"
CACHE = Path(__file__).resolve().parents[2] / "data" / "cfb_availability.json"
#: A filing this long after its game's kickoff is about a game already played.
AFTER_KICKOFF_S = 6 * 3600

#: The report's word -> the engine's status; "" plays. First match wins, so "not available" is read before
#: "available" and "game time decision" before anything else.
WORDS = (
    (re.compile(r"\bgame[\s-]*time\b|\bgtd\b", re.I), "GTD"),
    (re.compile(r"\bunavailable\b|\bnot\s+available\b|\bout\b|\bsuspend|\binjured\s+reserve\b", re.I), "OUT"),
    (re.compile(r"\bdoubtful\b", re.I), "DOUBTFUL"),
    (re.compile(r"\bquestionable\b", re.I), "QUESTIONABLE"),
    (re.compile(r"\bprobable\b|\bavailable\b|\bactive\b|\bcleared\b", re.I), ""),
)
SUFFIX = re.compile(r"^(jr|sr|ii|iii|iv|v)\.?$", re.I)


def on() -> bool:
    return str(os.environ.get(ENV, "on")).strip().lower() not in ("off", "0", "false", "no")


def status_of(word) -> str | None:
    """The engine's status for a report's word: OUT, DOUBTFUL, QUESTIONABLE or GTD; "" when it says he plays;
    None when the word is not a status at all (a header, a blank cell)."""
    w = " ".join(str(word or "").split())
    if not w:
        return None
    for rx, status in WORDS:
        if rx.search(w):
            return status
    return None


def player_name(raw) -> str:
    """A report's name in the board's order: "#12 Smith, John (QB)" -> "John Smith"; "Smith Jr., John" ->
    "John Smith Jr."; a name already first-last is left as it is."""
    s = re.sub(r"^\s*#?\d{1,3}\s*[-–.]?\s+", "", str(raw or ""))
    s = re.sub(r"\s*\([^)]*\)", " ", s)
    parts = [p.strip() for p in s.split(",")]
    if len(parts) == 2 and parts[1] and not SUFFIX.match(parts[1]):
        s = f"{parts[1]} {parts[0]}"
    elif len(parts) == 3 and SUFFIX.match(parts[1]):
        s = f"{parts[2]} {parts[0]} {parts[1]}"
    return " ".join(s.split())


def _ts(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        d = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.timestamp()


def load(path: Path | None = None) -> dict:
    """The box's cache (written by the reader); {} when there is none or it cannot be read."""
    try:
        return json.loads(Path(path or CACHE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _kickoffs(games) -> dict:
    """{team key: (week start epoch, kickoff epoch or None)} for the slate's schools."""
    from .injuries import WEEK_LEAD_DAYS
    out = {}
    for g in games or []:
        try:
            d = _dt.date.fromisoformat(str(g.get("date") or "")[:10])
        except ValueError:
            continue
        start = _dt.datetime.combine(d - _dt.timedelta(days=WEEK_LEAD_DAYS), _dt.time.min,
                                     tzinfo=_dt.timezone.utc).timestamp()
        kick = _ts(g.get("kickoff") or g.get("commence_time"))
        for t in (g.get("home"), g.get("away")):
            if t:
                out[t] = (start, kick)
    return out


#: A school's formal name, peeled to the one the board knows ("The Ohio State University" -> "Ohio State",
#: "University of Michigan" -> "Michigan"); tried only after the name as written.
FORMAL = (re.compile(r"^\s*the\s+", re.I), re.compile(r"^\s*university\s+of\s+(?:the\s+)?", re.I),
          re.compile(r"\s+university\s*$", re.I), re.compile(r",?\s+(?:inc\.?|athletics)\s*$", re.I))


def school_key(name: str, lookup: dict) -> str:
    """The board's key for a report's school name, or "" when none fits."""
    from .cfbdata import resolve_team
    hit = resolve_team(name, lookup)
    if hit:
        return hit
    s = str(name or "")
    for rx in FORMAL:
        s = rx.sub("", s)
        hit = resolve_team(s, lookup) if s.strip() else ""
        if hit:
            return hit
    return ""


def filed_for(games, lookup: dict, cache: dict | None = None) -> list[dict]:
    """Each slate school's newest filing for its game, as rows {team, player, pos, status, word, at, conference,
    final}: ``status`` the engine's ("" plays). A filing from before the school's game week, or long after its
    kickoff, is another game's; a school the resolver cannot key is left out rather than guessed."""
    cache = load() if cache is None else cache
    when = _kickoffs(games)
    best: dict[str, dict] = {}
    for rep in cache.get("reports") or []:
        team = school_key(str(rep.get("school") or ""), lookup)
        if not team or team not in when:
            continue
        at = _ts(rep.get("filed_at"))
        start, kick = when[team]
        if at is None or at < start or (kick is not None and at > kick + AFTER_KICKOFF_S):
            continue
        prev = best.get(team)
        if prev is None or at > prev["_at"]:
            best[team] = {**rep, "_at": at}
    rows = []
    for team, rep in best.items():
        for p in rep.get("players") or []:
            status = status_of(p.get("word"))
            name = player_name(p.get("player"))
            if status is None or not name:
                continue
            rows.append({"team": team, "player": name, "pos": str(p.get("pos") or "").upper(), "status": status,
                         "word": " ".join(str(p.get("word") or "").split()), "at": rep["_at"],
                         "conference": rep.get("conference") or "", "final": bool(rep.get("final"))})
        if not rep.get("players"):
            # A filing that lists nobody still says nobody is designated.
            rows.append({"team": team, "player": "", "pos": "", "status": "", "word": "", "at": rep["_at"],
                         "conference": rep.get("conference") or "", "final": bool(rep.get("final"))})
    return rows


def espn_dates(rows, team_key) -> dict:
    """{(team key, normalised name): epoch} of each man's newest filing on ESPN's board (parse_injuries rows)."""
    from .oddsapi import normalize_name
    out: dict = {}
    for r in rows or []:
        team = team_key(r.get("team") or "")
        at = _ts(r.get("date"))
        if not team or at is None:
            continue
        key = (team, normalize_name(r.get("player") or ""))
        out[key] = max(at, out.get(key, at))
    return out


def overlay(espn: list[Injury], dates: dict, filed: list[dict]) -> tuple[list[Injury], dict]:
    """ESPN's board (``espn``, its filing times in ``dates``) with each school's filing (``filed``, from
    `filed_for`) laid over it, by the rule in this module's header. Returns ``(merged, note)`` where ``note``
    counts what the filings did: schools, added, changed, cleared [(team, player, was)], dropped."""
    from .injuries import POSITION_ROLE
    from .oddsapi import normalize_name
    note = {"schools": 0, "added": 0, "changed": 0, "cleared": [], "dropped": 0}
    if not filed:
        return list(espn), note
    by_team: dict[str, dict] = {}
    for r in filed:
        t = by_team.setdefault(r["team"], {"at": r["at"], "men": {}})
        if r["player"]:
            t["men"][normalize_name(r["player"])] = r
    note["schools"] = len(by_team)
    merged: list[Injury] = []
    seen: set = set()
    for inj in espn:
        school = by_team.get(inj.team)
        if school is None:
            merged.append(inj)
            continue
        key = normalize_name(inj.player)
        mine = school["men"].get(key)
        espn_at = dates.get((inj.team, key))
        newer_on_espn = espn_at is not None and espn_at > school["at"]
        if mine is None:
            if inj.status in ("QUESTIONABLE", "DOUBTFUL", "GTD") and not newer_on_espn:
                note["dropped"] += 1
                continue
            merged.append(inj)
            continue
        seen.add((inj.team, key))
        if newer_on_espn:
            merged.append(inj)
            continue
        if not mine["status"]:
            note["cleared"].append((inj.team, inj.player, inj.status))
            continue
        if mine["status"] != inj.status:
            note["changed"] += 1
            inj.status = mine["status"]
        merged.append(inj)
    for team, school in by_team.items():
        for key, r in school["men"].items():
            if (team, key) in seen or not r["status"]:
                continue
            merged.append(Injury(player=r["player"], team=team, position=r["pos"],
                                 role=POSITION_ROLE.get(r["pos"], r["pos"].lower()), status=r["status"]))
            note["added"] += 1
    return merged, note
