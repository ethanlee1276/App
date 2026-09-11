"""The bet journal must not be one `git add -A` away from being public.

Found on the real machine 2026-08-07. `git status` showed:

    Untracked files:
        data/ledger.db.pre-rescale-2026-08-06
        data/llm_spend.json
        data/sim_gate_failures.json

`data/ledger.db` is ignored and `*.db` is ignored, but a migration backup
is named `ledger.db.pre-rescale-<date>` — it ends in a date, not in `.db`,
so neither rule caught it and git offered up the whole settled journal as
an ordinary untracked file.

The test asks git itself rather than reading the patterns, because the
question is not "does .gitignore contain a line" but "would this path be
committed", and only `git check-ignore` answers that one.

Run directly: `python3 tests/test_gitignore.py`
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Paths that must never be committable. Written as the real names the
#: tools actually produce, not as the patterns that happen to catch them —
#: a pattern test passes while the pattern is wrong.
MUST_IGNORE = (
    "data/ledger.db",
    "data/history.db",
    "data/ledger.db.pre-rescale-2026-08-06",
    "data/ledger.db.pre-rescale-2027-01-01",
    "data/ledger.db.bak",
    "data/history.db.backup",
    "data/llm_spend.json",
    "data/sim_gate_failures.json",
    # The Yahoo OAuth token, 2026-08-15. `data/` is not ignored wholesale
    # — only named files under it are — so this needed saying explicitly,
    # and it is worse to leak than an API key: it is scoped to ONE
    # person's fantasy account and reads it until it is revoked.
    "data/yahoo_token.json",
    # Every user's email and password verifier, 2026-08-15. Covered by
    # `*.db`, named here anyway: this is the file whose leak would be a
    # breach of other people's data rather than only Ethan's, and a rule
    # that matters that much should be pinned by name.
    "data/accounts.db",
    "data/accounts.db-wal",
    "secrets.local",
    "secrets.local.old",
    "web/data/recommendations.json",
    # backup.sh's own output, 2026-08-16. Its default destination is
    # ./backups — a SIBLING of data/, so `data/backups/` never covered
    # it — and it writes `.db.gz`, which `*.db` does not match either.
    # Gzipped copies of the accounts and ledger databases, sitting
    # untracked in the checkout, one `git add -A` from being published.
    "backups/accounts-20260816T040000Z.db.gz",
    "backups/ledger-20260816T040000Z.db.gz",
    # The unredacted boards, 2026-08-16. engine/gate.py writes them
    # outside web/ so that no web server can serve them; committing them
    # would publish to GitHub exactly what the paywall withholds from the
    # site, which is the same leak by a slower route.
    "data/built/recommendations.json",
    "data/built/nba.json",
)

#: …and paths that must stay tracked. An ignore rule wide enough to cover
#: the journal can easily swallow the code that reads it.
MUST_NOT_IGNORE = (
    "engine/ledger.py",
    "engine/carry.py",
    "selfit.py",
    "web/css/styles.css",
    "web/js/app.js",
    "tests/test_gitignore.py",
    "docs/WHEN_HOME.md",
)


def _ignored(path: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", path],
                       cwd=ROOT, capture_output=True)
    return r.returncode == 0


def test_the_journal_and_its_backups_cannot_be_committed():
    missed = [p for p in MUST_IGNORE if not _ignored(p)]
    assert not missed, f"would be committed: {missed}"


def test_the_migration_backup_is_covered_by_name_not_by_luck():
    """The specific hole. `*.db` does not match a file whose name ends in a
    date, and this is the file rescale.py writes before it rewrites every
    stake in the journal."""
    assert _ignored("data/ledger.db.pre-rescale-2026-08-06")
    # Any date, not just the one that was on the machine that day.
    assert _ignored("data/ledger.db.pre-rescale-2099-12-31")


def test_the_code_is_still_tracked():
    """An ignore rule wide enough to hide the journal can hide the engine
    that reads it. `data/*` would pass the test above and empty the repo."""
    wrong = [p for p in MUST_NOT_IGNORE if _ignored(p)]
    assert not wrong, f"source is being ignored: {wrong}"


def test_no_journal_backup_is_actually_tracked_right_now():
    """Belt and braces: the rule could be right while a file slipped in
    before it existed, and once a path is tracked gitignore stops applying
    to it entirely."""
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True).stdout.split("\n")
    bad = [p for p in out
           if ".pre-rescale-" in p or p.endswith((".db", ".bak"))
           # secrets.local.example IS tracked on purpose — it is the empty
           # template the README tells you to copy. Only a real
           # secrets.local (or a stray sibling) is the problem.
           or (p.startswith("secrets.local") and p != "secrets.local.example")]
    assert not bad, f"already tracked and gitignore no longer applies: {bad}"


def test_the_tracked_secrets_template_is_empty():
    """It is committed on purpose, so the one thing that matters is that
    nobody ever fills it in and commits that instead of copying it."""
    path = os.path.join(ROOT, "secrets.local.example")
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        assert value.strip() == "", f"{key} carries a value in the template"


def test_the_nightly_runner_ships_executable():
    """`install-nightly.sh` chmod +x's it, so shipping it non-executable
    made every install dirty the working tree with a mode change that
    looked like an edit nobody made."""
    out = subprocess.run(["git", "ls-files", "-s", "tools/nightly.sh"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    assert out.startswith("100755"), out.strip() or "not tracked"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
