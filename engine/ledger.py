"""Bet-tracking ledger + bankroll — the self-evaluation system.

Logs every recommendation the model makes, grades each against the real outcome
as results come in, and tracks running performance and bankroll over time. This
is the piece that answers, over a real season, "is the model actually any good?"

  * **Bankroll-aware sizing** — each unit is a configurable percent of the
    *current* bankroll, so dollar stakes scale with the roll (proper bankroll
    management); the model's fractional-Kelly ``stake_units`` sets how many units.
  * **Grading** — an Over hits when the actual clears the line; pushes are
    returned; P&L is computed from the American price.
  * **Reporting** — record (W-L-P), ROI, units and dollars won, closing-line
    value, and breakdowns by grade and market.

SQLite (stdlib), a separate ``data/ledger.db`` from the data warehouse. Logging
is idempotent per (sport, date, player, market).
"""

from __future__ import annotations

import datetime
import math
import re
import sqlite3
from pathlib import Path

from . import markets as _markets
from .odds import american_to_decimal

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "ledger.db"

#: Markets that settle against a GAME rather than a player's stat line —
#: the main lines. Everything not in here is a player prop.
#:
#: One list, two callers, on purpose. The settler needs it to know whether
#: to look for a games row or a player log; account_health needs it to score
#: product mix. A second copy would drift the day a market is added, and the
#: failure would be silent in both places at once.
GAME_MARKETS = ("moneyline", "total", "spread", "team_total")

#: Buckets that DO NOT grade from the history database, whatever market
#: name they wear.
#:
#: Both put something other than a player in the `player` column and both
#: grade somewhere else entirely: `predmarket` carries an exchange ticker
#: and is settled by resolve_predmarket against the exchange's own
#: settlements; `ufc` carries a fighter no player_game_logs row will ever
#: name and is settled by settle_ufc from the MMA results feed. A UFC pick
#: is also stored with market='moneyline', so every audit that selects on
#: GAME_MARKETS sweeps it up.
#:
#: THIS IS THE THIRD TIME THAT HAS COST SOMETHING. The no-show sweep
#: offered to void 104 live desk tickets as scratched lineup players
#: (2026-08-18). `why_open` aged 130 September contracts off their journal
#: date and called them stuck (2026-08-23). And the doctor's grade-evidence
#: check looked for a `games` row behind 11 settled UFC bets — there has
#: never been one, there never will be, and it named `--settle all` as the
#: fix, which cannot help. Every one of those was an audit asking a
#: question that is not true of these two buckets, so the answer lives at
#: module scope where the next audit will find it rather than inside
#: whichever function was written last.
GRADED_ELSEWHERE = ("predmarket", "ufc")

# ``category`` separates the headline record ('main' — picks we stand
# behind) from measurement-only buckets ('longshot' — the HR board, tracked
# to learn whether it finds value, never mixed into the record). It is part
# of the unique key so a player recommended AND watchlisted the same night
# journals in both buckets.
_BETS_TABLE = """
CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, sport TEXT, date TEXT, player TEXT, market TEXT,
    side TEXT, line REAL, book TEXT, odds INTEGER,
    projection REAL, hit_prob REAL, edge REAL, confidence REAL, grade TEXT,
    stake_units REAL, stake_dollars REAL,
    status TEXT DEFAULT 'open', actual REAL,
    pnl_units REAL, pnl_dollars REAL, closing_line REAL,
    category TEXT DEFAULT 'main',
    UNIQUE (sport, date, player, market, category)
);
"""

#: The forecast log: what we said, when we said it, chained.
#:
#: "Permanent and time-stamped" is a promise until it is checkable. This
#: makes it checkable. Each row's hash covers the row's own content AND the
#: previous row's hash, so editing or deleting any past forecast changes
#: every hash after it — and `verify_forecast_log` finds the first break.
#: Publishing the head hash is what turns that into a public commitment:
#: a reader who wrote down last week's head can prove nothing before it
#: moved.
#:
#: It stores the FORECAST ONLY — never the outcome, the P&L or the closing
#: line. Those arrive later and would have to be written into a row that is
#: supposed to be frozen. The bets table remains the mutable record of what
#: happened; this is the immutable record of what was claimed beforehand.
_FORECAST_LOG = """
CREATE TABLE IF NOT EXISTS forecast_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    sealed_ts TEXT, bet_id INTEGER UNIQUE,
    ts TEXT, sport TEXT, date TEXT, player TEXT, market TEXT, side TEXT,
    line REAL, odds INTEGER, hit_prob REAL, category TEXT,
    prev_hash TEXT, hash TEXT
);
"""

SCHEMA = _BETS_TABLE + _FORECAST_LOG + """
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULTS = {"starting_bankroll": "1000", "unit_pct": "1.0",
            "bankroll": "1000",
            # OFF unless deliberately turned on. A default that
            # silently stopped betting real money would be a worse
            # surprise than one that silently kept going.
            "paper_mode": "0"}


def _migrate(conn) -> None:
    """Rebuild a pre-category bets table in place, preserving every row.

    SQLite can't alter a UNIQUE constraint, so the one-time upgrade renames,
    recreates with ``category`` in the key, copies, and drops."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bets)").fetchall()]
    if not cols or "category" in cols:
        return
    keep = ("id, ts, sport, date, player, market, side, line, book, odds, "
            "projection, hit_prob, edge, confidence, grade, stake_units, "
            "stake_dollars, status, actual, pnl_units, pnl_dollars, closing_line")
    conn.executescript(
        "ALTER TABLE bets RENAME TO bets_v1;\n"
        + _BETS_TABLE +
        f"INSERT INTO bets ({keep}, category) "
        f"SELECT {keep}, 'main' FROM bets_v1;\n"
        "DROP TABLE bets_v1;")


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    # WAL + a busy timeout, from the one place that explains why — see
    # engine/db.tune(). The refresher journals this file while the
    # settler grades and the server answers /api/record off it.
    from .db import tune as _db_tune
    # DEFAULT_DB is resolved at call time, not bound at import — a test (or
    # anything else) that repoints the module's DEFAULT_DB must actually win.
    path = Path(path if path is not None else DEFAULT_DB)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    _db_tune(conn)
    _migrate(conn)
    conn.executescript(SCHEMA)
    # Doubleheader leg (1/2) — lets the settler grade a DH bet against the
    # RIGHT game's stat line. NULL = single game or pre-migration row.
    try:
        conn.execute("ALTER TABLE bets ADD COLUMN leg INTEGER")
    except sqlite3.OperationalError:
        pass
    # Projected vs actual minutes — the basketball spec calls this the
    # single fastest diagnostic, and it is: if losses cluster on minutes
    # misses the rotation pipeline is broken, and if the minutes were right
    # and the results weren't, it's efficiency or variance. No other pair
    # of columns separates those two failure modes.
    # Minutes from bet log to the game's scheduled start (capture_lag) and
    # the hr_env dimensions: the park's HR index, signed wind toward CF at
    # pick time (+out/−in, NULL = unknown or indoors), and the roof state.
    # NULL = unknown at pick time (or pre-migration row).
    # …plus lineup_status: the batting slot at pick time (0 = not listed,
    # NULL = unknown/not a batter prop) and whether the card was official
    # or projected — the PA half of every batter prop, journaled.
    # …plus the three columns that make a corrected market refittable.
    # hit_prob is the claim AFTER both corrections — the calibration
    # temperature and the shrink toward the market — so a temperature
    # refitted on it would be a correction learned from corrected claims.
    # raw_prob is the same claim before the market shrink, and cal_temp /
    # cal_bias are the correction that was live when the row was logged;
    # calibrate.undo_temperature inverts the pair exactly. Captured now so
    # the history exists whenever that refit is actually wanted.
    #
    # The contract for any future refit is `cal_temp IS NOT NULL`: a row
    # that records its correction can be un-corrected, and one that does
    # not, cannot. NULL means pre-migration, or one of the paper-track
    # buckets (pricedout / loose / longshot), which write their own
    # inserts and do not capture this. Those rows are excluded rather than
    # assumed uncorrected — assuming is how the compounding starts.
    # …and closing_odds, which is what makes CLV work at all on a book like
    # this one. closing_line measures movement in LINE points, and a
    # home-run prop is quoted OVER 0.5 and closes at 0.5 — it cannot move.
    # On a journal that is two-thirds home runs, 84% of CLV readings were
    # ties by construction and the average was computed off whatever few
    # markets happened to have a movable line. Those markets move on PRICE,
    # the snapshots have carried it all along, and nothing read it.
    for col in ("proj_minutes", "actual_minutes", "lead_min", "park_hr",
                "wind_out", "roofed", "lineup_slot", "lineup_conf",
                "rest_days", "body_clock", "pen_own", "pen_opp",
                "raw_prob", "cal_temp", "cal_bias", "closing_odds",
                # The FIELD's fair at pick time, and how many books it
                # was. `edge` is measured against the book we shopped
                # to, which moves the benchmark with the outlier; this
                # is what it would have been measured against instead.
                # Evidence only — nothing prices from it. bookcheck.py.
                # WHICH BOOK LED the move against or with us, as a flag:
                # 1 when a sharp book went first, 0 when a recreational
                # one did, NULL when nothing moved. Journaled so the miner
                # can test §4's claim that the first mover carries the
                # information. Evidence only — nothing prices from it.
                "move_first_sharp",
                # §5's velocity tell: mph against his own recent baseline,
                # NULL on every row it was not measured for (hitter props,
                # and pitchers without a comparable baseline). NULL is not
                # "steady" — see losspatterns.velo_band.
                "velo_delta",
                # How deep he has been GOING, averaged over recent starts —
                # a projection knowable at pick time. Never tonight's
                # actual depth: that is the future when the bet is placed.
                "tto_proj",
                # §6's coverage tell: the OPPOSING defence's zone rate,
                # 0-1, from participation data already played. NFL props
                # only, NULL everywhere else — and NULL is not "balanced",
                # see losspatterns.coverage_band.
                "opp_zone_rate",
                "fair_consensus", "consensus_books",
                # What line movement DID to this pick, which nothing
                # recorded until 2026-08-07. engine/quality.apply_movement
                # shifts the score by +/-4 (+/-7 on steam), can raise the
                # letter, and REJECTS the pick outright when the drop puts
                # it under 70 — while linemoves.py's docstring said for
                # months that movement was "purely informational … because
                # we haven't measured its predictive value on our own
                # picks yet". It was never informational, and the reason
                # given for believing it was is the reason this column has
                # to exist: you cannot measure a signal you do not store.
                #
                # move_delta is the signed quality points actually applied,
                # NULL when no movement was observed for the prop. Rejected
                # picks land in the `loose` bucket carrying a negative one,
                # which is what makes the veto's own record readable.
                "move_delta", "move_steam"):
        try:
            conn.execute(f"ALTER TABLE bets ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass
    try:
        # The measured cause of a loss (engine/causes.py): "blowout (…)",
        # "short run (…)", or "variance". NULL = not yet swept.
        conn.execute("ALTER TABLE bets ADD COLUMN loss_cause TEXT")
    except sqlite3.OperationalError:
        pass
    # §11's human layer: the tag is a controlled vocabulary (mineable),
    # the note is free text (readable). engine/whytags.py owns the menus.
    try:
        conn.execute("ALTER TABLE bets ADD COLUMN why_tag TEXT")
        conn.execute("ALTER TABLE bets ADD COLUMN why_note TEXT")
    except sqlite3.OperationalError:
        pass
    for k, v in DEFAULTS.items():
        conn.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    return conn


# --- config / bankroll ------------------------------------------------------
def get_cfg(conn, key: str) -> str:
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return row[0] if row else DEFAULTS.get(key, "")


def set_cfg(conn, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()


def set_paper_mode(conn, on: bool) -> None:
    """Stop (or resume) putting money on the picks.

    Deliberately a stored config value rather than a command-line flag on
    the nightly build: the whole point is that it survives until it is
    deliberately turned off, and a flag has to be remembered every night
    by the person who least wants to think about it.
    """
    set_cfg(conn, "paper_mode", "1" if on else "0")


def paper_mode(conn) -> bool:
    return str(get_cfg(conn, "paper_mode") or "0") == "1"


def configure_bankroll(conn, starting: float | None = None, unit_pct: float | None = None) -> None:
    if starting is not None:
        set_cfg(conn, "starting_bankroll", starting)
        set_cfg(conn, "bankroll", starting)     # reset current to starting
    if unit_pct is not None:
        set_cfg(conn, "unit_pct", unit_pct)


def bankroll(conn) -> float:
    return float(get_cfg(conn, "bankroll"))


# --- logging ----------------------------------------------------------------
# Markets that are long shots by nature — plus-money, low-probability
# swings. They are measured in their own bucket at a flat nominal stake
# and must NEVER enter the headline record: a board of +650 home-run
# darts loses most nights by design, and mixing that into the main W-L
# and ROI makes the record describe the dart board instead of the picks
# the model actually stands behind. ``log_longshots`` journals them.
LONGSHOT_MARKETS = {"home_runs", "anytime_td"}


def journal_skip_reason(r: dict, only_recommended: bool = True) -> str | None:
    """Why this recommendation will NOT be journaled — or None if it will.

    The four conditions below used to live inline in the loop, which meant
    the only way to find out why a pick shown on the board never reached
    the journal was to read the loop and reason about it. A prop can be
    displayed as recommended and still be skipped here, and when that
    happens it is invisible everywhere downstream: no journal row, no
    Record entry, and nothing on the Live tab while its game is running.

    Naming it in one place lets --why-pick report the real reason instead
    of a guess, and lets the loop below use the same function, so the
    explanation cannot drift from the behaviour.
    """
    if only_recommended and not r.get("recommended"):
        return f"not recommended (grade {r.get('grade', '?')})"
    if r.get("has_market") is False:
        return ("no real book price — the edge is against a proxy line, and "
                "journaling it would put fictional P&L in the record")
    if r.get("market") in LONGSHOT_MARKETS:
        return f"{r.get('market')} is a long shot — journaled to its own bucket"
    stake = float(r.get("stake_units", 0) or 0)
    if stake <= 0:
        return ("stake is 0.00u — Kelly says this price is not beatable at "
                "our probability, so there is no bet to record")
    return None


def _kickoff_map(result: dict) -> dict:
    """team → kickoff stamp, from the result's own games list. Every
    sport's board carries kickoffs (they come off the odds events), so
    the capture_lag clock is derived HERE, once, for all of them."""
    kick: dict = {}
    for g in result.get("games") or []:
        k = g.get("kickoff") or g.get("commence_time")
        if not k:
            continue
        for side in ("home", "away"):
            if g.get(side):
                kick[g[side]] = k
    return kick


def log_recommendations(conn, result: dict, only_recommended: bool = True) -> int:
    """Insert open bets from a pipeline result dict. Stake dollars are sized
    from the current bankroll: stake_units × unit_pct% × bankroll."""
    from .losspatterns import minutes_until
    from .calibrate import correction_for as cal_correction
    sport = result.get("sport", "nfl")
    date = result.get("date", "")
    unit_dollars = float(get_cfg(conn, "unit_pct")) / 100.0 * bankroll(conn)
    # PAPER MODE. Ethan, 2026-08-09, after the CLV read came back
    # indistinguishable from zero on a cleaned instrument: keep the whole
    # machine running and stop putting money on it.
    #
    # Everything downstream is unchanged — picks are made, journaled,
    # settled against real results, and measured for CLV exactly as
    # before. Only two things differ. The row is filed under 'paper'
    # rather than 'main', so it never touches the headline record; and
    # its dollar stake is zero, because no dollars moved.
    #
    # stake_units is KEPT AS SIZED. That is the whole point: the paper
    # book has to answer "what would this have returned", and a stake of
    # zero cannot. `category` is what makes it costless, not the size.
    paper = str(get_cfg(conn, "paper_mode") or "0") == "1"
    category = "paper" if paper else "main"
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    kick = _kickoff_map(result)
    n = 0
    for r in result.get("recommendations", []):
        # One predicate, used by the loop AND by --why-pick, so the reason
        # the report gives is the reason the code acted on. Proxy prices,
        # long shots and zero stakes are all excluded; see the function.
        if journal_skip_reason(r, only_recommended):
            continue
        stake_units = float(r.get("stake_units", 0) or 0)
        # Read the correction HERE, in the same process that just priced
        # the pick, so what lands in the row is what was actually applied
        # rather than whatever the store holds by the time it settles.
        temp, bias = cal_correction(sport, r["market"])
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, line, "
            "book, odds, projection, hit_prob, edge, confidence, grade, stake_units, "
            "stake_dollars, status, category, leg, proj_minutes, lead_min, "
            "park_hr, wind_out, roofed, lineup_slot, lineup_conf, rest_days, "
            "body_clock, pen_own, pen_opp, raw_prob, cal_temp, cal_bias, "
            "fair_consensus, consensus_books, move_delta, move_steam, "
            "move_first_sharp, velo_delta, tto_proj, opp_zone_rate) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, sport, date, r["player"], r["market"], r.get("side", "OVER"),
             r["line"], r.get("book", ""), r.get("odds", -110), r.get("projection"),
             r.get("hit_prob"), r.get("edge"), r.get("confidence"), r.get("grade"),
             stake_units,
             # Zero dollars in paper mode, and it must be zero rather than
             # small: `performance` sums this column for the dollar P&L,
             # and a paper book that moves the dollar line is not paper.
             0.0 if paper else round(stake_units * unit_dollars, 2),
             category,
             # Which doubleheader leg this bet belongs to — the settler
             # grades against that game's stat line, not a coin flip.
             r.get("game_number") if r.get("doubleheader") else None,
             # The minutes this bet assumed. Basketball props are minutes
             # bets wearing a stat's name; without this column a loss can't
             # be attributed to the rotation read or to the shooting.
             r.get("proj_minutes"),
             # capture_lag: minutes to the game's scheduled start at log
             # time, from the rec's own clock or the board's games list.
             minutes_until(r.get("kickoff") or kick.get(r.get("team"))
                           or kick.get(r.get("opponent"))),
             # hr_env: the park's HR index and the wind toward CF at pick
             # time — measured now, mined nightly, so "wind out at
             # Wrigley" becomes a slice the tribunal can convict.
             r.get("park_hr"), r.get("wind_out"),
             1 if r.get("roofed") else 0 if r.get("roofed") is not None
             else None,
             # lineup_status: the PA half of a batter prop.
             r.get("lineup_slot"),
             1 if r.get("lineup_confirmed") else 0
             if r.get("lineup_confirmed") is not None else None,
             # fatigue: days of rest and the kickoff hour on this team's
             # own clock. Journaled so the miner can decide, on our record,
             # whether a short week or a 10am body clock is a real pocket.
             r.get("rest_days"), r.get("body_clock"),
             # bullpen: weighted relief innings behind this pick, both
             # sides — the measurement the existing multiplier never had.
             r.get("pen_own"), r.get("pen_opp"),
             # The claim before the market shrink, and the correction that
             # produced it. Together they invert (calibrate.undo_temperature)
             # back to the model's own uncorrected number — the only pairs a
             # refit of an already-corrected market could honestly learn on.
             r.get("raw_prob"), temp, bias,
             # The field at pick time, beside the book we shopped to.
             r.get("fair_consensus"), r.get("consensus_books"),
             # What line movement did to this pick's quality score, stamped
             # by quality.apply_movement itself. NULL means no movement was
             # observed for the prop, which is not the same as a movement
             # of zero — the veto's record has to be able to tell "the
             # market did not move" from "the market moved and we ignored
             # it". movecheck.py reads exactly this pair.
             r.get("move_delta"), r.get("move_steam"),
             r.get("move_first_sharp"), r.get("velo_delta"),
             r.get("tto_proj"), r.get("opp_zone_rate")))
        n += cur.rowcount
    # Recommended game bets journal too (sharp-anchor picks live or die by
    # forward results). Moneylines store player = the team picked, line 0.5,
    # side OVER, actual 1/0 — so the standard grader applies. Totals store
    # player = the matchup key (AWAY@HOME) with the real line and side.
    for r in result.get("game_bets", []):
        if not r.get("recommended"):
            continue
        bt = r.get("bet_type")
        if bt == "moneyline":
            player, market = r.get("pick", ""), "moneyline"
            side, line = "OVER", 0.5
        elif bt == "total":
            player = (r.get("matchup") or "").replace(" ", "")
            market = "total"
            side, line = (r.get("side") or "OVER").upper(), float(r.get("line") or 0)
        elif bt == "spread":
            # player = the team laid. The line is stored NEGATED so the
            # standard side-aware grader applies unchanged: a spread bet
            # covers when the team's margin beats the number, i.e.
            # margin > -spread — so actual = margin, line = -spread,
            # side = OVER, and margin == -spread grades as the push it is.
            player, market = r.get("team", ""), "spread"
            side, line = "OVER", -float(r.get("line") or 0)
        elif bt == "team_total":
            player = r.get("team", "")
            market = "team_total"
            side, line = (r.get("side") or "OVER").upper(), float(r.get("line") or 0)
        else:
            continue
        if not player:
            continue
        stake_units = float(r.get("stake_units", 0) or 0)
        if stake_units <= 0:
            continue                     # not a bet — see above
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, line, "
            "book, odds, projection, hit_prob, edge, confidence, grade, stake_units, "
            "stake_dollars, status, leg, rest_days, body_clock) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', ?, ?, ?)",
            (now, sport, date, player, market, side, line,
             r.get("book", "best"), r.get("odds", -110), None,
             r.get("win_prob"), r.get("edge"), r.get("confidence"),
             r.get("grade"), stake_units, round(stake_units * unit_dollars, 2),
             r.get("game_number") if r.get("doubleheader") else None,
             # Fatigue, for the side this bet is about. A short week or a
             # 10am body clock is a spread's business at least as much as a
             # prop's — this row carried no dimension at all, so half the
             # NFL journal was invisible to the miner even once the props
             # started reporting. Empty for a GAME total, which is about
             # both teams and belongs to neither; see pipeline._finish_bet.
             r.get("rest_days"), r.get("body_clock")))
        n += cur.rowcount
    conn.commit()
    return n


# Long-shot markets we can actually settle from ingested game logs —
# journaling unsettleable bets would just accumulate rows stuck open
# forever. anytime_td settles from the weekly-stats TD rows
# (engine.ingest.nfl_td_rows) that maintenance ingests all season.
SETTLEABLE_LONGSHOTS = {"home_runs", "anytime_td"}


def log_longshots(conn, result: dict, flat_stake: float = 0.1) -> int:
    """Journal the Long Shots board — the board's picks, and nothing else.

    The board is three rows: the value picks, topped up from the
    most-likely ranking. Those go to ``category='longshot'`` at a small flat
    stake with zero dollar exposure, and that is the record the Record page
    scores.

    THE WATCHLIST IS NO LONGER JOURNALED. It used to write every
    real-priced home run on the slate to ``category='longshot_watch'`` as a
    calibration sample — a couple of hundred rows a night, which was most of
    the journal by volume and all of the noise in it. The measurement it
    bought (does the model's claimed probability beat the market's implied
    one?) is real but it was never worth two hundred rows an evening in a
    bucket nobody reads, and it made every audit, every settle pass and
    every stuck-bet report a wall of names.

    What that costs, stated plainly: the long-shot calibration sample now
    grows three a night instead of two hundred, so it will take far longer
    to say anything about the HR model's probabilities. Existing
    longshot_watch rows are left alone — they are real measurements already
    taken — but nothing adds to them.
    """
    sport = result.get("sport", "mlb")
    date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = _journal_longshot_rows(conn, result.get("long_shots") or [],
                               sport, date, now, "longshot", flat_stake)
    conn.commit()
    return n


def _journal_longshot_rows(conn, rows, sport, date, now, category,
                           flat_stake) -> int:
    n = 0
    for r in rows:
        market = r.get("market", "home_runs")
        if market not in SETTLEABLE_LONGSHOTS:
            continue
        try:
            odds = int(r.get("odds") or 0)
        except (TypeError, ValueError):
            continue
        # Plus-money and real: the boards already filter, but the journal is
        # the last line of defense against a proxy or mis-lined price.
        if not r.get("player") or odds <= 100 or (r.get("book") or "").lower() == "proxy":
            continue
        # A projected-lineup hitter is a guess about who plays, not a bet.
        # The board still shows him (caveated); the journal waits for the
        # confirmed lineup — otherwise every rest day strands a third of
        # the night's rows as no-shows that can never settle.
        if r.get("lineup_confirmed") is False:
            continue
        if category == "longshot_watch":
            # A pick also sits on the watchlist. One measurement per bet —
            # the record bucket already has him tonight.
            dup = conn.execute(
                "SELECT 1 FROM bets WHERE sport=? AND date=? AND player=? "
                "AND market=? AND category='longshot'",
                (sport, str(r.get("game_date") or "").strip() or date,
                 r["player"], market)).fetchone()
            if dup:
                continue
        # The GAME's own date, not the slate label. A 9pm Eastern first
        # pitch is already tomorrow in UTC, so a slate stamped off a UTC
        # clock can sit a day ahead of the date the box score is filed
        # under — and a bet dated one day off its own result cannot settle.
        # Measured on a real journal: thirty home-run bets dated 07-27 whose
        # players were every one of them logged on 07-26.
        row_date = str(r.get("game_date") or "").strip() or date
        from .losspatterns import minutes_until
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category, lead_min, "
            "park_hr, wind_out, roofed, lineup_slot, lineup_conf) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', "
            "?, ?, ?, ?, ?, ?, ?)",
            (now, sport, row_date, r["player"], market, "OVER", 0.5,
             r.get("book", ""), odds, None, r.get("model_prob"),
             r.get("edge", r.get("ev_per_unit")), r.get("confidence"),
             r.get("grade", "Watch"), flat_stake, 0.0, category,
             # capture_lag matters MOST here: home runs are the volume, the
             # market that self-closed, and the tail price stale lines hurt.
             minutes_until(r.get("game_kickoff") or r.get("kickoff")
                           or r.get("commence_time")),
             # hr_env: this is the board park and wind exist to explain.
             r.get("park_hr"), r.get("wind_out"),
             1 if r.get("roofed") else 0 if r.get("roofed") is not None
             else None,
             r.get("lineup_slot"),
             1 if r.get("lineup_confirmed") else 0
             if r.get("lineup_confirmed") is not None else None))
        n += cur.rowcount
    return n


# Stale-line flags journal only on markets whose results we actually ingest;
# anything else would sit open forever and eventually void wrongly. NFL
# yardage markets settle from the weekly stats maintenance ingests Aug–Feb;
# NBA stat markets from the CDN boxscores it ingests Oct–Jun.
STALE_SETTLEABLE = {"total_bases", "hits", "home_runs",
                    "pass_yds", "rush_yds", "rec_yds", "receptions",
                    "pts", "reb", "ast", "fg3m"}


# The looser-gates sampler settles from the same ingested logs as the
# main record; only settleable, calibration-open markets journal.
LOOSE_SETTLEABLE = {"total_bases", "hits", "strikeouts"}


def log_priced_out(conn, result: dict, flat_stake: float = 0.1) -> int:
    """Journal the picks the model liked and Kelly refused — 'pricedout'.

    A prop can carry a real grade and still size at 0.00u, because the edge
    bar compares us to the de-vigged fair number while Kelly compares us to
    the price on offer: beat fair by 2% and the vig can still eat it. Those
    used to be flagged recommended, shown on the board, and skipped by the
    journal — landing in no bucket at all.

    They are not bets and never get dollars. They are the empirical answer
    to "was Kelly right to refuse?": paper-track at a flat stake, grade
    nightly, read the bucket's win rate against the prices it declined. If
    this bucket is consistently profitable at those prices, the sizing is
    too strict. If it burns, the refusal was correct and the board is
    better off without them.
    """
    sport = result.get("sport", "mlb")
    date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = 0
    for r in result.get("priced_out") or []:
        if r.get("market") in LONGSHOT_MARKETS:
            continue                      # the HR board keeps its own record
        try:
            odds = int(r.get("odds") or 0)
        except (TypeError, ValueError):
            continue
        # A proxy price is not a price anyone declined; there is nothing to
        # learn from grading against a number no book offered.
        if (not r.get("player") or not odds
                or (r.get("book") or "").lower() == "proxy"
                or r.get("has_market") is False):
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'pricedout')",
            (now, sport, date, r["player"], r["market"],
             (r.get("side") or "OVER").upper(), float(r.get("line") or 0),
             r.get("book", ""), odds, r.get("projection"), r.get("hit_prob"),
             r.get("edge"), r.get("confidence"), r.get("grade", "?"),
             flat_stake, 0.0))
        n += cur.rowcount
    conn.commit()
    return n


def priced_out_report(conn) -> dict:
    """Was Kelly right to refuse these? The bucket's own scorecard."""
    p = performance(conn, category="pricedout")
    p["recent"] = recent_settled(conn, limit=15, category="pricedout")
    return p


def log_near_misses(conn, result: dict, flat_stake: float = 0.1) -> int:
    """Journal the props that JUST missed the bar — category='loose'.

    The standing question "should the filters be looser?" gets an
    empirical answer: paper-track the near-misses at a flat stake with
    zero dollar exposure, grade them nightly, and read the bucket's ROI.
    Profitable over 100+ graded → loosen the real gates. Burning → the
    gates were right. Never mixed into the headline record.
    """
    sport = result.get("sport", "mlb")
    date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = 0
    for r in result.get("near_miss") or []:
        if r.get("market") not in LOOSE_SETTLEABLE:
            continue
        try:
            odds = int(r.get("odds") or 0)
        except (TypeError, ValueError):
            continue
        if not r.get("player") or not odds or (r.get("book") or "").lower() == "proxy":
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, move_delta, move_steam, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'loose')",
            (now, sport, date, r["player"], r["market"],
             (r.get("side") or "OVER").upper(), float(r.get("line") or 0),
             r.get("book", ""), odds, None, r.get("hit_prob"), r.get("edge"),
             None, r.get("grade", "Near miss"), flat_stake, 0.0,
             # THE point of this bucket for the movement question. A pick
             # the movement veto killed lands here with quality just under
             # 70 and, without these two, is indistinguishable from a prop
             # that simply graded low. That is the whole population whose
             # outcomes say whether the veto earns its keep.
             r.get("move_delta"), r.get("move_steam")))
        n += cur.rowcount
    conn.commit()
    return n


def loose_report(conn, since: str | None = None) -> dict:
    """The looser-gates scoreboard: flat-stake record for the near-miss
    bucket, plus the decision framing the Record page renders."""
    p = performance(conn, category="loose", since=since)
    p["recent"] = recent_settled(conn, limit=15, category="loose", since=since)
    return p


# --- the prediction desk (Kalshi paper book) --------------------------------
# Ethan, 2026-08-11: "I've never once seen a recommended bet for our
# prediction market." These three functions are the missing spine: the
# desk's recommendations journal at a flat paper stake, resolve against
# the exchange's own settlements, and report as their own bucket — the
# identical earn-your-stakes contract the loose book runs under. A
# hundred-plus graded rows deciding promotion, not a feeling.

PREDMARKET_FLAT_STAKE = 0.1


def _price_to_american(prob: float) -> int:
    """The American odds a binary price implies — display + ROI math."""
    p = min(max(float(prob), 0.01), 0.99)
    return int(round(-100 * p / (1 - p))) if p >= 0.5 \
        else int(round(100 * (1 - p) / p))


def log_predmarket(conn, recs: list[dict], date: str | None = None) -> int:
    """Journal the desk's recommendations — category='predmarket'.

    One row per market ticker per day (the bets table's unique key, with
    the ticker in the player column). The price PAID is the side's own:
    buying NO at a 41-cent YES market costs 59 cents. hit_prob records
    what the desk claimed, so calibration can grade the claim later.
    """
    date = date or datetime.date.today().isoformat()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = 0
    for r in recs:
        if not r.get("rec") or not r.get("ticker") or r.get("prob") is None:
            continue
        side = r.get("rec_side") or "YES"
        cost = float(r["prob"]) if side == "YES" else 1 - float(r["prob"])
        model_p = r.get("model_p")
        p_side = (float(model_p) if side == "YES" else 1 - float(model_p)) \
            if model_p is not None else None
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, "
            "side, line, book, odds, hit_prob, edge, grade, stake_units, "
            "stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'predmarket')",
            (now, r.get("sport", "kalshi"), date, r["ticker"],
             r.get("desk", "kalshi_ml"), side, round(cost * 100, 1),
             "kalshi", _price_to_american(cost), p_side,
             (r.get("edge_pts") or 0) / 100.0,
             r.get("title", "")[:60] or "Desk", PREDMARKET_FLAT_STAKE,
             0.0))
        n += cur.rowcount
    conn.commit()
    return n


#: The event date Kalshi encodes in a game ticker: KXNFLGAME-26SEP13DALNYG-DA
#: is the Dallas/NY game on 2026-09-13. Two-digit year, three-letter month,
#: two-digit day, always preceded by a dash.
_PM_TICKER_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
_PM_MONTHS = {m: i + 1 for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"))}


def predmarket_event_date(ticker: str | None) -> str | None:
    """The ISO date a Kalshi ticker's contract is ABOUT, or None.

    THE HOLE THIS CLOSES. `log_predmarket` stores the day the desk made
    the recommendation, because the bets table has one date column and
    every other bucket journals on its slate date. For a prediction
    market those are not the same day and can be a month apart: on
    2026-08-11 the desk journaled 130 NFL game contracts for September.

    Everything downstream that asks "should this have graded by now?"
    was reading the journal date, so all 130 looked two weeks overdue
    the moment they were written — the doctor called them stuck, and
    `--settle all` swept twelve dead days finding `0 game(s)` on each,
    forever. The date is right there in the ticker; nothing had read it.

    Returns None for anything unparseable, and callers must treat that
    as "unknown", never as "fine" — an undated contract that really is
    stranded still needs to be visible.
    """
    m = _PM_TICKER_DATE.search(str(ticker or "").upper())
    if not m:
        return None
    mon = _PM_MONTHS.get(m.group(2))
    if not mon:
        return None
    try:
        return datetime.date(2000 + int(m.group(1)), mon,
                             int(m.group(3))).isoformat()
    except ValueError:
        return None                      # 26FEB30 and friends


def open_predmarket_tickers(conn, today: str | None = None) -> list[str]:
    """Open contracts worth asking the exchange to settle.

    A market cannot settle before its own event, so a September contract
    journaled in August is a request that can only ever come back
    unsettled. During a football season the open book is mostly those,
    and asking about all of them is a settlement pull that grows with the
    schedule instead of with the work.

    The cutoff is TOMORROW, not today, and anything whose ticker carries
    no readable date is always included: a day of slack costs one batch,
    and a contract we stop asking about is a contract that never grades —
    which is the failure this whole change exists to remove.
    """
    today = today or datetime.date.today().isoformat()
    try:
        cutoff = (datetime.date.fromisoformat(today)
                  + datetime.timedelta(days=1)).isoformat()
    except ValueError:
        cutoff = None
    out = []
    for r in conn.execute(
            "SELECT DISTINCT player FROM bets WHERE category='predmarket' "
            "AND status='open'"):
        ev = predmarket_event_date(r["player"]) if cutoff else None
        if ev is None or ev <= cutoff:
            out.append(r["player"])
    return out


def resolve_predmarket(conn, results: dict) -> int:
    """Grade open desk bets against exchange settlements.

    ``results``: {ticker: "yes" | "no"} for markets that finalized. A
    binary market cannot push. P&L is the binary payout at the price
    paid: winning a side bought at cost c returns (1-c)/c per unit."""
    n = 0
    for row in conn.execute(
            "SELECT id, player, side, line, stake_units FROM bets "
            "WHERE category='predmarket' AND status='open'").fetchall():
        res = (results.get(row["player"]) or "").lower()
        if res not in ("yes", "no"):
            continue
        won = (row["side"] or "YES").lower() == res
        cost = max(0.01, min(0.99, (row["line"] or 50.0) / 100.0))
        stake = row["stake_units"] or PREDMARKET_FLAT_STAKE
        pnl = round(stake * (1 - cost) / cost, 4) if won else -stake
        conn.execute(
            "UPDATE bets SET status=?, pnl_units=?, pnl_dollars=0 WHERE id=?",
            ("won" if won else "lost", pnl, row["id"]))
        n += 1
    conn.commit()
    return n


def predmarket_report(conn, since: str | None = None) -> dict:
    """The desk's own scoreboard — never mixed into the headline record."""
    p = performance(conn, category="predmarket", since=since)
    p["recent"] = recent_settled(conn, limit=15, category="predmarket", since=since)
    return p


def log_stale_flags(conn, result: dict, flat_stake: float = 0.1) -> int:
    """Journal the scanner's stale-line flags — the sampler for our best-
    measured signal.

    A book pricing a side ≥1pt cheaper than the field's consensus beat the
    eventual close 64.8% of the time (+1.49pt CLV, z=11.6) on 30k harvested
    quotes. That was measured on CLOSES; this bucket measures the thing
    that matters — does TAKING the flagged price make money at settlement?
    Flat stake, zero dollars, category='stale', never in the headline
    record. Pre-game flags only: an in-play price is stale for reasons the
    scanner can't see.

    The journal key has no side column, so if both sides of one prop are
    flagged the same day, only the larger gap (rows arrive gap-sorted)
    journals — fine for a measurement bucket.
    """
    sport = result.get("sport", "mlb")
    slate_date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    rows = ((result.get("market_scan") or {}).get("stale")) or []
    n = 0
    for r in rows:
        if r.get("live") or r.get("started"):
            continue
        market = r.get("market") or ""
        if market not in STALE_SETTLEABLE or not r.get("player"):
            continue
        try:
            odds = int(r.get("odds"))
            line = float(r.get("line"))
        except (TypeError, ValueError):
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'stale')",
            # Slate-level date first: it's the key settling maps to the
            # history DB (NFL journals '2025-W05', not the game's ISO day).
            (now, sport, slate_date or r.get("date"), r["player"], market,
             (r.get("side") or "OVER").upper(), line, r.get("book", ""), odds,
             None,
             # hit_prob = the field's consensus implied — what the flag
             # claims the true price is; edge = the gap being sampled.
             r.get("consensus"), (r.get("gap_pts") or 0) / 100.0,
             None, "Stale", flat_stake, 0.0))
        n += cur.rowcount
    conn.commit()
    return n


def stale_report(conn, since: str | None = None) -> dict:
    """The stale-line sampler's scoreboard: flat-stake record, hit rate vs
    the break-even the taken prices implied, and the consensus the flags
    claimed. If hit rate can't beat the taken price's break-even, the
    measured CLV never cashes and the signal stays display-only."""
    # The headline was windowed and the hit-rate row was not, so one
    # panel disagreed with itself (2026-08-24 six-day review).
    win = " AND date >= ?" if since else ""
    wargs: tuple = (since,) if since else ()
    p = performance(conn, category="stale", since=since)
    row = conn.execute(
        "SELECT AVG(CASE WHEN odds > 0 THEN 100.0 / (odds + 100.0) "
        "            ELSE -odds / (100.0 - odds) END) AS taken_p, "
        "AVG(hit_prob) AS consensus_p, AVG(edge) AS avg_gap, "
        "SUM(status='won') AS w, COUNT(*) AS n "
        "FROM bets WHERE category='stale' AND status IN ('won','lost')" + win,
        wargs).fetchone()
    p["avg_taken_implied"] = round(row["taken_p"], 4) if row["taken_p"] is not None else None
    p["avg_consensus_implied"] = (round(row["consensus_p"], 4)
                                  if row["consensus_p"] is not None else None)
    p["avg_gap_pts"] = round(row["avg_gap"] * 100, 2) if row["avg_gap"] is not None else None
    p["actual_hit_rate"] = round(row["w"] / row["n"], 4) if row["n"] else None
    p["recent"] = recent_settled(conn, limit=15, category="stale",
                                 since=since)
    return p


def log_form_picks(conn, result: dict, team_form: dict,
                   flat_stake: float = 0.1) -> int:
    """The team-form sampler: for every slate game where a HOT team meets a
    COLD one (form gap ≥ the bar), journal the hot side's moneyline at the
    REAL book price, flat 0.1u, category='form'.

    This is the measurement the "we're missing hot teams" instinct needs:
    streaks are the most public stat in sports, so the default assumption is
    the market already prices them. The sampler finds out — at the prices we
    could actually bet — and the fixed promotion bar (100+ graded, z ≥ 2,
    positive ROI) decides whether form ever becomes a recommendation input.
    Settles automatically through the existing moneyline path (player = the
    team picked, line 0.5, side OVER, actual 1/0).
    """
    from .mlb.teamform import FORM_GAP_BAR, form_score
    sport = result.get("sport", "mlb")
    slate_date = result.get("date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    scores = {t: form_score(f) for t, f in (team_form or {}).items()}
    n = 0
    for g in result.get("games", []):
        home, away = g.get("home"), g.get("away")
        sh, sa = scores.get(home), scores.get(away)
        if sh is None or sa is None or abs(sh - sa) < FORM_GAP_BAR:
            continue
        hot, hot_score = (home, sh) if sh > sa else (away, sa)
        odds = g.get("home_ml") if hot == home else g.get("away_ml")
        if not odds:
            continue                      # no real price — nothing to sample
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'form')",
            (now, sport, slate_date or g.get("date"), hot, "moneyline",
             "OVER", 0.5, "best", int(odds), None,
             # edge column carries the form gap being sampled.
             None, round(abs(sh - sa), 3), None, "Form", flat_stake, 0.0))
        n += cur.rowcount
    conn.commit()
    return n


def form_report(conn, since: str | None = None) -> dict:
    """The form sampler's scoreboard: does backing hot teams at real prices
    make money? Mirrors stale_report; graded nightly with everything else."""
    win = " AND date >= ?" if since else ""
    wargs: tuple = (since,) if since else ()
    p = performance(conn, category="form", since=since)
    row = conn.execute(
        "SELECT AVG(CASE WHEN odds > 0 THEN 100.0 / (odds + 100.0) "
        "            ELSE -odds / (100.0 - odds) END) AS taken_p, "
        "AVG(edge) AS avg_gap, SUM(status='won') AS w, COUNT(*) AS n "
        "FROM bets WHERE category='form' AND status IN ('won','lost')" + win,
        wargs).fetchone()
    p["avg_taken_implied"] = round(row["taken_p"], 4) if row["taken_p"] is not None else None
    p["avg_form_gap"] = round(row["avg_gap"], 3) if row["avg_gap"] is not None else None
    p["actual_hit_rate"] = round(row["w"] / row["n"], 4) if row["n"] else None
    p["recent"] = recent_settled(conn, limit=15, category="form",
                                 since=since)
    return p


def log_ufc_picks(conn, result: dict) -> int:
    """Journal the UFC card's picks — category='ufc', its own probation
    bucket (docs pattern: a newly opened gate earns its way into any
    headline through its own graded record, never by assertion).

    player = the fighter picked, market = moneyline, line 0.5, side OVER,
    actual 1/0 — the standard grader applies. Real prices only."""
    if result.get("status") != "card" or not result.get("picks"):
        return 0
    date = result.get("event_date", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    n = 0
    for p in result["picks"]:
        odds = p.get("odds")
        if not odds or not p.get("pick") or not date:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO bets (ts, sport, date, player, market, side, "
            "line, book, odds, projection, hit_prob, edge, confidence, grade, "
            "stake_units, stake_dollars, status, category) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'open', 'ufc')",
            (now, "ufc", date, p["pick"], "moneyline", "OVER", 0.5,
             p.get("book", ""), int(odds), None, p.get("p_final"),
             p.get("edge"), None, "Pick",
             float(p.get("stake_units") or 0), 0.0))
        n += cur.rowcount
    conn.commit()
    return n


def settle_ufc(conn, fetch_result=None) -> int:
    """Settle open UFC picks from post-card results.

    ``fetch_result(name, since_date)`` defaults to the ESPN MMA lookup;
    injectable for tests. won → 1/0 through the standard side-aware
    grader; a draw/NC voids, exactly as a book would."""
    import datetime as _dt
    if fetch_result is None:
        from .sources.espnmma import latest_result as fetch_result
    settled = 0
    for b in conn.execute("SELECT * FROM bets WHERE status='open' "
                          "AND sport='ufc'").fetchall():
        try:
            since = _dt.date.fromisoformat(b["date"])
        except (TypeError, ValueError):
            continue
        try:
            res = fetch_result(b["player"], since)
        except Exception:
            continue
        if not res:
            continue                       # card not fought/ingested yet
        if res.get("won") is None:
            conn.execute("UPDATE bets SET status='void', pnl_units=0, "
                         "pnl_dollars=0 WHERE id=?", (b["id"],))
        else:
            _settle_one(conn, b, 1.0 if res["won"] else 0.0, None)
        settled += 1
    conn.commit()
    return settled


def ufc_report(conn, since: str | None = None) -> dict:
    """The UFC bucket's scoreboard — same shape the other probation
    buckets export, graded fight by fight."""
    p = performance(conn, category="ufc", since=since)
    p["recent"] = recent_settled(conn, limit=15, category="ufc", since=since)
    return p


# --- settling ---------------------------------------------------------------
def _grade_side_aware(b, actual: float) -> tuple[str, float]:
    """(status, pnl_units) for a bet at a given actual — SIDE-AWARE.

    ``actual > line`` is only a win for an OVER — grading unders with the
    over's rule inverts half the journal, the same bug that once inverted the
    backtest's P&L."""
    side = (b["side"] or "OVER").upper()
    if actual == b["line"]:
        return "push", 0.0
    won = (actual > b["line"]) == (side == "OVER")
    if won:
        return "won", (american_to_decimal(b["odds"]) - 1.0) * (b["stake_units"] or 0.0)
    return "lost", -(b["stake_units"] or 0.0)


def _settle_one(conn, b, actual: float, closing_line: float | None,
                actual_minutes: float | None = None,
                closing_odds: float | None = None) -> None:
    """Grade one open bet and advance the bankroll."""
    status, pnl_u = _grade_side_aware(b, actual)
    pnl_d = round(pnl_u / b["stake_units"] * b["stake_dollars"], 2) if b["stake_units"] else 0.0
    conn.execute(
        "UPDATE bets SET status=?, actual=?, pnl_units=?, pnl_dollars=?, "
        "closing_line=?, actual_minutes=?, closing_odds=? WHERE id=?",
        (status, actual, round(pnl_u, 4), pnl_d, closing_line,
         actual_minutes,
         int(closing_odds) if closing_odds is not None else None,
         b["id"]))
    set_cfg(conn, "bankroll", round(bankroll(conn) + pnl_d, 2))


def _leg_row(rows, leg):
    """The stat row for a KNOWN doubleheader leg. Leg 1 owns the plain
    game_id; later legs carry the ``-G{n}`` suffix the ingest stamps in
    chronological order (MLB's game log is oldest-first). None when the
    bet doesn't know its leg or the row isn't there."""
    if not leg:
        return None
    leg = int(leg)
    for r in rows:
        gid = str((r["game_id"] if "game_id" in r.keys() else "") or "")
        tail = gid.rsplit("-G", 1)
        n = int(tail[1]) if len(tail) == 2 and tail[1].isdigit() else 1
        if n == leg:
            return r
    return None


def _pick_dh_game(games_rows, b, actual_fn):
    """Resolve which games row a TEAM-market bet grades against.

    Singles pass straight through (once final). On a doubleheader day a
    bet that knows its leg takes that game; a legacy bet without one
    settles only if the outcome is identical either way — and once every
    leg is final with the outcomes still disagreeing, it voids: grading
    against a coin-flip choice of game would be invention, and leaving
    it open forever is phantom exposure. Returns (row_or_None, verdict)
    where verdict is "void" or None (None row = wait).
    """
    rows = list(games_rows or [])
    finals = [g for g in rows
              if g["home_score"] is not None and g["away_score"] is not None]
    if len(rows) <= 1:
        return (finals[0] if finals else None), None
    picked = _leg_row(rows, b["leg"] if "leg" in b.keys() else None)
    if picked is not None:
        if picked["home_score"] is None or picked["away_score"] is None:
            return None, None            # our leg isn't final yet
        return picked, None
    if not finals:
        return None, None
    outcomes = {_grade_side_aware(b, actual_fn(g))[0] for g in finals}
    if len(outcomes) == 1 and len(finals) == len(rows):
        return finals[0], None
    if len(outcomes) > 1 and len(finals) == len(rows):
        return None, "void"
    return None, None                    # partial day — wait for the rest


def _team_day_final(hist_conn, where, wargs, log_row) -> bool:
    """True only with POSITIVE evidence the team's whole day is final —
    games rows exist and every one has a score. No games rows = no
    evidence = False; voiding an ambiguous bet needs proof, not absence."""
    team = log_row["team"] if "team" in log_row.keys() else None
    if not team:
        return False
    r = hist_conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(home_score IS NOT NULL), 0) "
        f"FROM games WHERE {where} AND (home=? OR away=?)",
        (*wargs, team, team)).fetchone()
    tot, fin = int(r[0] or 0), int(r[1] or 0)
    return bool(tot) and fin == tot


def _team_day_unfinished(hist_conn, where, wargs, log_row) -> bool:
    """True when the stat row's team has a game that day WITHOUT a final
    score in the games table — meaning the row may be a partial line from a
    game in progress, and nothing should grade against it yet. Unknown team
    or no game rows = no evidence either way → False (legacy behavior; the
    ingest layer separately withholds same-day rows for teams in play)."""
    team = log_row["team"] if "team" in log_row.keys() else None
    if not team:
        return False
    r = hist_conn.execute(
        f"SELECT COUNT(*), COALESCE(SUM(home_score IS NOT NULL), 0) "
        f"FROM games WHERE {where} AND (home=? OR away=?)",
        (*wargs, team, team)).fetchone()
    tot, fin = int(r[0] or 0), int(r[1] or 0)
    return bool(tot) and fin < tot


def _too_early_to_grade(hist_conn, where, wargs, log_row, bet_date: str) -> bool:
    """Should this stat row be treated as evidence yet?

    Two guards, because one signal was never enough:

      * _team_day_unfinished — the team HAS a game row that day without a
        final score. Positive evidence of a game in play. Catches nothing
        when the row is missing entirely.
      * that missing row is the actual bug. parse_results only writes games
        that FINISHED, so a game not yet started has no row at all, the
        first guard abstained, and the settler graded tonight's props
        against a stat line of zeros — every UNDER a winner, every OVER a
        loser, hours before first pitch. That is the wall of ticks and
        crosses on the Record page for games nobody has played.

    So on TODAY's and future dates the burden of proof flips: grade only
    with positive confirmation that the team's day is final. A game that
    has not started is, by definition, today or later — which is exactly
    where the strict rule bites and nowhere else.

    Older dates keep the permissive rule on purpose. Their games ARE over;
    absence of a games row there means thin ingest coverage (backfilled
    player logs predate the games table for whole seasons), and being
    strict would strand every one of those bets as open forever. So the
    strict window self-heals: a genuinely finished game that never got
    ingested waits a day, then grades.

    The window is today OR YESTERDAY because the two dates compared are not
    on the same clock — a 9pm Eastern first pitch is already tomorrow in
    UTC, so on a UTC box "today" turns strict off at the exact hour night
    games are being played.
    """
    if _team_day_unfinished(hist_conn, where, wargs, log_row):
        return True
    strict_from = (datetime.date.today()
                   - datetime.timedelta(days=1)).isoformat()
    if str(bet_date or "") >= strict_from:
        return not _team_day_final(hist_conn, where, wargs, log_row)
    return False


def _day_was_ingested(hist_conn, where: str, wargs: list) -> bool:
    """Does the history DB know anything about this day's games at all?

    Without this the audit below flags everything. A date with no game rows
    tells us nothing — the day may predate the games table, or belong to a
    sport that never stored scores. Absence of THIS team's final is only
    evidence when the day itself was ingested.
    """
    return bool(hist_conn.execute(
        f"SELECT COUNT(*) FROM games WHERE {where}", wargs).fetchone()[0])


def _team_day_not_final(hist_conn, where: str, wargs: list, team: str) -> bool:
    """True unless this team has a game with a FINAL SCORE that day.

    Deliberately stricter than _team_day_unfinished, which abstains when
    there are no game rows for the team. That abstention is the whole
    problem: parse_results only stores FINAL games, so a game in progress
    has no row at all, the guard returned False, and the settler graded
    against a partial stat line. For a repair pass the burden of proof runs
    the other way — confirm the game finished, or treat the grade as
    suspect.
    """
    if not team:
        return False
    n = hist_conn.execute(
        f"SELECT COUNT(*) FROM games WHERE {where} AND (home=? OR away=?) "
        f"AND home_score IS NOT NULL", (*wargs, team, team)).fetchone()[0]
    return not n


def premature_settles(conn, hist_conn) -> list[dict]:
    """Bets graded against a game that had not finished. Read-only.

    The ingest used to store partial stat lines from games in progress (see
    engine/ingest.py — the withholding guard read a field nobody filled), so
    the settler could grade a bet mid-game. An OVER already past its line
    lands on the right answer early; an UNDER grades as WON in the fourth
    inning and then the man doubles.

    A row is suspect when its day WAS ingested, the player has a stat line
    for it, and the player's team has no game with a final score that day.

    The day-ingested precondition is skipped inside the strict window (see
    _too_early_to_grade). It exists so a date that predates the games table
    doesn't flag its whole slate, but a graded bet on a game that has not
    STARTED is the loudest version of this bug and produces no games rows
    at all — the precondition was hiding exactly the rows worth showing.
    """
    out: list[dict] = []
    strict_from = (datetime.date.today()
                   - datetime.timedelta(days=1)).isoformat()
    for b in conn.execute(
            "SELECT * FROM bets WHERE status IN ('won','lost','push') "
            "ORDER BY date, player"):
        where, wargs = _hist_where(b)
        try:
            if (str(b["date"] or "") < strict_from
                    and not _day_was_ingested(hist_conn, where, wargs)):
                continue
            rows = hist_conn.execute(
                f"SELECT * FROM player_game_logs WHERE {where} AND player=? "
                f"AND market=?", (*wargs, b["player"], b["market"])).fetchall()
        except Exception:
            continue
        if not rows:
            # A bet graded through the DATE-SHAPE fallback has no row on its
            # own date at all — the settler reached back a day for it. Those
            # are the ones the fallback graded against last night's stat line
            # while tonight's game had not started, so the audit has to look
            # where the settler looked or it cannot see them. Without this it
            # skipped exactly the bets the repair exists to reopen.
            try:
                rows, wargs = _neighbour_day_rows_raw(hist_conn, b, where,
                                                      wargs)
            except Exception:
                continue
            if not rows:
                continue                # graded from something else entirely
            # The team is playing on the bet's OWN date and has not finished:
            # the grade came from the wrong game. _neighbour_day_rows now
            # refuses this case going forward; this finds the ones already in
            # the journal from when it did not.
            _, own_args = _hist_where(b)
            if _team_day_unfinished(hist_conn, where, own_args, rows[0]):
                out.append(_suspect(b, rows[0]))
            continue
        team = rows[0]["team"] if "team" in rows[0].keys() else ""
        if not _team_day_not_final(hist_conn, where, wargs, team):
            continue
        out.append(_suspect(b, rows[0]))
    return out


def _suspect(b, row) -> dict:
    """One row of the premature-settle audit. Reports what it touched rather
    than a count — this feeds a tool that edits a betting record."""
    return {
        "id": b["id"], "sport": b["sport"], "date": b["date"],
        "player": b["player"], "market": b["market"], "side": b["side"],
        "line": b["line"], "category": b["category"],
        "team": (row["team"] if "team" in row.keys() else "") or "",
        "status": b["status"], "actual": b["actual"],
        "pnl_dollars": b["pnl_dollars"] or 0.0,
        "pnl_units": b["pnl_units"] or 0.0,
    }


def repair_premature(conn, hist_conn, apply: bool = False) -> dict:
    """Reopen prematurely graded bets and drop the partial rows they used.

    Dry by default. Applying does three things in one transaction, and all
    three are required:

      * the bet returns to 'open' with its result fields cleared;
      * the bankroll is REVERSED by that bet's dollars, because _settle_one
        advanced it — reopening without this leaves phantom P&L behind;
      * the partial stat rows are deleted, because a re-settle would
        otherwise reach the same verdict from the same bad data.

    Returns what it did (or would do), never a bare count: this edits a
    betting record, and "47 rows repaired" is not something anyone can
    check afterwards.
    """
    rows = premature_settles(conn, hist_conn)
    plan = {"suspect": rows, "applied": bool(apply),
            "bankroll_before": bankroll(conn),
            "dollars_reversed": round(sum(r["pnl_dollars"] for r in rows), 2),
            "logs_deleted": 0}
    if not apply or not rows:
        plan["bankroll_after"] = plan["bankroll_before"] - (
            plan["dollars_reversed"] if rows else 0.0)
        return plan
    for r in rows:
        conn.execute(
            "UPDATE bets SET status='open', actual=NULL, pnl_units=NULL, "
            "pnl_dollars=NULL WHERE id=?", (r["id"],))
        b = conn.execute("SELECT * FROM bets WHERE id=?", (r["id"],)).fetchone()
        where, wargs = _hist_where(b)
        try:
            cur = hist_conn.execute(
                f"DELETE FROM player_game_logs WHERE {where} AND player=? "
                f"AND market=?", (*wargs, r["player"], r["market"]))
            plan["logs_deleted"] += cur.rowcount
        except Exception:
            pass
    set_cfg(conn, "bankroll",
            round(plan["bankroll_before"] - plan["dollars_reversed"], 2))
    conn.commit()
    hist_conn.commit()
    plan["bankroll_after"] = bankroll(conn)
    return plan


def _snapshot_closes() -> dict:
    """``{(normalized player, market, date): closing line}`` from the free
    line-move snapshots. The fallback CLV source: harvested odds_history
    closes cost credits and only exist for backtested dates, while these
    snapshots accrue on every paid live pull anyway."""
    try:
        from .linemoves import load_history, closing_lines_by_date
        return closing_lines_by_date(load_history())
    except Exception:            # never let CLV bookkeeping block settling
        return {}


def _snapshot_close_odds() -> dict:
    """``{(player, market, date): {"over": px, "under": px}}``.

    The price companion to :func:`_snapshot_closes`. Same free source, and
    the one that makes CLV mean anything on a fixed-line market: a
    home-run prop's LINE closes at 0.5 every night, so line CLV there is a
    zero that says nothing, while the price moves all evening.

    BOTH SIDES since 2026-08-09. It returned the over alone, and the
    caller keyed on (player, market, date) with no side, so every UNDER
    bet banked the OVER's close as its own — see
    `linemoves.closing_odds_by_date` for how that surfaced.
    """
    try:
        from .linemoves import load_history, closing_odds_by_date
        return closing_odds_by_date(load_history())
    except Exception:            # never let CLV bookkeeping block settling
        return {}


# NFL slates journal under the week label the site shows ('2025-W05');
# results land in the history DB as period '005' within a season.
_NFL_WEEK_DATE = re.compile(r"^(\d{4})-W(\d{1,2})$")


def _hist_where(b) -> tuple[str, list]:
    """SQL fragment + args locating this bet's results in the history DB.

    MLB journals ISO dates that ARE the log period, so sport+period is
    enough. An NFL bet's '2025-W05' maps to period '005' — and a bare
    week number repeats every season, so the season must join too or a
    2026 bet could settle against a 2025 stat line."""
    m = _NFL_WEEK_DATE.match(b["date"] or "")
    if b["sport"] == "nfl" and m:
        return ("sport=? AND season=? AND period=?",
                [b["sport"], int(m.group(1)), f"{int(m.group(2)):03d}"])
    return "sport=? AND period=?", [b["sport"], b["date"]]


#: A bet older than this whose game is long finished is not "waiting" —
#: something is stopping it, and the difference matters because one of them
#: needs patience and the other needs a fix.
STUCK_AFTER_DAYS = 2

#: Fewer distinct players than this on a date with games means the day was
#: only partly ingested — a full MLB slate stores several hundred. Below the
#: bar, a missing player says nothing about that player.
THIN_DAY_PLAYERS = 120


def _logged_within(hist_conn, b, want: str, days: int = 1) -> str | None:
    """The nearby date this player IS logged on, if any.

    Only meaningful for ISO dates; a week label has no neighbours.
    """
    import datetime as _dt

    from .sources.oddsapi import normalize_name
    # NFL week labels are not ISO week dates, and Python ≥3.11 parses
    # "2026-W01" as 2025-12-29 instead of raising — the ValueError guard
    # below stopped guarding. A week has no neighbouring days.
    if _NFL_WEEK_DATE.match(str(b["date"] or "")):
        return None
    try:
        d0 = _dt.date.fromisoformat(b["date"] or "")
    except ValueError:
        return None
    # Previous day FIRST: that is the one the settle will actually use, and
    # a report naming a day the grader ignores is worse than silent.
    for off in (-1, 1):
        if abs(off) > days:
            continue
        d = (d0 + _dt.timedelta(days=off)).isoformat()
        rows = hist_conn.execute(
            "SELECT DISTINCT player FROM player_game_logs "
            "WHERE sport=? AND period=?", (b["sport"], d))
        if any(normalize_name(r[0]) == want for r in rows):
            return d
    return None


def never_resolving_game(hist_conn, b, log_row, today=None) -> bool:
    """True when the team's scoreless game on the bet's date can NEVER get
    a score — so no amount of re-ingesting will release the settle guard.

    `parse_results` returns completed, SCORED games and nothing else
    (mlbstats.py: it skips anything whose `abstractGameState` is not Final,
    anything whose `codedGameState` is C/D/T — cancelled, postponed,
    suspended — and anything missing a score). It therefore cannot write a
    scoreless row at all. A scoreless row on a PAST date was written by the
    schedule/odds side for a fixture that was then never played.

    `db.coverage_gaps` already draws exactly this conclusion and flags such
    days `repairable=False`; the stuck report simply never asked it. That
    is how seventeen bets came to carry the instruction "Ingest the finals:
    python3 ingest.py mlb --dates 2026-07-27 --refresh" for twelve days —
    a command that provably does nothing, printed four lines above the same
    tool's own "nothing a re-ingest would fill".

    Measured on Ethan's DB, 2026-08-08: 2026-07-27 held 12 MLB game rows,
    11 with finals; the twelfth was CLE @ CIN, and every one of those
    seventeen bets is on a CIN or CLE player.

    THREE conditions, and the third is the one that keeps this honest.

    STRICTLY the past. A game in progress right now is scoreless for an
    entirely ordinary reason, and calling that unresolvable would void live
    bets. ``today`` is a parameter rather than a call to the wall clock so
    the answer does not change depending on when it is asked — the first
    cut read `date.today()` and disagreed with the `today` its own caller
    had been handed.

    THE DAY MUST SHOW IT WAS INGESTED — at least one OTHER game that date
    carrying a final. Without this the rule is too strong, and wrongly so:
    a scoreless row on a past date also describes a day nobody has fetched
    yet, where "ingest the finals" is exactly the right advice and voiding
    would throw away a bet that is about to grade. Ethan's 2026-07-27 had
    11 of 12 games scored, which is what makes the twelfth a fixture rather
    than a gap.
    """
    import datetime as _dt
    day = str(b["date"] or "")
    try:
        d = _dt.date.fromisoformat(day)
    except ValueError:
        return False                     # a week label has no day to judge
    ref = today or _dt.date.today().isoformat()
    try:
        if d >= _dt.date.fromisoformat(str(ref)):
            return False
    except ValueError:
        return False
    team = log_row["team"] if "team" in log_row.keys() else None
    if not team:
        return False
    r = hist_conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(home_score IS NOT NULL), 0) "
        "FROM games WHERE sport=? AND period=? AND (home=? OR away=?)",
        (b["sport"], day, team, team)).fetchone()
    tot, fin = int(r[0] or 0), int(r[1] or 0)
    if not tot or fin >= tot:
        return False
    day_fin = hist_conn.execute(
        "SELECT COALESCE(SUM(home_score IS NOT NULL), 0) FROM games "
        "WHERE sport=? AND period=?", (b["sport"], day)).fetchone()[0]
    return int(day_fin or 0) > 0


def _date_shift_repair_note(hist_conn, b, found_on: str,
                            today=None) -> str:
    """Why the neighbour-day repair has not graded this bet, in one line.

    "Logged under the next day" used to end with "tell me and I will fix
    the join" — but the join HAS a repair, and seventeen bets sat behind it
    anyway. The report and the repair share every guard below, so when a
    bet is stuck the report names the exact guard refusing instead of
    promising a fix that already shipped.
    """
    if found_on > str(b["date"] or ""):
        # Logged the day AFTER the bet. No mechanism explains a bet dated
        # before its own game — the UTC drift only ever pushes bets ahead.
        # The likely truth is that his real game on the bet's date was
        # never stored.
        return (f"logged the day AFTER the bet — that direction is never "
                f"the UTC drift; his game on {b['date']} was probably never "
                f"stored. Re-ingest it: python3 ingest.py {b['sport']} "
                f"--dates {b['date']} --refresh")
    where, wargs = _hist_where(b)
    rows, alt = _neighbour_day_rows_raw(hist_conn, b, where, wargs)
    if not rows:
        return (f"he is logged on {found_on}, but with no {b['market']} stat "
                f"row — that market was not stored for that day. Re-ingest "
                f"it: python3 ingest.py {b['sport']} --dates {found_on} "
                f"--refresh")
    if _team_day_unfinished(hist_conn, where, wargs, rows[0]):
        # Two very different situations wearing one message. The guard is
        # right either way — it refuses to grade a bet whose own game might
        # still be out there — but the REMEDY is opposite, and for twelve
        # days this printed the one that cannot work.
        if never_resolving_game(hist_conn, b, rows[0], today):
            return (f"{rows[0]['team']}'s game on {b['date']} has no final "
                    f"score and never will — a scoreless row on a past date "
                    f"is a postponed, cancelled or suspended fixture, and "
                    f"the results ingest only ever writes completed, scored "
                    f"games. Re-ingesting cannot fill it, so this bet cannot "
                    f"grade and is not waiting on anything. A prop on a game "
                    f"that was not played is a VOID: python3 launch.py "
                    f"--void-unplayed (dry run; add --apply to write it)")
        return (f"{rows[0]['team']} has a game on {b['date']} with no final "
                f"score stored, so the repair cannot rule out that the bet "
                f"is about THAT game. Ingest the finals: python3 ingest.py "
                f"{b['sport']} --dates {b['date']} --refresh")
    strict_from = (datetime.date.today()
                   - datetime.timedelta(days=1)).isoformat()
    if (str(b["date"] or "") >= strict_from
            and not _day_was_ingested(hist_conn, where, wargs)):
        return ("too recent to reach back safely — the strict window lifts "
                "in a day and it grades on the next pass")
    if _too_early_to_grade(hist_conn, where, alt, rows[0], b["date"]):
        return (f"cannot confirm the {found_on} game finished. Ingest that "
                f"date's finals: python3 ingest.py {b['sport']} --dates "
                f"{found_on} --refresh")
    return ("nothing is refusing — the repair can grade this; run "
            "python3 launch.py --settle all")


def relabel_cross_league(conn, hist_conn) -> int:
    """Re-file open hoops bets journaled under the other league's name.

    The NBA build runs as BOTH leagues, and for a while it journaled every
    pick as sport='nba' while the settle sweep read args.league — so WNBA
    bets sat where no WNBA ingest could ever reach them, reported as "no
    results ingested" on days the NBA does not even play. The build is
    fixed; this repairs the rows it already wrote.

    Strict on purpose: only OPEN bets, and only when the player appears in
    exactly ONE league's game logs. A name in both pools (or neither) is
    left alone — flipping on a guess would move the bet from one wrong
    place to another.
    """
    from .sources.oddsapi import normalize_name
    pools = {lg: {normalize_name(r[0]) for r in hist_conn.execute(
        "SELECT DISTINCT player FROM player_game_logs WHERE sport=?", (lg,))}
        for lg in ("nba", "wnba")}
    moved = 0
    for here, there in (("nba", "wnba"), ("wnba", "nba")):
        for r in conn.execute(
                "SELECT id, player FROM bets WHERE sport=? AND status='open' "
                "AND player IS NOT NULL", (here,)).fetchall():
            want = normalize_name(r["player"] or "")
            if want and want in pools[there] and want not in pools[here]:
                conn.execute("UPDATE bets SET sport=? WHERE id=?",
                             (there, r["id"]))
                moved += 1
    conn.commit()
    return moved


def _why_open_predmarket(b, date: str, today_d,
                         older_than: int) -> dict | None:
    """A prediction-market contract's own stuck test, or None if it isn't.

    A Kalshi row cannot be judged the way every other bucket is, on two
    counts, and judging it that way is what put 130 healthy contracts in
    the doctor's stuck list:

      * its journal date is the day the DESK recommended it, not the day
        the event happens — read the event date off the ticker instead;
      * it grades against the exchange's own settlements
        (`resolve_predmarket`), never against ingested game results, so
        `_hist_where` can only ever come back empty and "no results
        ingested" is a diagnosis pointing at a fix that cannot work.

    A contract whose event has not happened is not stuck at all. One whose
    event is done and which is still open is waiting on the exchange, and
    the fix is a desk build, not an ingest.
    """
    ev = predmarket_event_date(b["player"])
    ref, reason = (ev, "waiting on the exchange") if ev \
        else (date, "contract has no dated ticker")
    # fromisoformat does not fail on a week label — on Python ≥3.11
    # "2026-W1" quietly becomes a date in the previous December, which is
    # how football got aged 215 days into the past once already. A
    # contract journaled under one has no readable age at all.
    if _NFL_WEEK_DATE.match(ref or ""):
        return {"id": b["id"], "sport": b["sport"], "date": date,
                "player": b["player"], "market": b["market"],
                "age_days": older_than, "reason": reason, "event_date": ev}
    try:
        age = (today_d - datetime.date.fromisoformat(ref)).days
    except ValueError:
        return None
    if age < older_than:
        return None                       # the event has not happened yet
    return {"id": b["id"], "sport": b["sport"], "date": date,
            "player": b["player"], "market": b["market"],
            "age_days": age, "reason": reason,
            "event_date": ev}


def why_open(conn, hist_conn, today: str, older_than: int = STUCK_AFTER_DAYS
             ) -> list[dict]:
    """Every still-open bet whose day is done, and WHY it has not graded.

    `--settle all` sweeping back to a date weeks old is the symptom: those
    days keep re-appearing because something on them can never settle, and
    the sweep has no way to say so. It re-ingests, finds nothing new to
    match, reports zero, and leaves them open to be swept again tomorrow.

    Each returned row carries a ``reason`` naming which lookup failed:

      no results ingested   — nothing stored for that sport/date at all;
                              the ingest is the fix
      player has no log     — results ARE stored and this player is not in
                              them: a scratch, a DNP, or a name the journal
                              spells differently from the feed
      market not ingested   — the player played, but this stat was never
                              stored for him
      game not found        — a game-level bet (moneyline/total/spread)
                              whose game is not in the results

    Nothing here writes. It is a report, so it can be run on a live journal
    without deciding anything.
    """
    from .sources.oddsapi import normalize_name

    # No `date < ?` in the SQL. Journal dates are not all ISO: NFL writes
    # "2026-W1", and string-comparing that against "2026-08-01" puts it in
    # the FUTURE ("W" sorts above "0"), so every football bet was filtered
    # out of this report before it was looked at — on the one sport where a
    # stranded bet would sit unnoticed until the next season. Age is decided
    # below, where the week label has a branch.
    rows = conn.execute(
        "SELECT * FROM bets WHERE status='open' ORDER BY date").fetchall()
    out: list[dict] = []
    import datetime as _dt
    try:
        today_d = _dt.date.fromisoformat(today)
    except ValueError:
        today_d = _dt.date.today()

    for b in rows:
        date = b["date"] or ""
        if (b["category"] if "category" in b.keys() else "") == "predmarket":
            # Judged on its own terms — event date off the ticker, graded
            # by the exchange. None of the history lookups below can say
            # anything true about a Kalshi contract.
            pm = _why_open_predmarket(b, date, today_d, older_than)
            if pm:
                out.append(pm)
            continue
        # An NFL week label is NOT an ISO week date, and on Python ≥3.11
        # fromisoformat("2026-W01") happily returns 2025-12-29 — which
        # aged September's football 215 days into the PAST and put seven
        # future game bets in the doctor's stuck list. Detect the label
        # explicitly; a week is judged on content, never on the calendar
        # ISO thinks it means.
        real_age = not _NFL_WEEK_DATE.match(date)
        if real_age:
            try:
                age = (today_d - _dt.date.fromisoformat(date)).days
            except ValueError:
                age = older_than
                real_age = False
        else:
            age = older_than
        if age < older_than:
            continue
        where, wargs = _hist_where(b)
        extra: dict = {}
        game_market = b["market"] in GAME_MARKETS
        n_games = hist_conn.execute(
            f"SELECT COUNT(*) FROM games WHERE {where}", wargs).fetchone()[0]
        n_logs = hist_conn.execute(
            f"SELECT COUNT(*) FROM player_game_logs WHERE {where}",
            wargs).fetchone()[0]

        if game_market:
            # Judge the bet's OWN game, and judge finals, not row
            # existence. The schedule ingest writes September's W01 rows
            # in August with NULL scores, and "n_games > 0 → game not
            # found" put seven future bets in the doctor's stuck list on
            # Ethan's first nightly — a week that has not been PLAYED is
            # the calendar working, not a bet stuck.
            rows_g, _ = _game_bet_evidence(hist_conn, b, where, wargs)
            finals = [r for r in rows_g
                      if r["home_score"] is not None
                      and r["away_score"] is not None]
            if finals:
                reason = "gradeable now"
            elif rows_g and not real_age:
                continue          # scheduled, unplayed week — not stuck
            else:
                reason = ("no results ingested" if not n_games
                          else "game not found")
        elif not n_logs:
            reason = "no results ingested"
        else:
            want = normalize_name(b["player"] or "")
            names = {normalize_name(r[0]) for r in hist_conn.execute(
                f"SELECT DISTINCT player FROM player_game_logs WHERE {where}",
                wargs)}
            if want not in names:
                # "player has no log" is two different problems wearing one
                # label, and they need opposite fixes. Either the DAY is
                # thin — a partial ingest, where the answer is to re-fetch
                # it — or the day is complete and this one name is spelled
                # differently from the feed's, which is a name-map fix.
                # A count and the nearest name separate them.
                extra["day_players"] = len(names)
                extra["day_games"] = n_games
                import difflib
                near = difflib.get_close_matches(want, names, n=1, cutoff=0.8)
                if near:
                    extra["closest"] = near[0]
                # Before blaming the name or the player: is he logged on the
                # day NEXT DOOR? A 10pm Pacific first pitch is already
                # tomorrow in UTC, so a slate date and a game date can
                # disagree by one — and that is neither a DNP nor a spelling
                # problem, it is a boundary problem with its own fix.
                found_on = _logged_within(hist_conn, b, want, days=1)
                if found_on:
                    extra["logged_on"] = found_on
                    extra["repair"] = _date_shift_repair_note(
                        hist_conn, b, found_on, today)
                    reason = "logged under the next day"
                elif len(names) < THIN_DAY_PLAYERS:
                    reason = "day barely ingested"
                else:
                    reason = "player has no log"
            else:
                has = hist_conn.execute(
                    f"SELECT COUNT(*) FROM player_game_logs WHERE {where} "
                    f"AND market=?", (*wargs, b["market"])).fetchone()[0]
                reason = "market not ingested" if not has else "gradeable now"
        out.append({"id": b["id"], "sport": b["sport"], "date": date,
                    "player": b["player"], "market": b["market"],
                    "age_days": age, "reason": reason, **extra})
    return out


def unplayed_bets(conn, hist_conn, today=None) -> list[dict]:
    """Open bets whose own game was never played, and so can never grade.

    A prop on a postponed, cancelled or suspended fixture is no-action at
    every book, and leaving it open forever is phantom exposure that also
    keeps the day in `--settle all`'s sweep list for good. This finds them;
    it does not write.

    DELIBERATELY NARROW. It only claims a bet when the bet's own team has a
    scoreless game row on the bet's own PAST date — the same test
    `db.coverage_gaps` uses to call a day unrepairable. It does not reach
    for bets that are merely ungraded, and it says nothing about a day still
    in play.
    """
    out: list[dict] = []
    for b in conn.execute(
            "SELECT * FROM bets WHERE status='open' ORDER BY date, sport"
    ).fetchall():
        if not b["date"] or "-W" in str(b["date"]):
            continue
        team = _game_bet_team(b) if b["market"] in GAME_MARKETS \
            else _bet_team(hist_conn, b)
        if not team:
            continue
        if not never_resolving_game(hist_conn, b, {"team": team}, today):
            continue
        r = hist_conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(home_score IS NOT NULL), 0) "
            "FROM games WHERE sport=? AND period=? AND (home=? OR away=?)",
            (b["sport"], b["date"], team, team)).fetchone()
        tot, fin = int(r[0] or 0), int(r[1] or 0)
        out.append({"id": b["id"], "sport": b["sport"], "date": b["date"],
                    "player": b["player"], "market": b["market"],
                    "team": team, "games": tot, "finals": fin,
                    "stake_units": b["stake_units"] if "stake_units" in b.keys()
                    else None})
    return out


def _game_bet_team(b) -> str | None:
    """The team a GAME-level bet is on, read off the bet itself.

    THE HOLE THIS CLOSES. `_bet_team` finds a team by looking the bet's
    `player` up in `player_game_logs`, which is right for a prop and can
    never work for a game bet: `player` there is not a person. Moneyline,
    spread and team_total store the TEAM in that column, and total stores
    the matchup key `AWAY@HOME`. Neither ever matches a player name, so
    `unplayed_bets` returned None and skipped every game bet — which meant
    a moneyline on a postponed fixture could not be voided by the tool
    built to void bets on postponed fixtures.

    That is the doctor's "game not found" bucket. Six of them were sitting
    open on 2026-08-09 with `--settle all` as the advice, and settling
    cannot help: the game was never played, so no re-ingest will ever
    produce the score the settler is waiting for.

    Either half of a matchup key is enough — `never_resolving_game` asks
    whether that team has a scoreless row on that date, and both halves of
    a postponed game do.
    """
    p = str(b["player"] or "").strip()
    if not p:
        return None
    if "@" in p:
        # AWAY@HOME, with a possible doubleheader suffix (`-G2`) that is
        # part of neither team's name.
        home = p.split("@", 1)[1]
        return home.split("-G")[0].strip() or None
    return p


def _bet_team(hist_conn, b) -> str | None:
    """Which team the bet's player was on, from the results themselves.

    Read from the neighbouring day's log when the bet's own day has none —
    which is the whole situation here: the player has no row on the bet's
    date precisely because his game was never played.
    """
    from .sources.oddsapi import normalize_name
    want = normalize_name(b["player"] or "")
    if not want:
        return None
    import datetime as _dt
    # Same ≥3.11 landmine as _logged_within: a week label must not be
    # read as the ISO week it is not.
    if _NFL_WEEK_DATE.match(str(b["date"] or "")):
        return None
    try:
        d0 = _dt.date.fromisoformat(str(b["date"] or ""))
    except ValueError:
        return None
    for off in (0, -1, 1):
        d = (d0 + _dt.timedelta(days=off)).isoformat()
        for r in hist_conn.execute(
                "SELECT player, team FROM player_game_logs "
                "WHERE sport=? AND period=?", (b["sport"], d)):
            if normalize_name(r[0]) == want and r[1]:
                return r[1]
    return None


def void_unplayed(conn, rows: list[dict]) -> int:
    """Mark the given bets void — no action, zero P&L. Returns the count.

    Separate from `unplayed_bets` so the caller can show the list first.
    A settlement that surprises the person holding the journal is worse
    than one that waits for a keystroke.
    """
    n = 0
    for r in rows:
        # rowcount off THIS statement's cursor. `conn.total_changes` is
        # cumulative for the connection, so testing it per row counts every
        # write the connection has ever made and returns 1 forever.
        cur = conn.execute(
            "UPDATE bets SET status='void', pnl_units=0, pnl_dollars=0 "
            "WHERE id=? AND status='open'", (r["id"],))
        n += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    return n


def _neighbour_day_rows_raw(hist_conn, b, where: str, wargs: list):
    """This player's stat rows on the day before, when his own is empty.

    Returns ``(rows, wargs)`` — the args are handed back rewritten to the
    date that answered, so everything downstream (the doubleheader check,
    the day-finished guard) reasons about the right day.

    RAW: no judgement about whether reaching back is legitimate. That lives
    in ``_neighbour_day_rows``. The split exists because the settle path and
    the repair path need opposite things from the same lookup — the settler
    must refuse the illegitimate case, and the audit must be able to FIND
    the bets a previous version of the settler graded that way. An audit
    built on the guarded version cannot see them, which is exactly how the
    repair tool came to be blind to the grades it exists to reopen.
    """
    import datetime as _dt

    from .sources.oddsapi import normalize_name
    if "period=?" not in where:
        return [], wargs
    # Week labels have no neighbouring days; ≥3.11 would otherwise read
    # "2026-W01" as 2025-12-29 and query days nothing is filed under.
    if _NFL_WEEK_DATE.match(str(b["date"] or "")):
        return [], wargs
    try:
        d0 = _dt.date.fromisoformat(b["date"] or "")
    except ValueError:
        return [], wargs
    target = normalize_name(b["player"] or "")
    # The PREVIOUS day only, and the direction is not a preference — it is
    # the geography. Every mechanism that produces this drift labels a US
    # evening game with a UTC clock, and 9pm Eastern is 01:00 the NEXT day
    # in UTC. So a bet carrying the shift always sits AHEAD of its result,
    # never behind it.
    #
    # "Exactly one neighbour" was the first guard here and it was useless
    # for baseball: teams play most days, so a regular is logged on both
    # sides of any date and every bet stayed ambiguous. Twenty-four of
    # thirty survived it. Direction is the discriminator that actually
    # separates the case, and a match on date+1 keeps being refused —
    # nothing explains a bet dated BEFORE its own game, so grading one
    # would be inventing a reason.
    d = (d0 - _dt.timedelta(days=1)).isoformat()
    alt = list(wargs)
    alt[-1] = d
    rows = [c for c in hist_conn.execute(
                f"SELECT player, value, team, game_id "
                f"FROM player_game_logs WHERE {where} AND market=?",
                (*alt, b["market"]))
            if normalize_name(c["player"]) == target]
    if not rows:
        return [], wargs
    return rows, alt


def _neighbour_day_rows(hist_conn, b, where: str, wargs: list):
    """The neighbour-day rows, but only when reaching back is legitimate.

    THE REASON THE BET'S OWN DAY IS EMPTY DECIDES WHETHER THIS IS LEGAL.

    Two mechanisms leave a bet with no stat row on its own date, and they
    want opposite treatment:

      * the date-shape drift — the game WAS played, and its box score is
        filed one day back. Reaching back is the repair.
      * the ingest's withholding guard — the game has NOT been played, so
        the row is deliberately absent until the team's day is final.

    Nothing distinguished them, and the second case happens every single
    evening: today's rows are withheld by design, the player is logged
    yesterday because baseball teams play most days, and this fallback then
    graded TONIGHT'S bet against LAST NIGHT'S stat line, hours before first
    pitch. The withholding guard was manufacturing the exact precondition
    this fallback treats as evidence — the two fixes were undoing each
    other, which is why the premature grades survived the first repair.

    The neighbour row carries the team, and that is what the bet's own day
    can be asked about: if the team is playing on the bet's own date and the
    game has not finished, the bet is about THAT game and there is no
    neighbour to find.

    Deliberately the LOOSE check and not _too_early_to_grade. The strict arm
    wants positive proof the team's day is final, and on a day the team does
    not play there is no such proof to be had — demanding it refuses every
    genuine date-shape repair, which is the bug this fallback exists to fix.
    Positive evidence of a live game is the only thing that separates the
    two cases here.

    The limit, stated plainly: this leans on the slate ingest writing a
    games row for tonight's fixtures before they finish. MLB does —
    mlb_rows_from_slate writes them scoreless — and MLB is where the
    premature grades were appearing. A sport that writes no row until a game
    is final gets no protection from this line, and relies on the guard in
    the settle loop instead.
    """
    rows, alt = _neighbour_day_rows_raw(hist_conn, b, where, wargs)
    if not rows:
        return [], wargs
    if _team_day_unfinished(hist_conn, where, wargs, rows[0]):
        return [], wargs
    # And refuse when the bet's own day is invisible. The check above reads
    # the games table for the bet's date; if the slate was never ingested
    # there is nothing there to read, "no unfinished game" means "no
    # information", and inside the strict window that is not a licence to
    # reach back a day. Outside the window it is: an old date with no games
    # rows is ordinary thin coverage, and refusing there would retire the
    # date-shape repair for every backfilled season.
    strict_from = (datetime.date.today()
                   - datetime.timedelta(days=1)).isoformat()
    if (str(b["date"] or "") >= strict_from
            and not _day_was_ingested(hist_conn, where, wargs)):
        return [], wargs
    return rows, alt


def _game_bet_evidence(hist_conn, b, where, wargs):
    """Current games rows + the actual-function for a TEAM-market bet.

    One definition, two callers — the settler and the repair pass — for the
    same reason GAME_MARKETS is one tuple: these used to live only inside
    ``settle_from_history``, which meant ``resettle_mismatches`` could not
    re-derive a game bet's actual and had to exempt team markets on the
    ASSUMPTION that "they only ever settle from final scores". The NBA
    schedule parser broke that assumption (it passed live in-progress scores
    into the games table), and the exemption turned a bad grade into a
    permanent one: props graded off partial stats self-healed on the next
    pass, game bets never did.
    """
    if b["market"] == "moneyline":
        rows = hist_conn.execute(
            f"SELECT home, away, home_score, away_score, game_id "
            f"FROM games WHERE {where} AND (home=? OR away=?)",
            (*wargs, b["player"], b["player"])).fetchall()

        def actual(row):
            pick_home = row["home"] == b["player"]
            # Stored as line 0.5 / side OVER: actual 1.0 = pick won.
            return 1.0 if ((row["home_score"] > row["away_score"])
                           == pick_home) else 0.0
        return rows, actual
    if b["market"] == "total":
        # player = the matchup key (AWAY@HOME); actual = combined score.
        # LIKE catches doubleheader legs' -G suffixes.
        rows = hist_conn.execute(
            f"SELECT home, away, home_score, away_score, game_id "
            f"FROM games WHERE {where} AND (game_id=? OR game_id LIKE ?)",
            (*wargs, b["player"], b["player"] + "-G%")).fetchall()
        return rows, (lambda r: float(r["home_score"]) + float(r["away_score"]))
    # spread / team_total: player = the team; its own margin or score.
    rows = hist_conn.execute(
        f"SELECT home, away, home_score, away_score, game_id "
        f"FROM games WHERE {where} AND (home=? OR away=?)",
        (*wargs, b["player"], b["player"])).fetchall()

    def actual(row):
        home_side = row["home"] == b["player"]
        if b["market"] == "spread":
            return float((row["home_score"] - row["away_score"])
                         if home_side
                         else (row["away_score"] - row["home_score"]))
        return float(row["home_score"] if home_side else row["away_score"])
    return rows, actual


def settle_from_history(conn, hist_conn, sport: str | None = None) -> int:
    """Auto-settle open bets straight from the history database.

    Actuals come from ``player_game_logs`` (each bet's slate date + market),
    closing lines from harvested ``odds_history`` — no hand-built actuals
    file. Run it any time after results ingest; bets whose games haven't been
    ingested yet simply stay open.
    """
    from .sources.oddsapi import normalize_name
    from . import db as hist_db

    q = "SELECT * FROM bets WHERE status='open'"
    args: list = []
    if sport:
        q += " AND sport=?"
        args.append(sport)

    closes_cache: dict = {}
    settled = 0
    for b in conn.execute(q, args).fetchall():
        where, wargs = _hist_where(b)
        if b["market"] in GAME_MARKETS:
            rows, actual_fn = _game_bet_evidence(hist_conn, b, where, wargs)
            g, verdict = _pick_dh_game(rows, b, actual_fn)
            if verdict == "void":
                conn.execute("UPDATE bets SET status='void', pnl_units=0, "
                             "pnl_dollars=0 WHERE id=?", (b["id"],))
                settled += 1
                continue
            if g is None:
                continue
            _settle_one(conn, b, actual_fn(g), None)
            settled += 1
            continue
        rows = hist_conn.execute(
            f"SELECT value, team, game_id FROM player_game_logs WHERE {where} "
            f"AND market=? AND player=?",
            (*wargs, b["market"], b["player"])).fetchall()
        if not rows:
            # Name-shape fallback (feeds disagree on accents/suffixes).
            target = normalize_name(b["player"])
            rows = [c for c in hist_conn.execute(
                        f"SELECT player, value, team, game_id "
                        f"FROM player_game_logs WHERE {where} AND market=?",
                        (*wargs, b["market"]))
                    if normalize_name(c["player"]) == target]
        if not rows:
            # DATE-SHAPE fallback. A 9pm Eastern first pitch is already
            # tomorrow in UTC, so a slate labelled from a UTC clock can sit
            # one day ahead of the date the box score is filed under —
            # measured on a real journal: thirty home-run bets dated 07-27
            # whose players are all logged on 07-26.
            #
            # Narrow on purpose. It applies only when the bet's OWN date has
            # no log for this player at all, and exactly ONE neighbouring
            # date does. If both neighbours have one, the day is ambiguous
            # and the bet stays open — grading against a coin-flip choice of
            # game would put a wrong number in the record, which is worse
            # than an open bet because nothing downstream can tell it from a
            # right one.
            rows, wargs = _neighbour_day_rows(hist_conn, b, where, wargs)
        if not rows:
            continue
        # Confirm the game FINISHED — do not merely fail to prove it did not.
        # On today's slate that means positive proof; see _too_early_to_grade.
        # The cost is that a bet whose game genuinely finished but never got
        # ingested stays OPEN rather than being graded — visible, honest,
        # and surfaced by the doctor's stuck-bets check, where a wrong grade
        # is invisible and permanent.
        if _too_early_to_grade(hist_conn, where, wargs, rows[0], b["date"]):
            continue
        if len(rows) > 1:
            # DOUBLEHEADER day: one stat row per leg (game_id suffix -G2 on
            # the second). A bet that KNOWS its leg grades against that
            # game's line; a legacy bet without one settles only when the
            # outcome is identical either way — and once the day is fully
            # final with the legs still disagreeing, it VOIDS: grading it
            # against a coin-flip choice of game would be invention, and
            # leaving it open forever is a slow leak of phantom exposure.
            picked = _leg_row(rows, b["leg"] if "leg" in b.keys() else None)
            if picked is None:
                def _wins(v):
                    over = (b["side"] or "OVER").upper() != "UNDER"
                    if v == b["line"]:
                        return "push"
                    return (v > b["line"]) == over
                outcomes = {_wins(float(r["value"])) for r in rows}
                if len(outcomes) > 1:
                    # Void needs PROOF the day ended with the legs still
                    # disagreeing; without games rows, keep waiting.
                    if _team_day_final(hist_conn, where, wargs, rows[0]):
                        conn.execute(
                            "UPDATE bets SET status='void', pnl_units=0, "
                            "pnl_dollars=0 WHERE id=?", (b["id"],))
                        settled += 1
                    continue
                picked = rows[0]
            rows = [picked]
        row = rows[0]

        ck = (b["sport"], b["market"])
        if ck not in closes_cache:
            closes_cache[ck] = hist_db.closing_odds_by_date(hist_conn, *ck)
        close = closes_cache[ck].get((normalize_name(b["player"]), b["date"]))
        close_line = float(close["line"]) if close else None
        if close_line is None:
            # No harvested close for this date — fall back to our own
            # recorded snapshots, so CLV accrues without spending credits.
            if "_snapshots" not in closes_cache:
                closes_cache["_snapshots"] = _snapshot_closes()
            close_line = closes_cache["_snapshots"].get(
                (normalize_name(b["player"]), b["market"], b["date"]))
        # The closing PRICE, which is the only thing that moves on a
        # fixed-line market. Captured from the same snapshots, so it costs
        # nothing and accrues on every pull that was already paid for.
        if "_snapshot_odds" not in closes_cache:
            closes_cache["_snapshot_odds"] = _snapshot_close_odds()
        # THE SIDE MATTERS. An UNDER bet scored against the OVER's closing
        # price is measured against the opposite of what it bought — which
        # is what made CLV's own internal check run backwards (winners beat
        # the close 41% of the time, losers 62%).
        # Keyed on the LINE as well: a closing price at a different line is
        # a different bet, and reading one as CLV inverts exactly the
        # cases where the line moved.
        _sides = closes_cache["_snapshot_odds"].get(
            (normalize_name(b["player"]), b["market"], b["date"],
             round(float(b["line"]), 1) if b["line"] is not None else None)
        ) or {}
        close_odds = _sides.get(
            "under" if (b["side"] or "OVER").upper() == "UNDER" else "over")
        # Capture the minutes actually played alongside the result, so the
        # journal can answer "did we lose because the rotation read was
        # wrong, or because she shot 3-for-12?" — the one question that
        # separates a pipeline bug from variance.
        actual_minutes = None
        if b["sport"] in ("nba", "wnba"):
            m = hist_conn.execute(
                f"SELECT value FROM player_game_logs WHERE {where} "
                f"AND market='min' AND player=? AND game_id=?",
                (*wargs, b["player"], row["game_id"])).fetchone()
            if m:
                actual_minutes = float(m["value"])
        _settle_one(conn, b, float(row["value"]), close_line,
                    actual_minutes=actual_minutes, closing_odds=close_odds)
        settled += 1

    # --- Void the no-shows ---------------------------------------------
    # A pick journaled from a projected lineup whose player never took the
    # field has no result and never will — the book voids that bet, and the
    # journal mirrors the book. Strictly gated: only on a day whose slate
    # is FULLY final and ingested (anything less is "not settled yet"), and
    # only when the player has no stat row of any kind that day. Voids
    # carry zero P&L and are excluded from every record aggregate.
    #
    # ONLY FOR BETS WHOSE "player" IS A PLAYER. Two categories put
    # something else in that column and grade somewhere else entirely:
    # predmarket rows carry an exchange TICKER (graded by
    # resolve_predmarket against the exchange's own settlements) and ufc
    # rows carry a fighter no player_game_logs row will ever name (graded
    # by settle_ufc, where a draw/NC is the only legitimate void). Both
    # ride the underlying sport's slate date, so on any fully-final day
    # this sweep saw "no stat row" and voided REAL open positions — found
    # 2026-08-18 when the doctor promised to void 104 live desk tickets
    # as scratched lineup players.
    NEVER_NOSHOW = GRADED_ELSEWHERE
    day_state: dict = {}
    day_players: dict = {}
    voided = 0
    # Heal what the unguarded sweep already broke: a voided desk ticket
    # is always wrong (nothing legitimately voids predmarket rows today),
    # so reopen them for the exchange grader. Idempotent, no rows = free.
    cur = conn.execute("UPDATE bets SET status='open' "
                       "WHERE category='predmarket' AND status='void'")
    if cur.rowcount:
        print(f"  reopened {cur.rowcount} desk ticket(s) a no-show sweep "
              f"had wrongly voided — the exchange grades those")
    for b in conn.execute(q, args).fetchall():
        # Team-level markets never void via the no-show rule — teams play.
        if b["market"] in GAME_MARKETS or not b["date"]:
            continue
        if b["category"] in NEVER_NOSHOW:
            continue
        key = (b["sport"], b["date"])
        where, wargs = _hist_where(b)
        if key not in day_state:
            r = hist_conn.execute(
                f"SELECT COUNT(*), SUM(CASE WHEN home_score IS NOT NULL "
                f"THEN 1 ELSE 0 END) FROM games WHERE {where}",
                wargs).fetchone()
            day_state[key] = (int(r[0] or 0), int(r[1] or 0))
        tot, fin = day_state[key]
        if not tot or fin < tot:
            continue
        if key not in day_players:
            day_players[key] = {normalize_name(p["player"]) for p in hist_conn.execute(
                f"SELECT DISTINCT player FROM player_game_logs "
                f"WHERE {where}", wargs)}
        if normalize_name(b["player"]) in day_players[key]:
            continue            # he played — the normal settle path owns him
        conn.execute("UPDATE bets SET status='void', pnl_units=0, pnl_dollars=0 "
                     "WHERE id=?", (b["id"],))
        voided += 1

    conn.commit()
    # Tag each fresh loss with its measured cause (blowout / short run /
    # variance) while the history rows are at hand — the nightly
    # postmortem narrates these tags instead of guessing at causes.
    try:
        from .causes import backfill as _tag_loss_causes
        _tag_loss_causes(conn, hist_conn)
    except Exception:                              # noqa: BLE001
        pass                 # a tagging hiccup must never block settling
    return settled + voided


def resettle_mismatches(conn, hist_conn) -> list[dict]:
    """Audit every settled stat bet against the CURRENT history rows and
    fix any wrong grade.

    The premature-settle bug graded bets off partial stat lines from games
    still in progress ("lost" at 0 total bases in the 4th inning). Once the
    real final numbers land, this pass finds every settled bet whose stat
    row now disagrees with the actual it was graded on, re-grades it
    side-aware, restates its P&L and the bankroll, and reports what moved.
    Idempotent — a clean journal is a no-op.

    Team markets are audited too, against the CURRENT games rows. They were
    exempt here for years, on the reasoning that "they only ever settle from
    final scores" — which was an assumption about the parsers, not a
    property of the settler, and the NBA schedule parser broke it by passing
    live in-progress scores into the games table. A total graded UNDER off a
    halftime 97 stayed wrong FOREVER under the exemption, because the very
    pass built to heal partial-data grades refused to look at it.
    """
    from .sources.oddsapi import normalize_name
    fixed = []
    marks = ", ".join("?" for _ in GAME_MARKETS)
    for b in conn.execute(
            f"SELECT * FROM bets WHERE status IN ('won','lost','push') "
            f"AND market IN ({marks})", GAME_MARKETS).fetchall():
        where, wargs = _hist_where(b)
        rows, actual_fn = _game_bet_evidence(hist_conn, b, where, wargs)
        g, _verdict = _pick_dh_game(rows, b, actual_fn)
        if g is None:
            # No final row to audit against — a game mid-play, a dropped
            # postponement, an ambiguous doubleheader. Correcting needs
            # evidence; absence is not it.
            continue
        actual = actual_fn(g)
        if b["actual"] is not None and abs(actual - float(b["actual"])) < 1e-9:
            continue          # graded on the number that stands — correct
        status, pnl_u = _grade_side_aware(b, actual)
        pnl_d = round(pnl_u / b["stake_units"] * b["stake_dollars"], 2) \
            if b["stake_units"] else 0.0
        conn.execute(
            "UPDATE bets SET status=?, actual=?, pnl_units=?, pnl_dollars=? "
            "WHERE id=?", (status, actual, round(pnl_u, 4), pnl_d, b["id"]))
        fixed.append({"date": b["date"], "player": b["player"],
                      "market": b["market"], "was": b["status"], "now": status,
                      "actual": actual})
    for b in conn.execute(
            f"SELECT * FROM bets WHERE status IN ('won','lost','push') "
            f"AND market NOT IN ({marks})", GAME_MARKETS).fetchall():
        where, wargs = _hist_where(b)
        rows = hist_conn.execute(
            f"SELECT value, team, game_id FROM player_game_logs WHERE {where} "
            f"AND market=? AND player=?",
            (*wargs, b["market"], b["player"])).fetchall()
        if not rows:
            target = normalize_name(b["player"])
            rows = [c for c in hist_conn.execute(
                        f"SELECT player, value, team, game_id "
                        f"FROM player_game_logs "
                        f"WHERE {where} AND market=?", (*wargs, b["market"]))
                    if normalize_name(c["player"]) == target]
        if len(rows) > 1:
            # Doubleheader day: a bet that knows its leg re-checks against
            # that game's row; without one, ambiguity stays untouchable.
            picked = _leg_row(rows, b["leg"] if "leg" in b.keys() else None)
            rows = [picked] if picked is not None else rows
        if len(rows) != 1:
            continue          # missing or ambiguous (doubleheader) — leave it
        if _too_early_to_grade(hist_conn, where, wargs, rows[0], b["date"]):
            continue          # game still running — its numbers aren't evidence
        actual = float(rows[0]["value"])
        if b["actual"] is not None and abs(actual - float(b["actual"])) < 1e-9:
            continue          # graded on the number that stands — correct
        status, pnl_u = _grade_side_aware(b, actual)
        pnl_d = round(pnl_u / b["stake_units"] * b["stake_dollars"], 2) \
            if b["stake_units"] else 0.0
        conn.execute(
            "UPDATE bets SET status=?, actual=?, pnl_units=?, pnl_dollars=? "
            "WHERE id=?", (status, actual, round(pnl_u, 4), pnl_d, b["id"]))
        fixed.append({"date": b["date"], "player": b["player"],
                      "market": b["market"], "was": b["status"], "now": status,
                      "actual": actual})
    if fixed:
        conn.commit()
        recompute_bankroll(conn)
        # A regrade can flip a loss either way: re-run the cause sweep so
        # a new loss gets its tag and a reversed one loses its stale tag.
        try:
            from .causes import backfill as _tag_loss_causes
            _tag_loss_causes(conn, hist_conn)
        except Exception:                          # noqa: BLE001
            pass
    return fixed


def settle(conn, actuals: dict[tuple[str, str], float], sport: str | None = None,
           date: str | None = None, closing: dict[tuple[str, str], float] | None = None) -> int:
    """Grade open bets against actual results. ``actuals`` maps (player, market)
    -> the stat the player posted. Updates each settled bet's P&L and advances
    the bankroll.

    ``closing`` supplies closing lines for CLV; when omitted they're derived
    automatically from the recorded line-move snapshots, so closing-line value
    accrues without any manual bookkeeping."""
    dated: dict = {}
    if closing is None:
        try:
            # DATED snapshots, keyed (player, market, date). The undated map
            # keys on (player, market) alone, which in a sport that plays
            # every night resolves to the last price ever seen for that
            # prop — a July bet could take August's line as its "close".
            dated = _snapshot_closes()
        except Exception:      # never let CLV bookkeeping block settling
            dated = {}
        closing = {}
    q = "SELECT * FROM bets WHERE status='open'"
    args: list = []
    if sport:
        q += " AND sport=?"; args.append(sport)
    if date:
        q += " AND date=?"; args.append(date)

    from .sources.oddsapi import normalize_name
    settled = 0
    for b in conn.execute(q, args).fetchall():
        key = (b["player"], b["market"])
        if key not in actuals:
            continue
        close = closing.get(key)
        if close is None:
            close = dated.get((normalize_name(b["player"]), b["market"],
                               b["date"]))
        _settle_one(conn, b, float(actuals[key]), close)
        settled += 1
    conn.commit()
    return settled


# --- reporting --------------------------------------------------------------
def _claim_gap(bets) -> dict:
    """Did the board's stated confidence come true, over these bets?

    THE NUMBER THE ERA SECTION IS TITLED AFTER. "Model eras — did the
    re-tune work?" has been answerable only in W-L, ROI and CLV, and all
    three need a season to say anything: a 50-bet era swings ±10 points
    of ROI on variance alone. The claim gap converges far faster, because
    every settled bet contributes a measurement rather than a coin flip
    on the P&L — which is the same asymmetry calibhistory's docstring
    makes about sweeps against the forward record.

    It is also the only number that says whether the model is HONEST as
    opposed to lucky. A board claiming 60% on picks that land 48% is
    wrong about itself by twelve points, and every edge, EV figure and
    Kelly stake is wrong with it, whatever the ROI happens to be doing.

    THE SHIPPED CLAIM, NOT THE RAW ONE. `hit_prob` is what the board
    actually showed after every correction, and what the board showed is
    what the era IS. shapecheck reads raw on purpose — it is fitting a
    correction and must not measure one already applied — but that is a
    different question from "was the page telling the truth".

    Pushes are excluded: a push is not a claim that came true or failed.
    """
    rows = [b for b in bets
            if b["status"] in ("won", "lost") and b["hit_prob"] is not None]
    n = len(rows)
    if not n:
        return {"n": 0, "claimed": None, "landed": None, "gap": None,
                "se": None}
    claimed = sum(float(b["hit_prob"]) for b in rows) / n
    landed = sum(1 for b in rows if b["status"] == "won") / n
    se = math.sqrt(max(landed * (1.0 - landed), 1e-9) / n)
    return {"n": n, "claimed": round(claimed, 4), "landed": round(landed, 4),
            "gap": round(landed - claimed, 4), "se": round(se, 4)}


def _bet_clv(b) -> float | None:
    """Side-aware closing-line value for one settled bet, in line points.

    An over wants the line to RISE after the bet, an under wants it to fall;
    positive always means the market moved our way."""
    if b["closing_line"] is None:
        return None
    move = b["closing_line"] - b["line"]
    return move if (b["side"] or "OVER").upper() == "OVER" else -move


def repair_closing_odds(conn, apply: bool = False) -> dict:
    """Re-derive every settled bet's banked closing price, side- and
    line-aware, from the raw snapshots.

    WHY IT IS NEEDED. `closing_odds` is written at settle time, and until
    2026-08-09 the code that wrote it had two faults: it read the OVER
    price whatever side the bet took, and it ignored the line, so a close
    quoted at a different number was banked as if it were the same bet.
    Both are fixed, but a settled bet never settles again — the wrong
    values sit in the column forever, and `performance` reads them for
    the site's CLV figure and the nightly prose.

    `stakecheck --clv` sidesteps this by rebuilding from the snapshots
    every run and ignoring the banked column entirely. That was the right
    call for a report. It is not a fix for the stored data.

    Rows whose correct close cannot be found are set to NULL rather than
    left alone: a value known to have been written by the broken path is
    worse than no value, because nothing downstream can tell it is wrong.

    Returns a summary; writes only when `apply` is true.
    """
    from .sources.oddsapi import normalize_name
    snaps = _snapshot_close_odds()
    rows = conn.execute(
        "SELECT id, player, market, date, side, line, odds, closing_odds "
        "FROM bets WHERE status IN ('won','lost','push')").fetchall()
    fixed = cleared = agreed = filled = 0
    changes: list = []      # filled: had nothing, gains a close
    over_sample: list = []  # OVERWRITTEN: had a value, gets another
    clear_sample: list = [] # cleared: had a value, loses it
    for b in rows:
        sides = snaps.get(
            (normalize_name(b["player"]), b["market"], b["date"],
             round(float(b["line"]), 1) if b["line"] is not None else None)
        ) or {}
        want = sides.get(
            "under" if (b["side"] or "OVER").upper() == "UNDER" else "over")
        if want is not None and abs(float(want)) < 100:
            want = None            # not a legal American price; see linemoves
        had = b["closing_odds"]
        if want is None and had is None:
            continue
        if had is not None and want is not None and int(had) == int(want):
            agreed += 1
            continue
        # THREE OUTCOMES, COUNTED APART. The first dry run reported 2065
        # "rewritten" and sampled twelve, and all twelve were (none) ->
        # price — rows that simply had no close and now gain one. That is
        # pure coverage and it is safe. The rows that had a value and get
        # a DIFFERENT one are the only ones where something is being
        # overwritten, and they were invisible in a sample taken from the
        # front of the scan. A dry run that cannot show you the risky
        # subset is not doing the job a dry run exists to do.
        if want is None:
            cleared += 1
            kind = "cleared"
        elif had is None:
            filled += 1
            kind = "filled"
        else:
            fixed += 1
            kind = "overwritten"
        row = (b["date"], b["player"], b["side"], b["market"], b["line"],
               had, want)
        if kind == "overwritten" and len(over_sample) < 12:
            over_sample.append(row)
        elif kind == "cleared" and len(clear_sample) < 6:
            clear_sample.append(row)
        elif kind == "filled" and len(changes) < 6:
            changes.append(row)
        if apply:
            conn.execute("UPDATE bets SET closing_odds=? WHERE id=?",
                         (int(want) if want is not None else None, b["id"]))
    if apply:
        conn.commit()
    return {"settled": len(rows), "agreed": agreed, "overwritten": fixed,
            "filled": filled, "cleared": cleared,
            "sample": changes, "overwritten_sample": over_sample,
            "cleared_sample": clear_sample, "applied": apply}


def _bet_price_clv(b) -> float | None:
    """CLV in PROBABILITY POINTS, from the price rather than the line.

    The measurement line-based CLV cannot make. A home-run prop is quoted
    OVER 0.5 and closes at 0.5 — the line is incapable of moving, so its
    CLV is 0 forever and the whole market is invisible to the instrument.
    Those props move on price, and a home-run over taken at +400 that
    closes at +350 was a good bet by exactly the evidence CLV exists to
    give.

    Positive means the market moved TOWARD our side after we bet: the
    closing price is shorter than the one we took, so we got the better
    number. Stated in implied-probability points so it is comparable
    across prices — 2 points at +400 and 2 points at −150 are the same
    amount of having been right, where "50 cents of odds" is not.

    BOTH SIDES since 2026-08-09. This was OVER-only, and the reason given
    was sound at the time: the snapshots recorded the OVER price alone, so
    an under would have had to be scored against ``1 − P(over at close)``,
    which is not the same quantity — the vig means an over and an under at
    one book do not sum to 1, and that 4–5 point hold would swamp a signal
    measured in single points.

    That reason is gone. `linemoves.record_snapshots` never wrote
    `under_odds` at all, which is what made the over the only price
    available; it writes both now, and the settle path banks the price for
    the side the bet actually took. So an under is scored against the
    under's own close, and no 1−p substitution happens anywhere.

    It does not reach backwards. Snapshots taken before that fix hold no
    under price, so historical unders return None here exactly as they
    always did — `repair_closing_odds` will clear rather than invent them.
    """
    try:
        close = b["closing_odds"]
    except (KeyError, IndexError):
        return None                      # pre-migration row
    if close is None or not b["odds"]:
        return None
    from .odds import american_to_prob
    try:
        took = american_to_prob(int(b["odds"]))
        closed = american_to_prob(int(close))
    except (TypeError, ValueError):
        return None
    return closed - took


def process_grade(b) -> str | None:
    """Grade the DECISION, not the outcome.

    A won bet that closed worse than we took it got lucky; a lost bet that
    beat the close was a good bet that didn't land. Judging bets by result
    alone is how people talk themselves into bad process — this column is
    the antidote. None when no closing line is known."""
    clv = _bet_clv(b)
    if clv is None:
        return None
    if clv > 0:
        return "good"
    return "flat" if clv == 0 else "bad"


#: A slice needs this many bets WITH a captured close before its average
#: CLV is worth acting on. Same order as the miner's MIN_N: below it the
#: confidence band is wider than any signal the number could carry.
CLV_MIN_N = 40


def clv_coverage(conn, category: str = "main",
                 since: str | None = None) -> dict:
    """How much of the record actually has a closing line — per sport.

    CLV is the fastest-accruing evidence a bettor has: it grades the
    decision the moment the game starts, without waiting for the result.
    That only holds if the closes are real and plentiful, so this reports
    coverage before anything is built on top of it. ``ready`` says a
    sport has cleared ``CLV_MIN_N`` captured closes — the bar for its
    average to mean anything.
    """
    out: dict = {}
    for sp in TRACKED_SPORTS:
        # Windowed with the record: this prints "N of M settled picks
        # have a close", and an M that disagrees with the settled count
        # above it reads as one of the two numbers being wrong.
        q = ("SELECT * FROM bets WHERE status IN ('won','lost','push') "
             "AND category=? AND stake_units > 0 AND sport=?")
        cargs: list = [category, sp]
        if since:
            q += " AND date >= ?"
            cargs.append(since)
        bets = conn.execute(q, cargs).fetchall()
        if not bets:
            continue
        clvs = [c for c in (_bet_clv(b) for b in bets) if c is not None]
        settled = len(bets)
        out[sp] = {
            "settled": settled,
            "with_close": len(clvs),
            "coverage": round(len(clvs) / settled, 3) if settled else 0.0,
            "avg_clv": round(sum(clvs) / len(clvs), 3) if clvs else None,
            "beat_close": (round(sum(1 for c in clvs if c > 0) / len(clvs), 3)
                           if clvs else None),
            "ready": len(clvs) >= CLV_MIN_N,
        }
    tot = sum(v["settled"] for v in out.values())
    got = sum(v["with_close"] for v in out.values())
    return {"by_sport": out, "settled": tot, "with_close": got,
            "coverage": round(got / tot, 3) if tot else 0.0,
            "min_n": CLV_MIN_N,
            "ready_sports": sorted(s for s, v in out.items() if v["ready"])}


def implied_breakeven(odds) -> float | None:
    """The win rate one American price needs just to break even."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if not o:
        return None
    return (100.0 / (o + 100.0)) if o > 0 else (-o / (-o + 100.0))


def _book_breakeven(bets) -> float | None:
    """The average break-even across the prices a book actually took.

    Not a −110 assumption. A book of −200 favourites needs 66.7% and a
    book of +150 dogs needs 40%, and printing 52.4% beside either is a
    statement about a book nobody made.
    """
    rates = [r for r in (implied_breakeven(b["odds"]) for b in bets
                         if b["status"] != "push") if r is not None]
    return (sum(rates) / len(rates)) if rates else None


#: THE BOOK, as one thing. Ethan, 2026-08-13: "Combine our paper record
#: and normal money record. Combined all won and loss picks and continue
#: on recording how we usually do."
#:
#: This is the right unit of account and it always was, because paper mode
#: never changed a pick. `log_recommendations` does
#: `category = "paper" if paper else "main"` and touches nothing else —
#: same model, same projections, same gates, same pick_side, same
#: settlement. The two categories are one strategy either side of a
#: bookkeeping switch, so measuring them apart split one sample into two
#: underpowered halves and invited exactly the reading Ethan drew off it.
#:
#: WHAT STAYS SEPARATE, AND WHY IT HAS TO. Paper rows staked zero DOLLARS.
#: Their units are real (stakes are kept as sized, which is the whole
#: point of the book), so unit ROI pools honestly. Dollars do not: pooling
#: them would put money through the bankroll that was never at risk. Every
#: dollar figure below therefore stays real-money-only, and the payload
#: says which is which rather than leaving the reader to assume.
BOOK = ("main", "paper")


def performance(conn, sport: str | None = None,
                category: str | tuple[str, ...] = BOOK,
                since: str | None = None) -> dict:
    # ``stake_units > 0`` everywhere below: rows staked at zero were never
    # bets (an old grading bug shipped picks the vig had already eaten).
    # Counting them would inflate the W-L column with wagers nobody could
    # have won a unit on. They're reported separately as ``unstaked``.
    cats = (category,) if isinstance(category, str) else tuple(category)
    marks = ",".join("?" * len(cats))
    q = (f"SELECT * FROM bets WHERE status IN ('won','lost','push') "
         f"AND category IN ({marks}) AND stake_units > 0")
    args: list = list(cats)
    if sport:
        q += " AND sport=?"; args.append(sport)
    # `date >= ?` across mixed date formats, which needs stating exactly
    # because the obvious summary of it is wrong. NFL journals week
    # labels ("2026-W1") and everything else journals ISO days, and a
    # string comparison sorts them by their YEAR prefix first — so
    # "2024-W05" lands correctly BELOW a 2026 epoch, while "2026-W1" lands
    # above every day in its own year because "W" sorts above any digit.
    #
    # That is the right answer at the year level and the safe direction
    # inside the epoch's own year: a week from the current season is
    # included rather than silently dropped. (The remaining edge is a
    # January week of a season that started the previous autumn, which is
    # counted in with its season. For a display window that is the side to
    # err on.) An earlier draft of this comment claimed week labels always
    # sort above any ISO date; they do not, and a 2024 test caught it.
    if since:
        q += " AND date >= ?"; args.append(since)
    bets = conn.execute(q, args).fetchall()

    uq = (f"SELECT COUNT(*) FROM bets WHERE status IN ('won','lost','push') "
          f"AND category IN ({marks}) "
          f"AND (stake_units IS NULL OR stake_units <= 0)")
    uargs: list = list(cats)
    if sport:
        uq += " AND sport=?"; uargs.append(sport)
    if since:
        uq += " AND date >= ?"; uargs.append(since)
    unstaked = conn.execute(uq, uargs).fetchone()[0]

    wins = sum(1 for b in bets if b["status"] == "won")
    losses = sum(1 for b in bets if b["status"] == "lost")
    pushes = sum(1 for b in bets if b["status"] == "push")
    graded = wins + losses
    staked_u = sum(b["stake_units"] for b in bets if b["status"] != "push")
    net_u = sum(b["pnl_units"] or 0 for b in bets)
    net_d = sum(b["pnl_dollars"] or 0 for b in bets)
    clvs = [c for c in (_bet_clv(b) for b in bets) if c is not None]
    pclvs = [c for c in (_bet_price_clv(b) for b in bets) if c is not None]
    # Process record: of the bets where we know the close, how many were
    # good decisions regardless of result — plus the two honesty counters
    # (wins that got lucky, losses that were still good bets).
    process = {"good": 0, "flat": 0, "bad": 0,
               "lucky_wins": 0, "unlucky_losses": 0}
    for b in bets:
        g = process_grade(b)
        if g is None:
            continue
        process[g] += 1
        if b["status"] == "won" and g == "bad":
            process["lucky_wins"] += 1
        elif b["status"] == "lost" and g == "good":
            process["unlucky_losses"] += 1

    # Three readouts for the site's analytics footer (Ethan's desktop
    # render, 2026-08-11), each from the journal rather than invented:
    #   avg_price   — the average implied probability of the prices this
    #                 book actually took, expressed back in American odds.
    #                 A plain mean of American ints is arithmetic on two
    #                 different scales (+150 and −110 do not average to
    #                 +20 of anything); probabilities average cleanly.
    #   returned_u  — gross units back on wins and pushes (stake + pnl),
    #                 the "total won" a book's cashier would report.
    #   best_streak — longest run of consecutive wins in slate order.
    probs = [p for p in (implied_breakeven(b["odds"]) for b in bets
                         if b["odds"] is not None) if p]
    avg_price = None
    if probs:
        p = sum(probs) / len(probs)
        avg_price = int(round(-100 * p / (1 - p))) if p >= 0.5 \
            else int(round(100 * (1 - p) / p))
    returned_u = sum((b["stake_units"] or 0) + (b["pnl_units"] or 0)
                     for b in bets if b["status"] in ("won", "push"))
    best_streak = run = 0
    for b in sorted(bets, key=lambda b: (b["date"] or "", b["id"])):
        if b["status"] == "won":
            run += 1
            best_streak = max(best_streak, run)
        elif b["status"] == "lost":
            run = 0

    def bucket(field):
        out: dict[str, dict] = {}
        clv_lists: dict[str, list] = {}
        for b in bets:
            k = b[field] or "?"
            d = out.setdefault(k, {"w": 0, "l": 0, "net_u": 0.0})
            if b["status"] == "won": d["w"] += 1
            elif b["status"] == "lost": d["l"] += 1
            d["net_u"] += b["pnl_units"] or 0
            c = _bet_clv(b)
            if c is not None:
                clv_lists.setdefault(k, []).append(c)
        # CLV per bucket — the spec's "which module is actually earning"
        # readout, available long before the win-loss record means anything.
        for k, moves in clv_lists.items():
            out[k]["avg_clv"] = round(sum(moves) / len(moves), 3)
        return out

    return {
        "settled": len(bets), "wins": wins, "losses": losses, "pushes": pushes,
        "win_rate": (wins / graded) if graded else 0.0,
        # The win rate this book ACTUALLY has to clear, averaged over each
        # bet's own price. The page used to print a flat "break-even ≈
        # 52.4% at −110" beside it, which is the right number only for a
        # book of −110s. A book that buys short prices needs far more: on
        # this journal the real bar is around 58%, so 47% read as five
        # points short when it was ten. That is the site being reassuring
        # and wrong about the one number a bettor checks first.
        "breakeven": _book_breakeven(bets),
        "units_staked": round(staked_u, 2), "net_units": round(net_u, 2),
        "roi": (net_u / staked_u) if staked_u else 0.0,
        # REAL MONEY ONLY, and it is that way by construction rather than
        # by filter: a paper row settles with pnl_dollars 0 because no
        # dollars were ever at risk on it. Pooling the books in units is
        # honest; pooling them in dollars would run money through the
        # bankroll that never existed. The two counts below say the split
        # out loud so a reader never has to infer it from a suspiciously
        # small dollar figure beside a large unit one.
        "net_dollars": round(net_d, 2),
        "money_bets": sum(1 for b in bets
                          if b["status"] != "push" and (b["pnl_dollars"] or 0)),
        "paper_bets": sum(1 for b in bets if b["category"] == "paper"),
        "avg_price": avg_price,
        "returned_units": round(returned_u, 2),
        "best_streak": best_streak,
        "starting_bankroll": float(get_cfg(conn, "starting_bankroll")),
        "bankroll": bankroll(conn),
        # SPORT-SCOPED, and it was not. Every other number in this dict
        # honours the `sport` argument; this one counted the whole
        # journal, so `performance(conn, "mlb")` reported football's open
        # bets as baseball's. Invisible while one board was live, and
        # exactly wrong the moment six are.
        "open": conn.execute(
            f"SELECT COUNT(*) FROM bets WHERE status='open' "
            f"AND category IN ({marks})"
            + (" AND sport=?" if sport else "") + " AND stake_units > 0",
            (tuple(cats) + (sport,)) if sport else tuple(cats)).fetchone()[0],
        "unstaked": unstaked,
        "avg_clv": (sum(clvs) / len(clvs)) if clvs else None,
        # CLV coverage, because an average over 44% of the book is not a
        # book-wide number and was reading as one.
        "clv_n": len(clvs),
        # …and the price version, in probability points. On a fixed-line
        # market this is the ONLY CLV there is: the line closes where it
        # opened every night, so avg_clv reads 0 and says nothing, while
        # the price moved all evening. Reported apart rather than mixed —
        # line points and probability points are different units and
        # averaging them together would be arithmetic on two things.
        "avg_price_clv": (sum(pclvs) / len(pclvs)) if pclvs else None,
        "price_clv_n": len(pclvs),
        "process": process,
        "by_grade": bucket("grade"), "by_market": bucket("market"),
        "by_side": bucket("side"), "by_book": bucket("book"),
    }


def summary(conn, sport: str | None = None) -> str:
    p = performance(conn, sport)
    roll_delta = p["bankroll"] - p["starting_bankroll"]
    lines = [
        f"Ledger{f' · {sport.upper()}' if sport else ''}: "
        f"{p['settled']} settled ({p['wins']}-{p['losses']}-{p['pushes']}), "
        f"{p['open']} open",
        f"  Win rate {p['win_rate']:.1%}   ROI {p['roi']:+.1%}   "
        f"net {p['net_units']:+.2f}u",
        f"  Bankroll ${p['starting_bankroll']:.0f} → ${p['bankroll']:.2f} "
        f"({roll_delta:+.2f}, {roll_delta / p['starting_bankroll']:+.1%})",
    ]
    if p["avg_clv"] is not None:
        lines.append(f"  Closing-line value {p['avg_clv']:+.2f} pts avg")
    if p["by_grade"]:
        lines.append("  By grade:")
        for g, d in sorted(p["by_grade"].items(), key=lambda kv: -(kv[1]["w"] + kv[1]["l"])):
            lines.append(f"    {g:>11}: {d['w']}-{d['l']}  ({d['net_u']:+.2f}u)")
    if p["by_side"]:
        parts = [f"{s or '?'} {d['w']}-{d['l']} ({d['net_u']:+.2f}u)"
                 for s, d in sorted(p["by_side"].items())]
        lines.append("  By side:  " + "   ".join(parts))
    return "\n".join(lines)


# The dates each model re-tune shipped, oldest first. A bet is graded
# against the era it was journaled in, so "did the re-tune work" is
# answered by the journal itself instead of by memory. Append a row here
# on the next re-tune; everything downstream (report, Record page) follows.
MODEL_ERAS = [
    {"key": "v1", "label": "Original model", "start": None},
    {"key": "v2", "label": "Re-tuned gates — Scalpy 2.0 + pro NFL model",
     "start": "2026-07-29"},
    # THE BIGGEST CHANGE THIS MODEL HAS EVER HAD TO ITS OWN NUMBERS, and
    # it was not in this list until 2026-08-23 — so the Record page has
    # been blending eleven days of a differently-priced board into the
    # era before it, which is exactly what era_report's own docstring
    # says it exists to prevent.
    #
    # Four commits landed on 2026-08-12/13 and two of them move every
    # figure on the board:
    #
    #   07f313e  the selection haircut. stakecheck measured the model
    #            over-claiming by 9-10 points on the props it PICKS —
    #            51.5% claimed against 42.5% landed, and 59.7% against
    #            49.7% — so every edge, EV and Kelly stake was computed
    #            from a probability that far too high. Every claim now
    #            comes down before anything is derived from it.
    #   44e58b6  the price sets the stake, not the grade.
    #   5c8a839  the sloped ladder floor.
    #   b3b10c8  a second calibration knob, gated by a held-out judge.
    #
    # Starting 08-13 rather than 08-12: the haircut landed at 22:40 UTC,
    # so the boards priced on the 12th were mostly built before it. The
    # 13th is the first full day the new numbers ran.
    {"key": "v3",
     "label": "Claims cut to what our picks land; the price sets the stake",
     "start": "2026-08-13"},
]


#: The date the PUBLIC record starts counting from. Journaling is
#: unaffected — every row ever written is still in the database, still
#: graded, still training the model.
#:
#: Ethan, 2026-08-23: "i just dont want our data to be in the red since
#: when we first started in july the model wasnt tuned yet and its not
#: whats pulling bets now so we are displayong something thats hurting
#: us." That is a fair reading of what the number MEANS — a −22% ROI
#: earned by gates that no longer exist says nothing about the model
#: running tonight, which is the argument era_report below was written
#: to make — and it is only fair while the page SAYS SO. A record scoped
#: to a start date without a line admitting it is a curated record, and
#: this site's whole claim is that it grades in public. So:
#:
#:   * nothing is deleted. `all_time` in the export carries the full
#:     unscoped numbers, and the page links to them.
#:   * the page states the start date and how many settled picks sit
#:     before it, permanently, next to the headline.
#:   * every surface that quotes the record uses this one constant —
#:     including the paywall's proof block, which reads the same file.
#:
#: WORTH KNOWING: this is not an era boundary. MODEL_ERAS puts the big
#: re-tunes at 2026-07-29 and 2026-08-13, and the 13th is where the
#: claims were cut to what our picks actually land — "the biggest change
#: this model has ever had to its own numbers". 08-06 sits between them,
#: so it is a date, not a change. If the argument is ever challenged,
#: 2026-08-13 is the one that defends itself.
RECORD_EPOCH = "2026-08-06"


def era_report(conn) -> dict:
    """The headline record split at every model re-tune.

    A −22% ROI earned by gates that no longer exist says nothing about the
    model running tonight. Each era keeps its own W-L / ROI / CLV (and
    per-sport split), so the re-tune's effect is measured, not vibed.
    Category='main' only — the samplers already grade themselves.
    """
    starts = [e["start"] for e in MODEL_ERAS]
    eras = []
    for i, e in enumerate(MODEL_ERAS):
        start, end = e["start"], starts[i + 1] if i + 1 < len(starts) else None
        # The whole book, same as the headline — an era is a period of
        # the model's life, and paper mode did not start a new model.
        where = ("category IN ('main','paper') AND stake_units > 0")
        args: list = []
        if start:
            where += " AND date >= ?"
            args.append(start)
        if end:
            where += " AND date < ?"
            args.append(end)
        bets = conn.execute(
            f"SELECT * FROM bets WHERE {where} "
            f"AND status IN ('won','lost','push')", args).fetchall()
        wins = sum(1 for b in bets if b["status"] == "won")
        losses = sum(1 for b in bets if b["status"] == "lost")
        net = sum(b["pnl_units"] or 0.0 for b in bets)
        staked = sum(b["stake_units"] or 0.0 for b in bets
                     if b["status"] in ("won", "lost"))
        clvs = [c for c in (_bet_clv(b) for b in bets) if c is not None]
        by_sport: dict[str, dict] = {}
        for b in bets:
            d = by_sport.setdefault(b["sport"], {"w": 0, "l": 0, "net_u": 0.0})
            if b["status"] == "won":
                d["w"] += 1
            elif b["status"] == "lost":
                d["l"] += 1
            d["net_u"] = round(d["net_u"] + (b["pnl_units"] or 0.0), 2)
        eras.append({
            "key": e["key"], "label": e["label"], "from": start, "to": end,
            "settled": len(bets), "wins": wins, "losses": losses,
            "net_units": round(net, 2),
            "roi": round(net / staked, 4) if staked else 0.0,
            "avg_clv": round(sum(clvs) / len(clvs), 3) if clvs else None,
            "clv_n": len(clvs),
            "claim": _claim_gap(bets),
            "open": conn.execute(
                f"SELECT COUNT(*) FROM bets WHERE {where} AND status='open'",
                args).fetchone()[0],
            "by_sport": by_sport,
        })
    return {"eras": eras, "current": MODEL_ERAS[-1]["key"]}


def pnl_curve(conn, sport: str | None = None,
              since: str | None = None) -> list[dict]:
    """Cumulative settled P&L by slate date — the Record page's equity curve.

    One point per date with anything settled: that day's net units, the
    running total, and how many bets graded."""
    # Everything a DATE RANGE needs to state its own record, so the site
    # never has to fall back on all-time numbers under a windowed chart.
    #
    # Ethan, 2026-08-13, on the phone: "when I click the 1 week button
    # here for the record, it still displays all the information from our
    # all time record." He is right, and the data for the fix was already
    # half here — w, l and staked have ridden along since this function
    # was written, and the tiles never read them.
    #
    # Two more are added because a window CANNOT derive them:
    #   * dollars, which are not units × a constant. A paper row settles
    #     with pnl_dollars 0 by construction, so scaling a window's units
    #     by the all-time dollars-per-unit would run money through the
    #     bankroll that never existed.
    #   * the break-even, which is the mean of each bet's OWN implied
    #     rate. A week of −200 favourites needs 66.7% and a week of +150
    #     dogs needs 40%; carrying the all-time average into either is
    #     the same category of error, one column over. The sum and the
    #     count ride separately so any set of days can be averaged
    #     without weighting one day's price by another day's volume.
    be = ("CASE WHEN odds > 0 THEN 100.0 / (odds + 100.0) "
          "ELSE -odds / (-odds + 100.0) END")
    graded = "status != 'push' AND odds IS NOT NULL AND odds != 0"
    q = ("SELECT date, SUM(pnl_units) AS day_u, COUNT(*) AS n, "
         "SUM(status='won') AS w, SUM(status='lost') AS l, "
         "SUM(stake_units) AS staked, "
         "SUM(COALESCE(pnl_dollars, 0)) AS day_d, "
         "SUM(COALESCE(stake_dollars, 0)) AS staked_d, "
         f"SUM(CASE WHEN {graded} THEN {be} ELSE 0 END) AS be_sum, "
         f"SUM(CASE WHEN {graded} THEN 1 ELSE 0 END) AS be_n "
         "FROM bets "
         "WHERE status IN ('won','lost','push') "
         "AND category IN ('main','paper') "
         "AND stake_units > 0")
    args: list = []
    if sport:
        q += " AND sport=?"
        args.append(sport)
    # The curve has to start where the headline starts, or the page shows
    # a running total that disagrees with the number above it — and the
    # curve is the more convincing of the two, so the disagreement would
    # read as the headline lying.
    if since:
        q += " AND date >= ?"
        args.append(since)
    q += " GROUP BY date ORDER BY date"
    out, cum = [], 0.0
    for r in conn.execute(q, args):
        cum += r["day_u"] or 0.0
        # w/l/staked ride along so the site can compute an HONEST stat
        # block for any date range (Ethan's analytics render, 2026-08-11)
        # instead of showing all-time numbers under a 1-month chart.
        out.append({"date": r["date"], "day_u": round(r["day_u"] or 0.0, 2),
                    "cum_u": round(cum, 2), "n": r["n"],
                    "w": r["w"] or 0, "l": r["l"] or 0,
                    "staked": round(r["staked"] or 0.0, 2),
                    "day_d": round(r["day_d"] or 0.0, 2),
                    "staked_d": round(r["staked_d"] or 0.0, 2),
                    "be_sum": round(r["be_sum"] or 0.0, 4),
                    "be_n": r["be_n"] or 0})
    return out


def drawdown_factor(conn, sport: str | None = None,
                    drawdown_u: float = 10.0) -> float:
    """§10 drawdown circuit-breaker (docs/NFL_MODEL.md).

    After a 10-unit peak-to-trough drawdown (10% of bankroll at the standard
    1u = 1%), every stake is cut in half until the peak is recovered.
    Drawdowns are when systems start chasing; halving stakes makes the worst
    case survivable and removes the mathematical possibility of ruin.

    Returns 0.5 while in drawdown, else 1.0. Measured on the settled main
    journal — the same numbers the Record page shows."""
    peak = cum = 0.0
    for point in pnl_curve(conn, sport=sport):
        cum = point["cum_u"]
        peak = max(peak, cum)
    return 0.5 if (peak - cum) >= drawdown_u else 1.0


def recent_settled(conn, limit: int = 30, category: str = "main",
                   sport: str | None = None,
                   since: str | None = None) -> list[dict]:
    """The last settled picks, newest first — the site's receipts.

    Each row carries its side-aware CLV and process grade so the page can
    show "won but got lucky" / "lost but beat the close" honestly."""
    q = ("SELECT date, sport, player, market, side, line, odds, grade, status, "
         "pnl_units, hit_prob, closing_line, stake_units, loss_cause, "
         "why_tag, why_note FROM bets "
         "WHERE status IN ('won','lost','push') AND category=? "
         "AND stake_units > 0")
    args: list = [category]
    if since:
        q += " AND date >= ?"
        args.append(since)
    if sport:
        q += " AND sport=?"
        args.append(sport)
    rows = conn.execute(q + " ORDER BY date DESC, id DESC LIMIT ?",
                        (*args, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        c = _bet_clv(r)
        d["clv"] = round(c, 3) if c is not None else None
        d["process"] = process_grade(r)
        d["cause"] = d.pop("loss_cause")
        out.append(d)
    return out


#: A split has to earn its own chart. Below this many graded picks the
#: confidence band is wider than any miss it could show, so the row would
#: report noise with the authority of a measurement. The aggregate already
#: covers those bets — they are not dropped, just not given a headline.
SPLIT_MIN_N = 40

#: Days from journaling a pick to the event it resolves on. `ts` carries a
#: full timestamp and `date` is the slate day, so both are cut to a day
#: before subtracting — otherwise a pick published at 6pm for tomorrow's
#: game measures 0.75 days and floors to zero.
_HORIZON_SQL = "CAST(julianday(date) - julianday(substr(ts, 1, 10)) AS INTEGER)"

#: Horizon buckets, in days. Open-ended at the top because a futures bet has
#: no natural ceiling — and the label is chosen so a board where everything
#: lands in one bucket reads as "we only bet tonight", which is true and
#: worth knowing, rather than as a broken chart.
HORIZON_BUCKETS = [
    ("Same day", 0, 1),
    ("1–3 days", 1, 4),
    ("4–14 days", 4, 15),
    ("15+ days", 15, None),
]

#: Log loss is unbounded at the ends — a 0% forecast on something that
#: happened costs infinity, which would make one row swallow the whole
#: score and turn an honesty metric into a single-row lottery. Clamping to
#: 1e-4 caps the worst single bet at ~9.2, which is severe enough to hurt
#: and finite enough to average.
LOGLOSS_CLAMP = 1e-4


def _log_loss_one(p: float, won: float) -> float:
    """Cost of one forecast under the logarithmic rule."""
    import math
    p = min(max(p, LOGLOSS_CLAMP), 1.0 - LOGLOSS_CLAMP)
    return -(won * math.log(p) + (1.0 - won) * math.log(1.0 - p))


def calibration(conn, category: str = "main", bucket_pts: int = 5,
                since: str | None = None, sport: str | None = None,
                market: str | None = None,
                horizon: tuple[int, int | None] | None = None) -> dict:
    """Predicted vs realized, in probability buckets — the public honesty page.

    Groups every settled won/lost bet by the model's claimed hit probability
    (5-point buckets by default) and reports what actually happened in each,
    with a ±1.96·√(p(1−p)/n) band so small samples read as "too early", not
    as verdicts. Also scores the model's Brier against the market's own fair
    probability ON THE SAME BETS (fair = hit_prob − edge, since edge was
    stored as model-minus-fair at bet time): if we can't out-forecast the
    de-vigged close on our own selections, the edge story is fiction.

    Brier is reported alongside LOG LOSS, and the pair is the point. Both are
    strictly proper — neither can be gamed by shading probabilities toward
    50% — but they punish a confident miss very differently. Say 95% and be
    wrong: Brier charges 0.90, log loss charges 3.00. A model that is nearly
    right most nights and catastrophically wrong occasionally looks fine on
    Brier alone, and that is exactly the failure mode that empties a
    bankroll. Publishing only the gentler number is a choice, so we publish
    both.

    ECE — the average distance from the diagonal, weighted by how many bets
    sit in each bucket — is the one number that summarises the reliability
    diagram. It answers "when this model says a number, how far off is it
    typically", which neither Brier nor log loss answers, because both mix
    calibration together with resolution."""
    from math import sqrt
    q = ("SELECT hit_prob, edge, status FROM bets "
         "WHERE status IN ('won','lost') AND category=? AND hit_prob IS NOT NULL")
    args: list = [category]
    if since:
        # Era-scoped: judge the model running NOW on its own picks only.
        q += " AND date >= ?"
        args.append(since)
    if sport:
        # Sport-scoped: an aggregate calibration answers "is the SYSTEM
        # honest", which is worth knowing and is not the question a person
        # tuning one model is asking. A baseball model that reads 4 points
        # hot and a football model 4 points cold cancel to a perfect line
        # nobody should trust.
        q += " AND sport=?"
        args.append(sport)
    if market:
        # Per-market: the study's point is that calibration degrades on thin
        # markets, and an aggregate hides exactly that. A model 3 points hot
        # on total bases and 3 cold on strikeouts averages to a clean line.
        q += " AND market=?"
        args.append(market)
    if horizon is not None:
        # Days between journaling a pick and the event it resolves on. A
        # tonight prop and a season-long futures bet answer different
        # questions and should not share a chart.
        lo, hi = horizon
        q += " AND " + _HORIZON_SQL + " >= ?"
        args.append(lo)
        if hi is not None:
            q += " AND " + _HORIZON_SQL + " < ?"
            args.append(hi)
    rows = conn.execute(q, args).fetchall()
    nb = max(1, 100 // bucket_pts)
    buckets: list[dict] = [{"lo": i * bucket_pts, "hi": (i + 1) * bucket_pts,
                            "n": 0, "_p": 0.0, "_w": 0} for i in range(nb)]
    se_model = 0.0
    se_market = 0.0
    ll_model = 0.0
    ll_market = 0.0
    n_market = 0
    for r in rows:
        p = min(max(float(r["hit_prob"]), 0.0), 1.0)
        won = 1.0 if r["status"] == "won" else 0.0
        b = buckets[min(int(p * 100) // bucket_pts, nb - 1)]
        b["n"] += 1
        b["_p"] += p
        b["_w"] += won
        se_model += (p - won) ** 2
        ll_model += _log_loss_one(p, won)
        if r["edge"] is not None:
            fair = min(max(p - float(r["edge"]), 0.01), 0.99)
            se_market += (fair - won) ** 2
            ll_market += _log_loss_one(fair, won)
            n_market += 1
    out_buckets = []
    for b in buckets:
        if not b["n"]:
            continue
        pred = b["_p"] / b["n"]
        act = b["_w"] / b["n"]
        ci = 1.96 * sqrt(pred * (1.0 - pred) / b["n"])
        out_buckets.append({
            "lo": b["lo"], "hi": b["hi"], "n": b["n"],
            "predicted": round(pred, 4), "actual": round(act, 4),
            "ci": round(ci, 4), "in_band": abs(act - pred) <= ci})
    n = len(rows)
    # ECE over the buckets we actually have. Weighted by bucket population,
    # so a five-bet bucket miles off the diagonal cannot outvote a
    # thousand-bet bucket sitting on it.
    ece = (sum(b["n"] * abs(b["actual"] - b["predicted"]) for b in out_buckets) / n
           if n and out_buckets else None)
    return {
        "n": n, "bucket_pts": bucket_pts, "buckets": out_buckets, "since": since,
        "brier_model": round(se_model / n, 4) if n else None,
        "brier_market": round(se_market / n_market, 4) if n_market else None,
        # Positive = the model out-forecasts the de-vigged market prices on
        # its own picks; negative = the market knew better.
        "brier_edge": (round(se_market / n_market - se_model / n, 4)
                       if n and n_market else None),
        # Same comparison under the harsher proper rule. The two can and do
        # disagree — that disagreement is a finding, not a bug: it means the
        # gap between model and market is concentrated in the confident
        # tails rather than spread evenly across the book.
        "logloss_model": round(ll_model / n, 4) if n else None,
        "logloss_market": round(ll_market / n_market, 4) if n_market else None,
        "logloss_edge": (round(ll_market / n_market - ll_model / n, 4)
                         if n and n_market else None),
        "ece": round(ece, 4) if ece is not None else None,
    }


#: Fields the hash covers, in a fixed order. Order is part of the hash, so
#: this tuple is a format version: changing it invalidates every hash after
#: the change and the chain will read as broken from that point. Append a
#: new log rather than editing this.
FORECAST_FIELDS = ("bet_id", "ts", "sport", "date", "player", "market",
                   "side", "line", "odds", "hit_prob", "category")

#: The chain's anchor. A first row still needs something to hash against,
#: and a literal beats an empty string because "" is also what a NULL
#: prev_hash reads as after a bad migration.
GENESIS_HASH = "qellys-forecast-log-v1"


def _forecast_hash(prev_hash: str, row: dict) -> str:
    """One row's link. Values are rendered with repr-free, locale-free
    formatting so the same forecast hashes identically on any machine."""
    import hashlib
    parts = [prev_hash or GENESIS_HASH]
    for f in FORECAST_FIELDS:
        v = row.get(f)
        parts.append("" if v is None else
                     (f"{v:.6f}" if isinstance(v, float) else str(v)))
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def seal_forecasts(conn) -> int:
    """Append every journaled pick not already in the log. Returns how many.

    Called once after journaling rather than wired into each INSERT. There
    are eight-plus places that write a bet, several of them per-sport, and
    a new one gets added every time a sport does; a hook per site is a hook
    that will be forgotten. A sweep cannot be forgotten, and it is
    idempotent, so running it twice is free.

    Ordered by bet id so the chain is deterministic: two runs over the same
    journal produce the same head hash.
    """
    conn.executescript(_FORECAST_LOG)
    head = conn.execute(
        "SELECT hash FROM forecast_log ORDER BY seq DESC LIMIT 1").fetchone()
    prev = head["hash"] if head else GENESIS_HASH
    rows = conn.execute(
        "SELECT b.id AS bet_id, b.ts, b.sport, b.date, b.player, b.market, "
        "b.side, b.line, b.odds, b.hit_prob, b.category FROM bets b "
        "LEFT JOIN forecast_log f ON f.bet_id = b.id "
        "WHERE f.bet_id IS NULL ORDER BY b.id").fetchall()
    n = 0
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for r in rows:
        d = dict(r)
        h = _forecast_hash(prev, d)
        conn.execute(
            "INSERT OR IGNORE INTO forecast_log (sealed_ts, bet_id, ts, sport,"
            " date, player, market, side, line, odds, hit_prob, category,"
            " prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now, d["bet_id"], d["ts"], d["sport"], d["date"], d["player"],
             d["market"], d["side"], d["line"], d["odds"], d["hit_prob"],
             d["category"], prev, h))
        prev = h
        n += 1
    conn.commit()
    return n


def verify_forecast_log(conn) -> dict:
    """Recompute every link. Reports the FIRST break, not just a boolean.

    A chain that says only "broken" is nearly useless — the whole value is
    knowing where, because everything before the break is still proven.
    """
    try:
        rows = conn.execute(
            "SELECT * FROM forecast_log ORDER BY seq").fetchall()
    except Exception:                                  # noqa: BLE001
        return {"ok": True, "n": 0, "head": None, "broken_at": None}
    prev = GENESIS_HASH
    for r in rows:
        d = {f: r[f] for f in FORECAST_FIELDS}
        if r["prev_hash"] != prev or _forecast_hash(prev, d) != r["hash"]:
            return {"ok": False, "n": len(rows), "head": None,
                    "broken_at": r["seq"], "verified_through": r["seq"] - 1}
        prev = r["hash"]
    return {"ok": True, "n": len(rows), "head": prev if rows else None,
            "broken_at": None, "verified_through": len(rows)}


def _prereg_block(conn) -> dict:
    """Preregistered tests, evaluated against the journal.

    Registered forward on Ethan's instruction (2026-08-13) after
    `gradecheck` declined to convict the B+ bucket: 2.1 standard errors
    is not enough when the bucket was chosen for looking bad. See
    engine/prereg.py for the three properties that make it a
    preregistration rather than a note.
    """
    try:
        from . import prereg
        rows = [dict(r) for r in conn.execute(
            "SELECT date, sport, grade, odds, status FROM bets "
            "WHERE status IN ('won','lost') "
            "AND category IN ('main','paper') AND stake_units > 0")]
        return {"tests": prereg.report(rows)}
    except Exception:                                         # noqa: BLE001
        return {"tests": []}


def _hypothesis_lab_block() -> dict:
    """The stored hypothesis-lab state, for export_json. Store-read only —
    a missing store is the designed empty state, never a failure."""
    try:
        from . import hypotheses as hyp
        store = hyp.load()
        hyps = store.get("hypotheses") or []
        return {
            "generated": store.get("generated"),
            "retested": store.get("retested"),
            "model": store.get("model"),
            "hypotheses": hyps,
            "watchlist": store.get("watchlist") or [],
            "n_confirmed": sum(1 for h in hyps
                               if h.get("status") == "confirmed"),
            "n_rejected": sum(1 for h in hyps
                              if h.get("status") == "rejected"),
            "n_collecting": sum(1 for h in hyps
                                if h.get("status") == "collecting"),
            "n_closed": sum(1 for h in hyps
                            if h.get("action") == "close"),
        }
    except Exception:                              # noqa: BLE001
        return {"hypotheses": [], "watchlist": [], "n_confirmed": 0,
                "n_rejected": 0, "n_collecting": 0, "n_closed": 0}


def restated_performance(conn, sport: str | None = None,
                         since: str | None = None) -> dict:
    """The same graded picks, re-sized on TODAY's staking scale.

    The official record is receipts — stakes as the bets were actually
    made, including the era when every path sized off a twenty-unit
    ruler and a conviction play weighed the same as a lottery ticket.
    This view answers Ethan's question about that era honestly: what
    would the record and ROI read if every settled pick had been priced
    and staked by the CURRENT model? Read-only, computed fresh from
    journaled probability, price and grade — history itself is never
    edited.

    TWO changes are replayed, and the second is the one that moves it.

    * The stake: the price ladder, 1u = 1% of bankroll, no grade cap.
    * The CLAIM: the selection haircut. This is the important one.
      Re-sizing alone answers "what if we had bet these differently",
      which is a smaller question than the one worth asking — the
      haircut changes WHICH bets exist, because a probability shifted
      down by nine points stops clearing break-even at its own price and
      Kelly refuses it outright. Restating the stakes while leaving the
      claims uncorrected would describe a model that never existed:
      today's sizing on yesterday's optimism.

    A pick today's Kelly refuses at its HAIRCUT probability and journaled
    price is EXCLUDED and counted, because today's model would not have
    made that bet at all.

    WHAT THIS IS NOT. It is not the record and the page must never let it
    be read as one. Ethan, 2026-08-16: "our roi shows the right number
    ... it should get better with our changes." The record cannot get
    better from a code change — those bets were made at those stakes and
    the money moved. What CAN answer his question is this: the same
    nights, priced by the model we have now. If the changes are worth
    anything, the gap between this line and the record is where it shows
    up first — long before enough new bets settle to prove it forward.

    MAIN only, exactly like performance(): the headline record describes
    the picks the model stands behind, and the long-shot dimes have their
    own bucket with their own scoreboard — blending them back in here
    would re-create, in the restated view, the exact pollution the
    buckets exist to prevent.
    """
    from .odds import american_to_decimal
    from .selectionfit import apply_haircut
    from .staking import kelly_units
    q = ("SELECT sport, status, odds, hit_prob, grade FROM bets "
         "WHERE status IN ('won','lost','push') "
         "AND category IN ('main','paper')")
    args: list = []
    if sport:
        q += " AND sport=?"
        args.append(sport)
    # Same window as the record it sits beside. This line's whole job is
    # to be COMPARED with the headline — "the same nights, priced by the
    # model we have now" — and two lines drawn over different nights are
    # not a comparison.
    if since:
        q += " AND date >= ?"
        args.append(since)
    wins = losses = pushes = excluded = 0
    staked = net = 0.0
    for b in conn.execute(q, args):
        p, odds = b["hit_prob"], b["odds"]
        if p is None or odds is None or not 0.0 < float(p) < 1.0:
            excluded += 1
            continue
        # The haircut FIRST, on the sport that bet was made in. Applying
        # it here and not at all is the difference between "what if we
        # had sized these differently" and "what would today's model have
        # done" — and only the second is worth printing beside a record.
        p = apply_haircut(str(b["sport"] or "").lower(), float(p))
        # The grade no longer scales a stake — the price does (see
        # engine/staking.py's ladder). It still picks the Kelly fraction
        # used as the VETO, which is the only job it has left here.
        grade = str(b["grade"] or "")
        frac = 0.5 if grade == "A+" else 0.25
        stake = kelly_units(float(p), int(odds), frac)
        if stake <= 0:
            excluded += 1
            continue
        if b["status"] == "push":
            pushes += 1
            continue
        staked += stake
        if b["status"] == "won":
            wins += 1
            net += stake * (american_to_decimal(int(odds)) - 1.0)
        else:
            losses += 1
            net -= stake
    return {"settled": wins + losses + pushes, "wins": wins,
            "losses": losses, "pushes": pushes,
            "units_staked": round(staked, 2), "net_units": round(net, 2),
            "roi": (net / staked) if staked else 0.0,
            "excluded": excluded}


def _prose_block() -> dict:
    """The prose lanes' stored output, for export_json. Store-read only —
    the export path must never be able to spend a token — and guarded so a
    missing store never costs the export."""
    try:
        from . import prose
        return prose.site_block()
    except Exception:                              # noqa: BLE001
        return {}


def _loss_patterns_block(conn) -> dict:
    """The miner's view of this journal, for export_json. Guarded like
    every other block: a mining failure must never cost the export."""
    try:
        from . import losspatterns as lp
        return lp.mine(lp.records_from_ledger(conn))
    except Exception:                              # noqa: BLE001
        return {"n_records": 0, "tested": 0, "findings": [], "closed": []}


def _selection_haircut_block() -> dict:
    """selectionfit's stored verdict, for export_json.

    Reads the STORE rather than refitting, so the page always shows the
    correction the board was actually priced with. Refitting here would
    print a number no pick has ever been sized on — which is the exact
    kind of "true but not what happened" the Record page exists to avoid.
    """
    try:
        from . import selectionfit
        return selectionfit.report()
    except Exception:                              # noqa: BLE001
        return {}


def _self_tuning_block() -> dict:
    """self_tuning_report with its own history connection, for export_json.

    Guarded because export runs everywhere — settle passes, CI, fresh
    clones with no stats DB. sqlite would invent an empty file on connect,
    which is harmless here (trend simply returns nothing), but a raise
    must never cost the record export."""
    try:
        from . import db as hist_db
        h = hist_db.connect()
        try:
            return self_tuning_report(h)
        finally:
            h.close()
    except Exception:                              # noqa: BLE001
        return self_tuning_report(None)


def self_tuning_report(hist_conn=None) -> dict:
    """The learning loop, made visible.

    Everything reported here already happens nightly with no human in it:
    ``calibrate.fit`` reads every settled bet, refits one temperature per
    market (T > 1 pulls probabilities toward 50% — the model ran hot;
    T < 1 pushes them out — it ran shy), a fit that runs to the edge of its
    search range closes that market by itself, and ``calibhistory`` stamps
    every sweep with the commit that produced it so "is it getting better"
    has an answer with causes attached.

    None of that was on the site. A learning loop nobody can see is
    indistinguishable from a static model — and worse, the honest answer to
    "does this thing adjust to its own results?" was YES while every page
    implied nothing of the sort. This block is that answer, rendered.
    """
    import json

    from . import calibrate as cal
    out = {"markets": [], "trend": {}, "last_refit": None,
           "closed": [], "improving": 0, "tracked": 0}
    # calibrate.load() is the runtime accessor and deliberately strips the
    # stored file to {key: (temperature, intercept)} — all the correction
    # path needs. This report needs the whole fit record (samples, Brier
    # before/after), so it reads the file save() wrote. cal.DEFAULT_PATH is
    # read at call time on purpose: a default argument freezes at import
    # and silently ignores a repointed path (tests, tools).
    stored: dict = {}
    try:
        p = Path(cal.DEFAULT_PATH)
        if p.is_file():
            raw = json.loads(p.read_text())
            if isinstance(raw, dict):
                stored = raw
    except (ValueError, OSError):
        stored = {}
    for key, d in sorted(stored.items()):
        if not isinstance(d, dict):
            continue
        try:
            t = float(d["temperature"])
        except (KeyError, TypeError, ValueError):
            continue
        k_sport, _, k_market = key.partition(":")
        sport = d.get("sport") or (k_sport if k_market else "")
        market = d.get("market") or k_market or key
        boundary = t <= cal.GRID_MIN + 1e-9 or t >= cal.GRID_MAX - 1e-9
        if boundary:
            # The fitter wanted a bigger correction than the search allows:
            # its own way of saying "unreliable here, not merely
            # miscalibrated". is_reliable() reads the same signal and the
            # engines hard-pass the market — no human decided that.
            out["closed"].append({"sport": sport, "market": market})
        out["markets"].append({
            "sport": sport, "market": market,
            "temperature": round(t, 3),
            "samples": int(d.get("samples", 0) or 0),
            "brier_before": d.get("brier_before"),
            "brier_after": d.get("brier_after"),
            "at_boundary": boundary,
            "reading": ("closed by its own fit" if boundary
                        else "ran hot — tempered toward 50%" if t > 1.05
                        else "ran shy — pushed outward" if t < 0.95
                        else "clean"),
        })
    try:
        mt = Path(cal.DEFAULT_PATH).stat().st_mtime
        out["last_refit"] = datetime.datetime.fromtimestamp(mt)\
            .isoformat(timespec="seconds")
    except OSError:
        pass
    # Rung two: the recency-dial fits (engine/formfit.py) — the model's
    # own recipe, refit from outcomes. "Default kept" rows ship too: a
    # dial the record examined and left alone is part of the story.
    try:
        from . import formfit as ff
        out["weights"] = ff.report(ff.DEFAULT_PATH)
    except Exception:                              # noqa: BLE001
        out["weights"] = []
    # Rung three: per-player memory (engine/playerfit.py) — who the blend
    # misreads, with "memory off" rows shipped too: a memory the record
    # tried and rejected is part of the story.
    try:
        from . import playerfit as pfit
        out["players"] = pfit.report(pfit.DEFAULT_PATH)
    except Exception:                              # noqa: BLE001
        out["players"] = []
    if hist_conn is not None:
        try:
            from . import calibhistory as ch
            for sport in sorted({m["sport"] for m in out["markets"]
                                 if m["sport"]} or {"mlb"}):
                tr = ch.trend(hist_conn, sport)
                if tr:
                    out["trend"][sport] = tr
                    out["improving"] += sum(1 for v in tr.values()
                                            if v.get("improved"))
                    out["tracked"] += len(tr)
        except Exception:                          # noqa: BLE001
            pass
    return out


def calibration_splits(conn, category: str = "main", since: str | None = None,
                       sport: str | None = None, min_n: int = SPLIT_MIN_N) -> dict:
    """Calibration broken out by market and by horizon.

    The study's fifth lesson: calibration degrades on thin markets and on
    long horizons, and an aggregate hides both. A model reading three points
    hot on total bases and three cold on strikeouts averages to a line that
    looks perfect and is not — the same argument that already split this
    report by sport, applied one level down.

    Two honesty rules, both about not over-claiming from a small board:

      * a split needs ``min_n`` graded picks to get a row at all, and the
        ones that don't clear it are COUNTED and reported rather than
        silently dropped, so "we only show four of eleven markets" is
        visible;
      * if every pick lands in one horizon bucket, the horizon split is
        returned with ``degenerate: True``. That is the true answer for a
        board that only bets tonight, and it should read as a fact about our
        betting rather than as a chart with one bar.
    """
    base = dict(category=category, since=since, sport=sport)

    markets: list[dict] = []
    q = ("SELECT market, COUNT(*) n FROM bets WHERE status IN ('won','lost') "
         "AND category=? AND hit_prob IS NOT NULL")
    args: list = [category]
    if since:
        q += " AND date >= ?"
        args.append(since)
    if sport:
        q += " AND sport=?"
        args.append(sport)
    q += " GROUP BY market ORDER BY n DESC"
    counts = conn.execute(q, args).fetchall()
    held_back = 0
    for r in counts:
        if (r["n"] or 0) < min_n:
            held_back += 1
            continue
        rep = calibration(conn, market=r["market"], **base)
        if rep.get("n"):
            rep["market"] = r["market"]
            markets.append(rep)

    horizons: list[dict] = []
    for label, lo, hi in HORIZON_BUCKETS:
        rep = calibration(conn, horizon=(lo, hi), **base)
        if rep.get("n"):
            rep["label"] = label
            rep["lo_days"] = lo
            rep["hi_days"] = hi
            horizons.append(rep)
    occupied = [h for h in horizons if h["n"] >= min_n]

    return {
        "markets": markets,
        "markets_held_back": held_back,
        "min_n": min_n,
        "horizons": horizons,
        # One bucket holding everything is not a distribution. Say so.
        "horizon_degenerate": len(occupied) < 2,
    }


# Account-health scoring weights — how much each behavior pattern
# contributes to a book's 0–100 limit-risk estimate. They sum to 100.
HEALTH_MIN_BETS = 5
HEALTH_W_CLV = 40          # books limit closing-line beaters first
HEALTH_W_CONCENTRATION = 20  # living in one low-limit prop market
HEALTH_W_PROP_MIX = 15     # a book of nothing but props has no cover
HEALTH_W_STAKES = 13       # precise, model-sized stakes read sharp
HEALTH_W_VOLUME = 12       # sheer graded volume at one shop

#: Signals a risk desk uses that this journal structurally cannot see. Named
#: rather than omitted: a score that quietly drops four of seven inputs
#: implies a completeness it does not have, and the reason each one is
#: missing is different and worth saying.
HEALTH_BLIND_SPOTS = [
    ("Bet timing after a line move",
     "we know when WE published a pick, not when you placed a bet — "
     "deriving one from the other would be inventing a number"),
    ("Promo and free-bet behavior", "not tracked; this tool takes no money"),
    ("Deposit and withdrawal pattern", "same — no account is linked, by design"),
    ("Device, IP and browser fingerprint",
     "deliberately out of scope: watching these is how you'd be tempted to "
     "spoof them, and that is account fraud rather than bankroll management"),
]


def account_health(conn, since: str | None = None) -> dict:
    """Estimate, per book, how 'sharp' this journal looks to a risk desk.

    Books don't publish limit criteria, but the patterns they act on are
    well known: consistently beating the close, hammering one prop market,
    and precise non-round stakes. This scores OUR OWN journaled behavior
    against those patterns — 0 (recreational-looking) to 100 (walking
    limit-risk) — with the drivers and the concrete actions that would
    lower it. It is inference from our own betting record, nothing more:
    no insider knowledge of any book's actual risk rules."""
    q = ("SELECT * FROM bets WHERE status IN ('won','lost','push') "
         "AND category='main'")
    args: list = []
    if since:
        q += " AND date >= ?"
        args.append(since)
    bets = conn.execute(q, args).fetchall()
    by_book: dict[str, list] = {}
    for b in bets:
        by_book.setdefault(b["book"] or "?", []).append(b)

    books = []
    for book, rows in by_book.items():
        if len(rows) < HEALTH_MIN_BETS:
            continue
        # CLV beat rate — the strongest limit signal a book can see.
        clvs = [c for c in (_bet_clv(b) for b in rows) if c is not None]
        beat_rate = (sum(1 for c in clvs if c > 0) / len(clvs)) if clvs else None
        clv_pts = (beat_rate if beat_rate is not None else 0.5) * HEALTH_W_CLV
        # Market concentration — share of volume in the single busiest market.
        mkts: dict[str, int] = {}
        for b in rows:
            mkts[b["market"] or "?"] = mkts.get(b["market"] or "?", 0) + 1
        top_market, top_n = max(mkts.items(), key=lambda kv: kv[1])
        conc = top_n / len(rows)
        conc_pts = conc * HEALTH_W_CONCENTRATION
        # Product mix — share of volume in player props rather than main
        # lines. A DIFFERENT signal from concentration, and the pair is why
        # both are scored: "40% of volume is home runs" is concentration,
        # "94% of volume is props" is mix, and a book spread evenly across
        # eight prop markets scores clean on the first while being exactly
        # the profile the study describes. Props and niche markets carry the
        # lowest limits, so they are where limiting starts before it spreads.
        prop_n = sum(1 for b in rows if (b["market"] or "") not in GAME_MARKETS)
        prop_share = prop_n / len(rows)
        mix_pts = prop_share * HEALTH_W_PROP_MIX
        # Stake pattern — fraction of dollar stakes that aren't round $5s.
        staked = [b["stake_dollars"] for b in rows if b["stake_dollars"]]
        sharp_stakes = (sum(1 for s in staked if abs(s / 5.0 - round(s / 5.0)) > 1e-9)
                        / len(staked)) if staked else 0.0
        stake_pts = sharp_stakes * HEALTH_W_STAKES
        # Volume exposure — graded bets at this one shop, saturating at 100.
        vol_pts = min(len(rows) / 100.0, 1.0) * HEALTH_W_VOLUME

        score = round(clv_pts + conc_pts + mix_pts + stake_pts + vol_pts)
        band = "low" if score < 35 else ("moderate" if score <= 65 else "elevated")

        drivers = []
        if beat_rate is not None:
            drivers.append(f"beats the close on {beat_rate:.0%} of tracked bets"
                           + (" — the #1 pattern risk desks act on"
                              if beat_rate >= 0.55 else ""))
        drivers.append(f"{conc:.0%} of volume is {top_market}")
        if prop_share >= 0.8:
            drivers.append(f"{prop_share:.0%} of volume is player props — the "
                           "lowest-limit markets on the board, and where "
                           "limiting starts before it spreads")
        elif prop_share <= 0.4:
            drivers.append(f"{1 - prop_share:.0%} of volume is main lines, which "
                           "is the deepest, most tolerant part of the book")
        if sharp_stakes > 0.5:
            drivers.append("stakes are precise model-sized amounts, not round numbers")
        actions = []
        if conc >= 0.5:
            actions.append(f"mix in main-line bets (sides/totals) so {top_market} "
                           f"isn't {conc:.0%} of your volume here")
        elif prop_share >= 0.8:
            # Only when concentration DIDN'T already say it — otherwise the
            # card gives the same advice twice in two different sentences.
            actions.append("add sides and totals — spread across eight prop "
                           "markets still reads as an all-props account, and "
                           "main lines are where a book has room to take you on")
        if sharp_stakes > 0.5:
            actions.append("round stakes to the nearest $5 — precision costs "
                           "almost nothing in EV and reads recreational")
        if len(by_book) == 1:
            actions.append("open a second book and split volume — one outlet "
                           "is a single point of failure")
        if score > 65:
            actions.append("route your most limit-prone plays (props with big "
                           "CLV) to the book you care least about keeping")
        books.append({
            "book": book, "bets": len(rows), "score": score, "band": band,
            "beat_close_rate": round(beat_rate, 3) if beat_rate is not None else None,
            "avg_clv": round(sum(clvs) / len(clvs), 3) if clvs else None,
            "top_market": top_market, "concentration": round(conc, 3),
            "prop_share": round(prop_share, 3),
            "sharp_stake_rate": round(sharp_stakes, 3),
            "drivers": drivers, "actions": actions})
    books.sort(key=lambda d: -d["score"])
    return {
        "books": books,
        "disclaimer": ("Inferred from your own journaled betting patterns — "
                       "an estimate of how sharp your action looks, not "
                       "knowledge of any sportsbook's actual risk rules."),
        # Shipped WITH the score, not buried under it. Four of the seven
        # signals a risk desk uses are not in this number, and a reader who
        # can't see which ones will over-trust it.
        "blind_spots": [{"signal": s, "why": w} for s, w in HEALTH_BLIND_SPOTS],
    }


def longshot_report(conn, since: str | None = None) -> dict:
    """The Long Shots scoreboard.

    The W-L / ROI record covers ONLY ``category='longshot'`` — the board's
    actual picks. The calibration readout ("does the model's claimed
    probability beat the books' implied?") deliberately spans picks AND the
    watchlist: it is a measurement, and the bigger sample is what made the
    MIN_MODEL_PROB quartile analysis possible. The watchlist's own burn
    rate is reported separately so nobody mistakes it for a record.
    """
    # `since` REACHES EVERY QUERY, not just the signature. This accepted
    # the parameter and used it nowhere — so the epoch-scoped export
    # shipped an all-time Long Shots record directly under the page's
    # "record shown from <epoch>" disclosure, the exact headline/panel
    # disagreement the 2026-08-23 "EVERYTHING" pass was for. Found in the
    # 2026-08-24 six-day review.
    win = " AND date >= ?" if since else ""
    wargs: tuple = (since,) if since else ()
    p = performance(conn, category="longshot", since=since)
    row = conn.execute(
        "SELECT COUNT(*) AS n, AVG(hit_prob) AS model_p, "
        "AVG(100.0 / (odds + 100.0)) AS implied_p, "
        "AVG(CASE WHEN status='won' THEN 1.0 ELSE 0.0 END) AS actual_p "
        "FROM bets WHERE category IN ('longshot', 'longshot_watch') "
        "AND status IN ('won','lost') AND odds > 0" + win, wargs).fetchone()
    p["calibration_n"] = row["n"] or 0
    p["avg_model_prob"] = round(row["model_p"], 4) if row["model_p"] is not None else None
    p["avg_implied_prob"] = round(row["implied_p"], 4) if row["implied_p"] is not None else None
    p["actual_hit_rate"] = round(row["actual_p"], 4) if row["actual_p"] is not None else None
    p["recent"] = recent_settled(conn, limit=15, category="longshot",
                                 since=since)
    # The watchlist sample, kept visibly apart: every real-priced homer on
    # the slate, graded at a nominal flat stake purely to tune the model.
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(status='won'), 0) AS w, "
        "COALESCE(SUM(pnl_units), 0) AS u, COALESCE(SUM(stake_units), 0) AS s "
        "FROM bets WHERE category='longshot_watch' "
        "AND status IN ('won','lost')" + win, wargs).fetchone()
    p["watch"] = {
        "graded": row["n"] or 0, "wins": row["w"] or 0,
        "net_units": round(row["u"], 2),
        "roi": round(row["u"] / row["s"], 4) if row["s"] else 0.0,
        # Open picks are not windowed: a pick is open NOW whatever day
        # it was journaled, and hiding pre-epoch open bets would make the
        # count disagree with the settle loop that still owes them.
        "open": conn.execute(
            "SELECT COUNT(*) FROM bets WHERE category='longshot_watch' "
            "AND status='open'").fetchone()[0],
    }
    # Which long-shot markets carry the bucket, and at what price. Average
    # odds matter here in a way they don't for the main record: a +250
    # board and a +900 board that both hit 12% are wildly different bets.
    row = conn.execute(
        "SELECT COUNT(*) n, AVG(odds) avg_odds, MIN(odds) min_odds, "
        "MAX(odds) max_odds FROM bets WHERE category='longshot' "
        "AND status IN ('won','lost')" + win, wargs).fetchone()
    p["avg_odds"] = round(row["avg_odds"]) if row["avg_odds"] is not None else None
    p["odds_range"] = ([row["min_odds"], row["max_odds"]]
                       if row["n"] else None)
    p["by_sport"] = {}
    for r in conn.execute(
            "SELECT sport, COUNT(*) n, SUM(status='won') w, "
            "COALESCE(SUM(pnl_units),0) u FROM bets WHERE category='longshot' "
            "AND status IN ('won','lost')" + win + " GROUP BY sport", wargs):
        p["by_sport"][r["sport"]] = {"n": r["n"], "w": r["w"],
                                     "net_u": round(r["u"], 2)}
    return p


def open_by_day(conn, today: str) -> list[dict]:
    """Open picks grouped by slate date, newest first.

    "70 open" is never a useful number on its own: tonight's picks are
    supposed to be open, picks from a finished day are a symptom, and the
    two are indistinguishable in a total. Each entry carries ``stale``
    (the day is over, so these should already have graded) so a caller can
    say which kind it is looking at, and ``gradeable_by_date`` — whether a
    per-date results pass could close anything here at all, which is what
    keeps `--settle all` out of days holding nothing but exchange
    contracts.
    """
    # Per ROW, not a GROUP BY: a prediction-market contract's slate date
    # is the day the desk recommended it, and the day its event actually
    # happens is encoded in the ticker. Deciding "this day is over" off
    # the journal date alone marked twelve future NFL days stale in
    # August and sent `--settle all` back through every one of them,
    # nightly, finding `0 game(s)` each time.
    by_day: dict = {}
    ripe: dict = {}          # something here really should have graded
    gradeable: dict = {}     # a per-DATE results pass could grade something
    for r in conn.execute(
            "SELECT date, category, player FROM bets WHERE status='open'"):
        d = r["date"] or ""
        cat = r["category"] or "main"
        counts = by_day.setdefault(d, {})
        counts[cat] = counts.get(cat, 0) + 1
        if cat == "predmarket":
            # Graded by resolve_predmarket against exchange settlements —
            # a date ingest has nothing to offer it, ever. An undated
            # ticker still counts as ripe so it cannot hide.
            ev = predmarket_event_date(r["player"])
            if ev is None or ev < today:
                ripe[d] = True
        else:
            gradeable[d] = True
            if bool(d) and d < today:
                ripe[d] = True
    return [{"date": d, "counts": by_day[d], "total": sum(by_day[d].values()),
             "stale": bool(d) and d < today and ripe.get(d, False),
             "gradeable_by_date": gradeable.get(d, False)}
            for d in sorted(by_day, reverse=True)]


#: The reasons an open bet has not graded, in the order that matters for
#: acting on them. READY is the diagnostic one: a ready bet still open
#: means the settle PASS is not running — not that results are missing.
OPEN_REASONS = {
    "ready": "ready to grade — results are in; a settle pass will close it",
    "waiting": "waiting — the game is not confirmed final yet",
    "exchange": "a prediction-market contract — it grades when the "
                "exchange settles it and the next desk build reads that "
                "settlement. There is nothing to ingest",
    "no_results": "no results for this date in the history DB yet — "
                  "ingest has not reached it",
    "no_statline": "game is in, but this player has no stat line "
                   "(did not play, or a name the feed spells differently)",
    "no_grade_source": "this market has no automatic results source right "
                       "now (e.g. NFL/CFB preseason player props)",
}


def explain_open(conn, hist_conn, today: str | None = None) -> dict:
    """Say, per open bet, WHY it has not settled — reusing the settler's
    own lookups so the answer matches what a real settle pass would find.

    This exists because "the bets aren't settling" has three completely
    different fixes and they are indistinguishable from the record page:

      * READY bets prove the settle PASS is not running (the server is not
        up, or the nightly job was never installed) — nothing is wrong with
        the data, it just needs `--settle`.
      * NO_RESULTS bets mean the results ingest has not reached that date —
        a feed/reachability problem, not a settle problem.
      * NO_STATLINE / NO_GRADE_SOURCE bets cannot grade from what exists:
        a DNP, a name mismatch, or a market (preseason props) with no feed.

    Never raises: a diagnostic that can crash is one more thing to debug.
    """
    import datetime as _dt
    today = today or _dt.date.today().isoformat()
    from .sources.oddsapi import normalize_name

    def _reason(b) -> str:
        try:
            where, wargs = _hist_where(b)
            if b["market"] in GAME_MARKETS:
                rows, _ = _game_bet_evidence(hist_conn, b, where, wargs)
                # A game ROW is not a game RESULT: the schedule ingest
                # writes W1 rows in August with NULL scores, and calling
                # those "ready" sent Ethan to --settle all for bets whose
                # games are a month out — the tool contradicting itself
                # in back-to-back commands. Finals only.
                final = [r for r in rows
                         if r["home_score"] is not None
                         and r["away_score"] is not None]
                if final:
                    return "ready"
                if rows:
                    return "waiting"
                # No game row at all. Preseason team markets DO have
                # finals, so the only "no grade source" case here is a
                # genuinely missing feed date — report it as such.
                return ("no_results" if not _day_was_ingested(
                    hist_conn, where, wargs) else "no_statline")
            # Player market: mirror settle_from_history's join exactly.
            rows = hist_conn.execute(
                f"SELECT value FROM player_game_logs WHERE {where} "
                f"AND market=? AND player=?",
                (*wargs, b["market"], b["player"])).fetchall()
            if not rows:
                target = normalize_name(b["player"])
                rows = [c for c in hist_conn.execute(
                            f"SELECT player FROM player_game_logs "
                            f"WHERE {where} AND market=?",
                            (*wargs, b["market"]))
                        if normalize_name(c["player"]) == target]
            if rows:
                return ("waiting" if _too_early_to_grade(
                    hist_conn, where, wargs, rows[0], b["date"]) else "ready")
            # Nothing logged for this player. Distinguish "day not ingested"
            # from "day is in, player absent" — different fixes. "In" means
            # the day has ANY logs for this sport/period (games-table
            # presence is not enough — whole seasons of player logs were
            # backfilled before the games table existed).
            day_in = bool(hist_conn.execute(
                f"SELECT 1 FROM player_game_logs WHERE {where} LIMIT 1",
                wargs).fetchone()) or _day_was_ingested(hist_conn, where,
                                                        wargs)
            if day_in:
                # NFL/CFB preseason player props have no weekly-stats source
                # until the regular season; name that rather than blaming a
                # DNP the feed would actually have logged.
                if (b["sport"] in ("nfl", "cfb")
                        and "pre" in (b["date"] or "").lower()):
                    return "no_grade_source"
                return "no_statline"
            return "no_results"
        except Exception:                                       # noqa: BLE001
            return "no_results"

    buckets: dict = {k: [] for k in OPEN_REASONS}
    for b in conn.execute("SELECT * FROM bets WHERE status='open'").fetchall():
        # A Kalshi contract is in its own bucket for the same reason it is
        # in why_open's: `_reason` below runs the history lookups a settle
        # pass runs, and none of them can say anything true about a market
        # the EXCHANGE grades. Sent through them, 130 healthy contracts
        # came out as NO_RESULTS — with "check the feeds" as the advice.
        pm = (b["category"] if "category" in b.keys() else "") == "predmarket"
        ev = predmarket_event_date(b["player"]) if pm else None
        item = {"id": b["id"], "sport": b["sport"], "date": b["date"],
                "market": b["market"], "player": b["player"],
                "side": b["side"] if "side" in b.keys() else None,
                "line": b["line"] if "line" in b.keys() else None,
                # For a contract, "the day is over" means the EVENT is
                # over — its date column is the day the desk picked it.
                "stale": (bool(ev) and ev < today) if pm
                else bool(b["date"]) and (b["date"] or "") < today}
        if pm:
            item["event_date"] = ev
        buckets["exchange" if pm else _reason(b)].append(item)
    return {
        "total": sum(len(v) for v in buckets.values()),
        "buckets": {k: v for k, v in buckets.items()},
        "counts": {k: len(v) for k, v in buckets.items()},
    }


def unstaked_scorecard(conn) -> dict:
    """Were the 0.00-unit picks actually profitable? Measure, don't argue.

    They win often — that's not the question. The question is whether they
    won often enough to beat the prices they were offered at. This reports
    the realized hit rate against the average break-even those odds imply,
    plus the flat-stake P&L they would have produced."""
    rows = conn.execute(
        "SELECT odds, status FROM bets WHERE category='main' "
        "AND (stake_units IS NULL OR stake_units <= 0) "
        "AND status IN ('won','lost')").fetchall()
    if not rows:
        return {"n": 0}
    wins = sum(1 for r in rows if r["status"] == "won")
    be = sum(1.0 / american_to_decimal(r["odds"]) for r in rows) / len(rows)
    net = sum((american_to_decimal(r["odds"]) - 1.0) if r["status"] == "won"
              else -1.0 for r in rows)
    hit = wins / len(rows)
    return {"n": len(rows), "wins": wins, "losses": len(rows) - wins,
            "hit_rate": round(hit, 4), "break_even": round(be, 4),
            "edge_pts": round((hit - be) * 100, 2),
            "roi": round(net / len(rows), 4)}


def resize_unstaked(conn, stake_units: float = 0.1) -> int:
    """Give already-journaled zero-stake picks a flat stake and real P&L.

    A grading bug once shipped picks the vig had already eaten, and Kelly
    sized them at 0.00 units — so they sat in the journal as wins and
    losses worth nothing, and the profit (or loss) they actually produced
    never showed on the record. This sizes every one of them at a flat
    ``stake_units`` and recomputes P&L from the price and result, exactly
    like the long-shot bucket: units only, no dollars, measurement not
    a claim that money was placed."""
    rows = conn.execute(
        "SELECT id, odds, status FROM bets "
        "WHERE category='main' AND (stake_units IS NULL OR stake_units <= 0)"
    ).fetchall()
    n = 0
    for r in rows:
        if r["status"] == "won":
            pnl = round((american_to_decimal(r["odds"]) - 1.0) * stake_units, 4)
        elif r["status"] == "lost":
            pnl = -stake_units
        else:
            pnl = 0.0            # push, or still open
        conn.execute(
            "UPDATE bets SET stake_units=?, pnl_units=? WHERE id=?",
            (stake_units, pnl if r["status"] in ("won", "lost", "push") else None,
             r["id"]))
        n += 1
    conn.commit()
    return n


def recompute_bankroll(conn) -> float:
    """Rebuild the bankroll from the main journal's realized dollars.

    The running value is advanced bet-by-bet as things settle, so any
    repair that moves or re-sizes rows leaves it stale. This restates it
    from what the record actually says."""
    start = float(get_cfg(conn, "starting_bankroll"))
    total = conn.execute(
        "SELECT COALESCE(SUM(pnl_dollars), 0) FROM bets WHERE category='main' "
        "AND status IN ('won','lost','push')").fetchone()[0] or 0.0
    val = round(start + total, 2)
    set_cfg(conn, "bankroll", val)
    return val


def split_watch_from_longshots(conn) -> int:
    """Repair: move watchlist rows out of the Long Shots record bucket.

    The journal used to put the ENTIRE watchlist — every real-priced homer
    on the slate, often 100+ names a night — into ``category='longshot'``
    alongside the (max three) picks, so the Long Shots W-L was scoring the
    dart board. Watchlist rows are identifiable by their grade ('Watch';
    picks always carry a real grade) and move to ``longshot_watch`` with
    their settled P&L intact. Safe to run every build — a no-op once clean.
    """
    rows = conn.execute(
        "SELECT id, sport, date, player, market FROM bets "
        "WHERE category='longshot' AND grade='Watch'").fetchall()
    moved = 0
    for r in rows:
        dup = conn.execute(
            "SELECT id FROM bets WHERE sport=? AND date=? AND player=? "
            "AND market=? AND category='longshot_watch'",
            (r["sport"], r["date"], r["player"], r["market"])).fetchone()
        if dup:
            conn.execute("DELETE FROM bets WHERE id=?", (r["id"],))
        else:
            conn.execute(
                "UPDATE bets SET category='longshot_watch' WHERE id=?",
                (r["id"],))
        moved += 1
    conn.commit()
    return moved


def move_longshots_out_of_main(conn, stake_units: float = 0.1) -> int:
    """Relocate already-journaled long-shot markets into their own bucket.

    Home-run and anytime-TD props that cleared the main board were being
    journaled twice — once in the headline record, once in the long-shot
    bucket. The headline record is supposed to describe the picks the
    model stands behind, not a board of plus-money darts, so the main
    copies are moved out (or dropped when the long-shot copy already
    exists) and the bankroll is restated."""
    marks = ",".join("?" for _ in LONGSHOT_MARKETS)
    rows = conn.execute(
        f"SELECT * FROM bets WHERE category='main' AND market IN ({marks})",
        tuple(LONGSHOT_MARKETS)).fetchall()
    moved = 0
    for r in rows:
        dup = conn.execute(
            "SELECT id FROM bets WHERE sport=? AND date=? AND player=? "
            "AND market=? AND category='longshot'",
            (r["sport"], r["date"], r["player"], r["market"])).fetchone()
        if dup:
            conn.execute("DELETE FROM bets WHERE id=?", (r["id"],))
        else:
            if r["status"] == "won":
                pnl = round((american_to_decimal(r["odds"]) - 1.0) * stake_units, 4)
            elif r["status"] == "lost":
                pnl = -stake_units
            elif r["status"] == "push":
                pnl = 0.0
            else:
                pnl = None                    # still open
            conn.execute(
                "UPDATE bets SET category='longshot', stake_units=?, "
                "stake_dollars=0, pnl_units=?, pnl_dollars=0 WHERE id=?",
                (stake_units, pnl, r["id"]))
        moved += 1
    conn.commit()
    recompute_bankroll(conn)
    return moved


# Every board that journals a bet. Polymarket is deliberately absent: its
# flags are not wagers in this ledger, they are graded in
# `predmarkets.json` by their own report card, and folding a
# prediction-market flag rate into a betting P&L would make both numbers
# mean nothing.
TRACKED_SPORTS = ("nfl", "cfb", "mlb", "nba", "wnba", "ufc")


def sport_report(conn, sport: str,
                 since: str | None = None) -> dict:
    """One sport's whole record — the tuning view.

    The combined page answers "is the system making money", which is the
    question an owner asks. This answers "is THIS model any good", which
    is the question the next change to it depends on, and the aggregate
    actively hides it: a baseball model reading four points hot and a
    football model reading four points cold average to a perfect
    calibration line nobody should trust.
    """
    perf = performance(conn, sport, since=since)
    return {
        "sport": sport,
        "overall": perf,
        "curve": pnl_curve(conn, sport, since=since),
        "recent": recent_settled(conn, 20, sport=sport, since=since),
        "calibration": calibration(conn, sport=sport),
        "calibration_era": calibration(conn, since=MODEL_ERAS[-1]["start"],
                                       sport=sport),
        # Enough graded bets for the numbers above to mean anything. Stated
        # rather than implied: a 3-1 record is not a 75% win rate, and a
        # page that shows one without the other invites exactly that read.
        "thin": perf.get("settled", 0) < MIN_GRADED_FOR_SIGNAL,
        "min_graded": MIN_GRADED_FOR_SIGNAL,
    }


# Below this, a per-sport record is a small sample wearing a percentage.
# Not a gate on showing it — hiding your own results is its own dishonesty
# — but the page says so next to every rate it prints.
MIN_GRADED_FOR_SIGNAL = 30


def _parlay_report(conn) -> dict:
    """The parlay bucket, or an empty one. Imported here rather than at the
    top so parlayledger stays a leaf module — it reads this file's tables and
    reuses its CLV, and a top-level import either way would be a cycle."""
    try:
        from . import parlayledger
        return parlayledger.report(conn)
    except Exception:          # never let the parlay bucket break the record
        return {"graded": 0, "open": 0, "probation": True}


def _edge_rows(conn, category: str = "main",
               since: str | None = None) -> list[dict]:
    """Settled bets in the shape the information test wants."""
    q = ("SELECT status, hit_prob, odds FROM bets WHERE status IN "
         "('won','lost') AND category=? AND stake_units > 0")
    args: list = [category]
    if since:
        q += " AND date >= ?"
        args.append(since)
    return [dict(r) for r in conn.execute(q, args)]


def record_edge_run(conn, category: str = "main",
                    since: str | None = None) -> dict | None:
    """Measure and bank the information test. Called from the settle, so
    the series grows on its own.

    The measurement that made this worth automating took a terminal and a
    person remembering to run it — which in practice means it gets run
    when something feels wrong, exactly the moment least able to tell a
    real change from the mood that prompted the check.
    """
    from . import edgehistory
    rows = _edge_rows(conn, category, since=since)
    return edgehistory.record(conn, rows, category=category,
                              clv=_edge_clv(conn, category, since))


def _edge_clv(conn, category: str = "main",
              since: str | None = None) -> dict | None:
    """The panel's second instrument: mean price CLV and its error.

    One implementation, used by the banked run AND by the live snapshot —
    they print the same "over N bets with a close" sentence, and two
    copies of this arithmetic is two chances for those N to differ.
    """
    try:
        q = ("SELECT side, odds, closing_odds FROM bets WHERE status IN "
             "('won','lost') AND category=?")
        args: list = [category]
        if since:
            q += " AND date >= ?"
            args.append(since)
        clvs = [c for c in (_bet_price_clv(b) for b in conn.execute(q, args))
                if c is not None]
        if not clvs:
            return None
        mean = sum(clvs) / len(clvs)
        var = (sum((c - mean) ** 2 for c in clvs) / (len(clvs) - 1)
               if len(clvs) > 1 else 0.0)
        return {"clv_mean": mean, "clv_se": (var / len(clvs)) ** 0.5,
                "clv_n": len(clvs)}
    except Exception:                                       # noqa: BLE001
        return None


def _edge_snapshot(conn, category: str = "main",
                   since: str | None = None) -> dict | None:
    """The information test as it stands RIGHT NOW over the displayed window.

    MEASURED FRESH RATHER THAN READ BACK. Ethan, 2026-08-23, pointing at
    the panel's header: "fix where it says 500 bets" — it read "558
    settled bets" beside a 431-pick record, because this returned the
    last BANKED run and every banked run was measured over the whole
    journal.

    Banking is still right for the trend: each stored run is what the
    test said on the night it ran, and rewriting those would be inventing
    a history. But the headline number is a statement about the record on
    screen, so it is computed over the same bets that record covers.
    """
    from . import edgehistory
    if not since:
        return edgehistory.latest(conn, category)
    rows = _edge_rows(conn, category, since=since)
    m = edgehistory.measure(rows)
    if m is None:
        return None            # all winners or all losers: AUC undefined
    m["category"] = category
    # The denominator the "Data quality" tile needs: won/lost staked rows
    # in this window — the rows the test COULD use. measure() then drops
    # any without a stored probability, so eligible - n is exactly "how
    # many settled picks have no probability". The tile used to derive
    # this from overall.settled instead, which counts PUSHES — so one
    # push made the panel read "Partial — 1 settled pick(s) have no
    # stored probability" forever, a false sentence about data integrity
    # on the panel whose whole job is being believed (2026-08-24 review).
    m["eligible"] = len(rows)
    for k, v in (_edge_clv(conn, category, since) or {}).items():
        m[k] = v
    return m


def _edge_series(conn, category: str = "main") -> list[dict]:
    from . import edgehistory
    return edgehistory.series(conn, category)


def export_json(conn, path) -> None:
    """Write the journal's performance to a JSON file the website renders.

    Called after every settle, so the Track Record page always reflects the
    latest graded picks without anyone touching a terminal."""
    import datetime as _dt
    import json as _json
    from pathlib import Path as _Path
    # THE PUBLIC RECORD STARTS AT RECORD_EPOCH; the journal does not.
    # Everything before it is still in the database, still graded, still
    # training the model — see the constant for the whole argument and
    # the conditions it is fair under. `all_time` below is the unscoped
    # answer, exported beside the scoped one so the page can show what it
    # is leaving out rather than quietly leaving it out.
    since = RECORD_EPOCH
    # ONE SCAN PER WINDOW. This ran performance(conn) three times — once
    # for all_time.overall and twice more inside hidden_settled — and
    # performance(conn, since=...) twice, each a full pass over every
    # settled bet, on a path the settle loop executes every five minutes
    # on a one-core box. show_epoch() already did it the cheap way.
    allp = performance(conn)
    scoped = performance(conn, since=since)
    out = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "record_epoch": since,
        # The reader's word for every market id, shipped rather than
        # retyped in the front end. The Record page's splits table had a
        # hand-kept copy of this and it had drifted: it spelled the
        # basketball markets `points`/`rebounds`/`assists` while the
        # journal stores `pts`/`reb`/`ast`, so those rows rendered raw
        # beside "Total Bases" and "Outs Recorded". See engine/markets.
        "market_words": _markets.words(),
        "all_time": {
            "overall": allp,
            "curve_from": (pnl_curve(conn) or [{}])[0].get("date"),
            # The count that makes the disclosure concrete: "N settled
            # picks before this date are journaled and still train the
            # model" is a fact a reader can weigh. "Some" is not.
            "hidden_settled": max(0, allp["settled"] - scoped["settled"]),
        },
        "overall": scoped,
        "mlb": performance(conn, "mlb", since=since),
        "nfl": performance(conn, "nfl", since=since),
        "curve": pnl_curve(conn, since=since),
        "recent": recent_settled(conn, since=since),
        "model_eras": era_report(conn),
        "longshots": longshot_report(conn, since=since),
        "stale_flags": stale_report(conn, since=since),
        "form_sampler": form_report(conn, since=since),
        "loose_sampler": loose_report(conn, since=since),
        # THE PREDICTION DESK — Kalshi paper book (sports cross-model +
        # weather-vs-forecast), earning its stakes on the same terms as
        # every other unproven bucket. See docs/PREDICTION_DESK.md.
        "predmarket": predmarket_report(conn, since=since),
        "ufc_record": ufc_report(conn, since=since),
        # IS THERE AN EDGE AT ALL — the 2026-08-09 finding, kept live
        # rather than re-derived by hand. `edge_now` is the latest run,
        # `edge_trend` the series. See docs/THE_INFORMATION_TEST.md.
        "edge_now": _edge_snapshot(conn, since=since),
        "edge_trend": _edge_series(conn),
        # THE PAPER BOOK as a summary. Note that it is not a book kept
        # OUTSIDE the record: `overall` above defaults to BOOK, which is
        # ("main", "paper"), so these rows are already in every headline
        # number. This line exists so the export still says how much of
        # that pool was staked on paper.
        "paper": performance(conn, category="paper", since=since),
        "paper_mode": paper_mode(conn),
        # `paper_recent` — the hundred paper rows themselves — was dropped
        # on 2026-08-20 along with the Record page panel that was its only
        # reader (Ethan: "we dont really need that area any more").
        #
        # Say the consequence plainly rather than let it be discovered: no
        # page now LISTS an individual paper bet, because `recent_settled`
        # defaults to category="main". Their totals are unaffected — every
        # headline number above pools both books — but the row-by-row
        # receipts below them are money rows only. If those rows are ever
        # wanted back, the honest fix is to widen the main receipts list to
        # BOOK rather than to re-add a second list beside it, since the
        # curve those receipts sit under already counts them.
        # Per-sport, so each model can be tuned on its own evidence rather
        # than on the average of six.
        # SCOPED, and the first draft of this was not — which is the
        # whole bug Ethan hit. "the record page still shows us down 20
        # units … and thats for every spot on the page." The per-sport
        # tabs read THIS block, so leaving it all-time meant the headline
        # said one thing and every tab beside it said another.
        #
        # The reasoning that left it unscoped was wrong on its own terms:
        # this is the WEBSITE's payload and nothing else reads it. The
        # tuning that needs every row — the miner, the calibration fits,
        # the era split — runs in Python against the database, which is
        # untouched. "we will keep all the other data that we dont
        # display for ourselves" is exactly right, and the database is
        # where that data lives.
        "by_sport": {sp: sport_report(conn, sp, since=since)
                     for sp in TRACKED_SPORTS},
        "tracked_sports": list(TRACKED_SPORTS),
        "calibration": calibration(conn, since=since),
        # The same chart scoped to the CURRENT model era — the all-time
        # chart is dominated by picks from gates that no longer exist.
        "calibration_era": calibration(conn, since=MODEL_ERAS[-1]["start"]),
        # By market and by horizon: an aggregate hides a model that is hot
        # on one market and cold on another, which is the pair of errors
        # most worth finding.
        "calibration_splits": calibration_splits(conn, since=since),
        # The selection haircut. Sits beside the calibration chart because
        # it is the same question asked of a different population: that
        # chart grades the probability surface, this grades the SUBSET we
        # bet, and the gap between them is what selecting on our own
        # estimation error costs. Emitted even when nothing is applied —
        # "measured and calibrated" and "never measured" have to be
        # distinguishable on the page.
        "selection_haircut": _selection_haircut_block(),
        # Sealed first, so the published head covers everything journaled up
        # to this export rather than lagging it by a run.
        "forecast_log": (seal_forecasts(conn), verify_forecast_log(conn))[1],
        # The learning loop, rendered: nightly temperatures, self-closed
        # markets, and the sweep trend. Own history connection, own guard —
        # a missing stats DB (CI, fresh clone) yields an empty block, never
        # a failed export.
        "self_tuning": _self_tuning_block(),
        # The blind-spot miner: slices of the record whose stated
        # probabilities systematically missed, under false-discovery
        # control. Mined fresh from THIS journal so the page always shows
        # the record it sits on; the persisted store the pick-time veto
        # reads is refreshed at settle time.
        "loss_patterns": _loss_patterns_block(conn),
        # The hypothesis lab: LLM-proposed slice intersections and the
        # tribunal's verdicts. Read from the store — the export never
        # calls an API; the paid propose step is CLI-only.
        "hypothesis_lab": _hypothesis_lab_block(),
        "prereg": _prereg_block(conn),
        # The prose lanes: the nightly postmortem and the weekly model
        # brief, read from their stores — the paid calls happen in the
        # settle pass (capped) and the CLI, never here.
        "prose": _prose_block(),
        # The record re-sized on today's staking scale — receipts above
        # stay receipts; this answers "what WOULD it read" without ever
        # editing a settled row.
        "restated": {"overall": restated_performance(conn, since=since),
                     "by_sport": {sp: restated_performance(conn, sp,
                                                           since=since)
                                  for sp in TRACKED_SPORTS}},
        "account_health": account_health(conn, since=since),
        # How much of the record has a real closing line behind it — the
        # honest prerequisite for anything that wants to reason from CLV.
        "clv_coverage": clv_coverage(conn, since=since),
        # §13: the parlay record is reported SEPARATELY and never blended.
        # Its own key, its own tables, its own notional — nothing above this
        # line moves when a ticket settles.
        "parlays": _parlay_report(conn),
    }
    p = _Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Atomic: the Record page polls this file while every settle pass
    # rewrites it — an in-place write hands a poll that lands mid-write
    # a truncated JSON (the same race gate.publish and the profiles
    # already guard against).
    import os as _os
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(_json.dumps(out, indent=2))
    _os.replace(tmp, p)
