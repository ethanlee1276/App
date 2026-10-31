"""The public repository holds no way in (2026-10-28).

This repository is public on GitHub. From 2026-08-20 a redemption code (a
free year, for up to a hundred accounts) sat in its docs, its deploy
scripts and its tests, and the members' Discord invite in two more files:
anybody who read them had a way in. The real ones are pasted at a prompt
(`sudo ./deploy/setenv.sh NAME`) and live in /etc/qellys/env only. What
these hold, over every tracked text file:

  - a Discord invite is a placeholder;
  - every code written as CODE:months:uses is an example;
  - the go-live wizard writes no code and offers no invite of its own.

    python3 tests/test_the_public_repository_holds_no_way_in.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The placeholders, and the fixtures that only ever meet a test's own env.
INVITES = {"...", "xxxxxxxx", "PROBEcode", "aB3", "first", "abc"}
CODES = {"EXAMPLECODE", "ONEMONTH", "PAIR", "SOLO", "REAL", "GOOD", "CODE", "SOMECODE"}


def _tracked():
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    for name in names.decode().split("\0"):
        path = ROOT / name
        if not name or path.suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff2", ".gz", ".db"):
            continue
        try:
            yield name, path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue


def test_no_invite_but_a_placeholder():
    found = {(name, m.group(1)) for name, text in _tracked()
             for m in re.finditer(r"discord(?:\.gg|\.com/invite|app\.com/invite)/([A-Za-z0-9._-]+)", text)}
    real = sorted(f"{n}: {c}" for n, c in found if c not in INVITES)
    assert not real, f"an invite in a public file (paste it at the prompt instead): {real}"
    assert found, "the scan read nothing"


def test_every_code_written_down_is_an_example():
    found = set()
    for name, text in _tracked():
        for line in text.splitlines():
            if "QB_CODES" in line:
                found |= {(name, c) for c in re.findall(r"\b([A-Za-z][A-Za-z0-9_-]{2,}):\d+:\d+\b", line)}
    real = sorted(f"{n}: {c}" for n, c in found if c.upper() not in CODES)
    assert not real, f"a redemption code in a public file: {real}"
    assert {c for _n, c in found} >= {"EXAMPLECODE"}, found


def test_the_wizard_writes_no_code_and_offers_no_invite():
    src = (ROOT / "deploy" / "golive.sh").read_text(encoding="utf-8")
    code = re.sub(r"(?m)^\s*#.*$", "", src)
    assert '"$SETENV" QB_CODES' not in code, "the wizard sets a code again"
    assert '"${QB_DEFAULT_DISCORD:-}"' in code and '"${QB_DEFAULT_EMAIL:-}"' in code
    assert "Paste it, or press Enter to skip" in code, "an empty default must skip, not set an empty value"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
