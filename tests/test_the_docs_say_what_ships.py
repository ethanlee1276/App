"""The documents describe the code that runs.

Audit 2026-09-30, B3 and the Phase 0 mismatches (roadmap #36): the README
and three model specs said quarter/half Kelly sized the bets (a price
ladder has since 2026-08-12, Kelly only vetoes); the parlay spec promised
a probation exit nothing computes; the deploy README said grey cloud while
production runs orange; and "account health" read like a per-user
feature. Each claim is pinned to the code that makes it true, so the next
change to the code has to change the sentence too.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _r(rel):
    return (ROOT / rel).read_text()


def test_no_document_says_kelly_sizes_a_main_board_bet():
    readme = _r("README.md")
    assert "quarter-Kelly, capped" not in readme
    assert "price ladder" in readme and "VETOES" in readme
    for rel in ("docs/NFL_MODEL.md", "docs/MLB_MODEL.md"):
        assert "**What ships (since 2026-08-12):** Kelly does not size the bet." in _r(rel), rel
    assert "**What ships:** CFB is on probation" in _r("docs/CFB_MODEL.md")
    # …and the code the sentences describe still does that.
    staking = _r("engine/staking.py")
    assert "def units_for_price(" in staking and "veto" in staking.lower()


def test_the_parlay_probation_exit_is_described_as_unbuilt_while_it_is():
    parlays = _r("engine/parlays.py")
    doc = _r("docs/PARLAY_MODEL.md")
    if '"probation": True' in parlays:
        assert "**What ships:** the exit is not built." in doc
    assert "Gate 7 — exposure, and the stake we would have made" in parlays
    assert "**What ships:** Gate 7 computes the stake the ticket WOULD carry" in doc


def test_account_health_says_whose_action_it_scores():
    assert "never reads a\n  visitor's sportsbook accounts" in _r("GUIDE.md")


def test_the_deploy_readme_says_production_runs_behind_the_proxy():
    dep = _r("deploy/README.md")
    # The proxy was found off on 2026-10-09; the README says so and points
    # at the walkthrough that turns it back on (updated 2026-10-10).
    assert "**Orange from 2026-08-21; found grey (off) on 2026-10-09.**" in dep
    assert '"Turning it back on, step by step"' in dep
    assert "### Turning it back on, step by step" in _r("docs/DEPLOY.md")
    assert "engine/cfips.py" in dep and (ROOT / "engine" / "cfips.py").exists()
    assert (ROOT / "deploy" / "cfips.sh").exists()


def test_the_backup_comment_names_history_db_as_backed_up():
    b = _r("deploy/backup.sh")
    assert "history.db   — BACKED UP since 2026-09-30" in b


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
