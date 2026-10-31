"""The referee before kickoff (NFL): who has the game, and what his games have looked like.

    python3 -m engine.nflrefs --fit                    # crew tendencies, saved (weekly, Tuesdays)
    python3 -m engine.nflrefs                          # this week: who is assigned, from where
    python3 -m engine.nflrefs --set "PIT@NO=Clay Martin"   # name one by hand

Ethan, 2026-10-24: "yes build all of D" — D being the public betting
percentages, the referee before kickoff and PFF grades, the three things
his research docs had that our game report did not.

WHAT IT SAYS AND WHAT IT DOES NOT. refcheck.py asked, on 7,340 games, the
only question that would make a referee part of the read: does his past
predict a game against the CLOSING total or spread, in a season his record
never saw? It does not (held-out correlation -0.02 and -0.01). So this is
context on the report and nothing else — it moves no number, and the
report says so in the same line. What his games have looked like is still
a fair thing to want to know before kickoff: how many penalties his crew
calls, how often his games have gone over the closing total, how often the
home team covered.

THE TENDENCIES (`fit`), from nflverse's public files the box already
reads: the schedule (each game's referee, filled after it is played, with
its score and closing lines) and the play-by-play (every penalty marked on
a play). Over the seasons since FIRST_SEASON, per referee: games, penalties
a game (both teams), penalty yards a game, the home team's share of them,
games over the closing total, home covers and home wins; and the same for
the league, so a number is never read without its average. Saved to
data/models/nfl_referees.json; a referee under MIN_GAMES says so.

WHO HAS THE GAME (`assigned`), in this order:

  1. Named by hand (`--set`), for a week no feed has yet.
  2. ESPN's game summary (`gameInfo.officials`), the feed the box already
     reads for every live game; read once every SOURCE_TTL per game, and
     only inside LOOKAHEAD_DAYS of kickoff.
  3. Football Zebras' weekly assignments post, read through the site's
     public WordPress feed once every SOURCE_TTL, credited on the page. A
     row counts only when it names two teams and a referee this league
     already knows, so a layout change finds nothing rather than a wrong
     name.

Nothing is guessed: no assignment found, the report says the referee is
named late in the week, as it always has.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import json
import os
import re
from collections import defaultdict

from . import modelstate

#: Tendencies from this season on: the referee leads the same crew for a
#: season, and crews are reshuffled most winters, so older seasons describe
#: other crews.
FIRST_SEASON = 2024
#: Under this many games a referee's numbers are said to be thin.
MIN_GAMES = 12
#: How long one source's answer is kept before it is asked again.
SOURCE_TTL = 6 * 3600
#: Assignments are reported midweek; nothing is asked further out.
LOOKAHEAD_DAYS = 5

FZ_FEED = ("https://www.footballzebras.com/wp-json/wp/v2/posts"
           "?search=referee%20assignments%20week%20{week}&per_page=5&_fields=title,content,link,date")
SOURCE_WORDS = {"set": "named by hand", "espn": "ESPN", "footballzebras": "Football Zebras"}


def _store_path() -> str:
    return modelstate.path("nfl_referees.json")


def _set_path() -> str:
    return modelstate.path("nfl_referees_set.json")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---- the tendencies -------------------------------------------------------------------------

def penalties_by_game(plays) -> dict:
    """{game_id: {"flags", "yards", "home_flags"}} from play-by-play rows
    carrying game_id, home_team, penalty, penalty_team, penalty_yards."""
    out: dict = defaultdict(lambda: {"flags": 0, "yards": 0.0, "home_flags": 0})
    for p in plays:
        if str(p.get("penalty") or "").split(".")[0] != "1":
            continue
        g = out[str(p.get("game_id") or "")]
        g["flags"] += 1
        g["yards"] += abs(_f(p.get("penalty_yards")) or 0.0)
        g["home_flags"] += int(bool(p.get("penalty_team")) and p.get("penalty_team") == p.get("home_team"))
    return dict(out)


def _blank() -> dict:
    return {"games": 0, "flags": 0, "yards": 0.0, "home_flags": 0, "flag_games": 0,
            "over": 0, "lined": 0, "home_cover": 0, "spread_games": 0, "home_win": 0}


def _add(acc: dict, g: dict, pen: dict | None) -> None:
    hs, as_ = _f(g.get("home_score")), _f(g.get("away_score"))
    acc["games"] += 1
    acc["home_win"] += int(hs > as_)
    if pen is not None:
        acc["flag_games"] += 1
        acc["flags"] += pen["flags"]
        acc["yards"] += pen["yards"]
        acc["home_flags"] += pen["home_flags"]
    total, spread = _f(g.get("total_line")), _f(g.get("spread_line"))
    if total is not None and hs + as_ != total:
        acc["lined"] += 1
        acc["over"] += int(hs + as_ > total)
    # nflverse's spread_line is the home team's margin the market expects.
    if spread is not None and hs - as_ != spread:
        acc["spread_games"] += 1
        acc["home_cover"] += int(hs - as_ > spread)


def _finish(acc: dict) -> dict:
    def rate(a, b):
        return round(a / b, 4) if b else None
    return {"games": acc["games"],
            "flags": round(acc["flags"] / acc["flag_games"], 2) if acc["flag_games"] else None,
            "yards": round(acc["yards"] / acc["flag_games"], 1) if acc["flag_games"] else None,
            "home_share": rate(acc["home_flags"], acc["flags"]),
            "over": rate(acc["over"], acc["lined"]), "lined": acc["lined"],
            "home_cover": rate(acc["home_cover"], acc["spread_games"]),
            "home_win": rate(acc["home_win"], acc["games"])}


def tendencies(schedule, penalties: dict, first_season: int = FIRST_SEASON) -> dict:
    """{"league": {...}, "refs": {name: {...}}, "seasons": [first, last]}
    over the played regular-season and playoff games with a referee."""
    league, refs = _blank(), defaultdict(_blank)
    seasons = []
    for g in schedule:
        ref = str(g.get("referee") or "").strip()
        try:
            season = int(g.get("season"))
        except (TypeError, ValueError):
            continue
        if not ref or season < first_season or _f(g.get("home_score")) is None or _f(g.get("away_score")) is None:
            continue
        pen = penalties.get(str(g.get("game_id") or ""))
        _add(league, g, pen)
        _add(refs[ref], g, pen)
        seasons.append(season)
    return {"league": _finish(league), "refs": {k: _finish(v) for k, v in sorted(refs.items())},
            "seasons": [min(seasons), max(seasons)] if seasons else []}


def fit(first_season: int = FIRST_SEASON, say=print) -> dict:
    """Read the schedule and each season's play-by-play, save the tendencies."""
    from .sources.nflpbp import load_pbp_rows
    from .sources.nflverse import load_schedules
    schedule = load_schedules()
    last = max(int(g["season"]) for g in schedule if _f(g.get("home_score")) is not None)
    penalties: dict = {}
    for season in range(first_season, last + 1):
        got = penalties_by_game(load_pbp_rows(season, columns=("home_team", "penalty", "penalty_team",
                                                                  "penalty_yards")))
        penalties.update(got)
        say(f"  {season}: penalties read for {len(got):,} games")
    out = tendencies(schedule, penalties, first_season)
    out["fitted"] = _dt.date.today().isoformat()
    path = _store_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    os.replace(tmp, path)
    return out


def load() -> dict:
    try:
        with open(_store_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


# ---- who has the game -----------------------------------------------------------------------

def _key(away: str, home: str) -> str:
    return f"{away}@{home}"


def week_key(season: int, week: int) -> str:
    return f"{int(season)}-W{int(week):02d}"


def set_by_hand(season: int, week: int, pairs: list) -> dict:
    """Store ``["PIT@NO=Clay Martin", …]`` for one week; returns the week."""
    try:
        with open(_set_path(), encoding="utf-8") as fh:
            store = json.load(fh)
    except (OSError, ValueError):
        store = {}
    wk = store.setdefault(week_key(season, week), {})
    for text in pairs:
        game, _, name = str(text).partition("=")
        if "@" not in game or not name.strip():
            raise ValueError(f"expected AWAY@HOME=Name, got {text!r}")
        wk[game.strip().upper()] = name.strip()
    os.makedirs(os.path.dirname(_set_path()) or ".", exist_ok=True)
    with open(_set_path(), "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=1)
    return wk


def by_hand(season: int, week: int) -> dict:
    try:
        with open(_set_path(), encoding="utf-8") as fh:
            return json.load(fh).get(week_key(season, week)) or {}
    except (OSError, ValueError):
        return {}


def referee_of(summary: dict) -> str:
    """The referee named in an ESPN summary, or ""."""
    from .officials import parse
    for o in parse(summary):
        if o.get("role", "").lower() == "referee":
            return o["name"]
    return ""


def _nicknames() -> dict:
    """{word or words that name a team: abbreviation} — the nickname and
    the full name, lower case."""
    from .sources.oddsapi import TEAM_ABBR
    out = {}
    for full, abbr in TEAM_ABBR.items():
        out[full.lower()] = abbr
        out[full.rsplit(" ", 1)[-1].lower()] = abbr
    return out


def _rows(text: str) -> list[str]:
    """An HTML post as its rows of plain text: one per table row, list item,
    paragraph or line break."""
    # A raw line break inside a paragraph is only wrapping; the tags say
    # where a row ends.
    text = re.sub(r"\s*\n\s*", " ", text or "")
    text = re.sub(r"(?i)<\s*(/tr|/li|/p|br\s*/?|/h\d)\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*/t[dh]\s*>", " | ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return [re.sub(r"\s+", " ", _html.unescape(r)).strip() for r in text.split("\n") if r.strip()]


#: The places a post names a home team by, where one place is one team.
#: New York and Los Angeles hold two teams each and are left out: a
#: sentence naming only "Los Angeles" cannot say which game.
CITIES = {"arizona": "ARI", "glendale": "ARI", "atlanta": "ATL", "baltimore": "BAL", "buffalo": "BUF",
          "orchard park": "BUF", "carolina": "CAR", "charlotte": "CAR", "chicago": "CHI", "cincinnati": "CIN",
          "cleveland": "CLE", "dallas": "DAL", "arlington": "DAL", "denver": "DEN", "detroit": "DET",
          "green bay": "GB", "houston": "HOU", "indianapolis": "IND", "jacksonville": "JAX",
          "kansas city": "KC", "las vegas": "LV", "miami": "MIA", "minnesota": "MIN", "minneapolis": "MIN",
          "new england": "NE", "foxborough": "NE", "new orleans": "NO", "philadelphia": "PHI",
          "pittsburgh": "PIT", "san francisco": "SF", "santa clara": "SF", "seattle": "SEA",
          "tampa bay": "TB", "tampa": "TB", "tennessee": "TEN", "nashville": "TEN", "washington": "WAS",
          "landover": "WAS"}


def _sentences(row: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?;])\s+", row) if x.strip()]


def _teams_in(text: str, words: list, nick: dict) -> list:
    """[(position, team)] for every team a stretch of text names, each name
    read once (the longest first, so "Kansas City Chiefs" is one mention)."""
    rest, found = text, []
    for w in words:
        pat = rf"(?<!\w){re.escape(w)}(?!\w)"
        for m in re.finditer(pat, rest):
            found.append((m.start(), nick[w]))
        rest = re.sub(pat, lambda m: " " * len(m.group(0)), rest)
    return sorted(found)


def readings(content: str, referees, games=None, nicknames: dict | None = None) -> list:
    """[(sentence, referee, teams, "AWAY@HOME" or "", why)] for every
    stretch of a post that names a referee.

    THE POSTS ARE PROSE (the box, 2026-10-24: "Alan Eck will be in Chicago
    on Thursday as the Patriots square off with the Bears"), not a table.
    So each sentence is split at every referee it names, and each part's
    teams — by nickname, full name or a one-team city — are read. With the
    week's ``games`` (["AWAY@HOME", …]) a part is that game when every team
    it names plays in it, since a team plays once a week; order says
    nothing. Without them, two teams, the visitor first."""
    nick = dict(nicknames if nicknames is not None else _nicknames())
    if nicknames is None:
        nick.update(CITIES)
    names = sorted({str(r).strip() for r in referees if str(r).strip()}, key=len, reverse=True)
    words = sorted(nick, key=len, reverse=True)
    pairs = [tuple(str(g).upper().split("@", 1)) for g in games or [] if "@" in str(g)]
    out = []
    for row in _rows(content):
        for sent in _sentences(row):
            low = sent.lower()
            spots = sorted((m.start(), n) for n in names
                           for m in re.finditer(rf"(?<![\w.]){re.escape(n.lower())}(?!\w)", low))
            for i, (at, name) in enumerate(spots):
                stop = spots[i + 1][0] if i + 1 < len(spots) else len(low)
                part = low[0 if i == 0 else at:stop]
                part = re.sub(rf"(?<![\w.]){re.escape(name.lower())}(?!\w)", " " * len(name), part)
                teams = [t for _p, t in _teams_in(part, words, nick)]
                game, why = "", ""
                if not teams:
                    why = "no team named"
                elif pairs:
                    hit = [g for g in pairs if set(teams) <= set(g)]
                    if len(hit) == 1:
                        game = _key(*hit[0])
                    else:
                        why = "no one game this week holds " + "/".join(sorted(set(teams)))
                elif len(teams) == 2 and teams[0] != teams[1]:
                    game = _key(teams[0], teams[1])
                else:
                    why = f"{len(set(teams))} team(s), not a pair"
                out.append((sent, name, teams, game, why))
    return out


def parse_post(content: str, referees, nicknames: dict | None = None, games=None) -> dict:
    """{"AWAY@HOME": referee} from an assignments post (see `readings`).
    Two referees read onto one game: the one whose words name both its
    teams wins over a passing mention of one ("a rematch of the game Bill
    Vinovich worked in Dallas"); a tie, or a referee read onto two games,
    is neither's — a wrong name is worse than none."""
    got: dict = {}
    for _s, name, teams, game, _w in readings(content, referees, games, nicknames):
        if game:
            both = len(set(teams) & set(game.split("@")))
            got.setdefault(game, {})[name] = max(both, got.get(game, {}).get(name, 0))
    one = {}
    for g, cands in got.items():
        best = max(cands.values())
        top = [n for n, v in cands.items() if v == best]
        if len(top) == 1:
            one[g] = top[0]
    used: dict = {}
    for g, n in one.items():
        used.setdefault(n, []).append(g)
    return {g: n for g, n in one.items() if len(used[n]) == 1}


def _cached_json(url: str, name: str):
    from .sources.fetch import fetch_json
    return fetch_json(url, name, ttl=SOURCE_TTL, timeout=20)


def from_footballzebras(season: int, week: int, referees, games=None) -> dict:
    """The week's post, read off the site's public feed; {} when none.
    ``games`` is the week's ["AWAY@HOME", …] (see `readings`)."""
    try:
        posts = _cached_json(FZ_FEED.format(week=int(week)), f"fz_assignments_{season}_w{int(week):02d}.json")
    except Exception:                                        # noqa: BLE001
        return {}
    for p in posts if isinstance(posts, list) else []:
        title = _html.unescape(str(((p or {}).get("title") or {}).get("rendered") or ""))
        if not re.search(rf"(?i)\bweek\s*{int(week)}\b", title) or "assign" not in title.lower():
            continue
        if str(season) not in str(p.get("date") or "") + title + str(p.get("link") or ""):
            continue
        got = parse_post(str(((p or {}).get("content") or {}).get("rendered") or ""), referees, games=games)
        if got:
            return got
    return {}


def diagnose(games: list, season: int, week: int, store: dict | None = None,
             espn=None, posts_fetch=None, all_games: list | None = None) -> list:
    """What each source answered for the week, as lines: ESPN game by game
    (the officials it lists, by role), then Football Zebras (the posts the
    feed returned, which one is the week's, and what its rows named). For
    the box's run where nothing was named (2026-10-24): which link broke."""
    store = load() if store is None else store
    out = []
    espn = espn or _espn_summary
    for g in games:
        key = _key(g.get("away", ""), g.get("home", ""))
        try:
            summ = espn(g) or {}
            from .officials import parse
            crew = parse(summ)
            info = summ.get("gameInfo") or {}
            out.append(f"  ESPN {key}: " + (", ".join(f"{o['role'] or '?'} {o['name']}" for o in crew) if crew else
                                           ("no summary (no ESPN id for the game)" if not summ else
                                            f"no officials listed yet (gameInfo keys: {sorted(info)[:8]})")))
        except Exception as exc:                             # noqa: BLE001
            out.append(f"  ESPN {key}: {type(exc).__name__}: {str(exc)[:160]}")
    url = FZ_FEED.format(week=int(week))
    try:
        posts = (posts_fetch or (lambda: _cached_json(url, f"fz_assignments_{season}_w{int(week):02d}.json")))()
    except Exception as exc:                                 # noqa: BLE001
        out.append(f"  Football Zebras: {type(exc).__name__}: {str(exc)[:200]}")
        return out
    posts = posts if isinstance(posts, list) else []
    out.append(f"  Football Zebras: the feed returned {len(posts)} post(s)")
    refs = _known_referees(store)
    for p in posts[:5]:
        title = _html.unescape(str(((p or {}).get("title") or {}).get("rendered") or ""))
        content = str(((p or {}).get("content") or {}).get("rendered") or "")
        wk = bool(re.search(rf"(?i)\bweek\s*{int(week)}\b", title)) and "assign" in title.lower()
        this = str(season) in str(p.get("date") or "") + title + str(p.get("link") or "")
        keys = [_key(g.get("away", ""), g.get("home", "")) for g in all_games or games]
        got = parse_post(content, refs, games=keys) if wk and this else {}
        out.append(f"    {str(p.get('date') or '')[:10]} {title[:70]!r}: "
                   + ("the week's post, " + (f"{len(got)} game(s) named" if got else
                                             f"no game read ({len(_rows(content))} rows)")
                      if wk and this else "not the week's post"))
        if wk and this:
            # Every stretch that names a referee, and what it was read as.
            for sent, name, teams, game, why in readings(content, refs, keys)[:24]:
                out.append(f"      {name}: {'/'.join(teams) or '-'} -> {game or why}   «{sent[:90]}»")
    out.append(f"  {len(refs)} referee names known to match against")
    return out


def _known_referees(store: dict) -> set:
    names = set((store.get("refs") or {}).keys())
    try:
        from .sources.nflverse import load_schedules
        names |= {str(g.get("referee") or "").strip() for g in load_schedules()
                  if str(g.get("season")) >= str(FIRST_SEASON)}
    except Exception:                                        # noqa: BLE001
        pass
    return {n for n in names if n}


def assigned(games: list, season: int, week: int, store: dict | None = None,
             today: _dt.date | None = None, espn=None, zebras=None) -> dict:
    """{"AWAY@HOME": (referee, source)} for the week's games, from the first
    source that names each. ``espn(game) -> summary`` and ``zebras(season,
    week, referees) -> {...}`` stand in for the feeds in a test."""
    today = today or _dt.date.today()
    store = load() if store is None else store
    out = {k.upper(): (v, "set") for k, v in by_hand(season, week).items()}
    soon = []
    for g in games:
        key = _key(g.get("away", ""), g.get("home", ""))
        try:
            days = (_dt.date.fromisoformat(str(g.get("date"))[:10]) - today).days
        except ValueError:
            continue
        if key not in out and 0 <= days <= LOOKAHEAD_DAYS:
            soon.append((key, g))
    if not soon:
        return out
    espn = espn or _espn_summary
    for key, g in soon:
        try:
            name = referee_of(espn(g) or {})
        except Exception:                                    # noqa: BLE001
            name = ""
        if name:
            out[key] = (name, "espn")
    if any(key not in out for key, _g in soon):
        got = (zebras or from_footballzebras)(season, week, _known_referees(store),
                                             [_key(g.get("away", ""), g.get("home", "")) for g in games])
        for key, _g in soon:
            if key not in out and got.get(key):
                out[key] = (got[key], "footballzebras")
    return out


def _espn_ids() -> dict:
    from .sources.nflverse import load_schedules
    return {(r.get("away_team"), r.get("home_team"), r.get("gameday")): r.get("espn")
            for r in load_schedules() if r.get("espn")}


_IDS: dict = {}


def _espn_summary(g: dict) -> dict:
    from .sources.espnplays import fetch_summary
    if not _IDS:
        _IDS.update(_espn_ids())
    eid = _IDS.get((g.get("away"), g.get("home"), str(g.get("date"))[:10]))
    return fetch_summary("nfl", str(eid), ttl=SOURCE_TTL) if eid else {}


# ---- on the board ---------------------------------------------------------------------------

def card(name: str, source: str, store: dict) -> dict:
    """What a game carries: the referee, where he was named, his games
    and the league's beside them."""
    return {"referee": name, "source": source, "source_words": SOURCE_WORDS.get(source, source),
            "record": (store.get("refs") or {}).get(name) or {}, "league": store.get("league") or {},
            "seasons": store.get("seasons") or []}


def attach(result: dict, season: int, week: int, **kw) -> str:
    """Stamp ``officials`` on each game whose referee is known. Never raises."""
    try:
        store = load()
        games = [g for g in result.get("games") or [] if isinstance(g, dict)]
        got = assigned(games, season, week, store=store, **kw)
        n = 0
        for g in games:
            hit = got.get(_key(g.get("away", ""), g.get("home", "")))
            if hit:
                g["officials"] = card(hit[0], hit[1], store)
                n += 1
        by = defaultdict(int)
        for _name, src in got.values():
            by[SOURCE_WORDS.get(src, src)] += 1
        return (f"Referees: {n} of {len(games)} game(s) named"
                + (f" ({', '.join(f'{v} {k}' for k, v in sorted(by.items()))})" if by else "")
                + ("" if store else "; no tendencies fitted yet (python3 -m engine.nflrefs --fit)"))
    except Exception as exc:                                 # noqa: BLE001
        return f"Referees skipped: {exc}"


def words(o: dict, home: str = "the home team") -> str:
    """The report's sentence for a game's referee, or "" when there is none."""
    name = o.get("referee") or ""
    if not name:
        return ""
    rec, lg = o.get("record") or {}, o.get("league") or {}
    since = (o.get("seasons") or [None])[0]
    head = f"Referee: {name} ({o.get('source_words') or o.get('source') or ''})."
    n = rec.get("games") or 0
    if not n:
        return head + " We have no games of his in our record yet."
    bits = []
    if rec.get("flags") is not None and lg.get("flags") is not None:
        bits.append(f"{rec['flags']:.1f} penalties a game (league {lg['flags']:.1f})")
    if rec.get("over") is not None and lg.get("over") is not None:
        bits.append(f"{rec['over'] * 100:.0f}% over the closing total (league {lg['over'] * 100:.0f}%)")
    if rec.get("home_cover") is not None and lg.get("home_cover") is not None:
        bits.append(f"home teams covered {rec['home_cover'] * 100:.0f}% (league {lg['home_cover'] * 100:.0f}%)")
    thin = ", a thin sample" if n < MIN_GAMES else ""
    body = (f" His {n} games since {since}{thin}: " + "; ".join(bits) + ".") if bits else f" {n} games in our record."
    return head + body + " " + CAVEAT


#: What refcheck.py measured, said with every referee line.
CAVEAT = ("Over 7,340 games a referee's record added nothing the closing line did not already "
          "hold, so this is context, not part of the read.")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fit", action="store_true", help="read the schedule and play-by-play, save the tendencies")
    ap.add_argument("--set", nargs="+", metavar="AWAY@HOME=Name", help="name this week's referee(s) by hand")
    ap.add_argument("--season", type=int, default=0)
    ap.add_argument("--week", type=int, default=0)
    ap.add_argument("--why", action="store_true", help="say what each source answered this week")
    a = ap.parse_args(argv)
    if a.fit:
        out = fit()
        lg = out.get("league") or {}
        print(f"  {len(out.get('refs') or {})} referees, {lg.get('games', 0)} games {out.get('seasons')}: "
              f"league {lg.get('flags')} penalties a game, {lg.get('over')} over the closing total")
        for name, r in sorted((out.get("refs") or {}).items(), key=lambda kv: -(kv[1].get("flags") or 0)):
            print(f"    {name:<22} {r['games']:>3} games  {r.get('flags') or 0:>5.1f} pen  "
                  f"over {(r.get('over') or 0) * 100:>3.0f}%  home cover {(r.get('home_cover') or 0) * 100:>3.0f}%")
        return 0
    from .sources.nflverse import load_schedules
    sched = load_schedules()
    today = _dt.date.today().isoformat()
    ahead = sorted((r for r in sched if str(r.get("gameday")) >= today and r.get("game_type") == "REG"),
                   key=lambda r: r.get("gameday"))
    season = a.season or (int(ahead[0]["season"]) if ahead else today[:4])
    week = a.week or (int(ahead[0]["week"]) if ahead else 1)
    if a.set:
        print(f"  {week_key(season, week)}: {set_by_hand(season, week, a.set)}")
    games = [{"away": r["away_team"], "home": r["home_team"], "date": r["gameday"]}
             for r in sched if str(r.get("season")) == str(season) and str(r.get("week")) == str(week)]
    if a.why:
        soon = [g for g in games if str(g["date"]) >= today]
        for line in diagnose(soon, int(season), int(week), all_games=games):
            print(line)
    got = assigned(games, int(season), int(week))
    print(f"  {week_key(season, week)}: {len(got)} of {len(games)} game(s) have a referee named")
    for g in games:
        k = _key(g["away"], g["home"])
        name, src = got.get(k, ("", ""))
        print(f"    {g['date']} {k:<9} {name or '-':<22} {SOURCE_WORDS.get(src, src)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
