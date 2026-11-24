"""Every finished game's report, graded, kept for good (2026-11-16).

Ethan, 2026-11-16: "Like, people should be able to go back and still look at
this data and see if we were right or not."

A board keeps a finished game only until it moves on to the next slate (a day
for most leagues, a week for the NFL), and the page of an older game — a
team's schedule, last week's link — is built from the league's own feed
(engine/gamearchive), which knows nothing of ours. So once a finished game's
report has been graded on its box score (engine/reportgrade), it is written
here with everything its page graded beside it:

  * the report, every read and claim graded, its first section "How this
    report did";
  * the game's tickets (its `game_parlays` entry) and the picks its page drew
    (engine/reportkeep.PICK_LISTS);
  * the record's verdict on every pick of the game's players
    (engine/gameresults.read: the number each finished with, or a void), so the
    page grades each pick and leg at its own line, as on the night;
  * the final score.

One gzipped file a game, beside the private boards (engine/gate._full_dir_for):
`report_archive/<league>/<day>/<AWAY@HOME>.json.gz` — paid, as the reports are,
and never in the public tree. A file is written again only when what it holds
has changed. The server hands one to a member (/api/report_archive), and an old
game's page draws it under the score (js/detail.js). Standard library only;
`save` never raises.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

DIR = "report_archive"
#: A league, a day and a club as they may appear in a path: nothing else.
_LEAGUE = re.compile(r"^[a-z]{2,5}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLUB = re.compile(r"^[A-Za-z0-9 .&'():-]{1,48}$")


def _safe(sport: str, day: str, away: str, home: str) -> bool:
    return bool(_LEAGUE.match(str(sport or "")) and _DAY.match(str(day or ""))
                and _CLUB.match(str(away or "")) and _CLUB.match(str(home or "")))


def _club(code: str) -> str:
    """A club's code as a file name: college's "espn:2390" keeps its id."""
    return str(code).replace(":", "-").replace("/", "-")


def path_for(where, sport: str, day: str, away: str, home: str) -> Path | None:
    if not _safe(sport, day, away, home):
        return None
    return Path(where) / DIR / sport / day / f"{_club(away)}@{_club(home)}.json.gz"


def _names(report: dict, extra) -> set:
    """Every player a pick or a leg of this game names (normalized)."""
    from .gameresults import norm
    out: set = set()

    def walk(x):
        if isinstance(x, dict):
            if x.get("player") and (x.get("market") or x.get("bet") or x.get("pick")):
                out.add(norm(x["player"]))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(report)
    walk(extra)
    out.discard("")
    return out


def doc_for(report: dict, g: dict, sport: str, label: str, parlays, picks, results: dict) -> dict:
    """What one finished game's page grades, in one document."""
    lv = (g or {}).get("live") or {}
    names = _names(report, [parlays, picks])
    mine = {k: v for k, v in (results or {}).items() if k.split("|", 1)[0] in names}
    out = {"sport": sport, "date": str((g or {}).get("date") or "")[:10], "label": label,
           "game": f"{g.get('away')}@{g.get('home')}", "away": g.get("away"), "home": g.get("home"),
           "kickoff": g.get("kickoff") or "",
           "final": {"away": lv.get("away_score"), "home": lv.get("home_score")},
           "report": {k: v for k, v in report.items() if k != "_bets"}, "results": mine}
    if parlays:
        out["parlays"] = parlays
    if picks:
        out["picks"] = picks
    return out


def _read(path: Path) -> dict | None:
    """The document a file holds, or None (no file, or one that cannot be read)."""
    try:
        doc = json.loads(gzip.decompress(path.read_bytes())) if path.exists() else None
    except (OSError, ValueError, EOFError, gzip.BadGzipFile):
        return None
    return doc if isinstance(doc, dict) else None


def keep_start(report: dict, parlays, picks, old: dict | None) -> tuple:
    """WHAT A GAME CARRIED AT ITS START IS NEVER WRITTEN OVER WITH LESS (step AEA, 24 November 2026).

    A finished game's file is written again whenever what it holds changes, from what the build has for the
    game: the report kept from before the start, its tickets and its picks (engine/reportkeep). A build that
    had lost them for a game (live on the 24th: every NFL game of the week before but its Monday night read
    "unkept" on Report Picks, its parlays gone from its file while the Record still counted them) wrote the
    game again without them. So (report, parlays, picks) for the file: this build's, except where the file
    already holds the set the report carried at the start (``kept``) and this build has no such set, or holds
    picks and this build has none, or holds the report as kept before the start and this build has a report
    written after it. The kept report keeps this build's word on how its picks and parlays did
    (reportoutcome.KEY), read off the record."""
    if not isinstance(old, dict):
        return report, parlays, picks
    op = old.get("parlays")
    if isinstance(op, dict) and op.get("kept") and not (isinstance(parlays, dict) and parlays.get("kept")):
        parlays = op
    if old.get("picks") and not picks:
        picks = old["picks"]
    orep = old.get("report")
    if isinstance(orep, dict) and orep.get("kept") and isinstance(report, dict) and not report.get("kept"):
        from .reportoutcome import KEY
        mine = dict(orep)
        if report.get(KEY):
            mine[KEY] = report[KEY]
        report = mine
    return report, parlays, picks


def write(path: Path, doc: dict) -> bool:
    """The file, written only when what it holds has changed."""
    body = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        if path.exists() and gzip.decompress(path.read_bytes()) == body:
            return False
    except (OSError, EOFError, gzip.BadGzipFile):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(gzip.compress(body, mtime=0))
    tmp.replace(path)
    return True


def save(result: dict, reports: list, sport: str, out, results: dict | None = None) -> int:
    """Each finished game whose report is graded on its box score, written to
    the archive. ``results`` is the record's verdicts for the board
    (engine/gameresults.read, read here when none is given). Returns files
    written; never raises."""
    if not out:
        return 0
    try:
        from .gate import _full_dir_for
        from .reportkeep import KEPT_PICKS, parlays_for, picks_for
        where = _full_dir_for(out)
        label = str((result or {}).get("date") or "")
        games = {f"{g.get('away')}@{g.get('home')}|{str(g.get('date') or '')[:10]}": g
                 for g in (result or {}).get("games") or [] if isinstance(g, dict)}
        n = 0
        for r in reports or []:
            if not isinstance(r, dict) or (r.get("graded") or {}).get("status") != "graded":
                continue
            g = games.get(f"{r.get('away')}@{r.get('home')}|{str(r.get('date') or '')[:10]}")
            if not g:
                continue
            path = path_for(where, sport, str(g.get("date") or "")[:10], g.get("away"), g.get("home"))
            if path is None:
                continue
            if results is None:
                from .gameresults import read
                results = read(sport, label) or {}
            picks = ((result or {}).get(KEPT_PICKS) or {}).get(f"{g.get('away')}@{g.get('home')}") \
                or picks_for(result, g)
            rep, parlays, picks = keep_start(r, parlays_for(result, g), picks, _read(path))
            if write(path, doc_for(rep, g, sport, label, parlays, picks, results)):
                n += 1
        # THE REPORTS' OWN RECORD (engine/reportrecord): its index, brought up
        # to date with what was written (and built once where there is none).
        from . import reportrecord
        if n or not (Path(where) / DIR / sport / reportrecord.INDEX).exists():
            reportrecord.refresh(where, sport)
        return n
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ finished reports not archived ({type(exc).__name__}: {exc})")
        return 0


def load(sport: str, day: str, away: str, home: str, where=None) -> dict | None:
    """One archived game, or None (no such game, or a name that is not one)."""
    if where is None:
        from .gate import FULL_DIR
        where = FULL_DIR
    path = path_for(where, str(sport or "").lower(), day, away, home)
    if path is None or not path.exists():
        return None
    try:
        doc = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, ValueError, EOFError, gzip.BadGzipFile):
        return None
    return doc if isinstance(doc, dict) else None
