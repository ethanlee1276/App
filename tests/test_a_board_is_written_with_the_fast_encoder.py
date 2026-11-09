"""A board is written with the fast encoder, its browser copy made once, and
the board it replaces read only when it could be a downgrade
(engine/gate.publish, _compact, _write_served_sidecar, would_downgrade).

The NFL build's write stage took 14 to 17 seconds on 8 November. `json.dump`
to a file always takes the standard library's pure-Python encoder (only
`json.dumps` without an indent takes the C one: 1.19 s against 0.32 s on an
11.4 MB board); the browser's copy (`served`) was built twice, once for the
members' sidecar and once for the public file; and the downgrade guard read
and parsed the private copy it was about to replace (18 MB of indented JSON
for the NFL) on every publish, though on every ordinary build the new
board's own prices clear it. What these hold:

  * every file a publish writes is byte for byte what it wrote before —
    the private copy, the public copy (paywall off and on) and the sidecar,
    on a real board and on one built to trip an encoder (unicode, NaN,
    infinity, numeric and boolean keys);
  * the browser's copy is made once a publish;
  * the guard reads the old board only when the new one has no prices and
    says its odds attempt failed — and still refuses a real downgrade;
  * a check that raises is asked again the old way, deciding the same;
  * inside a build a publish names its steps' seconds (the NFL build's
    publish ran 22.4 seconds at 02:11 on 9 November with nothing to say
    which step), and outside one it prints nothing.

Run directly: `python3 tests/test_a_board_is_written_with_the_fast_encoder.py`
"""
import contextlib
import copy
import io
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gate                                             # noqa: E402
from engine.served import served                                    # noqa: E402


def _env(**kv):
    keep = {k: os.environ.get(k) for k in kv}
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    def restore():
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


def _old_bytes(payload, label):
    """What publish wrote before: the three files, each by `json.dump`,
    after the bet-slip links it stamps into the rows."""
    from engine import betlinks
    payload = copy.deepcopy(payload)
    payload = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    betlinks.stamp(payload, label)
    full, pub, side = io.StringIO(), io.StringIO(), io.StringIO()
    json.dump(payload, full, indent=2)
    doc = served(payload)
    doc = gate.redact(doc, label) if gate.enabled() else doc
    json.dump(doc, pub, separators=(",", ":"))
    json.dump(served(payload), side, separators=(",", ":"))
    return full.getvalue(), pub.getvalue(), side.getvalue()


def _real_board():
    from engine.pipeline import run_slate
    with contextlib.redirect_stdout(io.StringIO()):
        return run_slate(os.path.join(ROOT, "data", "sample_slate.json"))


def _tricky_board():
    return {"sport": "nfl", "date": "2026-11-08", "note": "Ståle — “quotes” ☂ 🏈   tab\t",
            "recommendations": [{"player": "Amon-Ra St. Brown", "book": "fanduel", "has_market": True,
                                 "prob": 0.1 + 0.2, "edge": float("nan"), "ceiling": float("inf"),
                                 "floor": -float("inf"), "big": 10 ** 30, "neg": -0.0,
                                 "alt_lines": [{"line": 5.5}], "rung_probs": {"5.5": 0.4}}],
            "most_likely": [{"player": "A", "market": "receptions"}],
            "board_shelves": [{"key": "likely", "rows": [{"player": "A", "market": "receptions"}]}],
            "by_number": {1: "one", 2.5: "two and a half", True: "yes", None: "nothing"},
            "empty": {}, "nested": [[[]], {"a": [1, 2, {"b": None}]}]}


def _publish(payload, label="nfl.json"):
    root = Path(tempfile.mkdtemp())
    public = root / "web" / "data" / label
    with contextlib.redirect_stdout(io.StringIO()):
        pub, full = gate.publish(copy.deepcopy(payload), public)
    side = gate.served_sidecar(Path(full))
    return (Path(full).read_text(), Path(pub).read_text(), side.read_text())


def test_every_file_is_byte_for_byte_what_it_was():
    for paywall in (None, "1"):
        restore = _env(QB_PAYWALL=paywall)
        try:
            for board in (_real_board(), _tricky_board()):
                want = _old_bytes(board, "nfl.json")
                got = _publish(board)
                for name, a, b in zip(("private", "public", "sidecar"), want, got):
                    assert a == b, f"{name} copy differs (paywall {paywall})"
        finally:
            restore()
    tricky = json.loads(_publish(_tricky_board())[1])
    assert math.isnan(tricky["recommendations"][0]["edge"]) and "alt_lines" not in tricky["recommendations"][0]


def test_the_browsers_copy_is_made_once_a_publish():
    calls = []
    keep = gate.served
    gate.served = lambda p: calls.append(1) or keep(p)
    try:
        _publish(_tricky_board())
    finally:
        gate.served = keep
    assert len(calls) == 1, f"served {len(calls)} times"


class _Reads:
    """Which files the guard opened."""

    def __enter__(self):
        self.seen, self.keep = [], Path.read_text
        seen, keep = self.seen, self.keep
        Path.read_text = lambda p, *a, **k: seen.append(str(p)) or keep(p, *a, **k)
        return self.seen

    def __exit__(self, *exc):
        Path.read_text = self.keep


def _priced():
    return {"recommendations": [{"player": "A", "book": "fanduel", "has_market": True}],
            "odds_status": {"checked": True, "matched": 3, "events": 2}}


def _unpriced(failed: bool):
    return {"recommendations": [{"player": "A", "book": "", "has_market": False}],
            "odds_status": ({"checked": True, "error": "401 from the odds API"} if failed
                            else {"checked": True, "matched": 0, "events": 2})}


def test_the_guard_reads_the_old_board_only_when_it_could_be_a_downgrade():
    full = Path(tempfile.mkdtemp()) / "nfl.json"
    full.write_text(json.dumps(_priced()), encoding="utf-8")
    with _Reads() as seen:
        assert gate.would_downgrade(_priced(), full, "nfl.json") is False
        assert gate.would_downgrade(_unpriced(failed=False), full, "nfl.json") is False
    assert str(full) not in seen, "an ordinary build never opens the board it replaces"
    with _Reads() as seen:
        assert gate.would_downgrade(_unpriced(failed=True), full, "nfl.json") is True, \
            "a real downgrade is still refused"
    assert str(full) in seen
    full.write_text(json.dumps(_unpriced(failed=False)), encoding="utf-8")
    assert gate.would_downgrade(_unpriced(failed=True), full, "nfl.json") is False, \
        "the old board had no prices either"
    assert gate.would_downgrade(_priced(), Path(tempfile.mkdtemp()) / "none.json", "nfl.json") is False


def test_a_check_that_raises_is_asked_again_the_old_way():
    full = Path(tempfile.mkdtemp()) / "nfl.json"
    full.write_text("{ torn", encoding="utf-8")
    odd = {"recommendations": 7, "odds_status": {"checked": True, "error": "x"}}   # not iterable
    assert gate.would_downgrade(odd, full, "nfl.json") is False, "unreadable old board: not evidence, as before"
    full.write_text(json.dumps(_priced()), encoding="utf-8")
    try:
        gate.would_downgrade(odd, full, "nfl.json")
        raised = False
    except TypeError:
        raised = True
    assert raised, "with a readable old board the bad payload raises where it always did"


def test_the_publish_refuses_a_downgrade_and_keeps_the_board():
    root = Path(tempfile.mkdtemp())
    public = root / "web" / "data" / "nfl.json"
    with contextlib.redirect_stdout(io.StringIO()):
        gate.publish(_priced(), public)
        before = Path(gate.board_source(public)).read_text()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gate.publish(_unpriced(failed=True), public)
    assert "REFUSED" in buf.getvalue()
    assert Path(gate.board_source(public)).read_text() == before


def test_a_publish_names_its_steps_only_inside_a_build():
    from engine import stageclock
    keep = dict(stageclock._STATE)
    root = Path(tempfile.mkdtemp())
    public = root / "web" / "data" / "nfl.json"
    try:
        stageclock._STATE.update(t0=None, last=None)
        quiet = io.StringIO()
        with contextlib.redirect_stdout(quiet):
            gate.publish(copy.deepcopy(_tricky_board()), public)
        assert "⏱" not in quiet.getvalue(), "the loop's refreshers and the tests print no clock"
        stageclock.start()
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            gate.publish(copy.deepcopy(_tricky_board()), public)
        lines = said.getvalue().splitlines()
        parts = stageclock.parse_parts(lines)
        assert list(parts) == ["publish nfl.json"], parts
        assert list(parts["publish nfl.json"]) == ["prepare", "bet links", "downgrade check", "served copy",
                                                   "private copy", "sidecar", "public copy"], parts
        assert all(v >= 0 for v in parts["publish nfl.json"].values())
        assert stageclock.parse(lines) == {}, "a part is never counted as a stage"
    finally:
        stageclock._STATE.clear()
        stageclock._STATE.update(keep)


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
            traceback.print_exc(limit=5)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
