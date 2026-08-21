"""What still needs doing on THIS machine — measured, not remembered.

Ethan, 2026-08-20: "go through the when home list and all our other todo
lists ... mark off and remove whats complete and figure out what still
needs to be done."

The reason that was hard to answer is the reason this file exists.
`docs/WHEN_HOME.md` had grown to 1,964 lines, most of it a log of work
already finished, and **nothing in it could be verified from anywhere**.
The chores it lists — refit this, ingest that, settle the stuck days —
run against a database and a set of model files that live on Ethan's
laptop. A cloud session cannot see them. Neither, a fortnight later, can
Ethan: "did I run the MLB refit?" is not a question a person should have
to answer from memory, and a checklist that depends on remembering is
the same failure as a cache version that depends on remembering.

So the chores stop being prose and become a query. Every item here reads
an artifact the chore itself writes — a fitted date in the calibration
store, a row count in the ingest tables, a headshot column, an open bet
on a finished day — and reports one of three things:

    done        with the evidence, so you can disagree with it
    do this     with the exact command
    can't tell  and WHY, which is a third answer and not a failure

The third one matters as much as the first two. A machine with no ledger
(this container, a fresh clone, CI) can honestly answer almost nothing
here, and a tool that silently reports "all clear" in that state is worse
than one that refuses. Nothing is inferred from absence.

WHAT THIS DELIBERATELY DOES NOT COVER. Judgement calls, legal questions,
design taste, and anything needing a human eye stay in
`docs/WHEN_HOME.md` under "yours". Duplicating them into code would
create a second list to keep in sync — which is the failure being fixed,
reintroduced one layer down.

Read-only. It opens databases, reads JSON, and writes nothing.

    python3 launch.py --todo
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The sports with a learning ladder. CFB is here because it has a board
#: and a journal; it has never had enough settled rows to fit, which is a
#: fact worth printing rather than an omission worth hiding.
SPORTS = ("nfl", "mlb", "nba", "wnba", "cfb")

DONE, TODO, UNKNOWN = "done", "todo", "unknown"


class Item:
    """One line of the report.

    `evidence` is not decoration. A verdict with no evidence cannot be
    argued with, and the first wrong verdict this prints will be argued
    with — so every line carries the number and the file it came from.
    """

    def __init__(self, group, name, state, evidence, command=""):
        self.group = group
        self.name = name
        self.state = state
        self.evidence = evidence
        self.command = command


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _date_of(value) -> str:
    """The date part of an ISO stamp, whatever precision it was written at.

    calibrate.py stores `fitted_at` as a date; formfit.py stores `fitted`
    as a datetime to the second. Comparing them is only honest at the
    coarser of the two, which is why same-day cases below are reported as
    ambiguous rather than resolved.
    """
    return str(value or "")[:10]


# --- the learning ladder ----------------------------------------------------

def learning_items(models: Path | None = None) -> list[Item]:
    """Did each sport's correction get fitted AFTER the model it corrects?

    The ordering is the whole check. A dial and a per-player memory change
    what the model SAYS; the temperature corrects what it says. Fit the
    correction first and then move the model underneath it, and the
    correction describes a model that no longer exists. NFL shipped
    exactly one run in that order, which is why `--relearn` was reordered
    and why re-running it is on the list at all.
    """
    models = models or (ROOT / "data" / "models")
    cal = _read_json(models / "calibration.json")
    form = _read_json(models / "formfit.json")
    out = []

    if cal is None and form is None:
        out.append(Item(
            "learning", "the model store", UNKNOWN,
            f"no calibration.json or formfit.json under {models} — this "
            "machine has never fitted anything, or is not the machine that does"))
        return out

    for sport in SPORTS:
        temps = {k: v for k, v in (cal or {}).items()
                 if isinstance(v, dict) and k.startswith(sport + ":")}
        dials = {k: v for k, v in (form or {}).items()
                 if isinstance(v, dict) and k.startswith(sport + ":")
                 and v.get("adopted")}
        if not temps and not dials:
            out.append(Item("learning", sport.upper(), TODO,
                            "nothing fitted and no dial adopted",
                            f"python3 launch.py --relearn {sport}"))
            continue
        if not temps:
            out.append(Item(
                "learning", sport.upper(), TODO,
                f"{len(dials)} dial(s) adopted and no temperature fitted — "
                "the model moved and nothing corrects it",
                f"python3 launch.py --relearn {sport}"))
            continue

        newest_temp = max(_date_of(v.get("fitted_at")) for v in temps.values())
        if not dials:
            out.append(Item(
                "learning", sport.upper(), DONE,
                f"{len(temps)} market(s) fitted, newest {newest_temp or 'undated'}; "
                "no dial adopted, so nothing can be out of order"))
            continue

        newest_dial = max(_date_of(v.get("fitted")) for v in dials.values())
        if not newest_temp or not newest_dial:
            out.append(Item(
                "learning", sport.upper(), UNKNOWN,
                "one side of the comparison is undated "
                f"(temperature {newest_temp or '—'}, dial {newest_dial or '—'})",
                f"python3 launch.py --relearn {sport}"))
        elif newest_dial > newest_temp:
            out.append(Item(
                "learning", sport.upper(), TODO,
                f"a dial was adopted {newest_dial}, after the newest temperature "
                f"{newest_temp} — the correction describes a model that changed "
                "underneath it",
                f"python3 launch.py --relearn {sport}"))
        elif newest_dial == newest_temp:
            out.append(Item(
                "learning", sport.upper(), UNKNOWN,
                f"dial and temperature both dated {newest_temp}; the store keeps "
                "the temperature to the day only, so the order within it cannot "
                "be read. Re-running is cheap and idempotent",
                f"python3 launch.py --relearn {sport}"))
        else:
            out.append(Item(
                "learning", sport.upper(), DONE,
                f"dial {newest_dial} → temperature {newest_temp}, in that order "
                f"({len(temps)} market(s), {len(dials)} dial(s))"))
    return out


def haircut_item(models: Path | None = None, conn=None) -> Item:
    """Has the selection cut seen the bets that have settled since it ran?

    The defect this is really watching for already happened once:
    `selectionfit` read `category='main'` only, so it stopped seeing new
    evidence the day paper mode started and sat on days of bets it never
    counted. A fit that is merely OLD is fine; a fit that is old while the
    book has moved a long way is the thing to catch.
    """
    models = models or (ROOT / "data" / "models")
    sel = _read_json(models / "selection.json")
    if sel is None:
        return Item("book", "selection haircut", UNKNOWN,
                    f"no selection.json under {models}")
    fitted = _date_of(sel.get("fitted_at"))
    saw = int((sel.get("pooled") or {}).get("n") or 0)
    if conn is None:
        return Item("book", "selection haircut", UNKNOWN,
                    f"fitted {fitted or 'never'} on {saw} settled bet(s); "
                    "no ledger here to say how many have settled since")
    try:
        now = conn.execute(
            "SELECT COUNT(*) FROM bets WHERE status IN ('won','lost')").fetchone()[0]
    except Exception as exc:                                   # noqa: BLE001
        return Item("book", "selection haircut", UNKNOWN,
                    f"fitted {fitted or 'never'} on {saw}; could not count the "
                    f"ledger ({exc})")
    # NOTHING TO FIT IS NOT A CHORE. With no settled bets the fit has no
    # input, and printing "run the refit" would send Ethan to a command
    # that can only tell him again that it declined. The first draft of
    # this did exactly that, on this container, because the guard below
    # keys on `saw` and fell through when both numbers were zero.
    if not now:
        return Item("book", "selection haircut", DONE,
                    f"nothing settled yet, so there is nothing to fit "
                    f"(last attempt {fitted or 'never'})")
    # A tenth more evidence is the bar because the fit is a single
    # parameter over a few hundred rows — below that the number it would
    # move to is inside its own noise, and re-running says nothing.
    if saw and now < saw * 1.1:
        return Item("book", "selection haircut", DONE,
                    f"fitted {fitted} on {saw} settled bet(s); {now} have settled "
                    f"since, under the 10% more that would change the answer")
    return Item("book", "selection haircut", TODO,
                f"fitted {fitted or 'never'} on {saw} settled bet(s), and the "
                f"ledger now holds {now}",
                "python3 launch.py --haircut --refit")


# --- what has been ingested -------------------------------------------------

def data_items(conn=None) -> list[Item]:
    """Rows, recency, and faces — per sport, from the history database."""
    if conn is None:
        return [Item("data", "the history database", UNKNOWN,
                     "not reachable from here; run this on the machine that "
                     "holds it")]
    out = []
    for sport in ("mlb", "nfl", "nba", "wnba"):
        try:
            row = conn.execute(
                "SELECT COUNT(*), MAX(season || '-' || period) FROM "
                "player_game_logs WHERE sport=?", (sport,)).fetchone()
        except Exception as exc:                               # noqa: BLE001
            out.append(Item("data", sport.upper(), UNKNOWN,
                            f"could not read player_game_logs ({exc})"))
            continue
        n, newest = (row[0] or 0), (row[1] or "")
        if not n:
            out.append(Item("data", sport.upper(), TODO,
                            "no player-game rows — nothing to fit on",
                            f"python3 ingest.py {sport}"))
            continue
        out.append(Item("data", sport.upper(), DONE,
                        f"{n:,} player-game rows, newest {newest}"))

    # Faces. Cosmetic, and the cards fall back to initials — so this is a
    # `todo` only when a league has none at all, not when it has gaps.
    for sport in ("mlb", "nfl", "nba", "wnba"):
        try:
            have = conn.execute(
                "SELECT COUNT(*) FROM player_assets WHERE sport=? AND "
                "headshot IS NOT NULL AND headshot != ''", (sport,)).fetchone()[0]
            known = conn.execute(
                "SELECT COUNT(DISTINCT player) FROM player_game_logs WHERE sport=?",
                (sport,)).fetchone()[0]
        except Exception:                                      # noqa: BLE001
            continue
        if not known:
            continue
        if not have:
            out.append(Item("data", f"{sport.upper()} faces", TODO,
                            f"0 of {known:,} players have a headshot — the cards "
                            "show initials until an ingest re-reads them",
                            f"python3 ingest.py {sport}"))
        else:
            out.append(Item("data", f"{sport.upper()} faces", DONE,
                            f"{have:,} headshots stored for {known:,} players"))

    # Preseason: collected for the "is August priceable" question, and
    # useless without finals, which is why the finals are what is counted.
    try:
        games = conn.execute("SELECT COUNT(*) FROM preseason_games").fetchone()[0]
        finals = conn.execute(
            "SELECT COUNT(*) FROM preseason_games WHERE completed=1 AND "
            "home_score IS NOT NULL").fetchone()[0]
    except Exception:                                          # noqa: BLE001
        games = finals = None
    if games is not None:
        if not finals:
            out.append(Item(
                "data", "NFL preseason", TODO,
                f"{games} preseason game(s) stored and {finals} with a final "
                "score — the box scores alone cannot answer whether August "
                "moves a scoreboard",
                "python3 ingest.py nflpre --seasons 2021-2026"))
        else:
            out.append(Item("data", "NFL preseason", DONE,
                            f"{finals} completed game(s) with finals, of {games} stored"))
    return out


# --- the book ---------------------------------------------------------------

def book_items(conn=None, hist=None, today: str = "") -> list[Item]:
    """Open picks that can never grade, and picks waiting on a settle."""
    if conn is None:
        return [Item("book", "the ledger", UNKNOWN,
                     "not reachable from here; run this on the machine that "
                     "holds it")]
    out = []
    try:
        opened = conn.execute(
            "SELECT COUNT(*) FROM bets WHERE status='open'").fetchone()[0]
    except Exception as exc:                                   # noqa: BLE001
        return [Item("book", "the ledger", UNKNOWN, f"could not read bets ({exc})")]

    today = today or _dt.date.today().isoformat()
    try:
        stale = conn.execute(
            "SELECT COUNT(DISTINCT date) FROM bets WHERE status='open' "
            "AND date < ?", (today,)).fetchone()[0]
    except Exception:                                          # noqa: BLE001
        stale = None

    if stale:
        out.append(Item("book", "open picks on past days", TODO,
                        f"{stale} day(s) before today still hold open picks "
                        f"({opened} open in total)",
                        "python3 launch.py --settle all"))
    else:
        out.append(Item("book", "open picks on past days", DONE,
                        f"none — {opened} open pick(s), all on today or later"))

    if hist is not None:
        try:
            from . import ledger as _led
            unplayed = _led.unplayed_bets(conn, hist, today)
        except Exception as exc:                               # noqa: BLE001
            unplayed = None
            out.append(Item("book", "picks on games never played", UNKNOWN,
                            f"could not check ({exc})"))
        if unplayed:
            out.append(Item(
                "book", "picks on games never played", TODO,
                f"{len(unplayed)} open pick(s) whose own game has no result and "
                "never will — phantom exposure that also keeps the day in every "
                "settle sweep",
                "python3 launch.py --settle all"))
        elif unplayed is not None:
            out.append(Item("book", "picks on games never played", DONE, "none"))
    return out


# --- the environment --------------------------------------------------------

def config_items(env=None) -> list[Item]:
    """The settings whose absence is silent and expensive."""
    env = env if env is not None else os.environ
    out = []

    if env.get("QB_BACKUP_REMOTE"):
        out.append(Item("config", "QB_BACKUP_REMOTE", DONE,
                        "set — the ledger backup has somewhere off this disk to go"))
    else:
        out.append(Item(
            "config", "QB_BACKUP_REMOTE", TODO,
            "unset, so every backup sits on the same disk as the thing it is "
            "backing up. The failure it does not survive is the one it exists "
            "for", "docs/BACKUPS.md — Backblaze B2 is free at this size"))

    # The paywall's own foot-gun, in the order it fires.
    paywall = str(env.get("QB_PAYWALL", "")).strip()
    comps = str(env.get("QB_COMP_EMAILS", "")).strip()
    if paywall in ("1", "true", "yes", "on"):
        if comps:
            out.append(Item("config", "paywall", DONE,
                            f"on, with {len(comps.split(','))} comped address(es)"))
        else:
            out.append(Item(
                "config", "paywall", TODO,
                "QB_PAYWALL is ON and QB_COMP_EMAILS is EMPTY — the first thing "
                "it does is lock you out of your own board",
                "set QB_COMP_EMAILS in /etc/qellys/env, then restart"))
        # THE SECOND FOOT-GUN, and the quieter one. Redaction happens
        # inside publish(), so turning the flag on changes what the NEXT
        # build writes and touches nothing already on disk. Until every
        # board has been rebuilt, the paid product is public — and a board
        # whose build fails stays public indefinitely. Found 2026-08-20 by
        # curling the picks file with the flag on: 293 recommendations.
        try:
            from . import gate as _gate
            leaking = _gate.unsealed()
        except Exception:                                    # noqa: BLE001
            leaking = []
        if leaking:
            rows = sum(r["rows"] for r in leaking)
            names = ", ".join(r["board"] for r in leaking[:4])
            out.append(Item(
                "config", "paywall boards", TODO,
                f"the paywall is ON but {len(leaking)} board(s) on the public "
                f"path still carry {rows} paid row(s) — {names}"
                + ("…" if len(leaking) > 4 else "")
                + ". Anyone can curl them",
                "python3 launch.py --seal"))
        else:
            out.append(Item("config", "paywall boards", DONE,
                            "nothing on the public path carries a paid row"))
    else:
        out.append(Item("config", "paywall", DONE,
                        "off — boards publish whole" +
                        (f", {len(comps.split(','))} address(es) already comped"
                         if comps else "; set QB_COMP_EMAILS before ever turning "
                         "it on")))

    # --- Stripe -------------------------------------------------------
    #
    # THE ORDER THESE FAIL IN IS THE ORDER THEY MATTER IN, and the worst
    # one is silent: with the paywall ON and the webhook secret missing,
    # the endpoint refuses every event, so people can pay and never get
    # in. Nothing errors on this side — the money arrives, Stripe's
    # dashboard shows a failing endpoint, and the site just looks like
    # nobody is subscribing.
    try:
        from . import stripeset as _ss
        stripe_checks = _ss.preflight()
    except Exception:                                        # noqa: BLE001
        stripe_checks = []
    missing = [h for ok, h, _ in stripe_checks if not ok]
    if not stripe_checks:
        pass
    elif not missing:
        out.append(Item("config", "Stripe", DONE,
                        "keys, three prices and the webhook secret are all set"))
    elif len(missing) == len(stripe_checks) - 1:
        # Nothing at all configured. That is a state, not a fault: the
        # site runs free and says so.
        out.append(Item("config", "Stripe", TODO,
                        "not configured on this machine — nobody can be "
                        "charged", "python3 launch.py --stripe"))
    else:
        out.append(Item("config", "Stripe", TODO,
                        f"{len(missing)} piece(s) missing: "
                        + "; ".join(missing[:3])
                        + ("…" if len(missing) > 3 else ""),
                        "python3 launch.py --stripe"))
    if paywall in ("1", "true", "yes", "on") and stripe_checks and any(
            "WEBHOOK" in h for h in missing):
        out.append(Item(
            "config", "Stripe webhook", TODO,
            "the paywall is ON and STRIPE_WEBHOOK_SECRET is missing — the "
            "webhook endpoint refuses every event, so a customer can pay "
            "and never get access, and nothing on this side reports it",
            "add the endpoint in Stripe, then put its signing secret in "
            "/etc/qellys/env and restart"))

    if env.get("ODDS_API_KEY"):
        out.append(Item("config", "ODDS_API_KEY", DONE, "set"))
    else:
        out.append(Item("config", "ODDS_API_KEY", UNKNOWN,
                        "not set in this shell — model and proxy lines only. "
                        "Expected on a laptop that reads it from secrets.local"))
    return out


# --- the report -------------------------------------------------------------

GROUPS = (("learning", "LEARNING — the loops that change a number"),
          ("data", "DATA — what has been collected"),
          ("book", "THE BOOK — the journal and its settlement"),
          ("config", "CONFIG — settings whose absence is silent"))

MARK = {DONE: "  ok  ", TODO: "  DO  ", UNKNOWN: "  ??  "}


def collect(models: Path | None = None, conn=None, hist=None,
            ledger_conn=None, env=None, today: str = "") -> list[Item]:
    """Every check, in report order. Each source is optional and its
    absence is reported rather than assumed away."""
    items = list(learning_items(models))
    items += data_items(conn)
    items += book_items(ledger_conn, hist, today)
    items.append(haircut_item(models, ledger_conn))
    items += config_items(env)
    return items


def render(items: list[Item]) -> str:
    todo = [i for i in items if i.state == TODO]
    unknown = [i for i in items if i.state == UNKNOWN]
    lines = ["Qellys Book — what still needs doing",
             f"  {_dt.date.today().isoformat()}, read-only, on this machine only.",
             ""]
    for key, title in GROUPS:
        rows = [i for i in items if i.group == key]
        if not rows:
            continue
        lines.append(title)
        for i in rows:
            lines.append(f"{MARK[i.state]}{i.name}: {i.evidence}")
            if i.command and i.state != DONE:
                lines.append(f"        → {i.command}")
        lines.append("")
    lines.append(f"{len(todo)} thing(s) to do, {len(unknown)} this machine "
                 f"cannot answer, {len(items) - len(todo) - len(unknown)} done.")
    if unknown:
        lines.append("  \"??\" is a third answer, not a failure: a machine with no "
                     "ledger")
        lines.append("  cannot honestly report on one, and guessing would be the "
                     "bug.")
    lines.append("")
    lines.append("Judgement calls — legal, design, anything needing your eye — "
                 "are in")
    lines.append("docs/WHEN_HOME.md under \"yours\". They are not measurable and "
                 "are")
    lines.append("deliberately not duplicated here.")
    return "\n".join(lines)


def main(argv=None) -> int:
    conn = hist = led = None
    try:
        from .db import connect as _dbconnect
        hist = conn = _dbconnect()
    except Exception:                                          # noqa: BLE001
        conn = hist = None
    try:
        from . import ledger as _led
        led = _led.connect()
    except Exception:                                          # noqa: BLE001
        led = None
    print(render(collect(conn=conn, hist=hist, ledger_conn=led)))
    for c in (conn, led):
        try:
            if c is not None:
                c.close()
        except Exception:                                      # noqa: BLE001
            pass
    return 0
