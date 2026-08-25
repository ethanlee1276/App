"""The docs' ✅ rows, checked against the code they claim.

Each model doc ends with an implementation map: one row per rule in the
spec, a ✅ when it is built, and the evidence — the file, usually the
constant or function. Those rows are the only place this system states
what it has finished, and they are prose, so nothing stops them rotting.
Rename a constant while fixing something and the row still cites the old
name; move a module and the row still names the old path. The map then
reads as authoritative and is quietly wrong, which is worse than no map.

Two properties, and the second is the one that makes it worth running:

  * it CATCHES a rename. A check that cannot fail is decoration, and this
    repo already applies that rule to its reconciliation gate.
  * it does not cry wolf. The first version reported ten renames that had
    not happened — it resolved `rules.py` literally instead of finding
    `engine/rules.py`, and looked for `betting.temper_edge` only inside
    the other file the same row cited. Ten false alarms is an audit
    nobody reads, and then the real drift walks past too.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mapcheck                                            # noqa: E402

ROOT = Path(mapcheck.ROOT)


def _doc(body: str) -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "FAKE_MODEL.md").write_text(
        "| rule | built | evidence |\n|---|---|---|\n" + body,
        encoding="utf-8")
    return d


def _audit_with(docs: Path):
    saved = mapcheck.DOCS
    mapcheck.DOCS = docs
    try:
        return mapcheck.audit()
    finally:
        mapcheck.DOCS = saved


# --- it catches drift ------------------------------------------------------
def test_a_renamed_constant_is_caught():
    """THE point. A ✅ row is the system's own claim that something is
    finished; one citing a constant that no longer exists is the map
    disagreeing with the code, and the map is what gets believed.

    The name is assembled at run time on purpose. `tests/` is inside the
    corpus the audit searches — as it should be, since a symbol a test
    references does exist — so spelling a fake constant as a literal here
    would put it in the corpus and the audit would correctly find it. The
    first version of this test did exactly that and passed nothing."""
    gone = "ZQ" + "_VANISHED_" + "CONSTANT"
    out = _audit_with(_doc(
        f"| §9 Something | ✅ | `engine/mlb/gamesim.py` `{gone}` |\n"))
    assert any(f["what"] == gone for f in out), out
    assert out[0]["kind"] == "symbol"


def test_a_deleted_file_is_caught():
    out = _audit_with(_doc(
        "| §9 Something | ✅ | `engine/definitely_gone.py` does it |\n"))
    assert any(f["kind"] == "path" and "definitely_gone" in f["what"]
               for f in out), out


def test_a_row_without_a_tick_is_not_audited():
    """A 📋 row is a promise, not a claim. Auditing it would report every
    parked idea as drift."""
    assert _audit_with(_doc(
        "| §9 Parked | 📋 | `engine/not_built_yet.py` |\n")) == []


# --- and it does not cry wolf ---------------------------------------------
def test_a_bare_filename_resolves_anywhere_in_the_tree():
    """The docs cite `rules.py` as often as `engine/rules.py`. Resolving
    only the literal string reported ten renames that had not happened."""
    assert _audit_with(_doc("| §9 X | ✅ | `rules.py` gates it |\n")) == []
    assert _audit_with(_doc("| §9 X | ✅ | `test_cfb.py` covers it |\n")) == []


def test_a_symbol_is_found_wherever_it_actually_lives():
    """`betting.temper_edge` cited beside `engine/quality.py` is untidy
    prose, not drift. A row citing the right symbol in the wrong module is
    a judgement call; a row citing a symbol that no longer exists is a
    fact. Only facts are reported."""
    assert _audit_with(_doc(
        "| §3 Haircut | ✅ | `engine/quality.py` TIER_SHRINK feeding "
        "`betting.temper_edge` |\n")) == []


def test_prose_in_backticks_is_not_mistaken_for_code():
    """These docs backtick market names, JSON keys and shell fragments.
    Reporting those would bury the one row that matters."""
    assert _audit_with(_doc(
        "| §9 X | ✅ | pays on `total_bases` when `over` clears, see the "
        "`Record` tab |\n")) == []


# --- the live map ----------------------------------------------------------
def test_the_real_implementation_map_is_clean():
    """The whole point of committing this: the shipped docs pass it. If
    this ever fails, either a doc row or the code moved, and the two no
    longer agree."""
    found = mapcheck.audit()
    assert found == [], found


def test_it_actually_checked_a_meaningful_number_of_rows():
    """A parser that silently matches nothing would also report clean."""
    rows = sum(1 for d in sorted(Path(mapcheck.DOCS).glob("*.md"))
               for _ in mapcheck._rows(d))
    assert rows > 100, rows


def test_quiet_mode_says_nothing_and_returns_the_verdict():
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mapcheck.main(["--quiet"])
    # THE VERDICT, AND WHAT IT WAS ABOUT. A bare `assert code == 0` fired
    # twice on GitHub Actions on 2026-08-25 — same commit, one run red
    # and the next green — and reported nothing but "AssertionError",
    # which says the map is dirty without saying which row. Quiet mode
    # prints nothing by design, so the message has to re-run the audit to
    # have anything to say. A check that can fail without explaining
    # itself costs an afternoon every time it does.
    assert code == 0, ("mapcheck --quiet reported drift: "
                       f"{mapcheck.audit()}")
    assert buf.getvalue() == ""


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
