"""Each game's report, kept watching: the injury report and the news, every few
minutes (2026-11-17).

Ethan, 2026-11-17: "make sure the game reports keep a constant watch and
update on nfl news and injuries". A report is written by its league's build,
once a board sweep (about half an hour on the box), and its "What changed"
log (engine/reportlog) says what moved between two builds. Between them the
world moves on its own: a starter ruled out on a Sunday morning, a player
downgraded on a Friday, a trade, a suspension. This watches for those as they
happen, between the builds.

EVERY WATCH_EVERY_S, for each league with games on its board in the next
eight days:

  the injury report   ESPN's board (engine/sources/espninjuries, read through
                      its own ten-minute courtesy cache), one row per player.
                      A designation that differs from the last one seen is an
                      UPDATE ("Questionable to Out"), stamped with when we saw
                      it and with ESPN's own posted time. The first sight of a
                      league's board is only remembered: a status that was
                      already true when the watch started is not news (the
                      rule engine/newsalerts keeps for members' players).
  the news            ESPN's newsroom (engine/sources/espnnews), every story
                      tagged with the teams and athletes it is about, and the
                      league's RSS headlines (engine/sources/news), matched on
                      the clubs' names and the listed players'. The last three
                      days', newest first; a story about an injury, a roster
                      move or a suspension is marked as one.

AND WRITES web/data/report_watch.json, free like the injuries and the
headlines it is made of (designations and titles: no pick, no line, no price).
Each game's page draws what landed after its report was written as a card
over the report ("Since this report was written", js/report.js, read again
every two minutes while the page stays open), and the next build folds it
into the report's own text (engine/gamereport sec_news).

Never raises into the launcher's loop: a league whose feed cannot be read
keeps the updates it had and says so. Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH_PATH = ROOT / "web" / "data" / "report_watch.json"
STATE_PATH = ROOT / "data" / "cache" / "report_watch_state.json"

#: How often the launcher's watcher runs (launch._report_watcher).
WATCH_EVERY_S = 300
#: The leagues watched: every league with an injury report and a newsroom.
LEAGUES = ("nfl", "cfb", "nba", "cbb", "nhl", "wnba", "mlb")
#: A game is watched from its board's slate until this long after kickoff.
AFTER_KICKOFF_S = 6 * 3600
#: ...and no further ahead than this.
AHEAD_S = 8 * 86400
#: How long an injury update stays on a game's card.
UPDATE_DAYS = 7
#: How far back a headline counts as news for a game.
NEWS_HOURS = 72
#: The most of each a game carries.
MAX_UPDATES, MAX_NEWS = 12, 8
#: A headline naming more clubs than this is about the league (a power
#: ranking, a week's picks), not about one game, and goes on no game's card.
MAX_TEAMS = 3

#: A headline about who plays: an injury, a roster move or a suspension.
INJURY_WORDS = re.compile(
    r"\b(injur\w*|rul(?:e|es|ed|ing) out|out for|week-to-week|day-to-day|questionable|doubtful|inactive|"
    r"concussion|hamstring|ankle|knee|groin|shoulder|calf|quad|achilles|acl|mcl|illness|"
    r"limited|did not practice|dnp|returns?|activated|designated to return|placed on ir|"
    r"injured reserve|\bir\b|out indefinitely|season-ending|surgery|game-time decision)\b", re.I)
ROSTER_WORDS = re.compile(
    r"\b(trade[sd]?|acquire[sd]?|sign(s|ed|ing)?|release[sd]?|waive[sd]?|cut[s]?|"
    r"suspen(d|ded|sion)|benched|bench(es)?|start(s|ing)? at quarterback|named starter|demoted|promoted)\b",
    re.I)


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def _iso(epoch: float) -> str:
    return _dt.datetime.fromtimestamp(epoch, _dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _epoch(stamp) -> float | None:
    try:
        return _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def board_path(league: str) -> Path:
    from . import routes
    return ROOT / "web" / "data" / routes.BOARD_FILES[league]


def watched_games(board: dict, now: float) -> list[dict]:
    """The board's games from six hours before now to eight days ahead:
    ``[{key, home, away, kickoff, names}]`` (names: the board's full names
    for the two clubs, where it carries them)."""
    out = []
    for g in (board or {}).get("games") or []:
        if not isinstance(g, dict) or not g.get("home") or not g.get("away"):
            continue
        t = _epoch(g.get("kickoff"))
        if t is None or t < now - AFTER_KICKOFF_S or t > now + AHEAD_S:
            continue
        out.append({"key": f"{g['away']}@{g['home']}", "home": str(g["home"]), "away": str(g["away"]),
                    "kickoff": str(g.get("kickoff") or ""),
                    "names": {str(g["home"]): g.get("home_name") or "", str(g["away"]): g.get("away_name") or ""}})
    return out


def team_table(league: str, games: list) -> dict:
    """{normalized name: code}: the league's full names (engine/teamdex),
    the board's own names for its clubs, and each club's nickname where no
    other club shares it ("chiefs" is KC; "giants" is NYG in the NFL and SF
    in baseball, each in its own league)."""
    from . import teamdex
    table: dict = {}
    nick: dict = {}
    full = dict(teamdex.name_map(league) or {})
    for g in games:
        for code, name in (g.get("names") or {}).items():
            if name:
                full.setdefault(name, code)
    for name, code in full.items():
        n = _norm(name)
        if n:
            table[n] = code
            words = n.split()
            if len(words) >= 2:
                nick.setdefault(words[-1], set()).add(code)
    for word, codes in nick.items():
        if len(codes) == 1 and len(word) >= 4 and word not in table:
            table[word] = next(iter(codes))
    return table


def code_of(name: str, table: dict) -> str | None:
    """A club's code from a name ESPN or a book wrote, dropping a trailing
    word at a time for a college mascot ("Duke Blue Devils" is "Duke")."""
    words = _norm(name).split()
    while words:
        hit = table.get(" ".join(words))
        if hit:
            return hit
        words = words[:-1]
    return None


def _flag(title: str) -> str | None:
    if INJURY_WORDS.search(title or ""):
        return "injury"
    if ROSTER_WORDS.search(title or ""):
        return "roster"
    return None


def injury_updates(rows: list, seen: dict, table: dict, now: float, first: bool) -> list:
    """The designations that moved since the last look, as updates; ``seen``
    is brought up to date in place. ``first``: the league's first look, which
    only remembers."""
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("player") or not r.get("status"):
            continue
        code = code_of(r.get("team") or "", table)
        if not code:
            continue
        key = f"{code}|{r['player']}"
        status = str(r["status"]).strip()
        was = (seen.get(key) or {}).get("status")
        seen[key] = {"status": status, "at": seen.get(key, {}).get("at", now) if was == status else now}
        if first or was == status:
            continue
        out.append({"at": _iso(now), "team": code, "player": r["player"], "pos": r.get("pos") or "",
                    "from": was, "to": status, "injury": r.get("injury") or "",
                    "posted": r.get("date") or None, "comment": r.get("comment") or ""})
    return out


def match_news(items: list, table: dict, players: dict, now: float) -> list:
    """Headlines from the last NEWS_HOURS with the clubs they are about:
    ``[{title, link, source, at, epoch, teams, players, flag}]``. A tagged
    story names its teams and athletes; an untagged headline is read for the
    clubs' names and the listed players' (``players``: {name: code})."""
    out, seen = [], set()
    by_player = {_norm(p): (p, c) for p, c in players.items() if len(_norm(p).split()) >= 2}
    for it in items:
        if not isinstance(it, dict) or not it.get("title") or not it.get("link"):
            continue
        ep = float(it.get("epoch") or 0)
        if ep and ep < now - NEWS_HOURS * 3600:
            continue
        key = _norm(it["title"])
        if it["link"] in seen or key in seen:
            continue
        teams, names = [], []
        for t in it.get("teams") or []:
            c = code_of(t, table)
            if c and c not in teams:
                teams.append(c)
        for a in it.get("athletes") or []:
            hit = by_player.get(_norm(a))
            names.append(a)
            if hit and hit[1] not in teams:
                teams.append(hit[1])
        padded = f" {key} "
        if not teams:
            for name, code in table.items():
                if f" {name} " in padded and code not in teams:
                    teams.append(code)
        for n, (p, c) in by_player.items():
            if f" {n} " in padded:
                if p not in names:
                    names.append(p)
                if c not in teams:
                    teams.append(c)
        if not teams or len(teams) > MAX_TEAMS:
            continue
        seen.update((it["link"], key))
        out.append({"title": it["title"], "link": it["link"], "source": it.get("source") or "",
                    "at": _iso(ep) if ep else None, "epoch": int(ep), "teams": teams, "players": names,
                    "flag": _flag(it["title"])})
    out.sort(key=lambda x: -x["epoch"])
    return out


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(path)


def _fetch_injury_rows(league: str) -> list:
    from .sources import espninjuries as E
    return E.drop_stale_returns(E.current_rows(E.parse_injuries(E.fetch_injuries(league))))


def _fetch_news(league: str) -> list:
    from .sources import espnnews
    return espnnews.fetch(league)


def _fetch_rss(league: str) -> list:
    from .sources import news
    return news.fetch_sport(league)


def run(now: float | None = None, leagues=LEAGUES, boards: dict | None = None, state_path: Path | None = None,
        out_path: Path | None = None, fetch_injuries=None, fetch_news=None, fetch_rss=None,
        publish: bool = True) -> dict:
    """One look at every watched league; writes the state and the free file.
    ``boards``: {league: board dict} in place of the board files (tests)."""
    t = time.time() if now is None else float(now)
    state_path = state_path or STATE_PATH
    state = _read(state_path)
    st_leagues = state.setdefault("leagues", {})
    out = {"generated_at": _iso(t), "every_s": WATCH_EVERY_S, "leagues": {}}
    for league in leagues:
        if boards is not None:
            board = boards.get(league) or {}
        else:
            from . import gate
            board = _read(Path(gate.board_source(board_path(league))))
        games = watched_games(board, t)
        if not games:
            continue
        table = team_table(league, games)
        teams = {c for g in games for c in (g["home"], g["away"])}
        st = st_leagues.setdefault(league, {})
        seen = st.setdefault("seen", {})
        events = [e for e in st.get("events") or []
                  if (_epoch(e.get("at")) or 0) >= t - UPDATE_DAYS * 86400]
        notes = []
        rows = []
        try:
            rows = (fetch_injuries or _fetch_injury_rows)(league) or []
            events += injury_updates(rows, seen, table, t, first=not st.get("looked"))
            st["looked"] = st.get("looked") or _iso(t)
        except Exception as exc:                          # noqa: BLE001
            notes.append(f"injury report not read: {type(exc).__name__}")
        st["events"] = events
        players = {}
        for r in rows:
            code = code_of(r.get("team") or "", table) if isinstance(r, dict) else None
            if code in teams and r.get("player"):
                players[r["player"]] = code
        items = []
        for name, fetch in (("ESPN newsroom", fetch_news or _fetch_news), ("headlines", fetch_rss or _fetch_rss)):
            try:
                items += fetch(league) or []
            except Exception as exc:                      # noqa: BLE001
                notes.append(f"{name} not read: {type(exc).__name__}")
        news = match_news(items, table, players, t)
        per = {}
        for g in games:
            mine = (g["home"], g["away"])
            per[g["key"]] = {
                "home": g["home"], "away": g["away"], "kickoff": g["kickoff"],
                "updates": sorted((e for e in events if e.get("team") in mine),
                                  key=lambda e: e.get("at") or "", reverse=True)[:MAX_UPDATES],
                "news": [n for n in news if set(n["teams"]) & set(mine)][:MAX_NEWS]}
        out["leagues"][league] = {"checked_at": _iso(t), "notes": notes, "games": per}
    _write(state_path, state)
    if publish:
        from . import gate
        gate.publish(out, out_path or WATCH_PATH, "report_watch.json")
    return out


def for_game(doc: dict, league: str, away: str, home: str) -> dict:
    """One game's watch from the file (the build's own read, engine/gamereport)."""
    return (((doc or {}).get("leagues") or {}).get(league) or {}).get("games", {}).get(f"{away}@{home}") or {}


def read() -> dict:
    """The file as the last look wrote it, or {}."""
    return _read(WATCH_PATH)


if __name__ == "__main__":
    got = run()
    for lg, d in got["leagues"].items():
        games = d["games"]
        print(f"{lg}: {len(games)} game(s), {sum(len(g['updates']) for g in games.values())} update(s), "
              f"{sum(len(g['news']) for g in games.values())} headline(s)"
              + (f" — {'; '.join(d['notes'])}" if d["notes"] else ""))
