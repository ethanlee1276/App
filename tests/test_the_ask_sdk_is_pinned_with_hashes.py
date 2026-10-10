"""The one installed package arrives at a known version with known bytes.

Audit 2026-09-30, E-6 (roadmap #30). `anthropic` was installed unpinned
from a line in docs/DEPLOY.md, with no requirements file, so every rebuild
of the box could take a different SDK and nothing could say which one was
answering Ask.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REQ = (ROOT / "requirements.txt").read_text()


def _pins():
    """{name: (version, [hashes])} from a pip-compile --generate-hashes file."""
    out, cur = {}, None
    for line in REQ.splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==([\w.]+)", line)
        if m:
            cur = m.group(1).lower()
            out[cur] = (m.group(2), [])
        for h in re.findall(r"--hash=sha256:([0-9a-f]{64})", line):
            out[cur][1].append(h)
    return out


def test_anthropic_is_pinned_and_every_package_carries_a_hash():
    pins = _pins()
    assert "anthropic" in pins and re.match(r"^\d+\.\d+\.\d+$", pins["anthropic"][0])
    assert len(pins) >= 5, "the transitive packages are pinned too"
    for name, (ver, hashes) in pins.items():
        assert hashes, f"{name}=={ver} has no hash — --require-hashes would refuse the file"
    loose = [l for l in REQ.splitlines() if re.match(r"^[A-Za-z]", l) and "==" not in l]
    assert not loose, f"unpinned lines: {loose}"


def test_the_install_line_requires_the_hashes():
    deploy = (ROOT / "docs" / "DEPLOY.md").read_text()
    assert "--require-hashes -r requirements.txt" in deploy
    assert "--ignore-installed typing_extensions anthropic" not in deploy, "the unpinned install is back"


def test_todo_says_when_the_box_drifts_from_the_pin():
    from engine import todo
    pin = _pins()["anthropic"][0]
    assert todo._sdk_pin(pin).state == todo.DONE
    drift = todo._sdk_pin("0.1.0")
    assert drift.state == todo.TODO and pin in drift.evidence and "--require-hashes" in drift.command
    assert "_sdk_pin()" in (ROOT / "engine" / "todo.py").read_text()


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
