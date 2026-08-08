#!/usr/bin/env python3
"""Which team-logo and player-headshot URLs actually resolve. Probe only.

    python3 assets.py --probe            # every sport
    python3 assets.py --probe --sport nfl

WHY THIS EXISTS BEFORE THE FEATURE. Every image host involved —
`a.espncdn.com`, `static.www.nfl.com`, `midfield.mlbstatic.com` — is
refused by the cloud container's network policy, so the URL patterns below
are recalled, not verified. This session has already paid three times for
writing code against an API shape nobody had called:

  * `limit=400` on ESPN's scoreboard, which EMPTIED every response
  * a custom User-Agent, which 403'd four feeds silently for weeks
  * `score: "0"`, read as a live 0-0 on 48 scheduled fixtures

A wrong logo URL fails softer than any of those — a broken image instead of
a wrong number — but it fails on every card at once, and a layout built
around an image that never arrives is worse than no image. So: run this on
a machine with a normal connection, send the output, and the feature gets
built against whatever answered.

NOTHING HERE IS WIRED INTO THE SITE. It writes nothing, caches nothing and
changes no board. It prints a table.

WHAT IT CANNOT TELL YOU. Only whether a URL returns an image. Whether the
site may USE these is a separate question with a real answer: team logos
are trademarks and headshots are licensed photographs. On a local board
served by `python3 launch.py` to one person that is a non-issue in
practice. It stops being one the day this gets a public address, and
hotlinking a league's own CDN is the version of it that gets noticed first.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TIMEOUT = 15

#: Candidate logo patterns. `{k}` is the league key, `{a}` the abbreviation
#: (lower-cased for ESPN, which is what its paths use).
LOGO_PATTERNS = [
    ("espn-500", "https://a.espncdn.com/i/teamlogos/{k}/500/{a}.png"),
    ("espn-500-dark", "https://a.espncdn.com/i/teamlogos/{k}/500-dark/{a}.png"),
    ("espn-scoreboard", "https://a.espncdn.com/combiner/i?img=/i/teamlogos/{k}/500/{a}.png&w=200&h=200"),
]

#: Which ESPN league key each of our sports uses, and three real
#: abbreviations to try — including one where our spelling and ESPN's are
#: known to differ, because that is where a naive map breaks.
SPORTS = {
    "nfl":  ("nfl",  ["kc", "was", "la"]),
    "mlb":  ("mlb",  ["nyy", "bos", "laa"]),
    "nba":  ("nba",  ["bos", "lal", "gs"]),
    "wnba": ("wnba", ["min", "lv", "ny"]),
    "cfb":  ("ncaa", ["333", "130", "2"]),   # ESPN uses numeric team ids here
}


def _get(url: str) -> tuple[str, str]:
    """(verdict, detail) — never raises, so one dead host cannot end the run."""
    req = urllib.request.Request(url)          # no custom User-Agent; see fetch.py
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read(4096)
            ctype = r.headers.get("Content-Type", "?")
            total = r.headers.get("Content-Length") or f"{len(body)}+"
            ok = ctype.startswith("image/")
            return ("OK " if ok else "NOT-IMAGE",
                    f"{r.status} {ctype} {total}b")
    except Exception as exc:                                  # noqa: BLE001
        return "FAIL", f"{type(exc).__name__}: {str(exc)[:60]}"


def probe_logos(only: str | None) -> None:
    print("=" * 78)
    print("TEAM LOGOS")
    print("=" * 78)
    for sport, (key, abbrs) in SPORTS.items():
        if only and sport != only:
            continue
        print(f"\n  {sport.upper()}  (ESPN league key '{key}')")
        for label, pat in LOGO_PATTERNS:
            for a in abbrs:
                url = pat.format(k=key, a=a)
                verdict, detail = _get(url)
                print(f"    {verdict:<10} {label:<16} {a:<5} {detail}")
                if verdict == "OK ":
                    break        # one success per pattern is enough to judge it


def probe_nfl_headshots() -> None:
    """The one case that needs no guessing: nflverse ships the URL.

    Measured on the cached 2026 roster — 2,824 of 2,930 players carry a
    `headshot_url`, 96%. So for NFL the question is not "what is the
    pattern" but only "does the host serve it to us".
    """
    print("\n" + "=" * 78)
    print("PLAYER HEADSHOTS — NFL (URL comes from the roster, not a guess)")
    print("=" * 78)
    path = os.path.join(ROOT, "data", "cache", "roster_2026.csv")
    if not os.path.exists(path):
        print("  no cached 2026 roster; run `python3 ingest.py nfl` first")
        return
    with open(path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh)
                if (r.get("headshot_url") or "").strip()]
    print(f"  {len(rows)} roster rows carry a headshot_url")
    print("\n  RAW, as nflverse ships it:")
    for r in rows[:2]:
        verdict, detail = _get(r["headshot_url"])
        name = r.get("full_name") or r.get("player_name") or "?"
        print(f"    {verdict:<10} {name[:24]:<24} {detail}")

    # THE SIZE IS THE PROBLEM, not the availability. Measured from Ethan's
    # machine 2026-08-08: 3,797,822 / 3,145,446 / 4,307,894 bytes. A board
    # showing twelve props would pull ~45MB of headshots to draw them at
    # 40px. That is not a face feature, it is a stall.
    #
    # These are Cloudinary URLs (`/image/upload/<transforms>/league/<id>`),
    # so transforms go in the path. Which ones this account allows is the
    # open question, and guessing it is how the last three feed bugs
    # happened — so it is asked here rather than written into the site.
    print("\n  RESIZED — which transform does this Cloudinary allow?")
    variants = [
        ("w_96,h_96,c_fill,g_face", "square crop centred on the face"),
        ("w_96,c_fill",             "width only, default gravity"),
        ("w_96",                    "width only, no crop"),
        ("t_headshot_desktop",      "a named preset, if one exists"),
    ]
    base = rows[0]["headshot_url"]
    name = rows[0].get("full_name") or "?"
    marker = "/image/upload/"
    if marker not in base:
        print(f"    the URL shape changed — no '{marker}' in {base[:70]}")
        return
    head, tail = base.split(marker, 1)
    # nflverse already ships `f_auto,q_auto` as the transform segment; the
    # new one replaces it rather than stacking a second copy.
    tail_id = tail.split("/", 1)[1] if "/" in tail else tail
    for tf, label in variants:
        url = f"{head}{marker}f_auto,q_auto,{tf}/{tail_id}"
        verdict, detail = _get(url)
        print(f"    {verdict:<10} {label:<34} {detail}")
        print(f"    {'':<10} {url[:96]}")
    print(f"\n    (all four are the same player: {name})")


def probe_other_headshots(only: str | None) -> None:
    """The sports where we hold a NAME and the CDN wants an ID.

    This is the real cost of the feature and the reason it is not one
    change: NFL hands us the URL, and every other sport needs an id we do
    not currently store anywhere — `player_game_logs` has `player` and no
    identifier. Each of these would mean capturing the id during ingest.

    NBA and WNBA are now DONE and are here only as a regression check: the
    box-score summary carries `athlete.headshot.href`, ingest writes it to
    `player_assets`, and the board reads it. MLB is still open, because we
    ingest statsapi — which gives MLB's ids, not ESPN's — so it needs a
    name→id join before an ESPN path means anything.
    """
    print("\n" + "=" * 78)
    print("PLAYER HEADSHOTS — the sports that need an ID we do not store")
    print("=" * 78)
    cands = [
        # THE TWO THE BOARD NOW SHIPS. Both are constructed from the person
        # id, because the Stats API publishes no photo URL — so unlike every
        # other entry here, these two are the ones a failure actually costs
        # something. The first is what `facePreview` builds; the second is
        # what the <img> falls back to on the first error. If both say FAIL,
        # MLB props are drawing initials and the path needs correcting.
        ("mlb", "SHIPPED · resized, what the page requests first",
         "https://img.mlbstatic.com/mlb-photos/image/upload/"
         "f_auto,q_auto,w_112,h_112,c_fill,g_face/v1/people/592450/"
         "headshot/67/current"),
        ("mlb", "SHIPPED · untransformed, the first-error fallback",
         "https://img.mlbstatic.com/mlb-photos/image/upload/"
         "w_180,q_auto/v1/people/592450/headshot/67/current"),
        ("mlb", "MLB Stats API spots, an alternative if the above fail",
         "https://midfield.mlbstatic.com/v1/people/592450/spots/120"),
        ("mlb", "ESPN, by ESPN athlete id — needs a join we do not have",
         "https://a.espncdn.com/i/headshots/mlb/players/full/33192.png"),
        ("nba", "ESPN, by ESPN athlete id",
         "https://a.espncdn.com/i/headshots/nba/players/full/1966.png"),
        ("wnba", "ESPN, by ESPN athlete id",
         "https://a.espncdn.com/i/headshots/wnba/players/full/2529205.png"),
    ]
    for sport, label, url in cands:
        if only and sport != only:
            continue
        verdict, detail = _get(url)
        print(f"  {verdict:<10} {sport:<5} {label}")
        print(f"  {'':<10} {detail}")
        print(f"  {'':<10} {url}")

    # Is the raw ESPN headshot worth resizing? The board ships the href the
    # feed handed us, untouched, because that URL cannot be wrong about its
    # own shape. Whether to route it through the combiner — as the LOGOS
    # already do, where it measured 40,228 bytes against 11,537 — is a
    # question with a number behind it, and this is the number. Both sizes
    # print; nobody has to remember which is which.
    if not only or only in ("nba", "wnba"):
        print("\n  Raw vs combiner, same ESPN headshot (decides whether the")
        print("  board should resize faces the way it resizes logos):")
        raw = "https://a.espncdn.com/i/headshots/nba/players/full/1966.png"
        sized = ("https://a.espncdn.com/combiner/i?img=/i/headshots/nba/"
                 "players/full/1966.png&w=112&h=112")
        for label, url in (("raw full", raw), ("combiner 112", sized)):
            verdict, detail = _get(url)
            print(f"    {verdict:<10} {label:<14} {detail}")


def _teams_for(sport: str) -> list[str]:
    """Every abbreviation the site actually uses for a sport, from the same
    teams_*.js the page reads — so the audit covers what will be rendered,
    not a list kept in step by hand."""
    import re
    fname = {"nfl": "teams.js"}.get(sport, f"teams_{sport}.js")
    path = os.path.join(ROOT, "web", "js", fname)
    if not os.path.exists(path):
        return []
    src = open(path, encoding="utf-8").read()
    return sorted(set(re.findall(r'^\s{2}"([A-Za-z0-9]{2,5})":\s*\{', src, re.M)))


def _cfb_ids() -> list[tuple[str, str]]:
    """``[(abbr, espn_id)]`` for college, from ESPN's own teams feed.

    College has no teams_*.js and never will: the FBS alone is 134 schools,
    precisely the list that rots. ESPN keys them numerically, the build
    already pulls those ids off this feed and ships them in the slate
    payload, and the board draws with them — so the audit checks the same
    ids the page will use, not a file that does not exist.

    NARROWED, BECAUSE THE FIRST RUN WAS MOSTLY NOISE. It reported 92 misses
    out of 756: Avila, Culver-Stockton, Dakota Wesleyan, Haskell, Pikeville
    — NAIA and D-II schools with no logo on ESPN's CDN and no route onto a
    D-I scoreboard. ``fetch_teams`` already asks for ``groups=80`` and the
    feed ignores it, answering with ESPN's whole college database. 92 misses
    nobody can act on is how a real one gets missed, so the audit keeps only
    schools filed under a conference the FBS groups feed knows.

    The fallback matters as much as the filter: when the payload carries no
    conference marker at all, this audits EVERYTHING and says so, rather
    than quietly reporting a clean sheet it never earned.
    """
    try:
        from engine.sources import cfbdata
        teams = cfbdata.parse_teams(cfbdata.fetch_teams())
    except Exception as exc:                                  # noqa: BLE001
        print(f"  CFB: teams feed unreachable ({type(exc).__name__}), skipped")
        return []
    every = sorted((ab, t.get("id", "")) for ab, t in teams.items()
                   if t.get("id"))
    # The groups feed says which NCAA division a school is in, which is the
    # filter this wants — D-I plays on the board, D-II and NAIA do not.
    # But it PAGINATES at 25 per division, and a filter built from a page is
    # worse than no filter: it would drop real FBS schools as confidently as
    # it drops Avila. So the map is used only if it is plainly not one page.
    try:
        division = cfbdata.fetch_group_divisions()
    except Exception:                                         # noqa: BLE001
        division = {}
    complete = len(division) > cfbdata.GROUP_PAGE * 8
    if complete:
        # Measured labels are FBS, FCS, NCAA Division II, NCAA Division III.
        # Excluding by the two lower names rather than allow-listing the two
        # upper ones, because a new D-I label would then still be audited.
        d1 = {tid for tid, div in division.items()
              if "Division II" not in div and "Division III" not in div}
        keep = [(ab, tid) for ab, tid in every if tid in d1]
        if keep:
            print(f"  CFB: {len(keep)} of {len(every)} schools are Division I; "
                  f"the rest never reach a board")
            return keep
    print(f"  CFB: no complete division list ({len(division)} schools, and a "
          f"page is {cfbdata.GROUP_PAGE} per division) — auditing all "
          f"{len(every)}, so expect misses you cannot act on")
    return every


#: Mirrors ESPN_ABBR in web/js/visuals.js. Two copies is a real hazard, and
#: `--audit` is exactly what catches them drifting: it reads the map out of
#: the JS rather than trusting this comment.
def _js_abbr_map() -> dict:
    import json
    import re
    src = open(os.path.join(ROOT, "web", "js", "visuals.js"),
               encoding="utf-8").read()
    m = re.search(r"const ESPN_ABBR = (\{.*?\n\};)", src, re.S)
    if not m:
        return {}
    body = m.group(1).rstrip(";")
    body = re.sub(r"(\w+):", r'"\1":', body)          # bare keys -> quoted
    body = re.sub(r",(\s*[}\]])", r"\1", body)        # trailing commas
    try:
        return json.loads(body)
    except ValueError:
        return {}


def _sketch(node, depth: int = 0, budget: list | None = None) -> list:
    """A payload's SHAPE, a few lines of it — never its contents.

    Added because the first diagnostic reported "parsed nothing" and stopped
    there, which named the symptom and hid the cause. All three shapes had
    reached the host and returned real JSON; what nobody could see was where
    in that JSON the conferences were sitting. Dumping the whole payload
    would be unreadable and would put a feed's contents in a chat log, so
    this prints keys, types and lengths only.
    """
    if budget is None:
        budget = [50]                       # total lines, shared across depth
    out: list = []
    pad = "      " + "  " * depth
    # Deep enough to see through this API's sports[0].leagues[0] envelope
    # and one level past it — which is exactly where the conferences would
    # be hiding if the envelope is the answer.
    if budget[0] <= 0 or depth > 6:
        return out
    if isinstance(node, dict):
        keys = list(node)[:12]
        budget[0] -= 1
        out.append(f"{pad}dict({len(node)})  {keys}")
        for k in keys:
            v = node.get(k)
            if isinstance(v, (dict, list)) and v:
                budget[0] -= 1
                out.append(f"{pad}  .{k}")
                out += _sketch(v, depth + 1, budget)
    elif isinstance(node, list):
        budget[0] -= 1
        out.append(f"{pad}list({len(node)})")
        if node:
            out += _sketch(node[0], depth + 1, budget)
    return out


def probe_conferences() -> int:
    """Which groups-feed shape actually returns conferences — and whether the
    built-in table has rotted underneath us.

    WHY THIS EXISTS. `--audit cfb` reported the conferences feed silent while
    the teams feed on the same host answered fine, and from the outside two
    very different failures look identical: the host refusing, and a payload
    that parses to nothing because the conferences were nested a level deeper
    than the parser looked. This separates them, and names the shape that
    works so the ladder can be trimmed to it.

    Cache is bypassed (ttl=0). A stale `espn_cfb_groups.json` is one of the
    candidate explanations, so reading it would answer the wrong question.
    """
    from engine.sources import cfbdata

    print("=" * 78)
    print("CFB CONFERENCES — which groups shape answers")
    print("=" * 78)
    # What the feed does carry: NCAA DIVISION, not conference. Measured, the
    # four labels are FBS / FCS / NCAA Division II / NCAA Division III, and
    # the team lists paginate at GROUP_PAGE. Nothing in pricing reads this.
    treport: list = []
    by_team = cfbdata.fetch_group_divisions(ttl=0, report=treport)
    print("  TEAM → NCAA DIVISION (what the feed does carry — not conference)")
    for label, count, note in treport:
        print(f"  {'OK ' if count else 'NO ':<5} {label:<12} {count:>4} "
              f"schools   {note[:70]}")
    if by_team:
        names: dict = {}
        for div in by_team.values():
            names[div] = names.get(div, 0) + 1
        print(f"\n  {len(by_team)} schools across {len(names)} divisions:")
        for div, n in sorted(names.items(), key=lambda kv: (-kv[1], kv[0])):
            flag = "  <- exactly one page" if n == cfbdata.GROUP_PAGE else ""
            print(f"    {n:>4}  {div}{flag}")
        if all(n == cfbdata.GROUP_PAGE for n in names.values()):
            print("\n  Every division is exactly one page, so this is a page")
            print("  and not a roster. It cannot be used to filter anything.")
    else:
        print("\n  No schools resolved — the shape dump below is the evidence.")

    print("\n  GROUP ID → NAME (asked for, and this feed does not carry it:")
    print("  its group nodes have no id. Kept so a fix would be noticed.)")
    report: list = []
    live = cfbdata.fetch_conferences(ttl=0, report=report, probe=True)
    for label, count, note in report:
        mark = "OK " if count > 1 else "NO "
        print(f"  {mark:<5} {label:<12} {count:>3} parsed")
        # The reason goes on its own line untruncated. Clipping it to fit a
        # column hid the actual error behind the URL that produced it, which
        # is the one thing this run is for.
        print(f"        {note}")
        if count > 1 or note.startswith("unreachable"):
            continue
        # It answered and we read nothing out of it. That is a parser
        # problem, not a network one, and the shape is the evidence.
        url = next((u for lbl, u, _ in cfbdata.GROUP_CANDIDATES
                    if lbl == label), "")
        cache = next((c for lbl, _, c in cfbdata.GROUP_CANDIDATES
                      if lbl == label), "")
        try:
            raw = cfbdata.fetch_json(url, cache, ttl=0,
                                     user_agent=cfbdata.DEFAULT_AGENT)
        except Exception as exc:                              # noqa: BLE001
            print(f"        (could not re-read for the shape: {exc})")
            continue
        print("        shape of what it returned:")
        for line in _sketch(raw):
            print(line)

    if not live:
        print("\n  Nothing usable. The board is running on the built-in table")
        print("  below, which this module's own header says goes stale every")
        print("  time a school changes conference.")
    else:
        print(f"\n  {len(live)} conferences resolved live.")

    built = cfbdata.CONFERENCE_IDS
    print(f"\n  Built-in table ({len(built)} ids) against the live answer:")
    for gid, name in sorted(built.items(), key=lambda kv: int(kv[0])):
        got = live.get(gid)
        if not live:
            state = "unchecked"
        elif got is None:
            state = "GONE from the live feed"
        elif got != name:
            state = f"RENAMED -> {got}"
        else:
            state = "matches"
        print(f"    {gid:>4}  {name:<20} {state}")
    extra = sorted(set(live) - set(built), key=lambda g: int(g) if g.isdigit() else 0)
    if extra:
        print(f"\n  {len(extra)} conference(s) the live feed knows and the "
              f"built-in table does not:")
        for gid in extra:
            print(f"    {gid:>4}  {live[gid]}")
    print("\n  Send this. A shape marked OK is the one to keep; GONE or")
    print("  RENAMED rows are the built-in table rotting, which is exactly")
    print("  what the live feed is supposed to prevent.")
    return 0


def probe_conference_table(date: str) -> int:
    """Is ``CONFERENCE_IDS`` still right? Derive the answer, don't recall it.

    THE QUESTION THIS EXISTS FOR. After the groups feed turned out to carry
    no conference names, that twelve-row table checked into cfbdata.py is
    the ONLY source for a game's conference — and conference feeds
    ``attention_tier``, which scales how much of an edge the CFB model
    believes. It still lists Pac-12, which after realignment is two schools
    rather than a conference.

    THE JOIN, because neither source can answer alone. CFBD knows which
    conference each school is in and does not know ESPN's numeric ids; the
    ESPN scoreboard stamps every team with a ``conferenceId`` and does not
    say what it is called. One school appearing in both gives one row of
    ``{conferenceId: name}``, and a Saturday's slate gives most of the
    table. Nothing here is recalled from memory.

    PROBE ONLY. It prints a comparison and changes nothing. Both CFBD's
    response shape and the join's hit rate are unverified — this container
    reaches neither host — so the shape of anything that fails is dumped
    rather than guessed at, which is the lesson from four rounds on ESPN's
    groups feed.
    """
    from engine.sources import cfbd, cfbdata

    print("=" * 78)
    print(f"CFB CONFERENCE TABLE — derived from {date}, not recalled")
    print("=" * 78)

    # 1. CFBD: school -> conference. Candidate paths, because which one this
    #    plan's key can reach is exactly what is unverified.
    school_conf: dict = {}
    year = date[:4]
    for label, path, params in (
            ("/conferences", "/conferences", {}),
            ("/teams/fbs", "/teams/fbs", {"year": year}),
            ("/teams", "/teams", {"year": year})):
        try:
            rows = cfbd._get(path, params, f"cfbd_probe_{label.strip('/')}"
                             .replace("/", "_") + ".json", ttl=0)
        except Exception as exc:                              # noqa: BLE001
            print(f"  NO   {label:<14} {type(exc).__name__}: {str(exc)[:70]}")
            continue
        if not isinstance(rows, list) or not rows:
            print(f"  NO   {label:<14} answered, but not a list of rows")
            continue
        print(f"  OK   {label:<14} {len(rows)} rows, "
              f"keys={sorted(rows[0])[:10]}")
        got = {str(r.get("school") or r.get("name") or "").strip():
               str(r.get("conference") or "").strip()
               for r in rows if isinstance(r, dict)}
        got = {k: v for k, v in got.items() if k and v}
        if got:
            school_conf = got
            print(f"       -> {len(got)} schools carry a conference here")
            break
        print(f"       -> no school/conference pair in these rows; shape:")
        for line in _sketch(rows[0]):
            print(line)

    if not school_conf:
        print("\n  CFBD gave no school->conference map. Nothing to join to;")
        print("  the table below stays unverified. Send the shapes above.")
        return 1

    # 2. ESPN scoreboard: team -> conferenceId, straight off the feed the
    #    build already reads every day.
    try:
        payload = cfbdata.fetch_scoreboard(date, ttl=0)
    except Exception as exc:                                  # noqa: BLE001
        print(f"\n  ESPN scoreboard for {date} unreachable: {exc}")
        return 1
    seen: dict = {}
    for ev in payload.get("events", []) or []:
        for c in ((ev.get("competitions") or [{}])[0]
                  .get("competitors", []) or []):
            t = c.get("team") or {}
            cid = str(t.get("conferenceId") or "").strip()
            name = (t.get("location") or t.get("displayName") or "").strip()
            if cid and name:
                seen[name] = cid
    print(f"\n  {len(seen)} teams on the {date} slate carry a conferenceId")
    if not seen:
        print("  No conferenceId on this slate — pick a date with games.")
        return 1

    # 3. The join. A school has to be spelled compatibly in both, so match
    #    on the loose key this module already uses for odds-feed names.
    by_key = {cfbdata.name_key(s): c for s, c in school_conf.items()}
    derived: dict = {}
    misses = 0
    for name, cid in seen.items():
        conf = by_key.get(cfbdata.name_key(name))
        if not conf:
            misses += 1
            continue
        derived.setdefault(cid, {})
        derived[cid][conf] = derived[cid].get(conf, 0) + 1
    print(f"  {len(seen) - misses} joined to a CFBD conference, {misses} not")

    # 4. The comparison. Majority name per id — one mis-joined school should
    #    not rename a conference.
    built = cfbdata.CONFERENCE_IDS
    print("\n  id   built-in              derived (from this slate)")
    resolved = {cid: max(names.items(), key=lambda kv: kv[1])[0]
                for cid, names in derived.items()}
    for cid in sorted(set(built) | set(resolved),
                      key=lambda c: int(c) if c.isdigit() else 0):
        old, new = built.get(cid, ""), resolved.get(cid, "")
        if not new:
            state = "not on this slate"
        elif not old:
            state = f"NEW -> {new}"
        elif cfbdata.conference_name(new) == old:
            state = "matches"
        else:
            state = f"RENAMED -> {new}"
        print(f"  {cid:>4}  {old:<20}  {state}")
    print("\n  Send this. RENAMED and NEW rows are the table rotting; a row")
    print("  that is merely 'not on this slate' proves nothing either way —")
    print("  run a busy Saturday to cover more of it.")
    return 0


def audit(only: str | None) -> int:
    """Fetch the logo for EVERY team the site can render, and name the misses.

    The map in visuals.js is recalled for everything the probe did not
    test, which is most of it. A miss is not a crash — the <img> removes
    itself and the monogram chip shows — but it is a team quietly wearing
    the old mark forever, which nobody would notice on a board they do not
    open. This is the measurement that replaces the memory.
    """
    amap = _js_abbr_map()
    if not amap:
        print("  could not read ESPN_ABBR out of visuals.js — audit aborted")
        return 2
    bad = 0
    for sport, (key, _) in SPORTS.items():
        if only and sport != only:
            continue
        # College is keyed by ESPN's numeric id, not by our abbreviation, so
        # its identities come off the same feed the build reads.
        if sport == "cfb":
            pairs = _cfb_ids()
        else:
            pairs = [(ab, amap.get(sport, {}).get(ab.upper(), ab.lower()))
                     for ab in _teams_for(sport)]
        teams = [ab for ab, _ in pairs]
        if not teams:
            if sport != "cfb":
                print(f"\n  {sport.upper()}: no teams file, skipped")
            continue
        misses = []
        for ab, espn in pairs:
            url = (f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/{key}"
                   f"/500/{espn}.png&w=96&h=96")
            verdict, detail = _get(url)
            if verdict != "OK ":
                misses.append((ab, espn, detail))
        print(f"\n  {sport.upper()}: {len(teams) - len(misses)}/{len(teams)} "
              f"logos resolve")
        for ab, espn, detail in misses:
            print(f"    MISS  {ab:<5} -> tried '{espn}'   {detail}")
        bad += len(misses)
    print(f"\n  {bad} miss(es) total.")
    if bad:
        print("  Send this and I will correct the map. Every miss renders the")
        print("  monogram chip in the meantime, which is the old behaviour.")
    return 0


def main(argv: list) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--probe", action="store_true",
                   help="try every candidate URL and report what answered")
    p.add_argument("--audit", action="store_true",
                   help="fetch the logo for EVERY team the site renders and "
                        "name the abbreviations that miss")
    p.add_argument("--conferences", action="store_true",
                   help="which CFB groups-feed shape answers, and whether "
                        "the built-in conference table has gone stale")
    p.add_argument("--conf-table", metavar="DATE", default="",
                   help="derive {conferenceId: name} by joining CFBD to an "
                        "ESPN slate, and compare it with the built-in table")
    p.add_argument("--sport", default="",
                   help="limit to one sport (nfl, mlb, nba, wnba, cfb)")
    a = p.parse_args(argv)
    if not (a.probe or a.audit or a.conferences or a.conf_table):
        p.print_help()
        return 1
    if a.conf_table:
        return probe_conference_table(a.conf_table)
    if a.conferences:
        return probe_conferences()
    only = a.sport.lower() or None
    if a.audit:
        print("=" * 78)
        print("LOGO AUDIT — every abbreviation the site can render")
        print("=" * 78)
        return audit(only)
    probe_logos(only)
    if not only or only == "nfl":
        probe_nfl_headshots()
    probe_other_headshots(only)
    print("\n" + "=" * 78)
    print("READ IT LIKE THIS")
    print("=" * 78)
    print("  Every logo pattern FAILs   -> the host is blocked or the path")
    print("                                changed; send the output and I")
    print("                                will find the shape that works.")
    print("  One pattern is OK          -> that is the one to build on, and")
    print("                                the abbreviation map is the only")
    print("                                remaining work for logos.")
    print("  NFL headshots OK           -> faces ship for NFL immediately;")
    print("                                the URL is already in the roster.")
    print("  MLB/NBA/WNBA OK            -> faces need an id captured during")
    print("                                ingest first. That is per-sport")
    print("                                work, not one change.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
