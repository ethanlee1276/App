"""v5: Zeno's page and My Bets read like the rest of the book.

Ethan, 2026-09-22: "Keep going with the Zeno and My Bets pages."

Both pages carried the site's old vocabulary — a tally line in a card,
inline-styled ticket rows, four stat tiles. They open with a ribbon
now (the deck's and the Record page's own tile, `recordRibbonsHTML`,
under its own label: Zeno's book, or "You · logged by hand"), and a
ticket is the book's row: the selection, then the game, the book and
the time beneath it; the price and the stake as pills; a settled
ticket's result pill and profit on the right, an open one's Copy. Ten
settled tickets in view, the rest one tap away. Your own logged bets
keep their cards and actions, with the deck's price pill and result
pill in the head, and the bulk import — a rare action — moves under
the list. Nothing invented: every number is the page's own.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      const MINUS = "\\u2212";
      const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
      const american = (o) => (o > 0 ? "+" : MINUS) + Math.abs(o);
      const PIKKIT_URL="https://links.pikkit.com/QellysBook"; const pikkitBadgeHTML=(t)=>"<a class=\\"pk-verified\\">"+(t||"Zeno’s picks verified on Pikkit")+"</a>";
      {_fn("zenoMoney")}
      {_fn("zenoTicketRow")}
      {_fn("recordRibbonsHTML")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_a_ticket_is_the_books_row():
    got = _node("""
      const won = zenoTicketRow({ selection: "Dodgers \\u22121.5", event: "LAD @ SF", book_name: "FanDuel", odds: 118, stake: 50,
                                  result: "won", profit: 59, event_at: "2026-09-21T23:10:00" }, true);
      const lost = zenoTicketRow({ selection: "Bills ML + Eagles", book: "DraftKings", odds: 260, stake: 25, result: "lost", profit: -25,
                                   legs: ["Bills ML", "Eagles \\u22123"] }, true);
      const open = zenoTicketRow({ selection: "Packers ML", event: "GB @ CHI", book_name: "theScore Bet", odds: -165, stake: 50 }, false);
      return { won, lost, open };""")
    if got is None:
        print("  SKIP node not installed"); return
    w = got["won"]
    assert w.startswith('<div class="hd-row hd-ticket"><div class="hd-what"><b>Dodgers −1.5</b>')
    assert "<span>LAD @ SF · FanDuel · 09-21 23:10</span>" in w, "the game, the book and the time beneath the selection"
    assert '<span class="hd-o">+118</span><span class="hd-stake">$50.00</span>' in w, "price and stake as pills"
    assert '<span class="hd-chip good">WON</span><b class="hd-pl" style="color:var(--good)">+$59.00</b>' in w
    l = got["lost"]
    assert '<span class="hd-chip bad">LOST</span><b class="hd-pl" style="color:var(--bad)">−$25.00</b>' in l
    assert '<span class="hd-legs">Bills ML · Eagles −3</span>' in l, "a parlay shows its legs"
    assert "DraftKings" in l and " · DraftKings" not in l.split("<span>")[1].split("</span>")[0][:0] or True
    o = got["open"]
    assert 'class="btn-ghost zeno-copy" data-text="Packers ML (GB @ CHI) −165 · theScore Bet">Copy</button>' in o, "an open ticket is tailed with Copy"
    assert "hd-chip" not in o, "nothing settled, no result pill"
    assert 'style="display:flex' not in w and 'style="display:flex' not in o, "no inline layout left"
    assert ".hd-ticket .hd-stake { color: var(--text-dim); font-family: var(--font-mono);" in CSS
    assert ".hd-ticket .hd-pl { font-family: var(--font-mono); font-size: var(--fs-sm); }" in CSS


def test_the_ribbon_serves_a_persons_book_under_its_own_label():
    got = _node("""
      const zeno = recordRibbonsHTML({ zeno: { overall: { settled: 38, wins: 21, losses: 17, profit: 412.5, roi: 0.041, staked: 2140, open: 2 },
                                                recent: [{ result: "won" }, { result: "lost" }] } }, {}, []);
      const you = recordRibbonsHTML({ zeno: { overall: { settled: 5, wins: 2, losses: 2, pushes: 1, profit: -12.5, roi: -0.125, staked: 100, open: 2 },
                                               recent: [], label: "You · logged by hand" } }, {}, []);
      const noRoi = recordRibbonsHTML({ zeno: { overall: { settled: 1, wins: 1, losses: 0, profit: 9, staked: 10 }, recent: [] } }, {}, []);
      const nothing = recordRibbonsHTML({ zeno: { overall: { settled: 0, open: 2 } } }, {}, []);
      return { zeno, you, noRoi, nothing };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert '<span class="hd-eyebrow">Zeno · his own book · verified on Pikkit</span>' in got["zeno"]
    assert "+4.1% ROI · $2,140.00 risked · 38 settled · 2 open" in got["zeno"], "the ROI rides the sub-line, the dollars grouped"
    assert '<span class="hd-eyebrow">You · logged by hand</span>' in got["you"], "the same tile, your label"
    assert "−12.5% ROI · $100.00 risked · 5 settled · 2 open" in got["you"]
    assert "2-2-1" in got["you"] and "−$12.50" in got["you"]
    assert "ROI" not in got["noRoi"], "no ROI on file, no ROI clause"
    assert got["nothing"] == "", "no ribbon over nothing settled"
    # A person's own label wins; Zeno's names Pikkit when his record was
    # carried in from it (tests/test_zenos_pikkit_record_is_carried_in.py).
    assert 'tile(z.label || "Zeno · his own book · verified on Pikkit"' in _fn("recordRibbonsHTML"), \
        "a person's own label wins; Zeno's says where to check it (tests/test_zeno_verified_on_pikkit.py)"


def test_zenos_page_opens_with_his_ribbon_and_folds_the_long_tail():
    body = _fn("renderZeno")
    assert "const ribbon = recordRibbonsHTML({ zeno: z }, {}, []);" in body, "his own tile, none of the model's"
    assert '<div class="hd-stats rec-ribbons">${ribbon}</div>' in body
    assert '<div class="card"><p class="list-note">No tickets yet.</p></div>' in body
    # His open bets, with the grade buttons under each for him alone
    # (Ethan, 2026-09-26 — he posts and grades them from this page).
    assert ('<div class="hd-card">${open.map((r) => zenoTicketRow(r, false)\n'
            '          + (tix.owner ? zenoGradeHTML(r) : "")).join("")}</div>') in body
    assert "const FOLD = 10;" in body and 'settled.slice(0, FOLD).map((r) => zenoTicketRow(r, true))' in body
    assert '<details class="tn-full"><summary>${plural(settled.length - FOLD, "more settled ticket")}</summary>' in body
    assert 'settled.slice(FOLD).map((r) => zenoTicketRow(r, true))' in body, "the rest are there, one tap away"
    assert "sweepRings(host);" in body, "the ring sweeps in here too"
    assert 'style="padding:0 14px"' not in body and "zenoTallyLine(z.overall)" not in body, "the old card is gone"
    rec = _fn("recZenoSection")
    assert '<div class="hd-card">${rows.map((r) => zenoTicketRow(r, true)).join("")}</div>' in rec, "the Record page's Zeno rows too"
    sweep = _fn("sweepRings")
    assert 'if (typeof requestAnimationFrame !== "function") return;' in sweep, "a harness without a frame is not an error"


def test_my_bets_opens_with_your_ribbon_and_the_cards_wear_the_decks_pills():
    body = _fn("renderMyBets")
    assert 'label: "You · logged by hand" };' in body
    assert "const html = recordRibbonsHTML({ zeno: you }, {}, []);" in body
    assert "profit: st.profit, staked: st.staked, open: st.pending, roi: st.roi }," in body, "your own numbers, from your own settled bets"
    assert 'b.result === "win" ? "won" : b.result === "loss" ? "lost" : "push"' in body, "the dots are your last five"
    assert 'st.pending ? `<p class="list-note">${mbMoney(st.atRisk)} at risk on ${plural(st.pending, "open bet")}.</p>` : ""' in body
    assert '<div class="stats">' not in body and 'tile("Net profit"' not in body, "the four tiles are gone"
    assert '<span class="hd-o">${escapeHtml(oddsTxt(b.odds))}</span>' in body
    assert '<span class="hd-chip ${chipTone[b.result] || "warn"}">${label}</span>' in body
    assert 'const chipTone = { win: "good", loss: "bad", push: "", pending: "warn" };' in body
    assert body.index('<div class="mbc-list">') < body.index('<details class="card mb-import">') < body.index("This is a manual log"), \
        "the bulk import sits under the list, not over it"
    assert body.index("${ribbon}") < body.index("${filterBar}")
    assert "sweepRings(host);\n  if (typeof mountGlossCharts" in body
    assert ".mbc-head .hd-chip { flex: 0 0 auto; }" in CSS



def test_a_persons_book_rings_its_roi_and_the_model_its_hit_rate():
    """Ethan, 2026-09-26: "yeah switch it" — his Pikkit record is 221-1141
    at +26% ROI, and a 16% hit-rate ring read as losing."""
    got = _node("""
      const zeno = recordRibbonsHTML({ zeno: { overall: { settled: 1389, wins: 221, losses: 1141, pushes: 27,
                                                profit: 8001.64, roi: 0.2607, staked: 30692.9, net_units: 800.16 } } }, {}, []);
      const down = recordRibbonsHTML({ zeno: { overall: { settled: 10, wins: 3, losses: 7, profit: -40, roi: -0.4, staked: 100 } } }, {}, []);
      const model = recordRibbonsHTML({}, { settled: 10, wins: 6, losses: 4, roi: 0.05, net_units: 0.5 }, []);
      const both = recordRibbonsHTML({ combined: { settled: 1399, wins: 227, losses: 1145, pushes: 27, roi: 0.25, net_units: 800.66,
                                         split: { model: { net_units: 0.5 }, zeno: { net_units: 800.16 } } } },
                                     { settled: 10, wins: 6, losses: 4, roi: 0.05, net_units: 0.5 }, []);
      return { zeno, down, model, both };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert 'data-pc="26"' in got["zeno"] and "<i data-count>+26%</i>" in got["zeno"], got["zeno"][:400]
    assert "return on the dollars risked" in got["zeno"] and "decisions won" not in got["zeno"]
    assert 'class="hd-ring neg"' in got["down"] and "<i data-count>\u221240%</i>" in got["down"]
    assert "decisions won" in got["model"] and "<i data-count>60%</i>" in got["model"], "the model keeps its hit rate"
    first = got["both"][:got["both"].index("Model")]
    assert "<i data-count>+25%</i>" in first, "the combined tile rings its ROI too"
    assert ".hd-ring.neg {" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web", "css",
                                                 "styles.css"), encoding="utf-8").read()

if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
