"""What each sport's model actually has behind it, checked rather than claimed.

Every sport here has a written spec, and every spec has an implementation
map in ``docs/``. Those maps are prose, and prose rots: a feed stops
resolving, a season's results never get ingested, a key expires, and the
document still says ✅ because nobody edited it.

This module answers the same question by looking. Each layer names the
thing a model needs, why it needs it, and a check that reads the real
database, the real cache and the real config. The output is deliberately
actionable — a missing layer prints the command that fixes it, because
"MLB umpires: missing" is only useful next to the thing you'd run.

Three states and they mean different things:

* **ok** — present and current enough to price with.
* **partial** — there but thin; the model runs and is weaker than it looks.
* **missing** — the model is running without it right now, and the line
  says what that costs.
* **parked** — no free source exists. Listed every time rather than
  quietly dropped, because a permanent gap you've stopped seeing is how a
  model's blind spot becomes its identity.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

OK, PARTIAL, MISSING, PARKED = "ok", "partial", "missing", "parked"
_ICON = {OK: "✅", PARTIAL: "🟡", MISSING: "❌", PARKED: "📋"}

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"


@dataclass
class Layer:
    name: str
    why: str
    state: str
    detail: str = ""
    fix: str = ""


@dataclass
class SportCoverage:
    sport: str
    label: str
    layers: list = field(default_factory=list)

    @property
    def score(self) -> tuple[int, int]:
        """(layers present, layers that could be present) — parked items are
        excluded from the denominator, because counting a gap with no
        source against the model would make the number meaningless."""
        live = [l for l in self.layers if l.state != PARKED]
        return sum(1 for l in live if l.state == OK), len(live)


# --- primitive checks -------------------------------------------------------
def _count(conn, sql: str, args: tuple = ()) -> int:
    try:
        return int(conn.execute(sql, args).fetchone()[0])
    except Exception:
        return 0


def _games(conn, sport: str) -> tuple[int, int]:
    total = _count(conn, "SELECT COUNT(*) FROM games WHERE sport=?", (sport,))
    scored = _count(conn, "SELECT COUNT(*) FROM games WHERE sport=? AND "
                          "home_score IS NOT NULL", (sport,))
    return total, scored


def _logs(conn, sport: str) -> int:
    return _count(conn, "SELECT COUNT(*) FROM player_game_logs WHERE sport=?",
                  (sport,))


def _cache_age_h(pattern: str) -> float | None:
    """Age of the NEWEST cache file matching a glob, in hours.

    A glob, not a filename, and that is a bug fix rather than a flourish:
    the injury feed caches as ``injuries_2026.csv`` and Statcast as
    ``savant_barrels_batter_2026.csv``, so checking for a fixed name
    reported two working feeds as never fetched. A scan that cries wolf is
    worse than no scan — you stop reading it, and then the real gap goes
    past you too.
    """
    try:
        hits = [p for p in CACHE.glob(pattern) if p.is_file()]
    except OSError:
        return None
    if not hits:
        return None
    newest = max(p.stat().st_mtime for p in hits)
    return round((time.time() - newest) / 3600, 1)


def _has_key(env: str) -> bool:
    try:
        from .secrets import load_local_secrets
        load_local_secrets()
    except Exception:
        pass
    return bool(os.environ.get(env))


def _journal(sport: str) -> tuple[int, int]:
    """(open, settled) bets for this sport."""
    try:
        from . import ledger
        conn = ledger.connect()
        o = _count(conn, "SELECT COUNT(*) FROM bets WHERE sport=? AND "
                         "status='open'", (sport,))
        s = _count(conn, "SELECT COUNT(*) FROM bets WHERE sport=? AND "
                         "status IN ('won','lost','push')", (sport,))
        conn.close()
        return o, s
    except Exception:
        return 0, 0


def _results_layer(conn, sport: str, need: int, fix: str) -> Layer:
    total, scored = _games(conn, sport)
    state = OK if scored >= need else PARTIAL if scored else MISSING
    return Layer(
        "Results history", "team ratings, spreads, totals and settlement all "
        "read finished games", state,
        f"{scored} finished game(s) of {total} scheduled (need ~{need})", fix)


def _logs_layer(conn, sport: str, need: int, fix: str) -> Layer:
    n = _logs(conn, sport)
    state = OK if n >= need else PARTIAL if n else MISSING
    return Layer("Player game logs", "every player prop is projected from "
                 "these; without them the board has no props at all", state,
                 f"{n} log row(s) (need ~{need})", fix)


def _odds_layer() -> Layer:
    if _has_key("ODDS_API_KEY"):
        return Layer("Sportsbook prices", "nothing is recommended against a "
                     "line we didn't fetch", OK, "ODDS_API_KEY is set")
    return Layer("Sportsbook prices", "nothing is recommended against a line "
                 "we didn't fetch", MISSING, "ODDS_API_KEY not set",
                 "free key at the-odds-api.com → secrets.local")


BOARD_FILE = {"nfl": "recommendations.json", "mlb": "mlb_recommendations.json",
              "nba": "nba.json", "wnba": "wnba.json", "cfb": "cfb.json",
              "ufc": "ufc.json"}


def _board_status(sport: str) -> str:
    """What the last build of this sport's board said about itself."""
    import json
    p = ROOT / "web" / "data" / BOARD_FILE.get(sport, "")
    try:
        return str(json.loads(p.read_text()).get("status") or "")
    except (OSError, ValueError):
        return ""


def _journal_layer(sport: str) -> Layer:
    o, s = _journal(sport)
    # An empty journal in the offseason is not a gap — there were no games
    # to bet. Reporting it as ❌ next to a real gap is how a scan trains
    # you to skim past the rows that matter.
    dormant = _board_status(sport) in ("offseason", "no_card")
    if not (o or s) and dormant:
        return Layer("Graded record", "CLV and the audit loop are what decide "
                     "whether this model is allowed to keep betting", PARTIAL,
                     "nothing journaled yet — this board is out of season, so "
                     "there has been nothing to bet",
                     "it fills itself once the season starts")
    state = OK if s >= 25 else PARTIAL if (o or s) else MISSING
    return Layer("Graded record", "CLV and the audit loop are what decide "
                 "whether this model is allowed to keep betting", state,
                 f"{s} settled · {o} open",
                 "" if s else "the board journals automatically once it runs")


# --- per-sport inventories --------------------------------------------------
def nfl(conn) -> SportCoverage:
    weeks = _count(conn, "SELECT COUNT(*) FROM team_weeks WHERE sport='nfl'")
    return SportCoverage("nfl", "NFL", [
        _results_layer(conn, "nfl", 250, "python3 ingest.py nfl"),
        _logs_layer(conn, "nfl", 5000, "python3 ingest.py nfl"),
        _odds_layer(),
        Layer("EPA / PROE / pace", "§5's volume-first projection — the inputs "
              "that separate a real usage read from a box-score average",
              OK if weeks >= 200 else PARTIAL if weeks else MISSING,
              f"{weeks} team-week row(s)", "python3 ingest.py nfl"),
        Layer("Injury report", "§7's ripple model holds clouded players and "
              "boosts the beneficiaries",
              OK if _cache_age_h("injuries_*.csv") is not None else MISSING,
              _fresh("injuries_*.csv"), "refreshes with the launcher"),
        Layer("Weather", "§7's wind bands block deep passing above 25mph",
              OK, "Open-Meteo, keyless"),
        Layer("Rosters / depth charts", "a traded player projected on his old "
              "team is a silently wrong number",
              OK if _cache_age_h("sleeper_players_nfl*.json") is not None else MISSING,
              _fresh("sleeper_players_nfl*.json"),
              "python3 launch.py --refresh-rosters"),
        Layer("Referee crews", "§7 crew foul tendencies feed the margins",
              PARKED, "no free assignment or tendency feed"),
        Layer("Coordinator tendencies", "§6 scheme profiles", PARKED,
              "no free tendency feed"),
        _journal_layer("nfl"),
    ])


def mlb(conn) -> SportCoverage:
    umps = _count(conn, "SELECT COUNT(*) FROM game_umpires")
    starters = _count(conn, "SELECT COUNT(*) FROM game_starters")
    return SportCoverage("mlb", "MLB", [
        _results_layer(conn, "mlb", 600, "python3 ingest.py mlb --seasons 2021-2026"),
        _logs_layer(conn, "mlb", 20000, "python3 ingest.py mlb --seasons 2021-2026"),
        _odds_layer(),
        Layer("Statcast", "exit velocity and barrel rate are the difference "
              "between a hitter's luck and his contact quality",
              OK if _cache_age_h("savant_*.csv") is not None else PARTIAL,
              _fresh("savant_*.csv"), "refreshes with the launcher"),
        Layer("Confirmed lineups", "a projected lineup that never took the "
              "field is a void, and betting it is a guess",
              OK if starters else MISSING, f"{starters} recorded lineup row(s)",
              "refreshes with the launcher"),
        Layer("Umpires", "plate-umpire zone size moves strikeout props more "
              "than most matchups do",
              OK if umps >= 100 else PARTIAL if umps else MISSING,
              f"{umps} game(s) with an umpire recorded", "refreshes with the launcher"),
        Layer("Park factors", "the same fly ball is a home run in one park "
              "and an out in another", OK, "built in, per park and per hand"),
        Layer("Catcher framing", "a framing catcher is worth real strikeouts",
              PARKED, "no free per-game framing feed"),
        _journal_layer("mlb"),
    ])


def nba(conn) -> SportCoverage:
    return SportCoverage("nba", "NBA", [
        _results_layer(conn, "nba", 400,
                       "python3 ingest.py nba --seasons 2021-2026 --scores-only"),
        # NOT --scores-only. That flag is precisely what SKIPS the logs, so
        # offering it as the fix for "0 player game logs" hands over a
        # command that cannot work — and worse, one that exits looking
        # successful because every day is already stored.
        _logs_layer(conn, "nba", 8000,
                    "python3 ingest.py nba --seasons 2024-2026"),
        _odds_layer(),
        Layer("Schedule feed", "the free NBA CDN answers 'is there a slate "
              "tonight' before a single credit is spent", OK,
              "cdn.nba.com, keyless"),
        Layer("Availability / injury report", "§2 says a prop is conditional "
              "until the player's status is confirmed; without a feed every "
              "projection assumes she plays", MISSING,
              "no feed wired — minutes come from recent games only",
              "the same gap the WNBA board has; a source would lift both"),
        Layer("Per-possession team defence", "pace pollutes points-allowed, "
              "which is the matchup input the grade reads", PARTIAL,
              "points allowed per GAME, labelled as directional"),
        Layer("Line movement per prop", "§4's first-mover read — who moved "
              "and whether we agree", PARKED,
              "no per-prop movement history is stored yet"),
        _journal_layer("nba"),
    ])


def wnba(conn) -> SportCoverage:
    from .hoops import WNBA
    return SportCoverage("wnba", "WNBA", [
        _results_layer(conn, "wnba", 200, "python3 ingest.py wnba --seasons 2021-2026"),
        _logs_layer(conn, "wnba", 3000, "python3 ingest.py wnba --seasons 2021-2026"),
        _odds_layer(),
        Layer("Schedule feed", "the day's slate and its finals",
              OK, "ESPN basketball/wnba, keyless"),
        Layer("Fitted tuning", "margin SD, blowout curves and stat spreads "
              "are the NBA's until this league has graded results of its own",
              PARTIAL if WNBA.probation else OK,
              "on probation — journaled and graded, not staked",
              "grades accumulate automatically; the bar lifts itself"),
        Layer("Availability / injury report", "§2.3 — the single highest-edge "
              "information category in this league, and the one that decides "
              "whether a prop is a bet or a conditional", MISSING,
              "no feed wired; freshness is capped and with it the grade, so "
              "half-Kelly stays out of reach",
              "the biggest single upgrade available to this board"),
        Layer("On/off + lineup data", "§5 — when X sits, whose usage jumps. "
              "In a 12-player league this is knowable and rarely priced",
              PARKED, "no free on/off feed; the injury ripple is modelled "
              "from minutes redistribution only"),
        Layer("International windows", "§6 — players arriving late or "
              "carrying an overseas season's fatigue", PARKED,
              "no structured source; a manual note would be guesswork"),
        _journal_layer("wnba"),
    ])


def cfb(conn) -> SportCoverage:
    from .cfb import ratings as R
    fit = R.fit_from_history(conn, {})
    talent_key = _has_key("CFBD_API_KEY")
    qb = ROOT / "data" / "cfb_qb_status.json"
    return SportCoverage("cfb", "College football", [
        _results_layer(conn, "cfb", R.MIN_GAMES,
                       "python3 ingest.py cfb --seasons 2021-2026"),
        Layer("Schedule / conferences / rankings", "attention tier is the "
              "whole model, and it reads all three", OK,
              "ESPN college-football feed, keyless"),
        _odds_layer(),
        Layer("Fitted variance", "how far games land from the projection "
              "decides every probability on the board",
              OK if fit.fitted else MISSING,
              fit.note.split(".")[0],
              "python3 ingest.py cfb --seasons 2021-2026"),
        Layer("Recruiting / talent prior", "§5-§6 — in September a team's own "
              "results are two games against unmeasured opponents; the "
              "high-school layer is what carries the number until then",
              OK if talent_key else MISSING,
              "CFBD_API_KEY is set" if talent_key else
              "no key — the board runs with no preseason prior",
              "" if talent_key else
              "free key at collegefootballdata.com/key → secrets.local"),
        Layer("Quarterback status", "§2.3 — a gate, not an adjustment; "
              "unconfirmed games publish conditionals",
              OK if qb.exists() else PARTIAL,
              "confirmations recorded" if qb.exists() else
              "none recorded yet — every game publishes as a conditional",
              'python3 launch.py --confirm-qb "TEAM"'),
        Layer("Play-by-play efficiency", "§5's success rate and drive stats",
              PARKED, "no free CFB play-by-play ingest"),
        _journal_layer("cfb"),
    ])


def ufc(conn) -> SportCoverage:
    doss = ROOT / "data" / "ufc_dossiers.json"
    n = 0
    if doss.exists():
        try:
            import json
            n = len(json.loads(doss.read_text()))
        except Exception:
            n = 0
    weigh = ROOT / "data" / "ufc_weighins.json"
    cards = ROOT / "data" / "ufc_cards.json"
    return SportCoverage("ufc", "UFC", [
        Layer("Fighter dossiers", "the engine refuses to bet a fighter it has "
              "no measured record for", OK if n >= 20 else PARTIAL if n else MISSING,
              f"{n} dossier(s)", "python3 ufc_dossiers.py"),
        _odds_layer(),
        Layer("Weigh-ins", "'missed weight → automatic void' was a rule with "
              "nothing behind it until this existed",
              OK if weigh.exists() else PARTIAL,
              "recorded" if weigh.exists() else "none recorded this card",
              'python3 launch.py --weigh-in "Fighter" 155.5'),
        Layer("Card venue", "§8 — a 25-foot cage raises finishes and altitude "
              "pushes them later; both reshape every method and distance "
              "price and neither rides in the odds feed",
              OK if cards.exists() else MISSING,
              "recorded" if cards.exists() else "not set — cage size and "
              "altitude unchecked, scored neutral",
              'python3 launch.py --card-venue "UFC Apex" "Las Vegas"'),
        Layer("Method / distance prop prices", "§3.8 — books derive method "
              "props off the moneyline, so the props are the numbers they "
              "did NOT think about. Without prices we can only publish our "
              "fair number for you to shop", PARTIAL,
              "our feed carries moneylines reliably and method markets "
              "rarely; unpriced markets publish a fair number instead",
              "shop the fair numbers on each pick card"),
        Layer("Line movement open → close", "§4 — MMA lines move further from "
              "open to close than almost any market, and the path is the "
              "signal", PARKED,
              "no per-fight movement history is stored yet"),
        Layer("Referee & judge assignments", "§8 — a quick-stoppage referee "
              "raises TKO probability; assigned judges shift every decision "
              "path", PARKED, "no structured assignment feed"),
        _journal_layer("ufc"),
    ])


def _fresh(cache_name: str) -> str:
    age = _cache_age_h(cache_name)
    return "never fetched" if age is None else f"cached {age}h ago"


BUILDERS = {"nfl": nfl, "mlb": mlb, "nba": nba, "wnba": wnba, "cfb": cfb,
            "ufc": ufc}


def scan(sports: list[str] | None = None) -> list[SportCoverage]:
    from .db import connect
    conn = connect()
    try:
        return [BUILDERS[s](conn) for s in (sports or list(BUILDERS))
                if s in BUILDERS]
    finally:
        conn.close()


def report(sports: list[str] | None = None) -> str:
    lines = ["Data & model coverage — measured, not claimed", ""]
    for cov in scan(sports):
        have, total = cov.score
        lines.append(f"{cov.label}  ({have}/{total} live layers present)")
        for l in cov.layers:
            lines.append(f"  {_ICON[l.state]} {l.name}: {l.detail}")
            lines.append(f"       why it matters — {l.why}")
            if l.fix and l.state in (MISSING, PARTIAL):
                lines.append(f"       → {l.fix}")
        lines.append("")
    lines.append("📋 = no free source exists. Listed every time on purpose: a "
                 "permanent gap you've stopped seeing is how a blind spot "
                 "becomes an identity.")
    return "\n".join(lines)
