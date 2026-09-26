"""Zeno's record up to 9/26, carried in from Pikkit's own cards.

Ethan, 2026-09-26: Juice Reel's API is still pending, Pikkit's export is
paid, and no free tracker both syncs and hands the bets out, so "can i
just tell you my pikkit record and send you screenshots". He sent
Pikkit's All time, 2026 and September 2026 cards (Verified, synced from
the books). data/zeno_snapshot.json holds what they say; the cards sit
beside the numbers on his page as the receipts; a ticket imported later
counts only if it settled after the snapshot, so nothing is counted
twice.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import zeno as Z                                          # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
SNAP = json.load(open(os.path.join(ROOT, "data", "zeno_snapshot.json"), encoding="utf-8"))


def _db():
    return Z.connect(os.path.join(tempfile.mkdtemp(), "zeno.db"))


def test_the_cards_as_sent():
    w = {x["key"]: x for x in SNAP["windows"]}
    assert (w["all"]["profit"], w["all"]["roi"], w["all"]["wins"], w["all"]["losses"], w["all"]["pushes"]) \
        == (8001.64, 0.2607, 221, 1141, 27)
    assert (w["2026"]["profit"], w["2026"]["roi"], w["2026"]["wins"], w["2026"]["losses"], w["2026"]["pushes"]) \
        == (1236.44, 0.3225, 57, 265, 9)
    assert (w["2026-09"]["profit"], w["2026-09"]["roi"], w["2026-09"]["wins"], w["2026-09"]["losses"],
            w["2026-09"]["pushes"]) == (571.53, 0.3494, 30, 150, 1)
    assert SNAP["source"] == "Pikkit" and SNAP["as_of"] == "2026-09-26T14:23:03"
    # The months he sent next (June, July, August 2026) — each its own card.
    assert (w["2026-08"]["profit"], w["2026-08"]["roi"], w["2026-08"]["wins"], w["2026-08"]["losses"],
            w["2026-08"]["pushes"]) == (53.12, 0.4284, 2, 7, 1)
    assert (w["2026-07"]["profit"], w["2026-07"]["roi"], w["2026-07"]["wins"], w["2026-07"]["losses"],
            w["2026-07"]["pushes"]) == (355.60, 0.6199, 13, 41, 4)
    assert (w["2026-06"]["profit"], w["2026-06"]["roi"], w["2026-06"]["wins"], w["2026-06"]["losses"],
            w["2026-06"]["pushes"]) == (260.93, 0.4007, 5, 18, 1)


def test_the_months_sit_inside_their_year():
    w = {x["key"]: x for x in SNAP["windows"]}
    months = [x for k, x in w.items() if len(k) == 7 and k.startswith("2026-")]
    assert sum(x["wins"] for x in months) <= w["2026"]["wins"]
    assert sum(x["losses"] for x in months) <= w["2026"]["losses"]


def test_the_months_fold_under_the_headline_cards():
    i = APP.index("function zenoSnapshotHTML(")
    fn = APP[i:APP.index("\n}\n", i)]
    assert 'Month by month · ${months.length}' in fn and "zeno-months" in fn
    assert "String(b.key).localeCompare(String(a.key))" in fn, "newest month first"


def test_every_receipt_is_on_the_site():
    for w in SNAP["windows"]:
        path = os.path.join(ROOT, "web", w["receipt"])
        assert os.path.getsize(path) > 10_000, w["receipt"]


def test_units_and_stake_are_read_back_from_pikkits_numbers():
    s = {w["key"]: w for w in Z.load_snapshot()["windows"]}
    a = s["all"]
    assert a["net_units"] == 800.16, "$8,001.64 at $10 a unit — the 800 units he quoted"
    assert abs(a["staked"] - 8001.64 / 0.2607) < 0.01 and a["settled"] == 1389


def test_his_record_is_pikkits_until_a_ticket_settles_after_it():
    conn = _db()
    try:
        o = Z.block(conn, Z.load_snapshot())["overall"]
        assert (o["wins"], o["losses"], o["pushes"], o["profit"], o["roi"]) == (221, 1141, 27, 8001.64, 0.2607)
        assert o["net_units"] == 800.16
        rows = [{"book": "fanduel", "external_id": "old", "placed_at": "2026-09-20T13:00:00",
                 "settled_at": "2026-09-20T16:00:00", "selection": "Already in Pikkit", "odds": -110,
                 "stake": 110, "result": "won"},
                {"book": "fanduel", "external_id": "new", "placed_at": "2026-09-27T13:00:00",
                 "settled_at": "2026-09-27T16:00:00", "selection": "After the snapshot", "odds": 100,
                 "stake": 100, "result": "won"}]
        Z.import_rows(conn, rows, source="test")
        o = Z.block(conn, Z.load_snapshot())["overall"]
        assert (o["wins"], o["losses"]) == (222, 1141), "the old ticket is inside Pikkit's numbers already"
        assert o["profit"] == 8101.64 and o["net_units"] == 810.16
    finally:
        conn.close()


def test_the_combined_line_takes_the_carried_record():
    conn = _db()
    try:
        z = Z.block(conn, Z.load_snapshot())
    finally:
        conn.close()
    model = {"settled": 100, "wins": 55, "losses": 45, "pushes": 0, "units_staked": 100.0, "net_units": 5.0}
    c = Z.combined(model, z)
    assert c["split"]["zeno"]["net_units"] == 800.16 and c["net_units"] == 805.16


def test_only_the_live_record_carries_it():
    src = open(os.path.join(ROOT, "engine", "zeno.py"), encoding="utf-8").read()
    i = src.index("def block_or_empty(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "if path is None:" in body and "snap = load_snapshot()" in body and "block(conn, snap)" in body


def test_the_page_says_where_it_came_from_and_shows_the_cards():
    i = APP.index("function zenoSnapshotHTML(")
    fn = APP[i:APP.index("\n}\n", i)]
    assert 'class="zeno-receipt"' in fn and "<img src=" in fn, "the Pikkit card is the receipt"
    assert "marked Verified by ${src}, as of" in fn
    assert "${zenoSnapshotHTML(z.snapshot, z.unit_dollars)}" in APP
    assert "Zeno · his own book · via ${z.snapshot.source || \"Pikkit\"}" in APP


def test_his_units_say_what_a_unit_is_worth():
    """Ethan, 2026-09-26: "make sure users know 1 unit is $10 so we can put
    a dollar amount behind the 800 units"."""
    assert "const unitNote = (ud) => (Number(ud) > 0 ? ` (1u = $${Number(ud)})` : \"\");" in APP
    assert "Zeno ${part(cb.split.zeno)}${unitNote(cb.unit_dollars)}" in APP, "on the combined tile"
    assert "u${unitNote(z.unit_dollars)} · `" in APP, "on his own tile"
    assert "Units at $${escapeHtml(String(unit))} each." in APP, "on his page"
    assert Z.unit_dollars() == 10.0


def test_the_calendars_add_up_to_pikkits_months():
    """Pikkit rounds each day to three figures; the days land within a
    dollar of the month, and the page names the month's total as Pikkit's."""
    for w in SNAP["windows"]:
        if w.get("days"):
            assert abs(sum(w["days"].values()) - w["profit"]) < 1.0, w["key"]
            assert all(k.startswith(w["key"] + "-") for k in w["days"]), w["key"]
            assert os.path.getsize(os.path.join(ROOT, "web", w["calendar_receipt"])) > 10_000
    assert sorted(w["key"] for w in SNAP["windows"] if w.get("days")) == ["2026-06", "2026-07", "2026-08", "2026-09"]
    i = APP.index("function zenoCalMonthHTML(")
    fn = APP[i:APP.index("\n}\n", i)]
    assert "(Pikkit’s total)" in fn and "Pikkit’s calendar" in fn


def test_the_calendar_is_drawn_our_way_one_month_at_a_time():
    """Ethan: "make the calendars our way and not the screenshots" — the
    Record page's grid, drawn from the days, with its arrows."""
    i = APP.index("function zenoCalendarHTML(")
    fn = APP[i:APP.index("\n}\n", i)]
    assert 'data-act="zenoCalSetMonth"' in fn and "zenoCalMonthHTML(ms[i])" in fn
    assert "<img" not in fn and "<img" not in APP[APP.index("function zenoCalMonthHTML("):i]
    assert "zenoCalSetMonth: (el, a) => window._zenoCalSetMonth(a)," in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
