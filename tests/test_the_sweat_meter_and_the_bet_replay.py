"""The sweat meter on a live saved slip, and the replay of its night once it settles.

Ethan, 2026-10-15, two of the sixteen ideas he asked to have built ("do
every one for every sport"): a live sweat meter and a bet replay. Our own
number throughout; nothing grades or moves a bet.

What these hold: the box keeps a saved slip's chance as it grades it —
before kickoff our chance it all hits, while it runs the chance for the
rest, then its last word — thinned (a point earns its place by time or by
a move), capped, never written after the slip is decided, and pruned with
age; the sweep keeps it for every slip it grades; the replay endpoint
gives a member their own slip only; the Live tab's slip card draws the
meter with its word and how far it moved; and My Bets offers the replay
on a settled saved slip and draws the night back, saying what it is.

Run directly: `python3 tests/test_the_sweat_meter_and_the_bet_replay.py`
"""
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import slipreplay as SR                              # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

EXTRAS = ROOT / "web" / "js" / "extras.js"
SLIP = ROOT / "web" / "js" / "slip.js"
T0 = 1_760_000_000.0


def _conn():
    conn = sqlite3.connect(":memory:")
    SR.ensure_table(conn)
    return conn


def _card(status=None, chance=None, ours=None):
    now = {} if status is None else {"status": status, **({"chance": chance} if chance is not None else {})}
    return {"now": now, "ours": ours}


def test_the_number_the_grade_says_now():
    assert SR.point(_card(ours=0.31)) == (0.31, "pre")
    assert SR.point(_card("open", 0.62)) == (0.62, "live")
    assert SR.point(_card("open")) is None, "a leg in play with no live number: nothing to keep"
    assert SR.point(_card("won")) == (1.0, "won") and SR.point(_card("lost")) == (0.0, "lost")
    assert SR.point({}) is None


def test_a_point_earns_its_place_and_the_last_word_ends_it():
    c = _conn()
    assert SR.bank(c, 1, "s1", _card(ours=0.31), T0)
    assert not SR.bank(c, 1, "s1", _card(ours=0.315), T0 + 60), "the same pre-game number again"
    assert SR.bank(c, 1, "s1", _card("open", 0.40), T0 + 3600)
    assert not SR.bank(c, 1, "s1", _card("open", 0.41), T0 + 3660), "a minute later and a point: not yet"
    assert SR.bank(c, 1, "s1", _card("open", 0.47), T0 + 3720), "a move of seven points earns a place at once"
    assert SR.bank(c, 1, "s1", _card("open", 0.475), T0 + 3720 + SR.GAP_S), "and time earns one too"
    assert SR.bank(c, 1, "s1", _card("lost"), T0 + 7200)
    assert not SR.bank(c, 1, "s1", _card("open", 0.9), T0 + 7300), "nothing after the last word"
    h = SR.history(c, 1, "s1")
    assert [k for _t, _p, k in h] == ["pre", "live", "live", "live", "lost"]
    assert h[-1][1] == 0.0 and SR.history(c, 2, "s1") == [], "another member's slip of the same id is not theirs"


def test_it_is_capped_and_pruned():
    c = _conn()
    for i in range(SR.CAP + 5):
        SR.bank(c, 1, "s2", _card("open", (i % 2) * 0.5), T0 + i)
    assert len(SR.history(c, 1, "s2")) == SR.CAP
    assert SR.bank(c, 1, "s2", _card("won"), T0 + 10_000), "the last word is kept past the cap"
    assert SR.prune(c, T0 + SR.KEEP_DAYS * 86400 + 20_000) == SR.CAP + 1 and SR.history(c, 1, "s2") == []


def test_the_sweep_keeps_it_and_the_endpoint_is_the_members_own():
    src = (ROOT / "engine" / "slipwatch.py").read_text(encoding="utf-8")
    i = src.index("def sweep(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "SR.ensure_table(conn)" in body and "SR.prune(conn, t)" in body
    assert body.index("SR.bank(conn, r[\"user_id\"], bid, card, t)") < body.index("done = settled(bet, card)"), \
        "kept before the settle, so the last word is on the tape"
    j = src.index("def run_once(")
    once = src[j:src.index("\ndef ", j + 10)]
    assert once.index("SR.ensure_table(conn)") < once.index("if not rows:"), \
        "the table is made on the first pass, slips or none (the box, 2026-10-16)"
    srv = (ROOT / "server.py").read_text(encoding="utf-8")
    assert '"/api/mybets/replay"' in srv
    j = srv.index("def _mybets_replay(")
    ep = srv[j:srv.index("\n    def ", j + 10)]
    assert "if not who or not self._entitled(conn, who):" in ep and "SR.history(conn, who[\"id\"], bid)" in ep


def test_an_account_s_replay_is_in_its_export_and_goes_with_it():
    """The Privacy Policy's pass of 2026-10-29: an account's deletion had
    left these rows to the 30-day prune, Download my data never carried
    them, and the policy never named the table."""
    import tempfile
    from engine import accounts as A
    with tempfile.TemporaryDirectory() as d:
        conn = A.connect(str(Path(d) / "acc.db"))
        SR.ensure_table(conn)
        _, who = A.create_user(conn, "you@example.com", "correct-horse-battery", confirmed=True)
        uid = int(who["id"])
        assert SR.bank(conn, uid, "s1", _card(ours=0.31), T0) and SR.bank(conn, uid, "s1", _card("won"), T0 + 3600)
        assert SR.bank(conn, uid + 1, "s9", _card(ours=0.5), T0), "somebody else's slip"
        conn.commit()
        got = A.export_user(conn, uid)["your_parlays_chance_through_the_night"]
        assert [(r["bet"], r["chance"], r["kind"]) for r in got] == [("s1", 0.31, "pre"), ("s1", 1.0, "won")], got
        A.delete_user(conn, uid)
        left = [tuple(r) for r in conn.execute("SELECT user_id FROM slip_chance")]
        assert left == [(uid + 1,)], ("only theirs goes", left)
    policy = (ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
    assert "<code>slip_chance</code>" in policy and "for the replay — 30 days" in policy


def _node(path, body):
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return None
    script = ("const vm = require('vm'); const fs = require('fs');"
              "const ctx = { window: {}, document: { addEventListener() {} } }; vm.createContext(ctx);"
              f"vm.runInContext(fs.readFileSync({json.dumps(str(path))}, 'utf8'), ctx);" + body)
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_live_slip_card_draws_the_meter():
    got = _node(SLIP, "const S = ctx.window.QBSlip;"
                "const a = S.sweatHTML('x', {status: 'open', chance: 0.42}), b = S.sweatHTML('x', {status: 'open', chance: 0.71}),"
                "c = S.sweatHTML('y', {status: 'open', chance: 0.08}), d = S.sweatHTML('y', {status: 'won'}),"
                "e = S.sweatHTML('z', {status: 'open'});"
                "process.stdout.write(JSON.stringify({a, b, c, d, e}));")
    if got is None:
        return
    assert "Coin flip" in got["a"] and "t-warn" in got["a"] and "since the last read" not in got["a"]
    assert "In control" in got["b"] and "▲ 29 since the last read" in got["b"], "the move from the read before"
    assert "Needs a miracle" in got["c"] and "t-bad" in got["c"]
    assert got["d"] == "" and got["e"] == "", "only a live slip whose rest has a number"
    src = SLIP.read_text(encoding="utf-8")
    assert 'sweatHTML(b.id, c.now) + hedgeHTML(c.hedge)' in src


def test_my_bets_plays_the_night_back():
    pts = [[T0, 0.31, "pre"], [T0 + 3600, 0.4, "live"], [T0 + 4200, 0.12, "live"], [T0 + 5400, 0.88, "live"],
           [T0 + 7200, 1.0, "won"]]
    got = _node(EXTRAS, f"const X = ctx.window.QBExtras;"
                f"process.stdout.write(JSON.stringify({{f: X.replayFacts({json.dumps(pts)}), html: X.replayHTML({{points: {json.dumps(pts)}}}),"
                f"none: X.replayHTML({{points: []}})}}));")
    if got is None:
        return
    f = got["f"]
    assert f["pre"] == 0.31 and f["end"] == "won" and f["lo"][1] == 0.12 and f["hi"][1] == 0.88
    assert abs(f["swing"]["d"] - 0.76) < 1e-9, "the biggest single jump, not the last word"
    html = got["html"]
    assert 'class="xr-path" pathLength="1"' in html and 'class="xr-end won"' in html
    assert "Before kickoff <b>31%</b>" in html and "Cashed" in html and "Our own number, not the book’s." in html
    assert "No replay for this slip yet" in got["none"]
    app = app_js()
    assert 'const replayBtn = (b) => b.src === "slip" && b.result !== "pending"' in app
    assert app.count("${replayBtn(b)}") == 2, "the card and the table both offer it"
    assert 'if (t.dataset.xt === "replay") replayInto(t);' in EXTRAS.read_text(encoding="utf-8")


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
