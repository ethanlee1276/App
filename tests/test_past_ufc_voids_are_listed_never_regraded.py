"""Past UFC voids that look like the midnight bug, listed and never re-graded.

Ethan, 2026-10-14, to "Want a read-only list of the past voids that look
like it? Their grades stay as they are": yes ("do 1-11").

The bug (fixed in step 47): a bout read from a copy saved before the bell
says "no winner", and after midnight UTC a bout dated the day before with
no winner reads as a draw, which voids. `ufcvoids.py` lists every UFC void,
reads each bout again from ESPN (fresh, never the copy the void came from)
and says which look like the bug and what they would have graded. It writes
nothing to the ledger.

Run directly: `python3 tests/test_past_ufc_voids_are_listed_never_regraded.py`
"""

import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger                                      # noqa: E402
import ufcvoids                                                # noqa: E402

CARD = "2026-09-27"


def _ledger():
    """A card of six picks: four voided as no winner (as the bug voided),
    one voided ten days on with no bout found, one won."""
    path = Path(tempfile.mkdtemp()) / "led.db"
    conn = ledger.connect(path)
    picks = [("Ada Striker", 120, 1.0), ("Bo Grappler", -150, 1.5), ("Cy Draw", 105, 1.0),
             ("Di Quiet", 110, 1.0), ("Ed Winner", -120, 1.0)]
    ledger.log_ufc_picks(conn, {"status": "card", "event_date": CARD, "picks": [
        {"pick": n, "odds": o, "book": "DraftKings", "p_final": 0.55, "edge": 0.05,
         "stake_units": u} for n, o, u in picks]})
    ledger.log_ufc_picks(conn, {"status": "card", "event_date": "2026-08-01", "picks": [
        {"pick": "Fy Gone", "odds": 130, "book": "FanDuel", "p_final": 0.5, "edge": 0.05,
         "stake_units": 1.0}]})
    first = {"Ada Striker": {"won": None, "date": CARD}, "Bo Grappler": {"won": None, "date": CARD},
             "Cy Draw": {"won": None, "date": CARD}, "Di Quiet": {"won": None, "date": CARD},
             "Ed Winner": {"won": True, "date": CARD}}
    ledger.settle_ufc(conn, fetch_result=lambda name, since: first.get(name),
                      today=dt.date(2026, 9, 28))
    return path, conn


#: What ESPN says now, for each fighter.
NOW = {"Ada Striker": {"found": "bout", "won": True, "date": CARD},
       "Bo Grappler": {"found": "bout", "won": False, "date": CARD},
       "Cy Draw": {"found": "bout", "won": None, "date": CARD},
       "Di Quiet": {"found": "unreachable"},
       "Fy Gone": {"found": "bout", "won": True, "date": "2026-08-02"}}


def _now(name, card):
    assert isinstance(card, dt.date)
    return NOW.get(name, {"found": "no bout"})


def _block(lines, name):
    i = next(k for k, x in enumerate(lines) if f"  {name} (" in x)
    return lines[i] + "\n" + lines[i + 1]


def test_the_voids_are_split_by_how_they_voided():
    path, _conn = _ledger()
    lines = ufcvoids.report(path, lookup=_now)
    text = "\n".join(lines)
    assert "5 UFC pick(s) voided in all: 4 as no winner" in text, text
    assert "1 with no bout found within 10 days" in text, text
    assert text.index("NO WINNER") < text.index("Ada Striker") < text.index("NO BOUT WITHIN 10 DAYS") \
        < text.index("Fy Gone"), text
    assert "Ed Winner" not in text, "a graded fight is not a void"


def test_a_bout_espn_now_shows_won_or_lost_is_marked_with_its_grade():
    path, _conn = _ledger()
    lines = ufcvoids.report(path, lookup=_now)
    ada = _block(lines, "Ada Striker")
    assert "(+120, DraftKings, 1u)" in ada, ada
    assert "he WON (bout dated 2026-09-27) — LOOKS LIKE THE BUG; it would have graded won, +1.20u" in ada, ada
    bo = _block(lines, "Bo Grappler")
    assert "he LOST" in bo and "would have graded lost, -1.50u" in bo, bo
    assert lines[-1] == ("LOOKS LIKE THE BUG: 2 — would have won 1 (+1.20u), lost 1 (-1.50u); "
                         "net -0.30u. Their grades stay as they are (void)."), lines[-1]


def test_a_real_draw_and_an_unanswered_read_are_never_called_the_bug():
    path, _conn = _ledger()
    lines = ufcvoids.report(path, lookup=_now)
    assert "a draw or no contest — the void stands" in _block(lines, "Cy Draw")
    assert "ESPN did not answer just now — can't say" in _block(lines, "Di Quiet")
    fy = _block(lines, "Fy Gone")
    assert "not the midnight bug" in fy and "LOOKS LIKE" not in fy, fy


def test_the_void_time_comes_off_the_audit_trail():
    path, _conn = _ledger()
    lines = ufcvoids.report(path, lookup=_now)
    ada = _block(lines, "Ada Striker").splitlines()[0]
    assert "voided 20" in ada and ada.endswith(" UTC"), ada


def test_nothing_in_the_ledger_changes():
    path, conn = _ledger()
    conn.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = sorted(tuple(r) for r in ledger.connect(path).execute(
        "SELECT id, status, pnl_units FROM bets"))
    ufcvoids.report(path, lookup=_now)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert sorted(tuple(r) for r in ledger.connect(path).execute(
        "SELECT id, status, pnl_units FROM bets")) == rows
    src = (ROOT / "ufcvoids.py").read_text(encoding="utf-8")
    assert "mode=ro" in src and "UPDATE" not in src and "INSERT" not in src and "DELETE" not in src


def test_a_lookup_that_raises_is_one_line_not_the_end_of_the_list():
    path, _conn = _ledger()

    def boom(name, card):
        if name == "Ada Striker":
            raise RuntimeError("down")
        return _now(name, card)
    lines = ufcvoids.report(path, lookup=boom)
    assert "can't say" in _block(lines, "Ada Striker")
    assert "LOOKS LIKE THE BUG" in _block(lines, "Bo Grappler")


# --- the ESPN read --------------------------------------------------------------
class _Espn:
    """espnmma's fetch layer, stubbed: answers from a dict, writing the cache
    file as the real one does, or (``down``) handing back the copy on disk."""

    def __init__(self, M, comps, down=()):
        self.M, self.comps, self.down = M, comps, set(down)

    def get(self, url, cache_name, ttl=0):
        path = self.M.CACHE_DIR / cache_name
        if ttl and path.exists() and time.time() - path.stat().st_mtime < ttl:
            return json.loads(path.read_text())
        if cache_name in self.down:
            if path.exists():
                return json.loads(path.read_text())
            raise self.M.DataUnavailable(url)
        data = self.comps[cache_name]
        path.write_text(json.dumps(data))
        return data


def _comp(cid, day, aid_won=None):
    return {"id": cid, "date": f"{day}T02:00Z",
            "competitors": [{"id": "7", "winner": aid_won is True},
                            {"id": "9", "winner": aid_won is False}]}


def _stub(down=(), comps=None):
    from engine.sources import espnmma as M
    old = (M.CACHE_DIR, M._get_json, M.find_athlete_id)
    M.CACHE_DIR = Path(tempfile.mkdtemp())
    log = {"events": {"items": [
        {"competition": {"$ref": "http://x/competitions/101"}},
        {"competition": {"$ref": "http://x/competitions/100"}}]}}
    comps = comps or {"espn_mma_evlog_7_p1.json": log,
                      "espn_mma_res_101.json": _comp("101", "2026-09-28", True),
                      "espn_mma_res_100.json": _comp("100", "2026-05-01", False)}
    fake = _Espn(M, comps, down)
    M._get_json, M.find_athlete_id = fake.get, (lambda name: "7" if name == "Ada Striker" else None)
    return M, old


def _unstub(M, old):
    M.CACHE_DIR, M._get_json, M.find_athlete_id = old


def test_espn_is_read_fresh_and_the_bout_nearest_the_card_answers():
    M, old = _stub()
    try:
        got = ufcvoids.espn_bout("Ada Striker", dt.date(2026, 9, 27))
        assert got == {"found": "bout", "won": True, "date": "2026-09-28"}, got
        assert ufcvoids.espn_bout("Nobody", dt.date(2026, 9, 27)) == {"found": "no fighter"}
        assert ufcvoids.espn_bout("Ada Striker", dt.date(2026, 7, 1)) == {"found": "no bout"}
    finally:
        _unstub(M, old)


def test_the_copy_on_disk_is_never_taken_as_espn_now():
    """The copy the void came from says no winner. ESPN down: the fetch layer
    hands that copy back, and the list must say it could not ask, never that
    the bout had no winner."""
    M, old = _stub(down={"espn_mma_res_101.json"})
    try:
        pre_bell = _comp("101", "2026-09-28", None)
        stale = M.CACHE_DIR / "espn_mma_res_101.json"
        stale.write_text(json.dumps(pre_bell))
        os.utime(stale, (time.time() - 86400 * 10, time.time() - 86400 * 10))
        assert ufcvoids.espn_bout("Ada Striker", dt.date(2026, 9, 27)) == {"found": "unreachable"}
    finally:
        _unstub(M, old)
    M, old = _stub(down={"espn_mma_evlog_7_p1.json"})
    try:
        assert ufcvoids.espn_bout("Ada Striker", dt.date(2026, 9, 27)) == {"found": "unreachable"}
    finally:
        _unstub(M, old)


def test_the_runbook_names_the_command():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "sudo -u qellys python3 ufcvoids.py" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
