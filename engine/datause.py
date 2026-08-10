"""Is the data we add actually USED, or is it just sitting there?

Ethan, 2026-08-09: "can we make sure that the data that we are adding is
actually being utilized and not just sittin there."

He was right, and the numbers were stark. On the day it was asked,
`engine/mlb/velocity.py` — velocity trend, §5's injury tell, ten tests,
validated against a real pitcher — had **zero** consumers outside its own
module and a CLI probe. `times_through_order` had one. `pitchesThrown`
had none at all, having been fetched every night for months inside a
boxscore nobody read that field from.

Each of those was shipped "evidence only, priced never by default", which
is the right instinct after `docs/THE_INFORMATION_TEST.md` — and it
degrades into a store nobody reads unless something checks.

THE FOUR PLACES A SIGNAL CAN LAND, and only the last two make the model
any different:

  probe     a human runs a command and reads it. Real, and invisible on
            any night nobody runs it.
  pipeline  the board build reads it, so it reaches the page.
  journal   it is written on every bet, which is what lets the loss miner
            and the hypothesis lab mine it — the LLM's menu comes from
            `losspatterns.features_of`, so a dimension missing there is
            a dimension the lab can never propose about.
  gate      it can refuse a pick.

A signal in none of them is inert. A signal in `probe` alone is a report.
Neither is wrong, and both should be a CHOICE rather than something
discovered months later.

This module states the choice for each signal and then checks it, by
reading the repo rather than by trusting the registry.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Every signal we have deliberately built, what proves it is consumed,
#: and where we INTEND it to land. `want` is the promise; the audit
#: reports the gap between it and what the code does.
#:
#: Adding a row here is part of adding a signal. That is the point: the
#: registry is the place the intention is written down, so "we never
#: decided" stops being a possible answer.
SIGNALS = (
    {"name": "velocity trend",
     "module": "engine/mlb/velocity.py",
     # `delta_for` and `velo_delta` are the names the pricing and journal
     # paths actually use; the first three are the probe's. Watching only
     # the probe's names reported this SHORT after the journal wiring
     # landed — the registry has to name every door the signal leaves by.
     "symbols": ("velocity_history", "trend_all", "primary_pitch",
                 "delta_for", "velo_delta", "velo_band"),
     "want": ("probe", "journal", "gate"),
     "why": "§5's injury tell. Journaled it becomes a mineable dimension "
            "the loss miner can convict on and the lab can propose about."},
    {"name": "times through order",
     "module": "engine/mlb/sources/pbp.py",
     "symbols": ("times_through_order", "tto_band", "tto_proj",
                 "projected_tto"),
     "want": ("probe", "journal", "gate"),
     "why": "§5. Third time through is a real, measurable penalty."},
    {"name": "pitch counts",
     "module": "engine/mlb/sources/pbp.py",
     "symbols": ("pitch_counts",),
     # `probe`, and DELIBERATELY not more. §5 wants a pitch-count
     # projection feeding the outs market, and two things argue against
     # building it next.
     #
     # It would be a PRICING change, not a dimension. Feeding the outs
     # projection moves numbers, and the information test says the
     # claimed edge carries none — a new input into a noise variable is
     # the exact move that finding rules out until something moves the
     # AUC off 0.5.
     #
     # And as a mining dimension it would nearly duplicate `tto`: how
     # deep he goes and how many pitches he throws are close to the same
     # fact, and the miner would spend its multiple-testing budget
     # convicting the same pocket twice. `losspatterns._dedupe` exists
     # because that has already happened once.
     "want": ("probe",),
     "why": "§5's pitch-count projection feeds the OUTS market, which "
            "makes it a pricing change rather than a dimension — parked "
            "until the edge test says a new input can earn its place. As "
            "a slice it would restate `tto` almost exactly."},
    {"name": "first-mover attribution",
     "module": "engine/linemoves.py",
     "symbols": ("first_mover", "first_mover_sharp", "move_first_sharp"),
     # `journal` only, and the omission is deliberate. It DOES render in
     # `summary_lines`, but that call site is inside `linemoves.py`
     # itself, so this scan cannot attribute it — and claiming a kind the
     # check cannot verify is how a green column stops meaning anything.
     # The journal claim is the one that matters anyway: a rendered
     # string informs a reader, a column lets the miner convict.
     "want": ("journal",),
     "why": "§4. Journaled so the miner can test whether a sharp book "
            "moving first predicts anything. NOT priced: movement "
            "already vetoes picks on an unmeasured signal (#80), and a "
            "second one would repeat that. Also rendered in the movement "
            "summary, which this scan cannot see."},
    {"name": "lineup-release boundary",
     # TWO modules: the boundary is recorded in `mlb/lineuptimes.py` and
     # measured by `linemoves.lineup_release_move`. Listing one made the
     # other look like a consumer of itself.
     "module": "engine/mlb/lineuptimes.py",
     "also": ("engine/linemoves.py",),
     "symbols": ("posted_at", "is_usable", "lineup_release_move"),
     "want": ("probe",),
     "why": "§4's baseball tell. Recording first; the measurement needs "
            "a few days of usable boundaries before it can be written."},
    {"name": "the edge test",
     "module": "engine/edgehistory.py",
     "symbols": ("record_edge_run", "edge_now"),
     # NOT `pipeline`: the Record page renders it, but that render is
     # JavaScript and this scan reads Python and shell. Claiming a kind
     # the check cannot see would make the row permanently SHORT and
     # teach everyone to ignore the column.
     "want": ("probe", "journal"),
     "why": "The 2026-08-09 finding. Banked nightly, rendered on the "
            "Record page (web/js/app.js, outside this scan), and led with "
            "in the lab's prompt."},
    {"name": "pitch arsenal",
     "module": "engine/mlb/arsenal.py",
     "symbols": ("mix_shift", "whiff_by_type", "show_arsenal",
                 "show_matchup", "parse_arsenal"),
     "want": ("probe",),
     "why": "§6. Pitch mix and per-type whiff rate, from the SAME cached "
            "playByPlay payloads --velo already loads — no new feed. The "
            "hitter half arrived 2026-08-10: Savant's pitch-arsenal "
            "board is one CSV a season, so §6 is complete as a probe."},
    {"name": "book sharpness",
     "module": "engine/booksharp.py",
     # NOT `measure`. That name appears in 120 files — the first cut
     # matched every one of them and reported this signal as living in
     # gate, journal and pipeline before a single caller existed. A
     # registry symbol has to be distinctive enough to be evidence.
     "symbols": ("compare_to_the_list", "show_booksharp", "MIN_SERIES"),
     "want": ("probe",),
     "why": "§4. The sharp-book hierarchy is a hand-written list today; "
            "this measures it from our own snapshots. Probe only — "
            "weighting the consensus by it is a pricing change."},
    {"name": "injury redistribution",
     "module": "engine/redistribute.py",
     # `redistribution` alone also hits engine/coverage.py's prose about
     # NBA minutes, which is a different word doing a different job.
     "symbols": ("show_redistribution", "MIN_OUT_GAMES"),
     "want": ("probe",),
     "why": "§7. injuries.py prices with invented multipliers (1.09 for a "
            "CB1); this measures where usage actually goes. Probe only "
            "until the edge test says a new input can earn its place."},
    {"name": "alignment and coverage",
     "module": "engine/sources/nflpart.py",
     "symbols": ("coverage_rates", "formation_rates", "show_alignment",
                 "opp_zone_rate", "coverage_band"),
     "want": ("probe", "journal", "gate"),
     "why": "§6. The coverage data the spec said did not exist. Journaled "
            "as `opp_zone_rate` so the loss miner can convict on it and "
            "the lab can propose about it — the cheapest real test of "
            "whether it carries anything, with nothing touching a grade."},
)

#: Where a consumer has to live to count as each kind. Checked by path,
#: because a signal read only by the file that produces it is not read.
_KINDS = {
    "probe": ("launch.py", "watch.py", "movecheck.py", "stakecheck.py",
              "doctor.py", "lineupwatch.py", "tools/"),
    "pipeline": ("engine/", "mlb_build.py", "nfl_build.py", "cfb_build.py",
                 "nba_build.py", "generate.py", "generate_mlb.py"),
    "journal": ("engine/ledger.py", "engine/losspatterns.py",
                "engine/hypotheses.py"),
    "gate": ("engine/quality.py", "engine/betting.py",
             "engine/mlb/betting.py"),
}


def _py_files() -> list[Path]:
    out = []
    # SHELL SCRIPTS ARE CONSUMERS TOO. `tools/lineups.sh` calls
    # `lineuptimes.coverage()` after every watch, which is the only thing
    # that reads that store on a normal day — and skipping tools/ reported
    # the lineup boundary as INERT while a scheduled agent was using it
    # nightly. Tests stay excluded: a signal read only by its own test is
    # not used, and counting that would make the check congratulate
    # itself.
    for p in sorted(list(ROOT.rglob("*.py")) + list(ROOT.rglob("tools/*.sh"))):
        rel = str(p.relative_to(ROOT))
        if rel.startswith("tests/") or "__pycache__" in rel:
            continue
        # THE AUDITOR IS NOT A CONSUMER. The registry below names every
        # symbol it looks for, so scanning this file finds all of them and
        # reports each signal as read — by the thing checking whether it
        # is read. The first run said "pitch counts: ok, in pipeline"
        # entirely on the strength of this module mentioning them.
        if rel == "engine/datause.py":
            continue
        out.append(p)
    return out


def consumers(symbols, own_module, also=()) -> dict:
    """Which files outside the producer mention any of these symbols.

    Deliberately a text scan and deliberately crude. A precise import
    graph would miss `getattr` and dynamic dispatch, and the question
    here is not "is this called on every path" — it is "does anything
    anywhere even mention it", which a repo-wide grep answers honestly.
    """
    hits: dict = {}
    for p in _py_files():
        rel = str(p.relative_to(ROOT))
        if rel == own_module or rel in (also or ()):
            continue
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for s in symbols:
            if s in body:
                hits.setdefault(rel, []).append(s)
    return hits


def _kind_of(rel: str) -> str | None:
    for kind, prefixes in _KINDS.items():
        for pre in prefixes:
            if rel == pre or rel.startswith(pre):
                # `journal` and `gate` live under engine/ too, so the more
                # specific match has to win — checked in dict order, with
                # pipeline's broad "engine/" last among them.
                if kind == "pipeline" and pre == "engine/":
                    continue
                return kind
    return "pipeline" if rel.startswith("engine/") else None


def audit() -> list[dict]:
    """Every signal, where it actually lands, and where it was meant to."""
    out = []
    for sig in SIGNALS:
        found = consumers(sig["symbols"], sig["module"], sig.get("also"))
        kinds = {k for k in (_kind_of(r) for r in found) if k}
        want = set(sig["want"])
        out.append({
            "name": sig["name"],
            "module": sig["module"],
            "why": sig["why"],
            "want": sorted(want),
            "have": sorted(kinds),
            "missing": sorted(want - kinds),
            "consumers": found,
            "inert": not kinds,
        })
    return out


def report() -> str:
    rows = audit()
    lines = ["", "=" * 70,
             "  IS THE DATA WE ADD ACTUALLY USED?", "=" * 70]
    inert = [r for r in rows if r["inert"]]
    short = [r for r in rows if r["missing"] and not r["inert"]]
    for r in rows:
        if r["inert"]:
            mark, note = "INERT ", "nothing anywhere reads it"
        elif r["missing"]:
            mark, note = "SHORT ", "missing: " + ", ".join(r["missing"])
        else:
            mark, note = "ok    ", "in " + ", ".join(r["have"])
        lines.append(f"  {mark} {r['name']:<26} {note}")
    if inert or short:
        lines.append("")
        for r in inert + short:
            lines.append(f"  {r['name']} — {r['why']}")
            if r["consumers"]:
                lines.append("    read by: " + ", ".join(sorted(r["consumers"])))
            else:
                lines.append("    read by: nothing")
    lines += [
        "",
        "  probe = a human runs a command · pipeline = the board build reads it",
        "  journal = written on every bet, so the miner and the lab can use it",
        "  gate = it can refuse a pick",
        "",
        "  A signal in `probe` alone is a report, which is a fine thing to be",
        "  — but it should be a choice made once, not a fact discovered in",
        "  six months. `want` in engine/datause.py is where that choice lives.",
        "",
    ]
    return "\n".join(lines)
