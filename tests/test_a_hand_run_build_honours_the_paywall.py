"""A build run by hand as the service's user honours the paywall it cannot
read.

Found 2026-11-17. The paywall flag lives in /etc/qellys/env, which systemd
hands the service and which no other user can read. A command run over ssh
as the service's user (`sudo -u qellys python3 futures_build.py cbb --odds`,
in RUN_NEXT) saw no flag, took the paywall for off, and wrote the full
board onto the public path. Caddy serves that path straight off disk, so it
stayed public until the next restart's seal. The service now records the
flag it was started with at boot. A process whose environment says nothing,
on a box whose settings it cannot read, takes that answer, and with no
record it fails closed.

Run directly: `python3 tests/test_a_hand_run_build_honours_the_paywall.py`
"""
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gate, secrets                                # noqa: E402


@contextmanager
def _box(hidden: bool, flag=None, record=None):
    """A process on a machine whose settings are (or are not) unreadable,
    with QB_PAYWALL set to `flag` (None: unset) and the service's record
    saying `record` (None: no record)."""
    d = Path(tempfile.mkdtemp())
    old_state, old_hidden = gate.STATE_FILE, secrets.system_env_hidden
    old_env = os.environ.get(gate.ENV_ENABLED)
    gate.STATE_FILE = d / ".paywall_state"
    secrets.system_env_hidden = lambda: hidden
    if flag is None:
        os.environ.pop(gate.ENV_ENABLED, None)
    else:
        os.environ[gate.ENV_ENABLED] = flag
    if record is not None:
        gate.STATE_FILE.write_text(record, encoding="utf-8")
    try:
        yield d
    finally:
        gate.STATE_FILE, secrets.system_env_hidden = old_state, old_hidden
        if old_env is None:
            os.environ.pop(gate.ENV_ENABLED, None)
        else:
            os.environ[gate.ENV_ENABLED] = old_env


def test_an_unset_flag_where_the_settings_are_readable_is_off():
    with _box(hidden=False, record="on"):
        assert not gate.enabled(), "a laptop or CI read the box's note"


def test_a_hand_run_build_on_the_box_takes_the_services_answer():
    with _box(hidden=True, record="on"):
        assert gate.enabled()
    with _box(hidden=True, record="off"):
        assert not gate.enabled()


def test_with_no_record_a_hand_run_build_fails_closed():
    with _box(hidden=True):
        assert gate.enabled(), "not told is not the same as off"


def test_the_environment_wins_over_the_record():
    with _box(hidden=True, flag="1", record="off"):
        assert gate.enabled()
    with _box(hidden=True, flag="0", record="on"):
        assert not gate.enabled()


def test_the_service_records_its_flag_at_boot_and_pins_it():
    with _box(hidden=True):
        assert gate.record_state() is False
        assert gate.STATE_FILE.read_text(encoding="utf-8") == "off"
        # Pinned: the service itself never asks the file again.
        gate.STATE_FILE.write_text("on", encoding="utf-8")
        assert os.environ[gate.ENV_ENABLED] == "0" and not gate.enabled()
    with _box(hidden=True, flag="1"):
        assert gate.record_state() is True
        assert gate.STATE_FILE.read_text(encoding="utf-8") == "on"


def test_the_boot_seal_records_before_it_decides_anything():
    import server
    with _box(hidden=True):
        server.seal_on_boot()
        assert gate.STATE_FILE.read_text(encoding="utf-8") == "off"
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    body = src[src.index("def seal_on_boot("):]
    assert body.index("_gate.record_state()") < body.index("if not _gate.enabled():")


def test_a_hand_run_publish_seals_the_public_copy():
    with _box(hidden=True, record="on") as d:
        public = d / "web" / "data" / "futures_cbb.json"
        full_path = gate.publish({"sport": "cbb", "teams": [{"team": "DUKE", "p_title": 0.12}]}, public)[1]
        served = json.loads(public.read_text(encoding="utf-8"))
        assert "teams" not in served and served.get("locked_reason") == "subscription"
        full = json.loads(Path(full_path).read_text(encoding="utf-8"))
        assert full["teams"][0]["team"] == "DUKE", "the members' copy lost its rows"


def test_the_record_is_the_boxs_state_not_code():
    ignored = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read().splitlines()
    assert "data/.paywall_state" in ignored and "data/.paywall_state.tmp" in ignored
    assert gate.STATE_FILE == gate.FULL_DIR.parent / ".paywall_state"


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
