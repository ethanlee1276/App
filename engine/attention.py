"""Public attention from Wikipedia — are the players everyone is reading about priced too high?

Ethan, 2026-10-16: "add everything now. 1-13" — idea 6. When a player's
Wikipedia page spikes, the public is paying attention to him, and public
attention is where public money goes. A book that knows its customers
shades the popular side. If it shades it far enough, the over on a
player everyone is reading about is the expensive side of the bet.

THE DATA. The Wikimedia pageviews API is official, free and keyless; it
asks only for a User-Agent that says who is asking, and it goes back to
July 2015. Every request names one article and a range of days, so a
whole season costs one call per player. Nobody has to be logged into
anything and nothing is scraped.

  * TITLES. A player's name is not his article ("Josh Allen" is several
    people), so each is looked up once with Wikipedia's own search, with
    his sport in the query, and the title kept (`wiki_titles`).
  * VIEWS. Daily human views per article, kept in `pageviews`. The builds
    keep the board's players current (a few seconds a build at most, each
    man at most once a day); `--backfill` fills past seasons for the
    measurement, resuming where it stopped.

THE READING. His attention ratio: the mean of his last three days' views
over his median day in the four weeks before them. Above SPIKE he is
being read about far more than usual.

THE BAR, WRITTEN BEFORE ITS FIRST RUN. On every stored close in the last
two seasons where his ratio, as it stood the day before the game, was at
or above SPIKE: the under must beat the close's own fair chance by
MIN_EXCESS, with t ≥ MIN_T, over at least MIN_CASES closes, above zero in
each season. The line shading is reported beside it (the close against
his season average, spiked against not). Until it holds nothing reads it.

Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
       "all-access/user/{title}/daily/{start}/{end}")
SEARCH = "https://en.wikipedia.org/w/api.php?action=query&list=search&srlimit=3&format=json&srsearch={q}"
#: Wikimedia's policy asks for a name and a way to reach the operator; a
#: bare one is throttled first (the 429s of 2026-10-17).
USER_AGENT = "QellysBook/1.0 (https://qellysbook.com; pageview research, one call per player)"
SPORT_WORDS = {"nfl": "American football", "cfb": "college football", "mlb": "baseball",
               "nba": "basketball", "wnba": "basketball", "nhl": "ice hockey"}

#: His recent window and the baseline before it, in days.
RECENT = 3
BASELINE = 28
#: "Being read about far more than usual."
SPIKE = 2.0
#: A build spends at most this long keeping views current, and calls the
#: API at most this often.
BUILD_SECONDS = 8.0
PAUSE = 0.2
#: A backfill is hundreds of calls in a row, so it goes slower.
BACKFILL_PAUSE = 1.0
#: After Wikipedia says "too many requests", no build asks again for this long.
COOLDOWN_SECONDS = 3600
#: The longest Retry-After we will sit through once before giving up for the run.
MAX_RETRY_WAIT = 30
#: The bar.
MIN_EXCESS = 0.03
MIN_T = 2.0
MIN_CASES = 300
STORE = "attention_verdict.json"

TABLES = """
CREATE TABLE IF NOT EXISTS wiki_titles (sport TEXT, player TEXT, title TEXT, looked_up TEXT,
    PRIMARY KEY (sport, player));
CREATE TABLE IF NOT EXISTS pageviews (title TEXT, date TEXT, views INTEGER, PRIMARY KEY (title, date));
"""


def ensure_tables(conn) -> None:
    conn.executescript(TABLES)


class RateLimited(Exception):
    """Wikipedia answered 429 twice: stop for now, keep what was fetched."""


def _cooldown_path() -> str:
    from . import modelstate
    return modelstate.path("attention_cooldown.json")


def cooling_down(now: float | None = None) -> bool:
    try:
        with open(_cooldown_path()) as fh:
            return float(json.load(fh).get("until") or 0) > (now if now is not None else time.time())
    except (OSError, ValueError, TypeError):
        return False


def start_cooldown(now: float | None = None) -> None:
    import os
    p = _cooldown_path()
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w") as fh:
            json.dump({"until": (now if now is not None else time.time()) + COOLDOWN_SECONDS}, fh)
    except OSError:
        pass


def _get_json(url: str, timeout: int = 20, sleep=time.sleep):
    """One call; a 429 waits out its Retry-After once (up to MAX_RETRY_WAIT)
    and then raises RateLimited rather than hammering on."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 — fixed https hosts
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                raise
            if attempt == 2:
                raise RateLimited(url) from exc
            try:
                wait = float(exc.headers.get("Retry-After") or 5)
            except (TypeError, ValueError, AttributeError):
                wait = 5.0
            sleep(min(max(wait, 1.0), MAX_RETRY_WAIT))


def pick_title(hits: list, name: str) -> str | None:
    """The first search hit whose title starts with his name — "Josh Allen
    (quarterback)" for Josh Allen, never "Allen Park" — or None."""
    want = name.strip().lower()
    for h in hits or []:
        t = str(h.get("title") or "")
        if t.lower() == want or t.lower().startswith(want + " ("):
            return t
    return None


def lookup_title(sport: str, name: str, get=_get_json) -> str | None:
    """His article's title, or None when the search finds no page that is
    his. A search that fails raises: "no page" is kept for good, and a
    network blip must not be."""
    q = urllib.parse.quote(f"{name} {SPORT_WORDS.get(sport, '')}".strip())
    hits = (get(SEARCH.format(q=q)).get("query") or {}).get("search") or []
    return pick_title(hits, name)


def fetch_views(title: str, start: str, end: str, get=_get_json) -> dict:
    """``{YYYY-MM-DD: views}`` for one article between two dates (inclusive).
    An article with no views in range answers 404, which is an empty dict."""
    url = API.format(title=urllib.parse.quote(title.replace(" ", "_"), safe=""),
                     start=start.replace("-", "") + "00", end=end.replace("-", "") + "00")
    try:
        items = get(url).get("items") or []
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise
    out = {}
    for it in items:
        ts = str(it.get("timestamp") or "")
        if len(ts) >= 8:
            out[f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"] = int(it.get("views") or 0)
    return out


def ratio(views: dict, day: str) -> dict | None:
    """His attention as it stood the morning of `day`: the last RECENT days
    before it over his median day in the BASELINE days before those."""
    d = _dt.date.fromisoformat(day)
    recent = [views.get((d - _dt.timedelta(days=i)).isoformat()) for i in range(1, RECENT + 1)]
    base = [views.get((d - _dt.timedelta(days=i)).isoformat()) for i in range(RECENT + 1, RECENT + BASELINE + 1)]
    recent = [v for v in recent if v is not None]
    base = sorted(v for v in base if v is not None)
    if len(recent) < RECENT or len(base) < BASELINE // 2:
        return None
    med = base[len(base) // 2] if len(base) % 2 else 0.5 * (base[len(base) // 2 - 1] + base[len(base) // 2])
    if med <= 0:
        return None
    r = sum(recent) / len(recent) / med
    return {"ratio": round(r, 2), "recent": round(sum(recent) / len(recent)), "usual": round(med),
            "spike": r >= SPIKE}


# ---- keeping views current (the builds) -----------------------------------------

def title_of(conn, sport: str, player: str, get=_get_json, today=None) -> str | None:
    ensure_tables(conn)
    r = conn.execute("SELECT title FROM wiki_titles WHERE sport=? AND player=?", (sport, player)).fetchone()
    if r is not None:
        return r[0] or None
    t = lookup_title(sport, player, get)
    conn.execute("INSERT OR REPLACE INTO wiki_titles VALUES (?,?,?,?)",
                 (sport, player, t or "", (today or _dt.date.today()).isoformat()))
    conn.commit()
    return t


def stored_views(conn, title: str) -> dict:
    return {d: v for d, v in conn.execute("SELECT date, views FROM pageviews WHERE title=?", (title,))}


def keep_current(conn, sport: str, players, get=_get_json, today=None, budget=BUILD_SECONDS) -> int:
    """Bring each player's last five weeks up to yesterday, each at most
    once a day, inside a few seconds. Returns the players refreshed."""
    ensure_tables(conn)
    if cooling_down():
        return 0                       # Wikipedia asked us to slow down within the hour
    today = today or _dt.date.today()
    yday = (today - _dt.timedelta(days=1)).isoformat()
    start = (today - _dt.timedelta(days=RECENT + BASELINE + 4)).isoformat()
    t0, n = time.monotonic(), 0
    for p in players:
        if time.monotonic() - t0 > budget:
            break
        try:
            title = title_of(conn, sport, p, get, today)
            if not title:
                continue
            have = conn.execute("SELECT MAX(date) FROM pageviews WHERE title=?", (title,)).fetchone()[0]
            if have and have >= yday:
                continue
            got = fetch_views(title, start, yday, get)
        except RateLimited:
            start_cooldown()
            break                      # what this build fetched is kept; the next hour's builds skip
        conn.executemany("INSERT OR REPLACE INTO pageviews VALUES (?,?,?)", [(title, d, v) for d, v in got.items()])
        conn.commit()
        n += 1
        time.sleep(PAUSE)
    return n


# ---- the ideas file -------------------------------------------------------------------

def ideas_section(props, games, board, sport, conn=None):
    """Each board player's attention as it stands today, from the views the
    box has kept (the journal step keeps them current). Reads only: before
    the first journal the tables do not exist and every player reads none."""
    import sqlite3
    players = sorted({row.get("player") for row in (board or {}).get("recommendations") or [] if row.get("player")})
    out: dict = {}
    if players:
        own = conn is None
        if own:
            from . import db as _db
            conn = _db.connect()
        try:
            today = _dt.date.today().isoformat()
            for p in players:
                try:
                    r = conn.execute("SELECT title FROM wiki_titles WHERE sport=? AND player=?", (sport, p)).fetchone()
                except sqlite3.OperationalError:
                    break                        # no journal has run on this database yet
                if not r or not r[0]:
                    continue
                views = stored_views(conn, r[0])
                a = ratio(views, today)
                if a:
                    last = sorted(views.items())[-30:]
                    out[p] = {**a, "title": r[0], "days": [v for _d, v in last]}
        finally:
            if own:
                conn.close()
    return {"players": out, "verdict": load_verdict(sport), "board_players": players}


def journal(sport: str, section: dict, conn=None) -> int:
    own = conn is None
    if own:
        from . import db as _db
        conn = _db.connect()
    try:
        return keep_current(conn, sport, (section or {}).get("board_players") or [])
    finally:
        if own:
            conn.close()


def pick_view(sec, player, market, side="", line=None):
    p = (sec.get("players") or {}).get(player)
    if not p:
        return None
    return {**p, "verdict": sec.get("verdict") or {}}


def game_view(sec, home, away):
    return None


# ---- the measurement (the box) -----------------------------------------------------------

def backfill(conn, sport: str, players, start: str, end: str, limit: int = 500, get=_get_json) -> int:
    """Past seasons for the measurement: one call per player for the whole
    range, skipping anyone already filled, at most `limit` a run."""
    ensure_tables(conn)
    n = 0
    for p in players:
        if n >= limit:
            break
        try:
            title = title_of(conn, sport, p, get)
            if not title:
                continue
            have = conn.execute("SELECT MIN(date) FROM pageviews WHERE title=?", (title,)).fetchone()[0]
            if have and have <= start:
                continue
            got = fetch_views(title, start, end, get)
        except RateLimited:
            # Everything fetched so far is committed; the next run resumes.
            start_cooldown()
            raise
        conn.executemany("INSERT OR REPLACE INTO pageviews VALUES (?,?,?)", [(title, d, v) for d, v in got.items()])
        conn.commit()
        n += 1
        time.sleep(BACKFILL_PAUSE)
    return n


def cases(conn, sport: str = "nfl", markets=("rec_yds", "rush_yds", "pass_yds", "receptions")) -> list:
    """Every stored close with his attention the day before and what he
    did: [(season, market, line, fair_over, ratio, over, season_avg)]."""
    from .bookmenu import closes_compact, fair_pair
    from .backtest import _norm
    from .formbook import game_dates
    ensure_tables(conn)
    titles = {_norm(p): t for p, t in conn.execute("SELECT player, title FROM wiki_titles WHERE sport=? AND title != ''",
                                                   (sport,))}
    dates = game_dates()
    views_cache: dict = {}
    out = []
    for m in markets:
        logs: dict = {}
        for r in conn.execute("SELECT season, period, player, team, value FROM player_game_logs "
                              "WHERE sport=? AND market=? AND value IS NOT NULL ORDER BY season, period", (sport, m)):
            try:
                d = dates.get((int(r[0]), int(r[1]), r[3]))
            except (TypeError, ValueError):
                continue
            if d:
                logs.setdefault(_norm(r[2]), []).append((int(r[0]), d, float(r[4])))
        closes = closes_compact(conn, sport, m)
        for name, games in logs.items():
            title = titles.get(name)
            if not title:
                continue
            if title not in views_cache:
                views_cache[title] = stored_views(conn, title)
            seen: dict = {}
            for season, d, actual in games:
                prior = seen.get(season) or []
                books = closes.get((name, d)) or {}
                if books:
                    lines = [q for q in books.values()]
                    line = sorted(q[0] for q in lines)[len(lines) // 2]
                    fairs = [fair_pair(q[1], q[2]) for q in lines if q[0] == line]
                    fairs = [f[0] for f in fairs if f]
                    a = ratio(views_cache[title], d)
                    if fairs and a and actual != line:
                        out.append((season, m, line, sum(fairs) / len(fairs), a["ratio"], int(actual > line),
                                    (sum(prior) / len(prior)) if prior else None))
                seen.setdefault(season, []).append(actual)
    return out


def _stats(xs):
    n = len(xs)
    if n < 2:
        return {"n": n, "excess": xs[0] if xs else None, "t": None}
    mu = sum(xs) / n
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return {"n": n, "excess": round(mu, 4), "t": round(mu / math.sqrt(var / n), 2) if var > 0 else None}


def verdict(rows) -> dict:
    from .bookmenu import held_seasons
    test = held_seasons({r[0] for r in rows})
    spiked = [r for r in rows if r[0] in test and r[4] >= SPIKE]
    ex = [(1 - r[5]) - (1 - r[3]) for r in spiked]
    per = {}
    for r in spiked:
        per.setdefault(str(r[0]), []).append((1 - r[5]) - (1 - r[3]))
    st = _stats(ex)
    per_s = {k: _stats(v) for k, v in sorted(per.items())}
    shade = {}
    for label, sel in (("spiked", lambda r: r[4] >= SPIKE), ("not", lambda r: r[4] < SPIKE)):
        diffs = [r[2] - r[6] for r in rows if r[6] and sel(r)]
        shade[label] = round(sum(diffs) / len(diffs), 2) if diffs else None
    return {"closes": len(rows), "test": sorted(test), "under_when_spiked": {**st, "by_season": per_s},
            "line_minus_average": shade,
            "holds": bool(st["n"] >= MIN_CASES and (st["excess"] or 0) >= MIN_EXCESS and (st["t"] or 0) >= MIN_T
                          and all((v["excess"] or 0) > 0 for v in per_s.values()))}


def load_verdict(sport: str) -> dict:
    from . import modelstate
    try:
        with open(modelstate.path(STORE)) as fh:
            return json.load(fh).get(sport) or {}
    except (OSError, ValueError):
        return {}


def save_verdict(sport: str, v: dict) -> str:
    from . import modelstate
    import os
    p = modelstate.path(STORE)
    try:
        with open(p) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    d[sport] = v
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=1)
    return p


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Wikipedia attention against the closing line")
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--backfill", action="store_true",
                    help="fill past seasons' views for every player with a stored close (resumes; --limit a run)")
    ap.add_argument("--limit", type=int, default=500, help="players a backfill run fetches")
    ap.add_argument("--save", action="store_true", help="keep the verdict where the pick page reads it")
    a = ap.parse_args(argv)
    from . import db as _db
    conn = _db.connect()
    try:
        if a.backfill:
            players = [r[0] for r in conn.execute(
                "SELECT DISTINCT player FROM player_game_logs WHERE sport=? AND season >= ? AND market IN "
                "('rec_yds','rush_yds','pass_yds')", (a.sport, _dt.date.today().year - 4))]
            try:
                n = backfill(conn, a.sport, players, f"{_dt.date.today().year - 4}-08-01",
                             (_dt.date.today() - _dt.timedelta(days=1)).isoformat(), a.limit)
                stopped = ""
            except RateLimited:
                n, stopped = None, (" Wikipedia asked us to slow down (429): everything fetched is kept — "
                                    "run this again in an hour and it carries on.")
            done = conn.execute("SELECT COUNT(DISTINCT title) FROM pageviews").fetchone()[0]
            print(f"Backfill: {'some' if n is None else n} player(s) fetched this run; {done} article(s) stored in all, "
                  f"of {len(players)} players.{stopped}")
        v = verdict(cases(conn, a.sport))
    finally:
        conn.close()
    u = v["under_when_spiked"]
    per = " · ".join("%s: %s (n %s)" % (k, s["excess"], s["n"]) for k, s in u["by_season"].items())
    print(f"Attention — {a.sport.upper()}: {v['closes']} closes with views the day before; test seasons {v['test']}")
    print(f"  ratio ≥ {SPIKE}: the under against the close's fair chance {u['excess']} (t {u['t']}, n {u['n']}) {per}")
    print(f"  the close minus his season average: spiked {v['line_minus_average']['spiked']}, "
          f"not {v['line_minus_average']['not']}")
    print(f"  THE BAR: ≥ {MIN_EXCESS:+.2f}, t ≥ {MIN_T}, ≥ {MIN_CASES} closes, above zero each season — "
          f"{'HOLDS' if v['holds'] else 'does not hold'}")
    if a.save:
        print(f"  saved → {save_verdict(a.sport, v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
