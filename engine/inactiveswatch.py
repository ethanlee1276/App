"""Which of ESPN's feeds shows an NFL game's inactives first (step ACH, 22 November 2026).

Ethan, 22 November: "find a faster inactives source than ESPN's injury board". The NFL's game-day inactives come
out 90 minutes before each kickoff, and each game's picks wait for both clubs' lists on ESPN's injury board
(engine/gameparlays.inactives_ready). On the Sunday the 4:25 games' lists reached our picks 25 to 42 minutes after
they came out: the board filed a club's men 1 to 21 minutes after, our copy of it was up to ten minutes old (a
minute now, in the window: espninjuries.ttl_for), and the build that reads it runs about every ten.

ESPN has other feeds that may carry the lists sooner: the game's summary (site.api and site.web.api), the
gamecast's (cdn.espn.com) and the core API's game roster of each club. None has been looked at for a game in its
inactives window, and this repository does not parse a shape it has not seen (espnprobe.py). This sandbox cannot
reach ESPN, so the box looks, without trusting a shape:

  * while an NFL game on the scoreboard copy is within WINDOW_MIN of its kickoff, each tick reads the injury board
    (the shared copy) and, in turn, at most PER_TICK of the other feeds' pages;
  * a page is walked by key, whatever its shape. A man is marked inactive where his entry's own ``active`` is
    false, its ``didNotPlay`` true, or one of its strings says inactive (a short status word, or a sentence the
    board's own test reads as one: engine/sources/injuries._INACTIVE). Each mark keeps where it was found: the
    path, list indices dropped, and the key. Key names only, never ESPN's words;
  * for each game, club and feed it notes when the feed first showed each man, and how many it showed.

``report`` sets each feed's first sighting of each man against the board's: minutes ahead (positive) or behind,
each sighting taken at the middle of the gap since that feed was last read, as engine/feedlatency does. Written to
web/data/inactives_watch.json after each tick in a window (counts and times, no names); the day's notes, names
included, stay in data/cache/inactiveswatch/. Nothing on the site reads either: a feed that proves faster is
switched in by a later step. Off without a deploy: ``sudo ./deploy/setenv.sh QB_INACTIVES_WATCH off``.
``python3 -m engine.inactiveswatch`` prints the report, read-only.
"""

from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "cache" / "inactiveswatch"
OUT = ROOT / "web" / "data" / "inactives_watch.json"
ENV = "QB_INACTIVES_WATCH"
#: Minutes before an NFL kickoff the watch opens, and after it shuts. It opens with the board's fresh minute
#: (espninjuries.INACTIVES_WINDOW_MIN) and stays a little past the kickoff, for a feed that marks its men only
#: once the game is on.
WINDOW_MIN = (100, 20)
TICK_S = 60
IDLE_S = 300
#: Pages a tick, the board aside. A game has five (two summaries, the gamecast, a roster a club): a Sunday-night
#: game's are each read every minute, a one o'clock slate's in turn.
PER_TICK = 16
TIMEOUT_S = 20
KEEP_DAYS = 30
FEEDS = {
    "summary": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event}",
    "web_summary": "https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event}",
    "gamecast": "https://cdn.espn.com/core/nfl/game?xhr=1&gameId={event}",
    "core_roster": ("https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{event}/competitions/"
                    "{event}/competitors/{team_id}/roster"),
}
#: A string this short is a status word ("Inactive"), not a sentence; a longer one counts only where it reads
#: as the board's own filings do ("... is inactive for Sunday's game").
SHORT = 40
_WORD = re.compile(r"\binactive\b", re.I)

_STATE: dict = {}       # day -> that day's notes
_TURN = [0]
_PRUNED = [""]


def on() -> bool:
    return str(os.environ.get(ENV, "on")).strip().lower() not in ("off", "0", "false", "no")


def _iso(t) -> str | None:
    if t is None:
        return None
    return _dt.datetime.fromtimestamp(float(t), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _et_day(t: float) -> str:
    from zoneinfo import ZoneInfo
    return _dt.datetime.fromtimestamp(t, ZoneInfo("America/New_York")).date().isoformat()


def _abbr(code: str) -> str:
    from .sources.livescores import ESPN_ABBR
    code = str(code or "").strip().upper()
    return ESPN_ABBR.get(code, code)


def _ref_id(ref, kind: str) -> str:
    m = re.search(rf"/{kind}/(\d+)", str(ref or ""))
    return m.group(1) if m else ""


def _team(d: dict, ids: dict):
    """Our code for the club a dict names in its ``team`` (an id, a core-API $ref or an abbreviation), or None."""
    t = d.get("team")
    if not isinstance(t, dict):
        return None
    tid = str(t.get("id") or "") or _ref_id(t.get("$ref"), "teams")
    if tid and tid in ids:
        return ids[tid]
    ab = t.get("abbreviation")
    return _abbr(ab) if isinstance(ab, str) and ab.strip() else None


def _person(d: dict):
    """(name, ESPN id) of the man a dict is about, or None: his ``athlete``'s, or the dict's own where it reads as
    a person's (a jersey, a first or last name, a playerId), never a club's (a location and an abbreviation)."""
    ath = d.get("athlete") if isinstance(d.get("athlete"), dict) else {}
    own = (any(k in d for k in ("jersey", "firstName", "lastName", "playerId"))
           and not ("location" in d and "abbreviation" in d))
    if not ath and not own:
        return None
    name = ath.get("displayName") or ath.get("fullName") or ""
    if not name and own:
        name = d.get("displayName") or d.get("fullName") or ""
    pid = str(ath.get("id") or "") or _ref_id(ath.get("$ref"), "athletes")
    if not pid and own:
        pid = str(d.get("playerId") or d.get("id") or "")
    name = name.strip() if isinstance(name, str) else ""
    if not name and not pid:
        return None
    return name, pid


def _key(name: str, pid: str) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(name) if name else f"id:{pid}"


def marks(page, ids: dict | None = None, club: str | None = None) -> tuple:
    """Every man ``page`` marks inactive, and where: ``({(club, place): {man: espn id}}, {place: {value: n}})``.
    ``place`` is the path to the mark (list indices dropped) and its key; ``club`` our code for his team where
    the page says it (``ids``: ESPN team id -> our code), else ``club`` (the club a roster page is for), else "?".
    The second dict counts every ``active`` and ``didNotPlay`` the page carries and every string that says
    inactive, marked or not: what the page looks like, in key names and counts."""
    from .sources.injuries import _INACTIVE
    from .sources.oddsapi import normalize_name
    ids = ids or {}
    found: dict = {}
    shapes: dict = {}

    def note(place, value):
        s = shapes.setdefault(place, {})
        s[value] = s.get(value, 0) + 1

    def mark(team, place, who):
        name, pid = who
        found.setdefault((team, place), {})[normalize_name(name) if name else f"id:{pid}"] = pid

    def walk(x, path, team, who):
        if isinstance(x, dict):
            team = _team(x, ids) or team
            who = _person(x) or who
            for k, v in x.items():
                place = f"{path}.{k}" if path else k
                if k in ("active", "didNotPlay") and isinstance(v, bool):
                    note(place, str(v).lower())
                    if who and ((k == "active" and v is False) or (k == "didNotPlay" and v is True)):
                        mark(team, place, who)
                elif isinstance(v, str):
                    short = len(v) <= SHORT
                    if (short and _WORD.search(v)) or (not short and _INACTIVE.search(v)):
                        place += "=word" if short else "=says"
                        note(place, "inactive")
                        if who:
                            mark(team, place, who)
                elif isinstance(v, (dict, list)):
                    walk(v, place, team, who)
        elif isinstance(x, list):
            for v in x:
                walk(v, path + "[]", team, who)

    walk(page, "", club or "?", None)
    return found, shapes


def board_marks(rows, games: list, now: float) -> dict:
    """{(club, "board"): {man: (espn id, filed)}} off the injury board's rows (espninjuries.parse_injuries): the
    men filed Out and inactive since their game's window opened, as the NFL build reads them
    (engine/sources/injuries.inactives_posted), whatever their number."""
    from .sources.espninjuries import _parse_iso_ts
    from .sources.injuries import INACTIVES_LEAD_S, _INACTIVE
    from .sources.oddsapi import TEAM_ABBR, normalize_name
    opens = {}
    for g in games:
        for c in (g["home"], g["away"]):
            opens[c] = (g["t0"] - INACTIVES_LEAD_S, g["t0"] + 5 * 3600)
    out: dict = {}
    for r in rows or []:
        if str(r.get("status") or "").strip().lower() != "out" or not _INACTIVE.search(str(r.get("comment") or "")):
            continue
        club = TEAM_ABBR.get(r.get("team") or "")
        win = opens.get(club)
        filed = _parse_iso_ts(r.get("date"))
        if not win or filed is None or not (win[0] <= filed <= win[1]):
            continue
        # His ESPN id, off his headshot's address (the board's rows keep no other): a feed that names a man
        # only by id is matched by it.
        m = re.search(r"/(\d+)\.(?:png|jpg)", str(r.get("face") or ""))
        pid = m.group(1) if m else ""
        out.setdefault((club, "board"), {})[normalize_name(r.get("player") or "")] = (pid, filed)
    return out


def _games(rows, now: float) -> list:
    """The scoreboard's NFL games within WINDOW_MIN of their kickoff."""
    from .sources.espninjuries import _parse_iso_ts
    before, after = WINDOW_MIN
    out = []
    for r in rows or []:
        t0 = _parse_iso_ts(getattr(r.get("live"), "start_time", ""))
        if t0 is None or not (t0 - before * 60 <= now <= t0 + after * 60) or not r.get("event_id"):
            continue
        out.append({"event": str(r["event_id"]), "home": r.get("home") or "", "away": r.get("away") or "",
                    "home_id": str(r.get("home_id") or ""), "away_id": str(r.get("away_id") or ""), "t0": t0})
    return out


def _get(url: str):
    """(status, page or None, bytes): one read, as fetch_json asks ESPN (no User-Agent of ours), never cached."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=TIMEOUT_S) as resp:
            raw = resp.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return "ok", json.loads(raw.decode("utf-8", errors="replace")), len(raw)
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}", None, 0
    except ValueError:
        return "not JSON", None, 0
    except Exception as exc:                                   # noqa: BLE001
        return type(exc).__name__, None, 0


def _path(day: str, root=None) -> Path:
    return Path(root or DIR) / f"{day}.json"


def _day_state(day: str, root=None) -> dict:
    st = _STATE.get(day)
    if st is None:
        try:
            st = json.loads(_path(day, root).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        st.setdefault("day", day)
        st.setdefault("games", {})
        _STATE.clear()
        _STATE[day] = st
    return st


def _feed(st: dict, g: dict, feed: str) -> dict:
    gs = st["games"].setdefault(g["event"], {"game": f"{g['away']}@{g['home']}", "home": g["home"],
                                             "away": g["away"], "kickoff": _iso(g["t0"]), "feeds": {}})
    return gs["feeds"].setdefault(feed, {"reads": 0, "clubs": {}, "places": {}})


def take(rec: dict, found: dict, t: float, iv, clubs: tuple, status: str = "ok", shapes=None, covers=None,
         slot: str = "*") -> int:
    """Notes one read of a feed into its record ``rec``: each man's first sighting (``t``, the gap ``iv`` since
    the feed was last read, where), the count of each club the page ``covers`` (a roster page one club, the
    others the game) when it changes, each place's count, and the page's shape, kept by ``slot``. Returns the men
    new to it."""
    rec["reads"] = int(rec.get("reads") or 0) + 1
    rec["status"] = status
    rec["last"] = round(t, 1)
    new = 0
    counts: dict = {}
    for (club, place), men in found.items():
        if club not in clubs:
            club = "?"
        cl = rec["clubs"].setdefault(club, {"men": {}, "counts": []})
        pl = rec["places"].setdefault(place, {"first": round(t, 1), "max": 0})
        pl["max"] = max(int(pl.get("max") or 0), len(men))
        here = cl.setdefault("by_place", {}).setdefault(place, {})
        for man, info in men.items():
            counts.setdefault(club, set()).add(man)
            pid, filed = info if isinstance(info, tuple) else (info, None)
            # Each place's own first sighting of him too: one place of a page can mark a whole roster (the core
            # API's `active` is false for most of a club's men on a game day) while another marks the list.
            if man not in here:
                here[man] = {"t": round(t, 1), "iv": None if iv is None else round(iv, 1), "id": pid or ""}
            if man in cl["men"]:
                continue
            cl["men"][man] = {"t": round(t, 1), "iv": None if iv is None else round(iv, 1), "id": pid or "",
                              "at": place, **({"filed": round(filed, 1)} if filed is not None else {})}
            new += 1
    for club in (covers or tuple(rec["clubs"])):
        cl = rec["clubs"].get(club)
        n = len(counts.get(club, ()))
        if cl is not None and (not cl["counts"] or cl["counts"][-1][1] != n):
            cl["counts"].append([round(t, 1), n])
    if shapes is not None:
        # What the newest page looks like: every place it carries an `active`, a `didNotPlay` or the word.
        rec.setdefault("shapes", {})[slot] = shapes
    return new


def watch_once(now=None, scoreboard=None, board=None, get=None, root=None, out=None) -> float:
    """One tick. Returns the wait before the next: TICK_S while an NFL game is in its window, IDLE_S when none
    is. ``scoreboard() -> rows``, ``board() -> (rows, fetched_at)`` and ``get(url) -> (status, page, bytes)`` are
    for tests. Never raises."""
    try:
        return _tick(now or time.time, scoreboard, board, get, root, out)
    except Exception:                                          # noqa: BLE001 — never let this stop the site
        return IDLE_S


def _scoreboard():
    from .sources.livescores import fetch_rows
    return fetch_rows("nfl", ttl=900)


def _board():
    from .sources import espninjuries as E
    rows = E.parse_injuries(E.fetch_injuries("nfl"))
    age = E.cache_age_s("nfl")
    return rows, (time.time() - age) if age is not None else time.time()


def _tick(clock, scoreboard, board, get, root, out) -> float:
    if not on():
        return IDLE_S
    now = clock()
    games = _games((scoreboard or _scoreboard)(), now)
    if not games:
        return IDLE_S
    day = _et_day(min(g["t0"] for g in games))
    st = _day_state(day, root)
    prune(day, root)
    # The board: one read for every game in its window, through the shared copy.
    try:
        rows, tb = (board or _board)()
        found = board_marks(rows, games, now)
        for g in games:
            rec = _feed(st, g, "board")
            prev = rec.get("copy")
            if prev is None or tb > prev:
                iv = (tb - prev) if prev is not None else None
                rec["copy"] = round(tb, 1)
                take(rec, {k: v for k, v in found.items() if k[0] in (g["home"], g["away"])}, tb, iv,
                     (g["home"], g["away"]))
    except Exception as exc:                                   # noqa: BLE001
        for g in games:
            _feed(st, g, "board")["status"] = type(exc).__name__
    # The other feeds, in turn.
    jobs = []
    for g in games:
        ids = {g["home_id"]: g["home"], g["away_id"]: g["away"]}
        for feed in ("summary", "web_summary", "gamecast"):
            jobs.append((g, feed, FEEDS[feed].format(event=g["event"]), ids, None))
        for side in ("away", "home"):
            if g[f"{side}_id"]:
                jobs.append((g, "core_roster", FEEDS["core_roster"].format(event=g["event"],
                                                                          team_id=g[f"{side}_id"]), ids, g[side]))
    start = _TURN[0] % len(jobs) if jobs else 0
    picked = (jobs[start:] + jobs[:start])[:PER_TICK]
    _TURN[0] = start + len(picked)
    for g, feed, url, ids, club in picked:
        rec = _feed(st, g, feed)
        status, page, size = (get or _get)(url)
        t = clock()
        seen = rec.setdefault("seen", {})
        slot = club or "*"
        iv = (t - seen[slot]) if slot in seen else None
        seen[slot] = round(t, 1)
        if page is None:
            rec["reads"] = int(rec.get("reads") or 0) + 1
            rec["status"] = status
            continue
        found, shapes = marks(page, ids, club)
        if club:
            # A roster page is one club's: a mark it gives no club is his.
            found = {((club if k[0] == "?" else k[0]), k[1]): v for k, v in found.items()}
        rec["bytes"] = size
        take(rec, found, t, iv, (g["home"], g["away"]), status, shapes,
             covers=(club,) if club else (g["home"], g["away"], "?"), slot=slot)
    _save(st, root)
    _publish(st, now, out)
    return TICK_S


def _save(st: dict, root=None) -> None:
    p = _path(st["day"], root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(st, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def prune(today: str, root=None) -> int:
    """Drop the days past KEEP_DAYS, once a day."""
    if _PRUNED[0] == today:
        return 0
    _PRUNED[0] = today
    cut = (_dt.date.fromisoformat(today) - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    n = 0
    for f in Path(root or DIR).glob("*.json"):
        if f.stem < cut:
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def _mid(m: dict) -> float:
    """A sighting's middle: the change came somewhere in the gap since the feed was last read."""
    return float(m["t"]) - float(m.get("iv") or 0) / 2


def _telling(by_slot: dict, most: int = 20) -> dict:
    """Up to ``most`` of a feed's places, its newest pages' counts added up, the ones that mark a man first (an
    `active` false, a `didNotPlay` true, the word)."""
    shapes: dict = {}
    for page in (by_slot or {}).values():
        for place, vals in (page or {}).items():
            into = shapes.setdefault(place, {})
            for v, n in vals.items():
                into[v] = into.get(v, 0) + n

    def marked(kv):
        place, vals = kv
        return bool(vals.get("false") and place.endswith("active")) or bool(
            vals.get("true") and place.endswith("didNotPlay")) or bool(vals.get("inactive"))
    return dict(sorted(shapes.items(), key=lambda kv: (not marked(kv), kv[0]))[:most])


def _against(men: dict, board: dict, by_id: dict) -> dict:
    """For the men both a feed and the board carried: how many, and the middle of the minutes the feed showed
    them ahead of the board (positive) or behind, and ahead of the board's own filing stamps."""
    ahead, ahead_filed = [], []
    for man, m in men.items():
        b = board.get(man) or (by_id.get(m.get("id")) if m.get("id") else None)
        if b is None:
            continue
        ahead.append((_mid(b) - _mid(m)) / 60)
        if b.get("filed") is not None:
            ahead_filed.append((float(b["filed"]) - _mid(m)) / 60)
    out = {"both": len(ahead)}
    if ahead:
        out["ahead_min"] = round(statistics.median(ahead), 1)
    if ahead_filed:
        out["ahead_of_filed_min"] = round(statistics.median(ahead_filed), 1)
    return out


def report(st: dict) -> list:
    """Per game and club, each feed's count and first sighting, and against the board: for the men both carried,
    the middle of the minutes the feed showed them ahead of the board (positive) or behind, and of the minutes
    ahead of the board's own filing stamps. Counts and times only."""
    games = []
    for ev, g in sorted((st.get("games") or {}).items(), key=lambda kv: (kv[1].get("kickoff") or "", kv[0])):
        feeds = g.get("feeds") or {}
        bclubs = (feeds.get("board") or {}).get("clubs") or {}
        clubs = {}
        for club in (g.get("away"), g.get("home"), "?"):
            board = (bclubs.get(club) or {}).get("men") or {}
            by_id = {m.get("id"): m for m in board.values() if m.get("id")}
            row = {}
            for feed, rec in feeds.items():
                men = ((rec.get("clubs") or {}).get(club) or {}).get("men") or {}
                if not men:
                    continue
                d = {"n": len(men), "first": _iso(min(m["t"] for m in men.values()))}
                if feed == "board":
                    filed = [m["filed"] for m in men.values() if m.get("filed") is not None]
                    if filed:
                        d["filed_first"], d["filed_last"] = _iso(min(filed)), _iso(max(filed))
                else:
                    d.update(_against(men, board, by_id))
                    # …and place by place (`take`): the place that marks the list, apart from one that marks more.
                    places = ((rec.get("clubs") or {}).get(club) or {}).get("by_place") or {}
                    if places:
                        d["places"] = {pl: dict({"n": len(ms), "first": _iso(min(m["t"] for m in ms.values()))},
                                                **_against(ms, board, by_id))
                                       for pl, ms in sorted(places.items()) if ms}
                row[feed] = d
            if row:
                clubs[club] = row
        games.append({"game": g.get("game"), "event": ev, "kickoff": g.get("kickoff"), "clubs": clubs,
                      "feeds": {f: {"reads": r.get("reads", 0), "status": r.get("status"),
                                    **({"bytes": r["bytes"]} if r.get("bytes") else {}),
                                    "places": {p: v for p, v in sorted((r.get("places") or {}).items())[:20]},
                                    **({"shapes": _telling(r.get("shapes"))} if r.get("shapes") else {})}
                                for f, r in sorted(feeds.items())}})
    return games


def _publish(st: dict, now: float, out=None) -> None:
    p = Path(out or OUT)
    doc = {"generated_at": _iso(now), "day": st.get("day"), "window_min": list(WINDOW_MIN),
           "feeds": ["board", *FEEDS], "games": report(st)}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def report_lines(games: list) -> list:
    lines = []
    for g in games:
        lines.append(f"{g.get('game')}  kickoff {g.get('kickoff')}")
        for club, row in (g.get("clubs") or {}).items():
            for feed, d in row.items():
                bits = [f"{d['n']} men", f"first {d.get('first')}"]
                if "ahead_min" in d:
                    bits.append(f"{d['ahead_min']:+.1f} min against the board ({d.get('both')} both carried)")
                if "ahead_of_filed_min" in d:
                    bits.append(f"{d['ahead_of_filed_min']:+.1f} against its filing stamps")
                if "filed_first" in d:
                    bits.append(f"filed {d['filed_first']} to {d.get('filed_last')}")
                lines.append(f"  {club:<4} {feed:<12} " + ", ".join(bits))
        for feed, f in (g.get("feeds") or {}).items():
            lines.append(f"  read  {feed:<12} {f.get('reads')} times, last {f.get('status')}")
    return lines or ["No NFL game has been in its inactives window on this box today."]


def main(argv=None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    day = argv[0] if argv else _et_day(time.time())
    try:
        st = json.loads(_path(day).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {"day": day, "games": {}}
    print("\n".join(report_lines(report(st))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
