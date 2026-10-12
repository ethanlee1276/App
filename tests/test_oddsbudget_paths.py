"""The budget module's state file must be redirectable, in every function.

THE TRAP. `def f(path=STATE_PATH)` binds the path ONCE, when the function
is defined. Reassigning `oddsbudget.STATE_PATH` afterwards — which is how
every test in this suite redirects a store, and how a caller would point
the budget at a different file — then changes nothing, and the function
keeps writing to the real `data/cache/odds_budget.json`.

WHY IT HAS TO BE PINNED. `engine/oddsbudget.py` already carried a comment
saying it resolves the path at call time, and that was true of three
functions out of twelve. The nightly sweep of 2026-10-12 ran the suite
with an audit hook on every write under `data/` and caught the rest:
`test_odds_keyring.py` sets `B.STATE_PATH` to a tempfile, drives a full
`oddsapi._request`, and wrote its fake quota into the real budget file on
whatever machine ran the suite — Ethan's laptop included, where that file
is the live record of a paid plan.

That test still PASSED, every time, because the half it asserts
(`key_is_spent(key, p)`) is handed the path explicitly; only the half it
writes escaped. A half-isolated test is the worst kind: green on both
machines, and quietly editing the real store on one of them.

So assert the RULE rather than the nine functions that broke it. Reading
the module's own source with ast, so a new function added next year is
covered the day it lands — no store, no database, no network, same verdict
on every machine.
"""

import ast
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as B  # noqa: E402

SOURCE = pathlib.Path(B.__file__).read_text(encoding="utf-8")

#: Module-level paths a signature default must never capture. Each one is a
#: real file on the box that runs this: the budget state, the spend ledger
#: and the authorisation log.
STORE_NAMES = ("STATE_PATH", "SPEND_LOG", "DECISIONS_LOG")


def _signature_defaults():
    """(function, argument, captured name) for every default that reads a
    module-level store path — the binding that cannot be redirected."""
    out = []
    for node in ast.parse(SOURCE).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = node.args
        pairs = list(zip(a.posonlyargs + a.args, [None] * (
            len(a.posonlyargs) + len(a.args) - len(a.defaults)) + list(a.defaults)))
        pairs += list(zip(a.kwonlyargs, a.kw_defaults))
        for arg, default in pairs:
            if isinstance(default, ast.Name) and default.id in STORE_NAMES:
                out.append((node.name, arg.arg, default.id))
    return out


def test_no_function_binds_a_store_path_in_its_signature():
    bound = _signature_defaults()
    assert not bound, (
        "a default argument binds once, at definition, so these cannot be "
        "redirected by reassigning the module attribute and will write to "
        "the real store: "
        + ", ".join(f"{fn}({arg}={name})" for fn, arg, name in bound))


def test_the_check_above_can_actually_see_a_binding():
    """A checker that reads nothing passes everything. Hand it the shape it
    is looking for and require that it objects."""
    global SOURCE
    keep = SOURCE
    try:
        SOURCE = "STATE_PATH = 1\ndef f(path=STATE_PATH):\n    return path\n"
        assert _signature_defaults() == [("f", "path", "STATE_PATH")]
    finally:
        SOURCE = keep


def test_every_function_that_takes_a_path_still_declares_one():
    """The fix is `path=None`, not deleting the argument. If a later pass
    'simplifies' the parameter away, callers lose the redirect entirely and
    this file's rule would be satisfied by a module nothing can point."""
    import inspect
    for name in ("load", "save", "record_quota", "mark_refreshed",
                 "paid_pull_result", "should_refresh", "reset", "key_report",
                 "summary", "key_state", "key_is_spent"):
        fn = getattr(B, name)
        params = inspect.signature(fn).parameters
        assert "path" in params, f"{name}() can no longer be redirected"
        assert params["path"].default is None, \
            f"{name}(path=) defaults to {params['path'].default!r}, not None"


def test_reassigning_the_state_path_actually_moves_the_write():
    """The rule, exercised rather than read: the end-to-end behaviour the
    nine signatures were silently denying."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    moved = tmp / "budget.json"
    real = keep = B.STATE_PATH
    B.STATE_PATH = moved
    try:
        B.record_quota(19999, used=1)
        assert moved.is_file(), \
            "record_quota ignored the redirected STATE_PATH"
        # And the real file was not the one that moved. Asserted as a path
        # comparison, not an existence check: on Ethan's box the real file
        # exists for honest reasons, and on a fresh clone it does not.
        assert pathlib.Path(real) != moved
        assert B.load().used == 1, "load() reads a different file than save()"
    finally:
        B.STATE_PATH = keep


def test_the_spend_ledger_sits_beside_whatever_state_file_is_in_use():
    """SPEND_LOG and DECISIONS_LOG are derived from STATE_PATH at IMPORT, so
    they are their own module attributes and a test that redirects only
    STATE_PATH still appends to the real ones. Pinned as a fact, so the two
    names stay separately redirectable rather than quietly collapsing into
    one that a STATE_PATH patch is assumed to carry."""
    base = pathlib.Path(B.STATE_PATH).parent
    assert pathlib.Path(B.SPEND_LOG).parent == base
    assert pathlib.Path(B.DECISIONS_LOG).parent == base
    assert pathlib.Path(B.SPEND_LOG) != pathlib.Path(B.DECISIONS_LOG)


def test_the_keyring_test_redirects_the_spend_ledger_too():
    """The specific leak, pinned where it happened: the one test in this
    suite that drives a real paid-request path must point every store it
    writes at a tempfile, not just the one it reads back."""
    src = pathlib.Path(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "test_odds_keyring.py")).read_text(
        encoding="utf-8")
    body = src[src.index("def test_an_exhausted_key_switches_mid_request"):]
    for name in ("STATE_PATH", "SPEND_LOG", "DECISIONS_LOG"):
        assert f"B.{name} =" in body, \
            (f"the mid-request keyring test no longer redirects {name}; its "
             f"writes land in the real data/cache/")


if __name__ == "__main__":
    import re as _re
    declared = _re.findall(r"^def (test_\w+)",
                           open(__file__, encoding="utf-8").read(), _re.M)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert not set(declared) - {f.__name__ for f in fns}
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
