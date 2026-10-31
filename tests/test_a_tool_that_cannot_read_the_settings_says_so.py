"""A tool that cannot read the box's settings says so, never "not set" (the
box, 2026-10-28).

Ethan's catch-up ran `sudo -u qellys python3 -m engine.trialnote`, and it
printed "Mail relay: NOT configured — nothing will send". The settings live
in /etc/qellys/env, root's and mode 600: the service has them from systemd,
and the service's user at a prompt cannot read them, so it cannot know.
What these hold:

  - engine.secrets.system_env_hidden is True when the file is there and this
    user cannot read it (or cannot look inside its folder), and False when
    there is no file or it reads;
  - trialnote's mail line then says it cannot see them and how to list the
    names (never the values), and says NOT configured only when it could
    look and they are not there.

    python3 tests/test_a_tool_that_cannot_read_the_settings_says_so.py
"""
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import accounts as A          # noqa: E402
from engine import mailer as M            # noqa: E402
from engine import secrets as S           # noqa: E402
from engine import trialnote as TN        # noqa: E402


@contextlib.contextmanager
def _patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


class _NoEntry:
    """A settings file in a folder only root may enter."""
    def stat(self):
        raise PermissionError(13, "Permission denied")


def test_hidden_only_when_the_file_is_there_and_will_not_read():
    with tempfile.TemporaryDirectory() as d:
        env = Path(d) / "env"
        with _patched(S, "_SYSTEM_ENV_FILE", env):
            assert S.system_env_hidden() is False, "no file: nothing hidden, and a tool may say not set"
            env.write_text("QB_MAIL_FROM=you@example.com\n")
            assert S.system_env_hidden() is False, "it reads"
            with _patched(os, "access", lambda p, mode: False):
                assert S.system_env_hidden() is True, "root's, mode 600, read by the service's user"
        with _patched(S, "_SYSTEM_ENV_FILE", _NoEntry()):
            assert S.system_env_hidden() is True


def _mail_line(hidden: bool) -> str:
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as d, _patched(A, "DB_PATH", Path(d) / "a.db"), \
            _patched(M, "configured", lambda: False), _patched(S, "system_env_hidden", lambda: hidden), \
            contextlib.redirect_stdout(out):
        assert TN._cli([]) == 0
    return [ln for ln in out.getvalue().splitlines() if ln.startswith("Mail relay:")][0]


def test_the_mail_line_says_it_cannot_see_rather_than_not_set():
    line = _mail_line(hidden=True)
    assert "not visible to this user" in line and "NOT configured" not in line, line
    assert "sudo ./deploy/setenv.sh --show" in line, "names and lengths, never a value"
    assert _mail_line(hidden=False) == "Mail relay: NOT configured — nothing will send (docs/EMAIL.md)."


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
