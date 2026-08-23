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


def test_it_never_asks_for_a_SPORTSBOOK_credential():
    """NARROWED 2026-08-15, and the narrowing is the point.

    This used to assert that no password field existed on the page at all.
    Ethan then asked for real accounts — *"we will be storing user
    information and passwords and logins"* — so the page now carries a
    Qellys sign-in, and the old assertion would have failed for the right
    reason at the wrong target.

    The rule underneath it survives intact: no field on this page asks for
    a DRAFTKINGS password. Ours can be scoped, changed and deleted by us;
    theirs cannot, which was always the actual argument. The bet-entry
    form is checked directly, so a credential field appearing THERE — the
    place a "connect your book" feature would land — still fails."""
    body = _slice("function renderMyBets(", "\n/* ================")
    form = _slice("const form = ", "host.innerHTML = ")
    # The manual-entry form takes no secret of any kind.
    input_types = set(re.findall(r'type="([a-z]+)"', form))
    assert "password" not in input_types, \
        f"a credential field appeared on the bet form: {input_types}"
    assert input_types <= {"text", "number", "date", "button", "file"}, \
        f"unexpected input types on the My Bets form: {input_types}"
    # And the page still states the choice, so the absence reads as
    # deliberate rather than forgotten.
    assert "No sportsbook passwords" in body


def test_entries_live_only_in_the_browser():
    """Local-first by construction: localStorage with a stable key so a
    redeploy does not orphan data, and the storage layer itself never
    talks to the network. What CHANGED on 2026-08-10 (Ethan: "make an
    account so you don't have to put in that info every time"): syncing
    now exists, but as an opt-in ACCOUNT layer that ships the data to
    the user's own laptop server and nowhere else — see
    tests/test_accounts.py for that contract. The mechanism pinned here
    is the separation: this block still contains no fetch; it only
    raises its hand via acctTouch and the account layer decides."""
    body = _slice("const MYBETS_KEY", "\n/* ================")
    assert 'MYBETS_KEY = "qb_mybets_v1"' in APP
    assert "localStorage.getItem(MYBETS_KEY)" in body
    assert "localStorage.setItem(MYBETS_KEY" in body
    # No network code in the storage layer — sync goes through acctTouch.
    assert "fetch(" not in body
    assert 'acctTouch("mybets")' in body


def test_export_and_import_exist_for_backup_and_device_move():
    assert "window.mbExport" in APP and "window.mbImport" in APP
    imp = _slice("window.mbImport", "window.")
    # Import MERGES by id rather than overwriting, so restoring a backup
    # cannot wipe newer entries.
    assert "have.has(b.id)" in imp


def test_bulk_import_parses_real_export_shapes():
    """The free version of Juice Reel's sync: a CSV importer. These run
    the SHIPPED functions under node against the shapes that actually
    occur — a Juice-Reel-style export, a book export with different
    header names in a different order, a spreadsheet paste (tabs), a
    quoted description containing a comma, decimal odds, EVEN, and the
    result words each book uses. Column matching is by NAME, never by
    position — the espnhoops rule."""
    node = shutil.which("node")
    if not node:
        return
    fns = _slice("const MB_HEADERS", "\n/* Parsed-but-not-committed")
    check = fns + r"""
const die = (msg) => { console.error(msg); process.exit(1); };
const eq = (got, exp, msg) => {
  if (JSON.stringify(got) !== JSON.stringify(exp)) die(msg + ": " + JSON.stringify(got) + " != " + JSON.stringify(exp));
};

// 1. Juice-Reel-shaped export, quoted comma in the description.
let r = mbRowsFromText(
  'Date Placed,Sportsbook,Bet Name,Odds,Risk,Result\n' +
  '2026-08-09,DraftKings,"Judge Over 1.5 TB, live",+150,$25.00,Won\n' +
  '08/08/2026,FanDuel,Yankees ML,-125,10,Lost\n', "Other");
eq(r.bets.length, 2, "two rows parse");
eq(r.bets[0].desc, "Judge Over 1.5 TB, live", "quoted comma survives");
eq(r.bets[0].odds, 150, "plus odds");
eq(r.bets[0].stake, 25, "dollar stake");
eq(r.bets[0].result, "win", "Won normalizes");
eq(r.bets[1].date, "2026-08-08", "US date normalizes");
eq(r.bets[1].result, "loss", "Lost normalizes");

// 2. Different names, different ORDER — name-matching, not position.
r = mbRowsFromText(
  'Status\tAmount\tPrice\tSelection\tDate\n' +
  'Void\t$50\t-110\tOver 8.5 runs\t2026-08-01\n', "BetMGM");
eq(r.bets.length, 1, "tsv parses");
eq(r.bets[0].result, "push", "Void is a push");
eq(r.bets[0].book, "BetMGM", "no book column -> fallback book");
eq(r.bets[0].desc, "Over 8.5 runs", "Selection maps to desc");

// 3. Decimal odds and EVEN convert; cashout never invents a grade.
r = mbRowsFromText(
  'Bet,Odds,Stake,Result\nA,1.91,10,win\nB,2.50,10,w\nC,even,10,Cashed Out\n',
  "Other");
eq(r.bets[0].odds, -110, "1.91 -> -110");
eq(r.bets[1].odds, 150, "2.50 -> +150");
eq(r.bets[2].odds, 100, "EVEN -> +100");
eq(r.bets[2].result, "pending", "cashout stays pending");

// 4. Unreadable rows are skipped WITH reasons, never guessed at.
r = mbRowsFromText(
  'Bet,Odds,Stake,Result\n,-110,10,win\nX,huh,10,win\nY,-110,zero,win\n',
  "Other");
eq(r.bets.length, 0, "no junk imported");
eq(r.skipped.length, 3, "each junk row named");
if (!r.skipped[1].reason.includes("odds")) die("odds reason missing");

// 5. No result column at all -> everything pending, not everything won.
r = mbRowsFromText('Bet,Odds,Stake\nA,-110,10\n', "Other");
eq(r.bets[0].result, "pending", "resultless import is pending");

// 6. A file with no usable header says so instead of importing noise.
r = mbRowsFromText('just,some,words\na,b,c\n', "Other");
eq(r.bets.length, 0, "headerless rejected");
if (!r.skipped[0].reason.includes("header")) die("header reason missing");

// 7. Dedupe signature: identity is day+book+wording+stake+price.
const a = { date: "2026-08-09", book: "DK", desc: "Yankees ML", stake: 25, odds: -125 };
eq(mbSig(a), mbSig({ ...a, desc: "  YANKEES ML " }), "sig folds case/space");
if (mbSig(a) === mbSig({ ...a, stake: 50 })) die("different stake must differ");
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


def test_bulk_import_previews_and_dedupes_before_committing():
    """Nothing lands from a file without a human seeing the parse: the
    preview shows counts + skip reasons + sample rows, dedupes against
    what is already logged, and only the Add button commits."""
    assert "window.mbBulkCommit" in APP
    show = _slice("function mbBulkShow(", "\nfunction renderMyBets(")
    assert "mbSig" in show, "preview does not dedupe"
    # THE BEHAVIOUR, not the word. This asserted the string "duplicate"
    # appeared in the summary, and went red when the copy changed from
    # "5 duplicate(s) skipped (already logged)" to "5 already logged" —
    # which is the same fact in fewer words. What has to hold is that
    # recognised rows are counted and kept out of the commit.
    assert "dupes.push" in show, "recognised rows are not held back"
    assert "dupes.length" in show, "the preview never mentions them"
    assert "skipped" in show.lower()
    assert "mbBulkCommit()" in show, "no commit step — imports would be blind"
    # The page carries the importer and says re-importing is safe.
    body = _slice("function renderMyBets(", "\n/* ================")
    assert "mb-bulk-text" in body and "mbBulkFile" in body
    assert "skipped, not doubled" in body


def test_the_same_bet_typed_and_imported_is_not_two_bets():
    """THE QUIET ONE, live in shipped code until 2026-08-23.

    `mbSig` keys on the description, which is right for re-importing the
    same export twice and wrong for what actually happens: you log a bet
    on your phone during the game, then import the book's CSV at the
    weekend.

        typed by you     "Judge o1.5 TB"
        from the book    "Aaron Judge Over 1.5 Total Bases"

    Different signature, so the import added a second copy — and the
    damage does not announce itself. Two rows for one wager doubles the
    staked total and halves the ROI on the page whose only job is
    telling you how you are doing.

    Runs the SHIPPED functions rather than reading them, because the two
    keys agreeing or disagreeing is the entire fix."""
    node = shutil.which("node")
    if not node:
        return
    check = _slice("function mbSig(", "\nfunction mbRowsFromText(") + """
const F = (m) => { console.error(m); process.exit(1); };
const typed = {date:"2026-08-20", book:"FanDuel",
               desc:"Judge o1.5 TB", stake:25, odds:-110};
const book  = {date:"2026-08-20", book:"FanDuel",
               desc:"Aaron Judge Over 1.5 Total Bases", stake:25, odds:-110};
if (mbSig(typed) === mbSig(book)) F("mbSig should NOT match — it keys on desc");
if (mbAcctKey(typed) !== mbAcctKey(book)) F("the same bet read as two");
// A book quotes cents and whole numbers; float noise is not a new bet.
if (mbAcctKey(typed) !== mbAcctKey({...book, stake:25.004, odds:-110.4}))
  F("rounding split one bet in two");
// Different day, different price, different book: all different bets.
if (mbAcctKey(typed) === mbAcctKey({...book, date:"2026-08-21"})) F("day");
if (mbAcctKey(typed) === mbAcctKey({...book, odds:-115})) F("price");
if (mbAcctKey(typed) === mbAcctKey({...book, book:"DraftKings"})) F("book");
// Case and padding on the book name are typing, not identity.
if (mbAcctKey(typed) !== mbAcctKey({...book, book:" fanduel "})) F("case");
console.log("ok");
"""
    out = subprocess.run([node, "-e", check], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr.strip() or out.stdout.strip()


def test_a_claimed_row_cannot_swallow_a_second_wager():
    """Two different bets can share a date, book, stake and price — a
    parlay and a straight at −110 for $25 on the same night. The preview
    claims each existing row at most once, or the second import row
    would vanish into the first."""
    show = _slice("function mbBulkShow(", "\nfunction renderMyBets(")
    assert "unclaimed" in show, "existing rows are not claimed one at a time"
    assert "pool.shift()" in show, (
        "a matched row is not consumed, so it can absorb every incoming "
        "bet with the same accounting key")


def test_an_import_settles_a_pending_bet_it_recognises():
    """The export is the authority on results, so a CSV full of graded
    bets should grade the pending copies already in the book. Without
    this the preview says "nothing to add" after a file that had every
    answer in it."""
    show = _slice("function mbBulkShow(", "\nfunction renderMyBets(")
    assert "_mbGraded" in show and "mine.result = b.result" in show
    assert "pending" in show
    # …and it must not un-settle anything: only a pending row is touched.
    i = show.index("mine.result = b.result")
    assert 'String(mine.result || "pending") === "pending"' in show[:i], (
        "a settled row can be rewritten by an import")


def test_the_preview_says_what_it_did_to_bets_it_recognised():
    """A preview reading "0 to add" after a file full of results reads
    as the import having done nothing."""
    show = _slice("function mbBulkShow(", "\nfunction renderMyBets(")
    assert "settled from this file" in show


def test_the_page_is_wired_like_every_other_standalone():
    assert 'data-sport="mybets"' in HTML
    assert 'id="view-mybets"' in HTML and 'id="mybets-body"' in HTML
    assert "async function renderMyBets" in APP or "function renderMyBets" in APP
    assert 'if (name === "mybets") renderMyBets();' in APP
    modes = APP[APP.index("const STANDALONE_MODES"):]
    assert '"mybets"' in modes[:modes.index("]")]


def test_the_insights_math_runs_under_node():
    """The SHIPPED grouping, banding, curve and takeaway functions, on
    known answers — including the gates: no verdict off a thin sample,
    pushes ride the money but never the record, and the leak line only
    fires on a real hole."""
    node = shutil.which("node")
    if not node:
        return
    fns = (_slice("function mbDecimal(", "function mbProfit(")
           + _slice("function mbProfit(", "\nfunction mbStats(")
           + _slice("function mbMoney(", "\nfunction ")
           + _slice("/* ---- The insights layer", "/* Mutations."))
    check = fns + """
const F = (msg) => { console.error(msg); process.exit(1); };
// Bands: +100 opens the dogs; garbage is null, never a bucket.
if (mbBand(-200) !== "Heavy favorites") F("band -200");
if (mbBand(-110) !== "Favorites") F("band -110");
if (mbBand(100) !== "Small dogs") F("band +100");
if (mbBand(250) !== "Longshots") F("band +250");
if (mbBand("abc") !== null) F("band garbage");
// Grouping: settled only; a push moves money, not the record.
const g = mbGroup([
  { result: "win", stake: 100, odds: 100, sport: "NFL" },
  { result: "loss", stake: 50, odds: -110, sport: "NFL" },
  { result: "push", stake: 25, odds: -110, sport: "NFL" },
  { result: "pending", stake: 999, odds: -110, sport: "NFL" },
], (b) => b.sport);
if (g.NFL.n !== 3 || g.NFL.wins !== 1 || g.NFL.losses !== 1) F("group record");
if (g.NFL.staked !== 175 || g.NFL.profit !== 50) F("group money");
// The curve accumulates in DATE order whatever order the list is in.
const c = mbCurve([
  { result: "loss", stake: 30, odds: -110, date: "2026-08-02" },
  { result: "win", stake: 100, odds: 100, date: "2026-08-01" },
]);
if (c.length !== 2 || c[0].pnl !== 100 || c[1].pnl !== 70) F("curve");
// Nine losing longshots: silence. Twelve: the leak line, with numbers.
const shot = (r) => ({ result: r, stake: 10, odds: 300, sport: "MLB" });
const nine = Array.from({ length: 9 }, () => shot("loss"));
if (mbTakeaways(nine).length !== 0) F("thin sample must stay silent");
const twelve = Array.from({ length: 12 }, () => shot("loss"));
const takes = mbTakeaways(twelve);
if (!takes.some((t) => t.includes("Longshots are the leak"))) F("leak line");
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


def test_the_insights_render_and_wait_for_a_sample():
    i = APP.index("function renderMyBets(")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert "What your book says about you" in body
    assert "if (st.settled < 3)" in body, \
        "an insights block over two bets is a horoscope"
    assert "sparkline(curve.map(" in body, "the bankroll curve must draw"
    assert "MB_BAND_ORDER" in body, "bands render in habit order, not ROI order"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
