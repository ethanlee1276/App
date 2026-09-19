"""A suite that reads the box it runs on is not a gate.

`engine.feedstate` closed this door for ``data/feedstate/``. The same
door was still open one directory over, and on 2026-08-27 it cost three
consecutive red CI runs that the local suite had called green:
`engine.cfbtdfit` fitted a temperature into ``data/models/
calibration.json``, that file is gitignored, and the correction lifts a
modelled probability — so a fixture's quotes cleared the EV bar on the
machine that had fitted it and nowhere else.

The direction is what makes it worth a module. A local run that passes
because the box is richer than a clone keeps passing right up until it
is deployed somewhere that never fitted anything.

Run directly: `python3 tests/test_modelstate.py`
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import modelstate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def test_unset_is_the_path_these_modules_always_used():
    saved = os.environ.pop(modelstate.ENV_VAR, None)
    try:
        assert modelstate.directory() == os.path.join("data", "models")
        assert modelstate.path("calibration.json") == \
            os.path.join("data", "models", "calibration.json")
    finally:
        if saved is not None:
            os.environ[modelstate.ENV_VAR] = saved


def test_the_environment_moves_every_model_together():
    saved = os.environ.get(modelstate.ENV_VAR)
    os.environ[modelstate.ENV_VAR] = "/tmp/qb-models-test"
    try:
        assert modelstate.directory() == "/tmp/qb-models-test"
        assert modelstate.path("prereg.json") == \
            "/tmp/qb-models-test/prereg.json"
    finally:
        if saved is None:
            os.environ.pop(modelstate.ENV_VAR, None)
        else:
            os.environ[modelstate.ENV_VAR] = saved


def test_an_empty_name_gives_the_directory_itself():
    """`engine.todo` wants the folder, not a file in it."""
    assert modelstate.path("").rstrip("/\\").endswith("models")


def test_every_fitted_model_resolves_through_it():
    """The point of a resolver is that nothing bypasses it. A module that
    keeps its own literal path is a module the suite still reads off the
    box."""
    for name in ("calibrate", "formfit", "hypotheses", "losspatterns",
                 "playerfit", "prereg", "prose", "selectionfit", "todo"):
        source = _read(os.path.join("engine", f"{name}.py"))
        assert "_modelstate" in source, name
        assert '"data/models/' not in source, name
        assert '"data" / "models"' not in source, name


def test_the_suite_points_it_at_a_sandbox():
    runner = _read("run_tests.py")
    assert 'env["QB_MODELS_DIR"]' in runner
    assert 'os.path.join(sandbox, "models")' in runner


def test_the_suite_still_sandboxes_the_other_two_doors():
    """Environment secrets and the feedstate directory. Closing a third
    door is no use if a previous one reopened."""
    runner = _read("run_tests.py")
    assert 'env["QB_FEEDSTATE_DIR"]' in runner
    assert 'STRIPE_' in runner


def test_the_calibration_store_actually_moves():
    saved = os.environ.get(modelstate.ENV_VAR)
    os.environ[modelstate.ENV_VAR] = "/tmp/qb-models-test"
    try:
        import engine.calibrate as cal
        importlib.reload(cal)
        assert str(cal.DEFAULT_PATH).startswith("/tmp/qb-models-test")
    finally:
        if saved is None:
            os.environ.pop(modelstate.ENV_VAR, None)
        else:
            os.environ[modelstate.ENV_VAR] = saved
        import engine.calibrate as cal
        importlib.reload(cal)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
