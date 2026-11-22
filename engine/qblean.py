"""A new starting quarterback's own lean between his targets, measured (step ABZ, 22 November 2026).

    sudo -u qellys nice -n 19 python3 -m engine.qblean        # the career splits, into data/cache/qb_lean.json
    python3 chemfit.py                                         # the measurement below, again

Ethan, 22 November: "the chemistry between quarterbacks and their wide receivers and their tight ends, as in one
quarterback may prefer to throw more to a certain wide receiver or tight end compared to another one, or they may
prefer to throw to tight ends more compared to wide receivers in general ... measure that and make sure that's
measured with our most likely picks and our game report picks ... our edge bets as well."

WHAT THE GAMES SAY (chemfit.py on nflverse's play-by-play, regular seasons 2017-2026; each setting chosen on
2021-2023 and judged on seasons it never saw; the bar written before each run):

  * ONE RECEIVER WITH ONE QUARTERBACK. A receiver's share of the targets in his games with this week's starter,
    against his share over all his recent games, where those were thrown by more than one starter: worse at every
    setting on 2021-2023 (-0.2% to -12.7%), and within half a percent either way on 2024-2026; the same for a
    starter coming back to games mostly thrown by someone else. The two shares sit 1.3 points apart at the median.
    A receiver's role is set by the offense, not by who throws to him, so it is not in any number.
  * HIS CATCH RATE AND YARDS A TARGET WITH ONE QUARTERBACK: no better than his own rates, either.
  * A NEW STARTER'S OWN SPLIT between wide receivers, tight ends and backs, in his first three starts for a team:
    a fifth of the way from the team's recent split toward his career split improved the split's error on six of
    the seven unseen seasons (2017 +11.7%, 2018 +12.1%, 2019 -0.6%, 2020 +6.5%, 2024 +1.8%, 2025 +2.3%, 2026 +0.7%;
    199 games, interval above zero). The size is the one-standard-error rule's on 2021-2023 (134 games): the best
    there, a blend of 0.35, fails on the unseen seasons (three of seven worse at 0.4), and every blend from 0.1 to
    0.2 passes, so the effect is real and small, and its size is not pinned down past "a fifth or less". His career tight-end share sits 5 points from the team's at the median, 12.5
    at the ninetieth percentile, so the move is a point or two of a position's share: 5 to 12% of a tight end's
    targets in the games it reaches. THIS is what moves a number.
  * The average shift after any change of starter (wide receivers -1.3 points, tight ends +1.2): worse on five of
    the seven unseen seasons, so not applied; the lean above is the starter's own.

WHAT THIS DOES. In a game where a team's starter is out or benched (engine/qbchange), each receiver's catches and
receiving yards move by how much his position's share moves LEAN_W of the way from the team's recent split (its
last RECENT_WEEKS weeks of targets) toward the new starter's career split (his targets in his starts since 2017,
at least MIN_TARGETS), capped at CAP either way. The change carries it (``lean``), so the board, Most Likely,
the Edge picks, the report's picks and its if-he-sits version all read it through engine/qbchange.effect, and the
report says it in words. Off without a deploy: ``sudo ./deploy/setenv.sh QB_QB_LEAN off``.
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "data" / "cache" / "qb_lean.json"
ENV = "QB_QB_LEAN"

#: The measured blend (chemfit.py B3: chosen on 2021-2023, judged on 2017-2020 and 2024-2026).
LEAN_W = 0.2
#: The starter's targets, in his starts, before his split is read.
MIN_TARGETS = 40
#: The most a position's targets move either way.
CAP = 0.15
#: The team's recent split: its last this many weeks.
RECENT_WEEKS = 8
#: A clean start: he threw at least this share of his team's passes.
START_SHARE = 0.8
#: The seasons a career is read from.
FIRST_SEASON = 2017
#: The markets a target's share reaches.
MARKETS = ("receptions", "rec_yds")
#: The doc's shape: 2 since each starter's games are kept club by club (step ACJ).
DOC_VERSION = 2
#: A receiver is kept on a starter's club line once he drew this many of his targets there in a season.
TEAM_TARGETS_MIN = 3
#: A starter back with a former club (`reunion`): his starts there, before his line there is said.
REUNION_MIN_STARTS = 4
GROUPS = ("WR", "TE", "RB")


def on() -> bool:
    return str(os.environ.get(ENV, "on")).strip().lower() not in ("off", "0", "false", "no")


def group(position) -> str:
    p = str(position or "").upper()
    return "WR" if p == "WR" else "TE" if p == "TE" else "RB" if p in ("RB", "FB", "HB") else ""


def _norm(name) -> str:
    return " ".join(str(name or "").lower().replace(".", " ").replace("'", "").replace("-", " ").split())


# --- the career splits, off the play-by-play the box already caches ------------------------------------------------
def count_season(rows, positions: dict, names: dict) -> dict:
    """{passer id: {"name", "WR", "TE", "RB", "starts", "teams"}} for one season's regular-season plays: each
    starter's targets in his clean starts (START_SHARE of his team's passes), by the receiver's position
    (``positions``: {gsis id: position}); ``names``: {gsis id: full name}. ``teams`` (step ACJ) keeps his clean
    starts club by club: {club: {"starts", "att", "cmp", "yds", "td", "targets", "tgt": {receiver's name:
    targets}}}: ``targets`` all he threw to a named receiver there, ``tgt`` the receivers he threw to at least
    TEAM_TARGETS_MIN times, so a starter back with a club he played for can
    be read against his own games there (`reunion`)."""
    games: dict = {}
    for r in rows:
        if str(r.get("season_type") or "REG") != "REG" or str(r.get("pass_attempt") or "") != "1":
            continue
        if "1" in (str(r.get("sack") or ""), str(r.get("two_point_attempt") or ""), str(r.get("qb_spike") or "")):
            continue
        qb, team, gid = r.get("passer_player_id"), r.get("posteam"), r.get("game_id")
        if not qb or not team or not gid:
            continue
        g = games.setdefault((gid, team), {"att": collections.Counter(), "tgt": collections.defaultdict(collections.Counter),
                                           "rec": collections.defaultdict(collections.Counter),
                                           "line": collections.defaultdict(collections.Counter)})
        g["att"][qb] += 1
        rid = r.get("receiver_player_id") or ""
        grp = group(positions.get(rid))
        if rid and grp:
            g["tgt"][qb][grp] += 1
        if rid and names.get(rid):
            g["rec"][qb][names[rid]] += 1
        if str(r.get("complete_pass") or "") == "1":
            g["line"][qb]["cmp"] += 1
            g["line"][qb]["yds"] += _num(r.get("yards_gained"))
        if str(r.get("pass_touchdown") or "") == "1":
            g["line"][qb]["td"] += 1
    out: dict = {}
    for (gid, team), g in games.items():
        qb, att = g["att"].most_common(1)[0]
        if att < START_SHARE * sum(g["att"].values()):
            continue
        mine = out.setdefault(qb, {"name": names.get(qb, ""), "WR": 0, "TE": 0, "RB": 0, "starts": 0, "teams": {}})
        mine["starts"] += 1
        for k in GROUPS:
            mine[k] += int(g["tgt"][qb].get(k, 0))
        club = mine["teams"].setdefault(team, {"starts": 0, "att": 0, "cmp": 0, "yds": 0, "td": 0, "targets": 0,
                                               "tgt": {}})
        club["starts"] += 1
        club["att"] += int(att)
        club["targets"] += int(sum(g["rec"][qb].values()))
        for k in ("cmp", "yds", "td"):
            club[k] += int(g["line"][qb].get(k, 0))
        for who, n in g["rec"][qb].items():
            club["tgt"][who] = club["tgt"].get(who, 0) + int(n)
    for mine in out.values():
        for club in mine["teams"].values():
            club["tgt"] = {w: n for w, n in sorted(club["tgt"].items(), key=lambda kv: -kv[1])
                           if n >= TEAM_TARGETS_MIN}
    return out


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


#: The play-by-play columns the count reads, beyond the loader's own.
PBP_COLUMNS = ("season_type", "pass_attempt", "passer_player_id", "receiver_player_id", "qb_spike")


def build(seasons, load_pbp=None, load_roster=None, have: dict | None = None, current: int | None = None) -> dict:
    """The career splits doc: {"seasons": {season: {passer id: counts}}, "built_at"}. A season already in ``have`` is
    kept as it was unless it is ``current`` (the season under way, read again). Never raises for one season: a
    season that will not load is left as it was, and said."""
    if load_pbp is None:
        from .sources.nflpbp import load_pbp_rows

        def load_pbp(season):
            return load_pbp_rows(season, columns=PBP_COLUMNS)
    if load_roster is None:
        from .sources.nflverse import load_rosters as load_roster
    # A doc written before the clubs were kept (step ACJ) is read again whole: its seasons have no ``teams``.
    kept = dict((have or {}).get("seasons") or {}) if int((have or {}).get("v") or 1) >= DOC_VERSION else {}
    doc = {"v": DOC_VERSION, "seasons": kept, "built_at": None, "notes": []}
    for season in seasons:
        key = str(season)
        if key in doc["seasons"] and season != current:
            continue
        try:
            roster = load_roster(season) or []
            positions = {str(r.get("gsis_id") or ""): r.get("position") or r.get("depth_chart_position") or ""
                         for r in roster if r.get("gsis_id")}
            names = {str(r.get("gsis_id") or ""): r.get("full_name") or r.get("player_name") or ""
                     for r in roster if r.get("gsis_id")}
            doc["seasons"][key] = count_season(load_pbp(season), positions, names)
        except Exception as exc:                             # noqa: BLE001
            doc["notes"].append(f"{season}: not read ({type(exc).__name__}: {exc})")
    doc["built_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    return doc


def save(doc: dict, path: Path | None = None) -> None:
    path = Path(path or PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(path)


def load(path: Path | None = None) -> dict:
    try:
        return json.loads(Path(path or PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def career(doc: dict, name: str) -> dict | None:
    """A quarterback's career split by name: {"WR", "TE", "RB" (shares), "targets", "starts"}; None under
    MIN_TARGETS or unknown."""
    want = _norm(name)
    if not want:
        return None
    tot = collections.Counter()
    for per in ((doc or {}).get("seasons") or {}).values():
        for row in (per or {}).values():
            if _norm(row.get("name")) == want:
                for k in GROUPS + ("starts",):
                    tot[k] += int(row.get(k) or 0)
    n = sum(tot[k] for k in GROUPS)
    if n < MIN_TARGETS:
        return None
    return {**{k: tot[k] / n for k in GROUPS}, "targets": n, "starts": tot["starts"]}


# --- a starter back with a club he played for (step ACJ) ------------------------------------------------------------
def reunion(doc: dict, name: str, team: str, season: int | None = None) -> dict | None:
    """A quarterback back with ``team`` after starting elsewhere: his clean starts for it before the last season he
    started for another club, added up. {"team", "first", "last", "starts", "att", "cmp", "yds", "td", "tgt"};
    None when he never left it, never started for it, or started for it fewer than REUNION_MIN_STARTS times."""
    want = _norm(name)
    if not want or not team:
        return None
    by_season: dict = {}
    for key, per in ((doc or {}).get("seasons") or {}).items():
        try:
            yr = int(key)
        except (TypeError, ValueError):
            continue
        if season is not None and yr > int(season):
            continue
        for row in (per or {}).values():
            if _norm((row or {}).get("name")) == want:
                for club, line in ((row or {}).get("teams") or {}).items():
                    by_season.setdefault(yr, {})[club] = line
    away = [yr for yr, clubs in by_season.items() if any(c != team for c in clubs)]
    if not away:
        return None
    last_away = max(away)
    stint = sorted(yr for yr, clubs in by_season.items() if team in clubs and yr < last_away)
    if not stint:
        return None
    tot = {"starts": 0, "att": 0, "cmp": 0, "yds": 0, "td": 0, "targets": 0}
    tgt: collections.Counter = collections.Counter()
    for yr in stint:
        line = by_season[yr][team]
        for k in tot:
            tot[k] += int(line.get(k) or 0)
        tgt.update({w: int(n) for w, n in (line.get("tgt") or {}).items()})
    if tot["starts"] < REUNION_MIN_STARTS:
        return None
    return {"team": team, "first": stint[0], "last": stint[-1], **tot, "tgt": dict(tgt.most_common())}


def reunion_words(r: dict, who: str, club: str = "the team", now_on: set | None = None, most: int = 3) -> str:
    """The reunion in a sentence: his starts for the club then, his line a game, and, of the men on the club now
    (``now_on``: normalized names), the most targets he threw to then, as shares of all his targets there. ""
    when there is none to say."""
    if not r or not r.get("starts"):
        return ""
    n = int(r["starts"])
    years = f"{r['first']}" if r["first"] == r["last"] else f"{r['first']}–{r['last']}"
    att, cmp_ = int(r.get("att") or 0), int(r.get("cmp") or 0)
    head = (f"{who} is back with {club}: in his {n} starts for them ({years}) he threw for "
            f"{round(float(r.get('yds') or 0) / n)} yards and {float(r.get('td') or 0) / n:.1f} touchdowns a game"
            + (f", completing {round(100 * cmp_ / att)}% of his passes" if att else ""))
    # Shares of every target he threw there, the receivers under the line too.
    total = int(r.get("targets") or 0) or sum(int(v) for v in (r.get("tgt") or {}).values())
    mates = [(w, int(v)) for w, v in (r.get("tgt") or {}).items() if now_on is None or _norm(w) in now_on]
    if total and mates:
        head += (f". Of the receivers there now, " + ", ".join(
            f"{w} drew {round(100 * v / total)}%" for w, v in mates[:most]) + " of his targets then")
    return head


# --- the team's recent split, and the factors ----------------------------------------------------------------------
def team_split(stats_rows, team: str, before_week: int | None = None, weeks: int = RECENT_WEEKS) -> dict | None:
    """The team's share of its targets by position over its last ``weeks`` weeks of the season's weekly stats
    (nflverse player_stats rows); None with too few targets to say."""
    by_week: dict = collections.defaultdict(collections.Counter)
    for r in stats_rows or []:
        if str(r.get("recent_team") or r.get("team") or "") != team:
            continue
        if str(r.get("season_type") or "REG") not in ("REG", ""):
            continue
        try:
            wk = int(float(r.get("week") or 0))
            tgt = float(r.get("targets") or 0)
        except (TypeError, ValueError):
            continue
        if before_week is not None and wk >= before_week:
            continue
        grp = group(r.get("position") or r.get("position_group"))
        if grp and tgt > 0:
            by_week[wk][grp] += tgt
    tot = collections.Counter()
    for wk in sorted(by_week)[-weeks:]:
        tot.update(by_week[wk])
    n = sum(tot[k] for k in GROUPS)
    if n < MIN_TARGETS:
        return None
    return {k: tot[k] / n for k in GROUPS}


def factors(team: dict, qb: dict, w: float = LEAN_W, cap: float = CAP) -> dict:
    """{group: multiplier on that position's targets}: its share moved ``w`` of the way toward the starter's,
    over its share now, within ``cap``."""
    out = {}
    for k in GROUPS:
        now = float(team.get(k) or 0)
        if now <= 0:
            continue
        moved = (1 - w) * now + w * float(qb.get(k) or 0)
        out[k] = round(min(1 + cap, max(1 - cap, moved / now)), 4)
    return out


def attach(changes: dict, doc: dict, stats_rows, week: int | None = None) -> dict:
    """Each change whose new starter has a career split, and whose team has a recent one, carries ``lean``:
    {"factors", "qb", "team", "targets", "starts"}. Returns ``changes``; never raises."""
    if not on() or not changes or not doc:
        return changes
    for team, ch in (changes or {}).items():
        try:
            if not isinstance(ch, dict) or ch.get("status") == "RETURNS" or not ch.get("replacement"):
                continue
            # BACK WITH A CLUB HE PLAYED FOR (step ACJ; Ethan, 22 November, of Kirk Cousins back with the
            # Vikings): his own games there, said on the report. Words only: whether they move a number is
            # chemfit.py's test R, on the box, and nothing here prices them.
            back = reunion(doc, ch["replacement"], team, _season_of(stats_rows))
            if back:
                ch["reunion"] = dict(back, now_on=sorted(_on_team(stats_rows, team)))
            qb = career(doc, ch["replacement"])
            split = team_split(stats_rows, team, before_week=week)
            if not qb or not split:
                continue
            ch["lean"] = {"factors": factors(split, qb), "qb": {k: round(qb[k], 3) for k in GROUPS},
                          "team": {k: round(split[k], 3) for k in GROUPS}, "targets": qb["targets"],
                          "starts": qb["starts"]}
        except Exception as exc:                             # noqa: BLE001
            print(f"  ⚠️ {team}'s new starter's lean not read ({type(exc).__name__}: {exc})")
    return changes


def _season_of(stats_rows):
    """The season the weekly rows are of (their newest), or None."""
    yrs = []
    for r in stats_rows or []:
        try:
            yrs.append(int(float(r.get("season") or 0)))
        except (TypeError, ValueError):
            continue
    return max(yrs) if yrs and max(yrs) > 0 else None


def _on_team(stats_rows, team: str) -> set:
    """The normalized names of the club's men with a target this season, off its weekly rows: the receivers on
    it now."""
    out = set()
    for r in stats_rows or []:
        if str(r.get("recent_team") or r.get("team") or "") != team:
            continue
        try:
            if float(r.get("targets") or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        name = r.get("player_display_name") or r.get("player_name") or ""
        if name:
            out.add(_norm(name))
    return out


def multiplier(ch: dict, prop) -> float:
    """The lean's multiplier for one prop (1.0 when it has none)."""
    if not on() or not isinstance(ch, dict) or getattr(prop, "market", "") not in MARKETS:
        return 1.0
    return float(((ch.get("lean") or {}).get("factors") or {}).get(group(getattr(prop, "position", "")), 1.0))


#: Position groups in words.
GROUP_WORDS = {"WR": "wide receivers", "TE": "tight ends", "RB": "running backs"}


def words(ch: dict, club: str = "the team") -> str:
    """The lean in a sentence, or ""."""
    lean = (ch or {}).get("lean") or {}
    f = lean.get("factors") or {}
    if not f:
        return ""
    who = ch.get("replacement") or "the new starter"
    qb, team = lean.get("qb") or {}, lean.get("team") or {}
    moved = [k for k in GROUPS if abs(f.get(k, 1.0) - 1) >= 0.01]
    head = (f"{who} has thrown {round(qb.get('TE', 0) * 100)}% of his targets to tight ends, "
            f"{round(qb.get('WR', 0) * 100)}% to wide receivers and {round(qb.get('RB', 0) * 100)}% to backs in his "
            f"starts ({lean.get('targets')} targets); {club} lately: {round(team.get('TE', 0) * 100)}%, "
            f"{round(team.get('WR', 0) * 100)}% and {round(team.get('RB', 0) * 100)}%")
    if not moved:
        return head + ", close enough that nothing moves"
    bits = ", ".join(f"the {GROUP_WORDS[k]}' targets {'+' if f[k] > 1 else '−'}{abs(round((f[k] - 1) * 100))}%"
                     for k in moved)
    return (f"{head}. A new starter's own split carried over a fifth of the way in his first starts (measured on "
            f"199 games, 2017–26), so {bits}")


def main(argv=None) -> int:
    from .seasons import season_of
    today = _dt.date.today().isoformat()
    current = season_of("nfl", today)
    doc = build(range(FIRST_SEASON, current + 1), have=load(), current=current)
    save(doc)
    n = sum(len(v or {}) for v in doc["seasons"].values())
    print(f"qb lean: {len(doc['seasons'])} season(s), {n} starter-seasons" +
          (f"; {'; '.join(doc['notes'])}" if doc["notes"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
