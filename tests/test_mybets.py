"""My Bets — the user's own sportsbook bet log, tracked client-side.

Ethan, 2026-08-10: "Add a way to log into sportsbook accounts and track
bets made by the user on the sportsbooks."

The account-LOGIN half is deliberately not built: no book offers an API,
so it would mean storing the user's password and scraping — against the
books' terms and a risk to the account. This pins that the page never
asks for a credential, that its P&L math (the one real computation) is
correct on pinned known answers by running the SHIPPED functions under
node, and that the page is wired like every other standalone one.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "web/index.html"), encoding="utf-8").read()


def _slice(start_marker, end_marker):
    i = APP.index(start_marker)
    return APP[i:APP.index(end_marker, i + 1)]


def test_the_pnl_math_is_correct_on_known_answers():
    """The American-odds payout is the only real computation on the page,
    so it runs the SHIPPED mbDecimal/mbProfit under node — not a copy."""
    node = shutil.which("node")
    if not node:
        return                      # node-less CI: the other tests still pin wiring
    fns = (_slice("function mbDecimal(", "function mbProfit(")
           + _slice("function mbProfit(", "\nfunction mbStats("))
    check = fns + """
const A = (got, exp, msg) => {
  if (Math.abs(got - exp) > 1e-6) { console.error(msg, got, "!=", exp); process.exit(1); }
};
A(mbDecimal(150), 2.5, "+150 decimal");
A(mbDecimal(-120), 1 + 100/120, "-120 decimal");
A(mbProfit({result:"win", stake:100, odds:150}), 150, "win +150");
A(mbProfit({result:"win", stake:110, odds:-110}), 100, "win -110");
A(mbProfit({result:"loss", stake:100, odds:-110}), -100, "loss");
A(mbProfit({result:"push", stake:100, odds:-110}), 0, "push");
A(mbProfit({result:"pending", stake:100, odds:-110}), 0, "pending");
if (mbDecimal("abc") !== null) { console.error("bad odds not null"); process.exit(1); }
console.log("ok");
"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(check)
        path = f.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr or out.stdout
    finally:
        os.unlink(path)


def test_it_never_asks_for_a_credential():
    """The whole safety argument in one assertion: no password field, no
    sportsbook login, nowhere on the page."""
    body = _slice("function renderMyBets(", "\n/* ================")
    # No credential INPUT anywhere on the page (the WORD "password" IS on
    # the page — its whole point is saying it never asks for one — so the
    # check is for a real field, not the noun).
    assert 'type="password"' not in (body + HTML).lower()
    # Only the manual-entry inputs exist; none of them is a secret.
    input_types = set(re.findall(r'type="([a-z]+)"', body))
    assert input_types <= {"text", "number", "date", "button", "file"}, \
        f"unexpected input types on My Bets: {input_types}"
    # And it states the choice, so the absence reads as deliberate.
    assert "No passwords" in body


def test_entries_live_only_in_the_browser():
    """Client-only by construction: localStorage, no fetch/POST to a
    server, and a stable storage key so a redeploy does not orphan data."""
    body = _slice("const MYBETS_KEY", "\n/* ================")
    assert 'MYBETS_KEY = "qb_mybets_v1"' in APP
    assert "localStorage.getItem(MYBETS_KEY)" in body
    assert "localStorage.setItem(MYBETS_KEY" in body
    # No network write of the user's bets.
    assert "fetch(" not in body


def test_export_and_import_exist_for_backup_and_device_move():
    assert "window.mbExport" in APP and "window.mbImport" in APP
    imp = _slice("window.mbImport", "window.")
    # Import MERGES by id rather than overwriting, so restoring a backup
    # cannot wipe newer entries.
    assert "have.has(b.id)" in imp


def test_the_page_is_wired_like_every_other_standalone():
    assert 'data-sport="mybets"' in HTML
    assert 'id="view-mybets"' in HTML and 'id="mybets-body"' in HTML
    assert "async function renderMyBets" in APP or "function renderMyBets" in APP
    assert 'if (name === "mybets") renderMyBets();' in APP
    modes = APP[APP.index("const STANDALONE_MODES"):]
    assert '"mybets"' in modes[:modes.index("]")]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
