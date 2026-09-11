"""Is the data we add actually used, or is it just sitting there?

Ethan asked exactly that, and on the day he asked it `velocity.py` — ten
tests, validated against a real pitcher — had zero consumers outside its
own module and a CLI probe.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import datause                                      # noqa: E402


def test_the_auditor_does_not_count_itself_as_a_consumer():
    """Its registry names every symbol it hunts for, so scanning its own
    file finds all of them and reports each signal as read — by the thing
    checking whether anything reads it. The first run said "pitch counts:
    ok, in pipeline" purely on that."""
    files = [str(p) for p in datause._py_files()]
    assert not any(f.endswith("engine/datause.py") for f in files)


def test_shell_scripts_count_as_consumers():
    """`tools/lineups.sh` calls `lineuptimes.coverage()` after every
    watch, which is the only thing that reads that store on a normal day.
    Skipping tools/ reported the lineup boundary INERT while a scheduled
    agent used it nightly."""
    files = [str(p) for p in datause._py_files()]
    assert any(f.endswith("tools/lineups.sh") for f in files)


def test_tests_do_not_count_as_consumers():
    """A signal read only by its own test is not used, and counting it
    would make this check congratulate itself."""
    files = [str(p) for p in datause._py_files()]
    assert not any("/tests/" in f for f in files)


def test_every_registered_signal_declares_where_it_should_land():
    for sig in datause.SIGNALS:
        assert sig["want"], f"{sig['name']} declares no destination"
        assert set(sig["want"]) <= set(datause._KINDS), sig["name"]
        assert sig["why"], f"{sig['name']} gives no reason"
        assert os.path.exists(os.path.join(datause.ROOT, sig["module"])), \
            sig["module"]


def test_a_signal_nothing_reads_is_reported_INERT():
    """The whole point. A fabricated signal no file mentions must come
    back inert rather than quietly passing."""
    fake = {"name": "nothing reads this", "module": "engine/datause.py",
            "symbols": ("zzz_a_symbol_no_file_contains_zzz",),
            "want": ("journal",), "why": "a control"}
    real = datause.SIGNALS
    datause.SIGNALS = real + (fake,)
    try:
        row = [r for r in datause.audit() if r["name"] == fake["name"]][0]
        rendered = datause.report()      # inside the try: the fake must
    finally:                             # still be registered to appear
        datause.SIGNALS = real
    assert row["inert"] is True
    assert row["missing"] == ["journal"]
    assert "INERT" in rendered


def test_the_first_mover_signal_reaches_the_journal():
    """It was INERT for a day: computed, tested, and read by nothing.
    Rendering it into a summary string was not enough — no other module
    could branch on it. Journaling makes it minable, which is what makes
    it useful, and is not the same as pricing from it."""
    row = [r for r in datause.audit()
           if r["name"] == "first-mover attribution"][0]
    assert not row["inert"], row
    assert "journal" in row["have"], row


def test_no_registered_signal_is_inert():
    """The check that will fail the next time something is built and left
    sitting. That is the failure it exists to cause."""
    inert = [r["name"] for r in datause.audit() if r["inert"]]
    assert not inert, f"nothing reads: {inert}"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
