"""Every fit and every invention, and where its answer lands — checked against the code, not remembered.

Ethan, 2026-10-17: "just cause we add features and data and shit and say
we did doesnt mean we are using them the right way so make sure all of our
tools and data are being used correctly and not just the ones you just
added but ALL tools and data we were and are using."

`engine/datause` asks that of the signals we pull. This asks it of the
things that MEASURE — every fitter, every measurement script, every one of
the thirteen inventions — because a measurement is the cheapest place for
work to go to waste: it runs on the box, it passes, and nothing reads it.

THE PLACES AN ANSWER CAN LAND:

  number    the projection or the pricer reads it — the fit's own store,
            or the measured constant it wrote into the code
  board     the Most Likely board reads it (a correction, a hold, a note
            the record judges)
  gated     it moves Most Likely and Edge the moment its own held-out
            verdict holds (engine/ideagate) — until then, a card
  card      shown on a pick, game or My Bets page; never a number, by design
  report    a person reads it; what it found is written into the code it
            names, or it found nothing to apply
  failed    it measured and did not clear its bar; not wired, on purpose

WHAT THE CHECK HOLDS (`problems()`, and tests/test_every_fit_lands_where_it_says):
every fitter and measurement script in the repo has a row here, so a new
one cannot be added without saying where it lands; a row that claims
"number", "board" or "gated" names the module that reads it, and that
module's source really does name it; a "gated" row is one of
engine/ideagate's gates; and nothing on the number path imports a fit that
failed its bar.

WHAT IT CANNOT SEE, as datause says of itself: a module that names a fit
may still read it wrongly. That is the value audit, and it lives in each
fit's own tests — the ones that feed a plausible input through and assert a
number comes back.

    python3 -m engine.wiremap            # the map, the gates, the findings
    python3 -m engine.wiremap --check    # exit 1 on any problem

Standard library only.
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LANDS = ("number", "board", "gated", "card", "report", "failed")

#: Where the projection, the pricer and the Most Likely board begin. A
#: module these reach, through any import at any depth, is on the number
#: path.
NUMBER_ROOTS = ("engine.pipeline", "engine.projection", "engine.betting", "engine.likely",
                "engine.likelyboard", "engine.ideagate")

#: (module, lands, read by, why). "read by" is the module whose source
#: names this one — for a measured constant, the module holding it.
FITS = (
    # ---- the projection and the pricer ------------------------------------------------------
    ("engine.formfit", "number", ("engine.projection",), "the form curve every projection blends with"),
    ("engine.playerfit", "number", ("engine.projection",), "per-player memory, adopted market by market"),
    ("engine.defensefit", "number", ("engine.defensevs",), "how much of a defence's rating reaches one player (TRANSFER)"),
    ("engine.cfb.defensefit", "number", ("engine.defensevs",), "the college twin (TRANSFER_CFB)"),
    ("engine.wxfit", "number", ("engine.weather",), "wind, cold and rain, measured 2016-2025"),
    ("engine.matefit", "number", ("engine.teammates",), "a teammate out at his position (the lineup step)"),
    ("engine.qbfit", "number", ("engine.qbchange",), "a missing starting quarterback, for his receivers and backs"),
    ("engine.injuryfit", "number", ("engine.injuries",), "the knock-on rules (KNOCK_ONS), measured 2022-2024"),
    ("engine.exitfit", "number", ("engine.nba.minutes",), "games a player left early, ruled per sport"),
    ("engine.hoops_fit", "number", ("nba_build",), "the basketball board's fitted pieces"),
    ("engine.cfbtdfit", "number", ("engine.tdscale",), "the college touchdown model, graded on four seasons"),
    ("engine.corrfit", "number", ("engine.parlays",), "the parlay pricer's correlation priors, measured"),
    ("engine.devigfit", "number", ("engine.devig",), "which de-vig the touchdown market wants (BAND_Z)"),
    ("engine.journalfit", "number", ("engine.ledger",), "the journal-learned drift every sport shares"),
    ("engine.deepfit", "number", ("engine.maintenance",), "runs the deep fitters nightly; their stores are read above"),
    ("engine.selectionfit", "number", ("engine.betting",), "the selection correction on Edge's claimed edge"),
    ("engine.pmfit", "number", ("engine.predmarket",), "the informed-flow weights on the prediction-market board"),
    ("bridgefit", "number", ("engine.carry",), "the usage bridge leans on last season in the volume role"),
    ("rolewindowfit", "number", ("engine.nflusage",), "the usage bridge weights his games by age (ROLE_HALF_LIFE)"),
    ("seasonpriorfit", "number", ("engine.carry",), "his own last season as the form's prior, week 4 on"),
    ("hoopsdvpfit", "number", ("engine.hoopsdvp",), "how much of a basketball defence reaches one line"),
    ("nbavacancy", "number", ("engine.nba.vacancy",),
     "the minutes a regular's absence opens for his teammates, once its held-out verdict holds"),
    ("tdearlyfit", "number", ("engine.touchdowns",), "September touchdown chances, graded"),
    ("cfbtargetfit", "number", ("engine.sources.cfbstats",), "a thrown-at, caught-nothing game counts as a zero"),
    ("marketfit", "number", ("engine.passint",), "which new markets the model can sort (interceptions shipped)"),
    ("cfbmarketfit", "number", ("engine.passint",), "the college volume markets and interceptions"),
    # ---- the Most Likely board --------------------------------------------------------------
    ("engine.rankfit", "board", ("engine.likely",), "the AUC that orders Most Likely and sets its floors"),
    ("engine.yardagefit", "board", ("engine.likely",), "the yardage markets' honest width"),
    ("engine.scanfit", "board", ("engine.likely",), "the scan's reasons: notes until MEASURED says a reason holds"),
    ("engine.tdmatchfit", "board", ("engine.tdscenarios",),
     "a bad defence adds nothing beyond the game total, so a scenario is a selection rule, the chance unmoved"),
    ("scanblendfit", "board", ("engine.teamchange",), "how much of a team's rating is this season"),
    ("pricetrust", "board", ("engine.likelyboard",),
     "the NFL one board never shows a chance above the books' price (PRICE_TRUST, Ethan's yes 2026-10-17)"),
    # ---- the inventions (engine/ideagate) ---------------------------------------------------
    ("engine.rookies", "gated", ("engine.ideagate",), "a thin rookie sample's prior"),
    ("engine.rolechange", "gated", ("engine.ideagate",), "the usage bridge's volume follows the detected role"),
    ("engine.kickphysics", "gated", ("engine.ideagate",), "a kicker's field goals in tonight's air"),
    ("engine.playsim", "gated", ("engine.ideagate",), "two teammates' legs from the same simulated games"),
    ("engine.bookmenu", "gated", ("engine.ideagate",), "a book's menu that does not add up"),
    ("engine.bookrecipe", "gated", ("engine.ideagate",), "the outcome recipe far from the line"),
    ("engine.attention", "gated", ("engine.ideagate",), "a spike in public attention"),
    ("engine.bookclusters", "gated", ("engine.ideagate",), "the market's fair chance, one vote per opinion"),
    ("engine.practice", "gated", ("engine.ideagate",), "a listed man unlikely to play"),
    ("engine.conformal", "gated", ("engine.ideagate",), "the honest range, where it beat our chance"),
    ("engine.nhl.endgame", "gated", ("engine.ideagate", "nhl_build"),
     "the NHL final score's shape (score effects, pulled goalie, empty net) on the puck line and total"),
    # ---- cards, by design -------------------------------------------------------------------
    ("engine.altcurve", "card", ("engine.ideas",), "picks sit at the main line, where the two curves agree"),
    ("engine.autopsy", "card", ("engine.ideas",), "it names the step that is wrong; it is not a step"),
    ("engine.risk", "card", ("server",), "My Bets only"),
    ("engine.mlb.xstatsfit", "card", ("engine.mlb.charts",), "expected stats on the hit page, measured before any use"),
    ("chartfit", "card", ("engine.gamescan",), "play charting: no lift, 2026-09-28 — notes on the scan, never counted"),
    ("ngsfit", "card", ("engine.gamescan",), "Next Gen Stats: no lift, 2026-09-28 — notes on the scan, never counted"),
    # ---- reports ----------------------------------------------------------------------------
    ("engine.crowdfit", "report", (), "is the Kalshi/Polymarket crowd right? evidence on the game page, never a number"),
    ("engine.nflfit", "report", (), "a fitted projection against the blend we ship; the blend kept"),
    ("engine.ripplefit", "report", (), "the usage ripple did not beat the close; the lineup step reads matefit instead"),
    ("engine.scriptfit", "report", (), "the spread's effect sits in the team total already (engine/tdfeatures)"),
    ("engine.proplivefit", "report", (), "is the live prop chance honest? the Live tab's own check"),
    ("engine.slipreadfit", "report", (), "is the parlay checker's off-board read honest? replayed on past seasons"),
    ("engine.nfl.prefit", "report", (), "preseason usage and results; the preseason board is shown, not priced"),
    ("engine.factors", "report", (), "what each football factor is worth; became matchup.DEFENSE_TRANSFER"),
    ("engine.haircut", "report", (), "how much claimed game-line edge survives — see FINDINGS"),
    ("guardfit", "report", (), "is the favourite guard steep enough? asked of the record"),
    ("likelyfit", "report", (), "which Most Likely picks to stop taking, tried on unseen weeks"),
    ("selfit", "report", (), "fits the selection correction and tries to fail it out of sample (engine/selectionfit)"),
    ("palettefit", "report", (), "a colour token back on its contrast target — design, not a model"),
    ("qbscriptfit", "report", (), "retired the spread tilt on volume, 2026-10-12: on today's base it adds nothing"),
    ("fieldcurvefit", "report", (), "the market's curve shape (PHI) the thin-pick test reads (research/thinmarket_box, "
     "EXP-R06); on no board until that passes and Ethan says yes"),
    # ---- failed their bar --------------------------------------------------------------------
    ("engine.cbfit", "failed", (), "a top corner's effect — did not hold on the box, 2026-10-04"),
    ("engine.tdinjfit", "failed", (), "an injury moving WHO scores — did not hold on the box, 2026-10-04"),
    ("engine.tdmanfit", "failed", (), "a man-beater against red-zone man — did not hold on the box, 2026-10-04"),
    ("engine.tdtop", "failed", (), "the top of the touchdown board too shy — did not hold on the box, 2026-10-04"),
    ("cfbbridgefit", "failed", (), "college's usage bridge — worse in every season, 2026-10-14; nothing ships"),
    ("defoutfit", "failed", (), "a defence missing its starters — worse in a held-out season in every market, 2026-10-12"),
)

#: Things the map found that a person decides — not changed here.
FINDINGS = (
    ("engine.haircut", "Measured 2026-09-19: the model's claimed moneyline edge did not survive in college or "
     "the NFL (survival about 0%, the interval spanning zero). The shipped college haircut (35% standard, 50% "
     "marquee) assumes 65% survives. Game-line Edge picks still pass when a raw edge is big enough; whether to "
     "refuse them outright is Ethan's call."),
    ("engine.ml", "The learned multiplier model is opt-in (`--model`); the box never passes it, and the measured "
     "steps (defence transfer, weather, teammates, quarterback) replaced what it did. Left off on purpose: turning "
     "it on would count those effects twice."),
    ("engine.projection", "The usage bridge's `att_usage` hook is never filled for the volume markets (attempts, "
     "completions, carries) — they have no usage bridge to fill it. Harmless: an empty hook moves nothing."),
)


# ---- the import graph ------------------------------------------------------------------------

def _files() -> dict:
    out = {}
    for d, _dirs, fs in os.walk(os.path.join(ROOT, "engine")):
        if "__pycache__" in d:
            continue
        for f in fs:
            if f.endswith(".py"):
                out[_name(os.path.join(d, f))] = os.path.join(d, f)
    for f in os.listdir(ROOT):
        if f.endswith(".py"):
            out[f[:-3]] = os.path.join(ROOT, f)
    return out


def _name(path: str) -> str:
    rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
    return rel[: -len(".__init__")] if rel.endswith(".__init__") else rel


def graph(files: dict | None = None) -> dict:
    """``{module: [engine modules it imports]}`` — every import at any
    depth of the file, function-level ones too (the builds import lazily)."""
    files = files or _files()
    g = {}
    for m, f in files.items():
        try:
            with open(f, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError, ValueError):
            continue
        pkg = m.split(".") if f.endswith("__init__.py") else m.split(".")[:-1]
        out = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                out.update(a.name for a in n.names if a.name.startswith("engine"))
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    base = pkg[: len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                    mod = ".".join(base + ([n.module] if n.module else []))
                else:
                    mod = n.module or ""
                if not mod.startswith("engine"):
                    continue
                out.add(mod)
                out.update(f"{mod}.{a.name}" for a in n.names if f"{mod}.{a.name}" in files)
        g[m] = sorted(x for x in out if x in files)
    return g


def reach(g: dict, roots) -> set:
    seen, stack = set(), list(roots)
    while stack:
        m = stack.pop()
        if m in seen or m not in g:
            continue
        seen.add(m)
        stack.extend(g[m])
    return seen


def lanes(g: dict | None = None) -> dict:
    """{module: "number" | "build" | "server" | "cli"} for every engine module."""
    g = g or graph()
    number = reach(g, NUMBER_ROOTS)
    builds = reach(g, [m for m in g if m.endswith("_build") and "." not in m])
    server = reach(g, ["server"])
    out = {}
    for m in g:
        if not m.startswith("engine"):
            continue
        out[m] = ("number" if m in number else "build" if m in builds else "server" if m in server else "cli")
    return out


# ---- the fits --------------------------------------------------------------------------------

def detected(files: dict | None = None, g: dict | None = None) -> list:
    """Every module that measures: an engine module or a top-level script
    with "fit" in its name (a top-level script that runs its engine twin —
    `defensefit.py` for engine/defensefit, `cfbdefensefit.py` for
    engine/cfb/defensefit — is that twin), plus the inventions ideagate
    gates."""
    files = files or _files()
    g = g if g is not None else graph(files)
    out = set()
    for m in files:
        last = m.split(".")[-1]
        if "fit" not in last or last.startswith("test_"):
            continue
        if "." not in m and any(x.split(".")[-1] in (m, m.replace("cfb", "", 1)) for x in g.get(m, ())):
            continue
        out.add(m)
    from .ideagate import GATES, NEVER
    out.update(f"engine.{mod}" for _n, mod, *_x in GATES)
    out.update(f"engine.{mod}" for _n, mod, *_x in NEVER)
    return sorted(out)


def _mentions(path: str, name: str) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return False
    return re.search(rf"\b{re.escape(name.split('.')[-1])}\b", src) is not None


def problems() -> list:
    """Every way the map and the code disagree. Empty is the bar."""
    files = _files()
    g = graph(files)
    rows = {m: (lands, by, why) for m, lands, by, why in FITS}
    out = []
    for m in detected(files, g):
        if m not in rows:
            out.append(f"{m}: measures something and the map does not say where it lands")
    from .ideagate import GATES
    gated = {f"engine.{mod}" for _n, mod, *_x in GATES}
    number = reach(g, NUMBER_ROOTS)
    for m, (lands, by, why) in rows.items():
        if lands not in LANDS:
            out.append(f"{m}: '{lands}' is not a place an answer lands")
        if m not in files:
            out.append(f"{m}: in the map, not in the repo")
            continue
        if lands in ("number", "board", "gated", "card"):
            if not by:
                out.append(f"{m}: says '{lands}' and names no reader")
            for r in by:
                if r not in files:
                    out.append(f"{m}: its reader {r} is not in the repo")
                elif not _mentions(files[r], m):
                    out.append(f"{m}: says {r} reads it, and {r} never names it")
        if lands == "gated" and m not in gated:
            out.append(f"{m}: says 'gated' and engine/ideagate has no gate for it")
        if lands == "failed":
            on = sorted(x for x in number if m in g.get(x, ()))
            if on:
                out.append(f"{m}: failed its bar and the number path imports it ({', '.join(on)})")
    return out


def report(sport: str = "nfl") -> str:
    g = graph()
    ln = lanes(g)
    out = ["Where every fit and invention lands (engine/wiremap)"]
    counts = {k: sum(1 for v in ln.values() if v == k) for k in ("number", "build", "server", "cli")}
    out.append(f"  engine modules: {counts['number']} on the number path, {counts['build']} build-only "
               f"(cards, journal), {counts['server']} pages and Ask only, {counts['cli']} command-line only")
    for lands in LANDS:
        rows = [r for r in FITS if r[1] == lands]
        out.append(f"\n  {lands.upper()} ({len(rows)})")
        for m, _l, by, why in rows:
            out.append(f"    {m:26s} {('→ ' + ', '.join(by)) if by else '':28s} {why}")
    from .ideagate import state
    out.append(f"\n  THE INVENTIONS' GATES — {sport}")
    for name, mod, moves, st in state(sport):
        out.append(f"    {name:10s} {st:26s} {moves}  (engine/{mod})")
    out.append("\n  FINDINGS FOR A PERSON")
    for m, text in FINDINGS:
        out.append(f"    {m}: {text}")
    bad = problems()
    out.append(f"\n  {'NO PROBLEMS: every fit lands where the map says' if not bad else str(len(bad)) + ' PROBLEM(S):'}")
    out.extend(f"    {p}" for p in bad)
    return "\n".join(out)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Where every fit and invention lands, checked against the code")
    ap.add_argument("--sport", default="nfl", help="the sport whose gates to show (default nfl)")
    ap.add_argument("--check", action="store_true", help="print only the problems; exit 1 if any")
    a = ap.parse_args(argv)
    if a.check:
        bad = problems()
        print("\n".join(bad) if bad else "every fit lands where the map says")
        return 1 if bad else 0
    print(report(a.sport))
    return 0


if __name__ == "__main__":
    sys.exit(main())
