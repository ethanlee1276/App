"""Everything we've bet: the model and Zeno in one line, the split shown.

Ethan, 2026-09-26: his own record (from Pikkit) should count in the
page's ROI and units — "my own record is up 800 units". Folding it into
the model's own number would make the picks look better than they have
done, so he chose a combined line that always shows what each side added,
with the model's own record left beside it. 1 unit = $10.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import zeno as Z                                          # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
LEDGER = open(os.path.join(ROOT, "engine", "ledger.py"), encoding="utf-8").read()

MODEL = {"settled": 400, "wins": 220, "losses": 170, "pushes": 10, "units_staked": 420.0,
         "net_units": 21.0, "roi": 0.05}


def _zeno(profit=8000.0, staked=40000.0):
    t = {"settled": 900, "wins": 500, "losses": 390, "pushes": 10, "staked": staked, "profit": profit}
    t["units_staked"], t["net_units"] = staked / 10, profit / 10
    return {"overall": t}


def test_dollars_become_units_at_ten_a_unit():
    assert Z.unit_dollars() == 10.0
    rows = [{"result": "won", "stake": 100.0, "payout": 190.0}, {"result": "lost", "stake": 50.0, "payout": 0.0},
            {"result": "open", "stake": 20.0, "payout": None}]
    t = Z._tally(rows)
    assert (t["profit"], t["net_units"], t["units_staked"]) == (40.0, 4.0, 15.0)


def test_the_combined_line_adds_units_and_keeps_the_split():
    c = Z.combined(MODEL, _zeno())
    assert c["net_units"] == 821.0 and c["units_staked"] == 4420.0
    assert c["roi"] == round(821.0 / 4420.0, 4)
    assert (c["wins"], c["losses"], c["settled"]) == (720, 560, 1300)
    assert c["split"]["model"]["net_units"] == 21.0 and c["split"]["zeno"]["net_units"] == 800.0
    assert MODEL["net_units"] == 21.0, "the model's own record is never changed"


def test_one_side_alone_is_not_a_combined_line():
    assert Z.combined(MODEL, {"overall": {"settled": 0}}) is None
    assert Z.combined({"settled": 0}, _zeno()) is None


def test_the_export_ships_both_and_never_folds_zeno_into_overall():
    # The model half is the record the page shows as the model's — the
    # pooled book (edge + Most Likely), which app.js seats as `overall` —
    # so the combined tile adds up with the tile beneath it.
    assert '"combined": _zeno.combined(_pooled["overall"], _zeno_block),' in LEDGER
    assert '"pooled": _pooled,' in LEDGER
    # Since 2026-09-30 (audit P1-1) the page's headline is the edge board
    # and the pooled book — this combined line's model half — is kept
    # beside it as its own labelled tile, so the two still read together.
    assert "s.pooled_overall = s.pooled.overall;" in APP, "the pooled book keeps its own seat"
    assert '"overall": scoped,' in LEDGER, "the model's overall stays its own"


def test_the_page_shows_the_split_and_only_on_the_whole_record():
    i = APP.index("function recordRibbonsHTML(")
    fn = APP[i:APP.index("\n}\n", i)]
    # Since 2026-09-30 (audit P1-1/V-5, Ethan's yes): the model's own tile
    # leads and the combined line follows it, labelled for what it adds.
    assert "Combined · Zeno’s book + ours" in fn
    assert "model ${part(cb.split.model)} · Zeno ${part(cb.split.zeno)}" in fn
    assert fn.index("if (ov.settled) {") < fn.index("const cb = (rec || {}).combined;"), "model leads, combined follows"
    # Re-anchored 2026-10-02: Zeno's all-sports tile leaves a league or a
    # window too (it sat on the NFL page beside the NFL's own numbers), and
    # the Most Likely half rides with the pooled one.
    assert ("const dAll = winO || scoped\n"
            "    ? { ...d, combined: null, zeno: null,\n"
            "        pooled_overall: winO ? null : src.pooled_overall,\n"
            "        likely_overall: winO ? null : src.likely_overall } : d;") in APP


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
