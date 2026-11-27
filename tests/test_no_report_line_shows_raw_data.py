"""No game report line shows raw data (step AIJ, 27 November 2026).

From 19 October to step AIH, an NFL or college report whose defense had a starting corner ruled out printed the
scan's stored record as it was ("DET is without {'name': ..., 'spot': 'RCB', 'status': 'Out'} in the secondary").
No test had a corner out, and nothing read the reports for text a reader should never see. This one builds every
league's sample report, the NFL's with a starting corner on injured reserve, and reads every line for: a stored
record or list, None, nan, undefined, a long unrounded decimal, a template left in, a corner's code, a status code
("is ir"), "a 80" for "an 80", a double space or full stop, a space before a comma, and empty brackets.

    python3 tests/test_no_report_line_shows_raw_data.py
"""
import contextlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

#: (pattern, what it means): text no reader should see in a report line.
BAD = [(r"\{'|\{\"", "a stored record"), (r"\['|\[\"", "a stored list"), (r"\bNone\b", "None"),
       (r"\bnan\b|\bNaN\b", "nan"), (r"\bundefined\b", "undefined"), (r"\d\.\d{4,}", "a long decimal"),
       (r"\$\{|\{[a-z_]+\}", "a template left in"), (r"\((LCB|RCB|NB)\)|\b(LCB|RCB) corner\b", "a corner's code"),
       (r" is (ir|pup)\b", "a status code"), (r"\ba (8\d?(\.\d)?|11|18)\b", "a for an"), (r"\S  +\S", "a double space"),
       (r" ,", "a space before a comma"), (r"[^.]\.\.(?!\.)", "a double full stop"), (r"\(\s*\)", "empty brackets")]
#: Keys that hold codes for the page, not words for the reader.
CODE_KEYS = {"lean", "claims", "key", "type", "kind", "id", "game_id", "market", "side", "team", "url", "href",
             "icon", "tone", "source", "word_key", "other", "unit", "spot"}


def _strings(x, out, path=""):
    if isinstance(x, str):
        out.append((path, x))
    elif isinstance(x, dict):
        for k, v in x.items():
            if k not in CODE_KEYS:
                _strings(v, out, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _strings(v, out, f"{path}[{i}]")


def _reports():
    import test_every_college_game_gets_a_report as CB
    import test_every_league_gets_a_game_report as LT
    import test_the_college_game_report as CT
    import test_the_game_report_reads_like_the_research as T
    from engine import gamereport as R
    from engine import leaguereport as L
    out = []
    with contextlib.redirect_stdout(io.StringIO()):
        out.append(("nfl", T._report()))
        board = T._board()
        cov = board["games"][0]["scan"]["coverage"] if "scan" in board["games"][0] else None
        if cov is None:
            cov = next(v for v in board.values() if isinstance(v, dict) and "coverage" in v)["coverage"]
        cov["DET"]["missing"] = [{"name": "Gone Starter", "spot": "RCB", "status": "IR"}]
        cov["DET"]["corners"].append({"name": "Fill In", "spot": "RCB", "targets": 9, "rating": 88.0,
                                      "yds_per_tgt": 6.1, "td": 0, "next_man_up": True})
        out.append(("nfl, a corner out", R.build(board["games"][0], board, allowed=T.ALLOWED, names=T.NAMES)))
        out.append(("cfb", CT._report()[1]))
        for sport, fn in (("mlb", LT._mlb_board), ("nhl", LT._nhl_board)):
            out.append((sport, LT._attach(fn(), sport)[0]))
        board, meta = LT._nba_board()
        out.append(("nba", LT._attach(board, "nba", meta=meta)[0]))
        b = CB._board()
        L.attach(b, "cbb")
        out += [("cbb", r) for r in b.get("game_reports") or []]
    return out


def test_every_sample_report_reads_as_words():
    reps = _reports()
    assert len(reps) >= 7 and all(isinstance(r, dict) and r.get("sections") for _n, r in reps), \
        [(n, type(r).__name__) for n, r in reps]
    bad = []
    for name, rep in reps:
        lines = []
        _strings(rep, lines)
        assert len(lines) > 30, (name, len(lines))
        for path, s in lines:
            for pat, what in BAD:
                m = re.search(pat, s)
                if m:
                    bad.append(f"{name} {path} [{what}]: …{s[max(0, m.start() - 50): m.end() + 50]}…")
    assert not bad, "\n".join(bad)


def test_the_corner_out_case_is_in_the_sample():
    rep = dict(_reports())["nfl, a corner out"]
    lines = []
    _strings(rep, lines)
    assert any("DET is without right cornerback Gone Starter (on injured reserve) in the secondary" in s
               for _p, s in lines)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:                                       # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {e!r}"[:3000])
    print(f"\n{len(fns) - failed} tests passed." if not failed else f"\n{failed} failed.")
    sys.exit(1 if failed else 0)
