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



def test_a_paid_pull_without_the_key_says_the_settings_are_roots():
    """The box, 2026-11-14: Ethan's `sudo -u qellys python3 futures_build.py
    cbb --odds` printed "No Odds API key ... get a free key", with the key
    sitting in /etc/qellys/env where the service reads it. It now says the
    file is root's and how to pass the key in, and still says "set one"
    where there is no file to read."""
    from engine.sources import oddsapi as OA
    keep = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("ODDS_API_KEY")}
    try:
        with _patched(OA, "api_keys", lambda explicit=None: []):
            with _patched(S, "system_env_hidden", lambda: True):
                try:
                    OA.get_api_key()
                    raise AssertionError("no key, no pull")
                except OA.OddsAPIError as exc:
                    said = str(exc)
                assert "/etc/qellys/env" in said and "only root can read" in said, said
                assert "sudo -u qellys env $(sudo grep -E '^ODDS_API_KEY' /etc/qellys/env | xargs) python3" in said
                assert "get a free key" not in said, "the box has one"
            with _patched(S, "system_env_hidden", lambda: False):
                try:
                    OA.get_api_key()
                    raise AssertionError("no key, no pull")
                except OA.OddsAPIError as exc:
                    assert "Set ODDS_API_KEY" in str(exc), "with nothing hidden, it says set one"
    finally:
        os.environ.update(keep)
    # The runbook's own command passes the key the same way.
    for doc in ("docs/RUN_NEXT.md", "docs/WHEN_YOU_ARE_HOME.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "sudo -u qellys python3 futures_build.py cbb --odds" not in text, doc
        assert ("sudo -u qellys env $(sudo grep -E '^ODDS_API_KEY' /etc/qellys/env | xargs) "
                "python3 futures_build.py cbb --odds") in text, doc

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
