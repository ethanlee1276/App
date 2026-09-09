"""A check that finds nothing must not read as a check that found nothing wrong.

This is the whole family behind #131, and it has cost real money and real
days:

  2026-08-18  the injuries page wore a nine-day-old "Active" on a man with
              a broken wrist. The refresh thread was dead; every board
              simply stopped moving, which looks exactly like a quiet
              night.
  2026-09-03  `engine/parlays.arbitrate_slate` read the paywalled copy of
              every board, found no parlays, and silently did not enforce
              the one-parlay-per-slate cap. `parlaycheck.py` then reported
              "every published ticket is internally consistent" having
              found no tickets to check.
  2026-09-06  both closing-line indexes are keyed by calendar date and
              were looked up with an NFL week label, so no football bet
              could ever be given a close — and it read as the ordinary
              "no close harvested yet". CLV is the one edge this book has
              measured, and the football half of it would have been
              absent all season.
  2026-09-08  `--why-empty` printed "no analyzed props at all" over a
              board holding 286, and `--check`'s knowledge-tier coverage
              measured zero reasons and said nothing at all, because its
              guard was `if reasons:` with no else.

Every one of those is the same shape: an empty result is a legal answer
to the question asked, so nothing raises and nothing looks wrong.

`doctor.py` is where that would hurt most, because it is the screen whose
entire job is to say whether anything is wrong. A check there that runs
against an absent database reports "0 open bets, no problems found" —
a health monitor confidently describing a machine it cannot see, which is
the sentence `has_history` was written under.

The sweep of 2026-09-09 found no live instances left: every board reader
resolves through `gate.board_source` (or, in devigcheck's case, follows
the `locked` marker and says so), and every doctor check that touches a
store already guards. This file is what keeps that true, because the
property is one commit from being lost and the loss is invisible.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SRC = open(os.path.join(ROOT, "doctor.py"), encoding="utf-8").read()

#: Checks that read no data store, so there is no empty case to guard.
#: Each names WHY, because an unexplained exemption is how a real one
#: gets added to the list.
NO_STORE = {
    "check_tests": "runs the test suite in a subprocess — its input is "
                   "the code, which is always present",
    "check_llm_spend": "reads a spend log whose absence IS the answer "
                       "(nothing has been spent)",
    "check_git": "asks git about the checkout, which exists by "
                 "definition if this is running",
    "check_correlation_priors": "iterates corrfit.ADOPT, a static table — "
                                "the denominator can never be zero",
}


def _checks() -> dict:
    """{name: body} for every check function in doctor.py."""
    starts = [(m.start(), m.group(1))
              for m in re.finditer(r"^def (check_\w+)\(", SRC, re.M)]
    out = {}
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(SRC)
        out[name] = SRC[pos:end]
    return out


def test_there_are_checks_to_check():
    """A regex that silently matches nothing would make every assertion
    below vacuous — which is the exact failure this file is about."""
    assert len(_checks()) >= 15, sorted(_checks())


def test_every_check_that_reads_a_store_says_so_when_there_is_none():
    """The one rule. `has_history` / `has_journal` answer "is there a real
    database here, or would connect() invent an empty one" — and on a
    fresh clone, a CI box or a scheduled cloud session the answer is no.
    Without the guard those checks all pass, loudly, about nothing."""
    missing = []
    for name, body in _checks().items():
        if name in NO_STORE:
            continue
        if not any(tok in body for tok in
                   ("_no_data", "has_journal()", "has_history()",
                    "if not fitted", "if not stocked", "if not stores")):
            missing.append(name)
    assert not missing, (
        "doctor.py check(s) with no empty-data path: " + ", ".join(missing)
        + ".\nEither guard with has_journal()/has_history() and _no_data(), "
        "or add the check to NO_STORE in this file WITH the reason it "
        "cannot go silent. A check that reports a machine it cannot see "
        "is worse than no check.")


def test_the_exemptions_are_real_checks_and_each_carries_a_reason():
    """An exemption list that drifts from the code is how a guard gets
    quietly dropped: delete the check, keep the entry, and the next one
    to take that name inherits a pass it never earned."""
    names = set(_checks())
    stale = sorted(set(NO_STORE) - names)
    assert not stale, f"NO_STORE names checks that no longer exist: {stale}"
    for name, why in NO_STORE.items():
        assert len(why) > 25, (name, why)


def test_a_crashing_check_becomes_a_finding_rather_than_a_pass():
    """`_check` turns an exception into a FAIL row. A bare try/except
    would make a broken check look healthy, which is the specific failure
    that makes monitoring worthless — doctor.py's own words."""
    i = SRC.index("def _check(rep, name)")
    block = SRC[i:i + 900]
    assert "except Exception" in block
    assert "rep.add(name, FAIL" in block
    assert "the check itself failed" in block


def test_an_absent_database_is_not_mistaken_for_an_empty_one():
    """`has_history` requires real SIZE, not mere existence: sqlite
    creates a valid empty database on connect, so `p.exists()` alone
    would pass on a box that has never ingested anything."""
    i = SRC.index("def has_history()")
    block = SRC[i:i + 900]
    assert "st_size" in block, block
    assert "connect() invent an empty one" in block


def test_the_board_readers_still_resolve_the_paywalled_copy():
    """The other half of the family, and the one with eight recorded
    instances. Every module that READS a board must resolve the public
    path to the private one — `gate.board_source` exists for exactly
    this and its own docstring keeps the tally."""
    import pathlib
    root = pathlib.Path(ROOT)
    # Readers only. A *_build.py names the path as its --out default and
    # writes it; naming a path you write is not reading a stripped board.
    readers = ("engine/parlays.py", "engine/parlayledger.py",
               "engine/boardlint.py", "engine/moments.py",
               "engine/sweat.py", "lineupwatch.py", "launch.py")
    for rel in readers:
        body = (root / rel).read_text(encoding="utf-8")
        assert "board_source" in body or "full_board" in body, rel


def test_the_devig_checker_follows_the_lock_and_says_which_copy_it_read():
    """It resolves differently on purpose and the difference is the
    point: pointed at an arbitrary file it follows the `locked` marker,
    and when there is no private copy behind one it REPORTS that rather
    than analysing a redacted payload as a clean empty board."""
    body = open(os.path.join(ROOT, "engine", "devigcheck.py"),
                encoding="utf-8").read()
    assert 'board.get("locked")' in body
    assert "no private copy was found" in body
    assert "the private board behind it" in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
