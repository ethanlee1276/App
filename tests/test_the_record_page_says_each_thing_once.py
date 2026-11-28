"""The Record page says each thing once, in words (RECDUP1, 2026-11-17).

Ethan: "You need to think like a user and wonder why all this information is
here. Why is all this repeated stuff here?"

The NBA's record was read top to bottom on the live site's own data that day,
about twenty phone screens of it. Three things on it:

  * the week's card printed the journal's market codes ("under 2.5 fg3m",
    "over 13.5 pts reb", "under 1.5 stl") and called one of its books "The
    one board", a name no page uses. It says the market in the site's words
    and the books by the names their own sections carry further down;
  * a league's tab listed its report picks and its tickets twice: the newest
    of each in a flat list under their totals, then every finished game's
    picks and parlays under How our reports did. Once the games are listed,
    the flat lists give way to one line that points at them; a league with
    no finished game checked yet keeps its lists, and so do the All tab and
    the Report Picks page's own record;
  * "By kind" held one row that repeated the tile above it word for word.
    A split is two kinds or more.

    python3 tests/test_the_record_page_says_each_thing_once.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REC = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")
RP = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "record.css").read_text(encoding="utf-8")

STUBS = r"""
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => '&#' + c.charCodeAt(0) + ';');
const escapeHtml = esc, escapeAttr = esc;
const icon = () => '', trueMinus = (x) => x, recWinDate = (d) => d;
const american = (o) => (o > 0 ? '+' + o : String(o));
const SPORT_META = { nba: { name: 'NBA' } };
const WORDS = { fg3m: '3-Pointers Made', pts_reb: 'Pts+Reb', stl: 'Steals' };
const marketWord = (k) => WORDS[k] || String(k).replace(/_/g, ' ');
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + 's'}`;
const tlUnits = (u) => `${u >= 0 ? '+' : '-'}${Math.abs(u).toFixed(2)}u`;
const toneOf = (u) => (u >= 0 ? 'pos' : 'neg');
const recTile = (k, v, sub) => `<div class="tile"><b>${k}</b>${v}<small>${sub || ''}</small></div>`;
const PARLAY_RATE_FLOOR = 20;
const lgCode = (s) => String(s).toUpperCase();
const GP_SCORE = {};
"""


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _const(src, name):
    i = src.index(f"const {name} = ")
    return src[i:src.index(";\n", i) + 2]


def _node(body: str, *names, extra: str = ""):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    js = STUBS + extra + "\n".join(names) + f"\nprocess.stdout.write(JSON.stringify((() => {{ {body} }})()));"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_weeks_card_says_the_market_in_words_and_the_books_by_their_sections():
    week = {"from": "2026-11-11", "to": "2026-11-17", "books": [
        {"book": "Most Likely", "w": 422, "l": 239, "p": 0, "units": -0.8, "hit": 0.64, "claimed": 0.61, "price": 0.64,
         "best": {"player": "James Harden", "side": "UNDER", "line": 2.5, "market": "fg3m", "odds": -110},
         "worst": {"player": "Deni Avdija", "side": "UNDER", "line": 3.5, "market": "fg3m", "odds": -245, "claim": 0.72}},
        {"book": "The one board", "w": 433, "l": 273, "p": 0, "units": -2.6, "hit": 0.61, "claimed": 0.61, "price": 0.64,
         "best": {"player": "Naji Marshall", "side": "OVER", "line": 13.5, "market": "pts_reb", "odds": -103},
         "worst": {"player": "Kyrie Irving", "side": "UNDER", "line": 1.5, "market": "stl", "odds": -230, "claim": 0.7}},
        {"book": "Edge picks", "w": 40, "l": 41, "p": 0, "units": 2.0, "hit": 0.49, "claimed": 0.53, "price": 0.48}]}
    got = _node(f"return weekRecapHTML({json.dumps(week)}, '');", _const(REC, "WK_BOOK"), _fn(REC, "weekRecapHTML"))
    if got is None:
        return
    assert "Best hit: James Harden under 2.5 3-Pointers Made (-110)" in got, got
    assert "Best hit: Naji Marshall over 13.5 Pts+Reb (-103)" in got
    assert "Toughest miss: Kyrie Irving under 1.5 Steals (-230) at 70%" in got
    for code in ("fg3m", "pts reb", " stl "):
        assert code not in got, code
    assert "<b>Most Likely list, staked picks</b>" in got and "<b>Most Likely board, every tier</b>" in got
    assert "<b>Edge picks</b>" in got and "The one board" not in got, "a name no page says"
    # The section titles those names are taken from.
    assert "Most Likely board" in REC and "Most Likely — ${" in REC and '"staked picks"' in REC


def _rep(by_market):
    """A league's report picks as the record file carries them: each market's wins, losses and units."""
    return {"settled": sum(v["w"] + v["l"] for v in by_market.values()), "open": 30,
            "wins": sum(v["w"] for v in by_market.values()), "losses": sum(v["l"] for v in by_market.values()),
            "net_units": round(sum(v["net_u"] for v in by_market.values()), 2), "by_market": by_market}


def test_one_kind_is_not_a_split():
    names = [_const(REC, n) for n in ("REC_RP_KINDS", "RP_SCORER_MARKETS", "RP_GAME_MARKETS", "RP_SOURCES",
                                      "RP_SOURCE_BEFORE")] + [
        _fn(REC, n) for n in ("rpKindOf", "rpKindWord", "rpKinds", "rpSourcesHTML", "rpPickWords", "rpPicksHTML")]
    recent = [{"sport": "nba", "date": "2026-11-16", "player": "Zach Edey", "side": "OVER", "line": 6.5,
               "market": "reb", "odds": -150, "status": "won"}]
    one = _rep({"reb": {"w": 40, "l": 20, "net_u": 0.2}, "ast": {"w": 29, "l": 12, "net_u": 0.14}})
    two = _rep({"reb": {"w": 60, "l": 30, "net_u": 0.3}, "moneyline": {"w": 9, "l": 2, "net_u": 0.04}})
    got = _node(f"""return {{ kinds: [Object.keys(rpKinds({json.dumps(one)})), Object.keys(rpKinds({json.dumps(two)}))],
                           one: rpPicksHTML({json.dumps(one)}, 'nba', {json.dumps(recent)}),
                           two: rpPicksHTML({json.dumps(two)}, 'nba', {json.dumps(recent)}) }};""", *names)
    if got is None:
        return
    assert len(got["kinds"][0]) == 1 and len(got["kinds"][1]) == 2, got["kinds"]
    assert "69 of 101" in got["one"] and "By kind" not in got["one"], "one row that says the tile above again"
    assert "By kind" in got["two"] and "<b>60 of 90</b> hit" in got["two"] and "<b>9 of 11</b> hit" in got["two"]
    # The newest picks are marked as the tab's flat list, to be said once (below).
    assert '<div data-rec-flat="picks"><div class="rr-head">Newest picks</div>' in got["one"]


def test_a_leagues_tab_lists_its_receipts_once():
    fake = r"""
const flats = [{ dataset: { recFlat: 'picks' }, innerHTML: 'ten rows' }, { dataset: { recFlat: 'parlays' }, innerHTML: 'ten tickets' }];
const host = { querySelectorAll: (s) => (s === '[data-rec-flat]' ? flats : []) };
"""
    got = _node("""
      const out = {};
      recReceiptsOnce(host, { isConnected: true }, 0); out.none = flats.map((f) => f.innerHTML);
      recReceiptsOnce(host, { isConnected: false }, 8); out.gone = flats.map((f) => f.innerHTML);
      recReceiptsOnce(host, { isConnected: true }, undefined); out.failed = flats.map((f) => f.innerHTML);
      recReceiptsOnce(host, { isConnected: true }, 8); out.listed = flats.map((f) => f.innerHTML.replace(/\\s+/g, ' '));
      return out;""", _fn(REC, "recReceiptsOnce"), extra=fake)
    if got is None:
        return
    for k in ("none", "gone", "failed"):
        assert got[k] == ["ten rows", "ten tickets"], (k, "no finished game listed: the flat lists are the receipts")
    picks, tickets = got["listed"]
    # Said once, after the last block (walk 8, 2026-11-18: the NFL tab said it three times running), naming
    # what the blocks above it held.
    assert picks == "", picks
    assert "Each game’s picks and tickets, hit or missed, are listed game by game under" in tickets
    assert "ten tickets" not in tickets
    assert 'data-rec-to-facts>How our reports did</button>, below.' in tickets
    # Wired: the fact checks answer with how many games they listed, and the mount passes it on.
    assert ('rpFactsInto(el, el.dataset.recFacts).then((games) => recReceiptsOnce(host, el, games));' in REC)
    into = _fn(RP, "rpFactsInto")
    assert "if (!slot || !league) return 0;" in into and "return (await rpFactsFill(slot, league)) || 0;" in into
    fill = RP[RP.index("async function rpFactsFill("):RP.index("/* EVERY PICK AND PARLAY, A CHECK OR AN X")]
    assert fill.rstrip().endswith("return games.length;\n}".rstrip()), "the games it listed"
    assert '<div data-rec-flat="parlays"><div class="rr-head">Newest tickets</div>' in REC
    # The Report Picks page's own record never mounts the fact checks beside it: its lists stay.
    book = _fn(REC, "renderReportBook")
    assert "recReceiptsOnce" not in book and "recFactsMount" not in book
    assert ".rec-to-facts {" in CSS and "[data-rec-to-facts]" in REC


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
