"""`--learning`: does the audit read the stores the writers actually write?

Ethan, 2026-08-16: "Check to see if the hypothesis lab and the model ai
thing we have learn from itself has even been doing anything ... I wanna
know if these are even doing anything or helping us."

The dangerous failure for a probe that answers THAT question is not a
crash. It is reading `blob["patterns"]` when the miner writes
`blob["findings"]`, reporting a confident zero, and being believed —
"nothing is working" is exactly the answer the reader is braced for, so a
wrong one sails straight through. Every key the audit reads is therefore
checked against the module that writes it, and the probe is run over
stores shaped like the pages Ethan screenshotted.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_the_store_paths_are_the_ones_the_fitters_write():
    """Not string literals in the probe — the writers' own constants."""
    from engine import calibrate, formfit, hypotheses, losspatterns, playerfit
    assert Path(formfit.DEFAULT_PATH).name == "formfit.json"
    assert Path(playerfit.DEFAULT_PATH).name == "playerfit.json"
    assert Path(losspatterns.DEFAULT_PATH).name == "losspatterns.json"
    assert Path(hypotheses.DEFAULT_PATH).name == "hypotheses.json"
    assert Path(calibrate.DEFAULT_PATH).name == "calibration.json"


def test_the_miner_keys_the_audit_reads_are_the_keys_mine_emits():
    """`n_records` / `tested` / `findings` / `closed`, read off the source
    of `mine` rather than assumed. Reading a key it does not write would
    report "nothing convicted" on a store full of convictions."""
    import inspect
    from engine import losspatterns as lp
    src = inspect.getsource(lp.mine)
    for key in ('"n_records"', '"tested"', '"findings"'):
        assert key in src, key
    # `closed` is assembled by save/mine's caller path; assert it is the
    # name the veto reads, which is what makes it the enforcing subset.
    assert 'store.get("closed")' in inspect.getsource(lp)


def test_the_adoption_flag_is_named_adopted_in_both_fitters():
    import inspect
    from engine import formfit, playerfit
    for mod in (formfit, playerfit):
        assert '"adopted"' in inspect.getsource(mod), mod.__name__


def test_a_hypothesis_only_reaches_a_pick_when_its_action_is_close():
    """The audit counts `action == "close"` as "enforcing". If confirmed
    hypotheses reached picks by some other route the audit would
    understate the lab, which is the opposite error but the same bug."""
    import inspect
    from engine import hypotheses as hyp
    src = inspect.getsource(hyp.tribunal)
    assert 'h["action"] = ("close"' in src


def test_the_audit_reproduces_the_pages_it_is_auditing():
    """Stores shaped like Ethan's screenshots in, his numbers out.

    Record page: 4 markets tuned, every projection dial and player memory
    fit kept the default, 4,095 rows mined over 103 slices, 1 pattern
    found, 0 self-closed. If the probe cannot reproduce the pages it is
    auditing, it is measuring something else.
    """
    tmp = Path(tempfile.mkdtemp())
    models = tmp / "data" / "models"
    models.mkdir(parents=True)
    (models / "calibration.json").write_text(json.dumps({
        "mlb:hits": {"temperature": 1.42, "brier_before": 0.2371,
                     "brier_after": 0.2357},
        "mlb:home_runs": {"temperature": 1.04, "brier_before": 0.0909,
                          "brier_after": 0.0907},
        "mlb:strikeouts": {"temperature": 2.02, "brier_before": 0.2434,
                           "brier_after": 0.2395},
        "mlb:total_bases": {"temperature": 1.32, "brier_before": 0.2356,
                            "brier_after": 0.2348}}))
    (models / "formfit.json").write_text(json.dumps(
        {f"mlb:{m}": {"adopted": False}
         for m in ("hits", "strikeouts", "total_bases")}))
    (models / "playerfit.json").write_text(json.dumps(
        {f"mlb:{m}": {"adopted": False}
         for m in ("hits", "outs", "strikeouts", "total_bases")}))
    (models / "losspatterns.json").write_text(json.dumps({
        "n_records": 4095, "tested": 103,
        "findings": [{"action": "watch"}], "closed": []}))
    (models / "hypotheses.json").write_text(json.dumps(
        {"hypotheses": [{"status": "collecting"}, {"status": "tested"},
                        {"status": "rejected"}]}))

    # In-process, with every store repointed at the fixture. Some of
    # these paths are absolute (off the package) and some relative (off
    # the working directory), so a shelled-out run with one cwd reached
    # only some of them, read zero markets, and passed every other
    # assertion — which is the same false-zero this file exists to stop.
    import contextlib
    import io
    from engine import calibrate, formfit, hypotheses, losspatterns, playerfit
    import launch

    mods = {calibrate: "calibration.json", formfit: "formfit.json",
            playerfit: "playerfit.json", losspatterns: "losspatterns.json",
            hypotheses: "hypotheses.json"}
    was = {m: m.DEFAULT_PATH for m in mods}
    was_cwd = os.getcwd()
    buf = io.StringIO()
    try:
        for m, name in mods.items():
            m.DEFAULT_PATH = models / name
        losspatterns._cache.clear(); hypotheses._cache.clear()
        os.chdir(tmp)
        with contextlib.redirect_stdout(buf):
            launch.show_learning()
    finally:
        os.chdir(was_cwd)
        for m, orig in was.items():
            m.DEFAULT_PATH = orig
        losspatterns._cache.clear(); hypotheses._cache.clear()
    out = buf.getvalue()

    assert "4 market(s) fitted" in out, out
    assert "4 carry a correction" in out, out
    assert out.count("every fit kept the default") == 2, out
    assert "4095 rows, 103 slices" in out, out
    assert "1 found · 0 enforcing" in out, out
    assert "3 proposed" in out and "0 confirmed" in out, out


def test_the_haircut_learns_from_the_paper_book_too():
    """The defect this audit found in the audit's own author's work.

    Paper mode files a row under 'paper' and changes nothing else — same
    pick, same sizing, same settlement. A fitter reading 'main' only
    therefore froze on the day the money came off, which is precisely the
    question Ethan asked ("have we been learning anything since we turned
    on the paper bets") and precisely the wrong answer to give.
    """
    from engine import selectionfit as sf
    assert set(sf.LEARNING_CATEGORIES) == {"main", "paper"}
    # And the measurement-only books stay out: they grade signals that
    # are never published, so a correction fitted on them would be a
    # correction for a board nobody sees.
    for book in ("longshot", "loose", "pricedout", "stale", "form"):
        assert book not in sf.LEARNING_CATEGORIES


def test_paper_mode_changes_only_the_category_and_the_dollars():
    """The claim the audit prints, asserted against the logging path.

    If paper mode also zeroed `stake_units` the paper book could not
    answer "what would this have returned", and every ROI on it would be
    a division by zero wearing a percentage.
    """
    import inspect
    from engine import ledger
    src = inspect.getsource(ledger.log_recommendations)
    assert 'category = "paper" if paper else "main"' in src
    assert "stake_units" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
