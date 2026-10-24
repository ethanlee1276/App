"""tools/catchup.sh: every any-day check in the runbook, in one go, and read-only.

Ethan, 2026-10-15: "check the runbook and make sure that there's no code
at all that I still need to run". Forty-odd lettered blocks in
docs/WHEN_YOU_ARE_HOME.md had never been pasted back, so the ones that can
run on any day became one script. These checks hold it to the runbook,
word for word, so the two cannot drift apart; keep it free of every
command that writes; and check that one block can neither swallow the next
one's lines nor stop the rest by running long.

Run directly: `python3 tests/test_the_catchup_script_is_the_runbooks_own_checks.py`
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "catchup.sh"
RUNBOOK = ROOT / "docs" / "WHEN_YOU_ARE_HOME.md"

#: The only lines that differ from the runbook, each named in the
#: script's own header with its reason.
CHANGED = {
    # AD's test, printed and not saved (the runbook: "add `--dry-run` to
    # print without saving").
    "cd /srv/qellys && sudo -u qellys nice -n 19 python3 -m engine.mlb.xstatsfit --dry-run",
    # K reads the last 20 lines of the weekly chart-fill log, not all of it.
    'journalctl -u qellys --since "today" --no-pager | grep -E "charts:|engine.chartfill" | tail -8; '
    "sudo -u qellys tail -20 /srv/qellys/data/cache/weekly_chartfill.log",
}

#: Words that mean a command writes something. None may appear in a block.
WRITES = ("--fill", "--apply", "setenv", "systemctl restart", "facesfill.py --sport", "x.save(",
          "-m engine.chartfill", "nbacodes", "--repair", "UPDATE ", "INSERT ", "DELETE ", "rm -",
          "> /srv", ">> /srv", "savant 2026", "launch.py --resettle")


def _sections():
    """[(label, title, limit, [command lines])] in the script's order."""
    out, cur = [], None
    for line in SCRIPT.read_text().split("\n"):
        m = re.match(r'^run (\w+) "([^"]+)" (\d+) <<\'SH\'$', line)
        if m:
            cur = (m.group(1), m.group(2), int(m.group(3)), [])
            continue
        if cur and line == "SH":
            out.append(cur)
            cur = None
            continue
        if cur:
            cur[3].append(line)
    assert cur is None, "a block is never closed"
    return out


def _runbook_letters():
    return set(re.findall(r"^\*\*([A-Z]{1,2})\. ", RUNBOOK.read_text(), re.M))


def test_the_script_is_valid_bash():
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_command_is_the_runbooks_own_line():
    book = set(RUNBOOK.read_text().split("\n"))
    stray = [ln for _l, _t, _s, lines in _sections() for ln in lines
             if ln.strip() and ln not in book and ln not in CHANGED]
    assert not stray, stray
    used = {ln for _l, _t, _s, lines in _sections() for ln in lines}
    assert CHANGED <= used, CHANGED - used


def test_nothing_in_it_writes():
    for label, _t, _s, lines in _sections():
        for ln in lines:
            hit = [w for w in WRITES if w in ln]
            assert not hit, (label, hit, ln)


def test_every_block_is_a_runbook_block_and_the_timed_ones_wait():
    letters = _runbook_letters()
    labels = [re.sub(r"\d+$", "", lab) for lab, _t, _s, _l in _sections()]
    assert set(labels) <= letters, set(labels) - letters
    # The ones that need a moment that is not "any day" are named and left out.
    head = SCRIPT.read_text().split("set -u")[0]
    for later in ("BG", "BH", "BI", "BJ"):
        assert later not in labels and later in head, later
    # BK waited for week 6 to settle; it has (2026-10-24), so it runs.
    assert "BK" in labels
    # Done already, or answered: not run again.
    for done in ("I", "L", "AG", "AI", "BB", "BC", "BD"):
        assert done not in labels, done


def test_every_block_has_a_limit_and_the_slow_ones_come_last():
    secs = _sections()
    assert len(secs) >= 40
    assert all(0 < s <= 2400 for _l, _t, s, _x in secs)
    slow = [lab for lab, _t, s, _x in secs if s >= 600]
    tail = [lab for lab, _t, _s, _x in secs][-len(slow):]
    assert slow == tail, (slow, tail)


def test_a_block_cannot_swallow_the_next_or_stop_the_rest():
    src = SCRIPT.read_text()
    fn = re.search(r"^run\(\) \{.*?^\}", src, re.S | re.M).group(0)
    assert "< /dev/null" in fn and "timeout" in fn
    demo = fn + "\n".join([
        "", "run X1 \"reads stdin\" 5 <<'SH'", "cat; echo after-cat", "SH",
        "run X2 \"runs long\" 1 <<'SH'", "sleep 3; echo never", "SH",
        "run X3 \"still runs\" 5 <<'SH'", "echo third-ran", "SH", ""])
    r = subprocess.run(["bash", "-c", demo], capture_output=True, text=True, timeout=30)
    out = r.stdout
    assert "after-cat" in out and "third-ran" in out, out
    assert "never" not in out and "(stopped after 1s)" in out, out
    assert out.index("===== X1.") < out.index("===== X2.") < out.index("===== X3."), out


def test_letters_run_those_blocks_only():
    """The runbook's DH (2026-10-24): `catchup.sh CT CU ...` runs the checks
    from CT on and nothing else; a letter also runs its numbered twin."""
    src = SCRIPT.read_text()
    fn = re.search(r"^run\(\) \{.*?^\}", src, re.S | re.M).group(0)
    demo = 'ONLY=" X1 DB "\n' + fn + "\n".join([
        "", "run X1 \"asked\" 5 <<'SH'", "echo one-ran", "SH",
        "run X2 \"not asked\" 5 <<'SH'", "echo two-ran", "SH",
        "run DB2 \"a twin\" 5 <<'SH'", "echo twin-ran", "SH", ""])
    out = subprocess.run(["bash", "-c", demo], capture_output=True, text=True, timeout=30).stdout
    assert "one-ran" in out and "twin-ran" in out and "two-ran" not in out, out
    assert '[ "$#" -gt 0 ] && ONLY=" $* "' in src
    labels = [lab for lab, _t, _s, _l in _sections()]
    for letter in ("CT", "CU", "CV", "CW", "CX", "CY", "CZ", "DA", "DB", "DC", "DE", "DH", "BK", "DB2", "DD", "DG"):
        assert letter in labels, letter
    assert not any("catchup.sh" in ln for _l, _t, _s, lines in _sections() for ln in lines), "it never calls itself"
    assert src.rstrip().endswith('echo "===== done in $((SECONDS / 60)) min"'), "the last line says it is done"


def test_it_refuses_to_run_without_root():
    src = SCRIPT.read_text()
    assert 'if [ "$(id -u)" != 0 ]; then' in src


def test_the_runbook_names_it():
    text = RUNBOOK.read_text()
    assert "nice -n 19 bash tools/catchup.sh 2>&1 | tee /tmp/catchup.txt" in text


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
