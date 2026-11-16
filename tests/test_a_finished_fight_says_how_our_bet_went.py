"""A finished UFC fight says how it ended and how our bet went, on its card.

Ethan, 2026-11-16: when it's over, show "if these props won or lost ... and
if our game report and reads was correct ... And that needs to be done for
all sports." UFC has no game page: its card is the fight's page. The live
card (data/ufc_live.json, engine/ufc/live) says each bout's end: who won,
how and when. Each fight card on the UFC tab carries a slot the live poll
fills as its bout ends (more.js ufcPaintResults): the result, and the bet the
card shows graded the way the fight-slip checker settles a leg
(engine/slipfight.result) for every market the card bets: the moneyline, the
distance, the method, a finish, the rounds and the exact round. A draw or a no
contest voids, as the record does (engine/ledger.settle_ufc). A bout two of
the card's fights could be, or one the feed hasn't said enough about, is left
ungraded. The fight report's call says whether it was right.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MORE = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
REPORT_JS = ROOT / "web" / "js" / "report.js"
UFC = MORE[MORE.index("/* EVERY FINISHED FIGHT, GRADED"):MORE.index("async function renderLiveFights(host) {")]
NORM = APP[APP.index("function resNorm(s) {"):APP.index("//: The game a pick belongs to")]

LIVE = {"bouts": [
    {"status": {"state": "post", "method": "KO/TKO", "round": 2, "clock": "3:10"},
     "fighters": [{"name": "Magomed Ankalaev", "winner": False}, {"name": "Alex Pereira", "winner": True}]},
    {"status": {"state": "post", "method": "DEC", "round": 3, "clock": "5:00"},
     "fighters": [{"name": "Kai Asakura", "winner": False}, {"name": "Tim Elliott", "winner": True}]},
    {"status": {"state": "post", "method": None, "round": 1, "clock": "1:02"},
     "fighters": [{"name": "Jon Doe", "winner": False}, {"name": "Jim Roe", "winner": False}]},
    {"status": {"state": "in", "round": 1, "clock": "2:00"},
     "fighters": [{"name": "Sean O'Malley", "winner": False}, {"name": "Merab Dvalishvili", "winner": False}]},
    {"status": {"state": "post", "method": "SUB", "round": 1, "clock": "2:30"},
     "fighters": [{"name": "Weili Zhang", "winner": True}, {"name": "Khalil Rountree Jr.", "winner": False}]},
    {"status": {"state": "post", "method": None, "round": 3, "clock": "5:00"},
     "fighters": [{"name": "Ann Lee", "winner": True}, {"name": "Bo Kim", "winner": False}]},
    {"status": {"state": "post", "method": "DEC", "round": 3, "clock": "5:00"},
     "fighters": [{"name": "Twin Smith", "winner": True}, {"name": "Other Jones", "winner": False}]},
    {"status": {"state": "post", "method": "DEC", "round": 3, "clock": "5:00"},
     "fighters": [{"name": "Twin Smith", "winner": False}, {"name": "Other Jones", "winner": True}]}]}


def _node(body):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    js = ("const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const escapeHtml = esc, escapeAttr = esc;"
          "const slots = []; const document = { querySelectorAll: () => slots };\n"
          + NORM + "\n" + UFC + f"\nUFC_LIVE = {json.dumps(LIVE)};\n"
          + f"process.stdout.write(JSON.stringify((() => {{ {body} }})()));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_each_bout_is_found_by_its_corners_and_read_once_it_is_over():
    got = _node("""const o = (f) => ufcOutcome(ufcBoutFor(f), f);
      return [o('Alex Pereira vs Magomed Ankalaev'), o("Sean O'Malley vs Merab Dvalishvili"),
              ufcBoutFor('Nobody vs Else'), o('Jon Doe vs Jim Roe'),
              o('Zhang Weili vs Khalil Rountree'), ufcBoutFor('Twin Smith vs Other Jones')];""")
    if got is None:
        return
    ko, live, none, draw, swapped, twice = got
    assert ko == {"winner": "Alex Pereira", "corner": 0, "method": "KO/TKO", "round": 2, "clock": "3:10"}, \
        "the feed lists him second; the card's own name and corner come back"
    assert live is None, "a bout still going says nothing"
    assert none is None
    assert draw["winner"] == "" and draw["corner"] is None, "no winner: a draw or a no contest"
    assert swapped["winner"] == "Zhang Weili" and swapped["corner"] == 0, \
        "his names in the other order, and a Jr. the card leaves off, are the same fighters"
    assert twice is None, "two bouts fit: no guess"


def test_every_market_the_card_bets_is_graded_the_checker_s_way():
    got = _node("""
      const o = (f) => ufcOutcome(ufcBoutFor(f), f);
      const ko = o('Alex Pereira vs Magomed Ankalaev'), dec = o('Kai Asakura vs Tim Elliott');
      const nc = o('Jon Doe vs Jim Roe'), sub = o('Zhang Weili vs Khalil Rountree');
      const blind = o('Ann Lee vs Bo Kim');
      const g = (fight, market, selection, out) => ufcGrade({ fight, market, selection }, out);
      const P = 'Alex Pereira vs Magomed Ankalaev', E = 'Kai Asakura vs Tim Elliott';
      const Z = 'Zhang Weili vs Khalil Rountree', L = 'Ann Lee vs Bo Kim';
      return {
        ml: [g(P, 'moneyline', 'Alex Pereira', ko), g(P, 'moneyline', 'Magomed Ankalaev', ko),
             g(Z, 'moneyline', 'Zhang Weili', sub), g(L, 'moneyline', 'Ann Lee', blind)],
        distance: [g(E, 'distance', 'Goes the distance', dec), g(P, 'distance', "Doesn't go the distance", ko),
                   g(P, 'distance', 'Goes the distance', ko), g(L, 'distance', 'Goes the distance', blind)],
        method: [g(P, 'method', 'Alex Pereira by KO/TKO', ko), g(P, 'method', 'Alex Pereira by Submission', ko),
                 g(E, 'method', 'Tim Elliott by Decision', dec), g(P, 'method', 'Magomed Ankalaev by KO/TKO', ko),
                 g(L, 'method', 'Ann Lee by Decision', blind), g(L, 'method', 'Bo Kim by Decision', blind)],
        finish: [g(P, 'fighter_finish', 'Alex Pereira by finish (KO or SUB)', ko),
                 g(Z, 'fighter_finish', 'Zhang Weili by finish (KO or SUB)', sub),
                 g(E, 'fighter_finish', 'Tim Elliott by finish (KO or SUB)', dec)],
        rounds: [g(P, 'round', 'Under 1.5 rounds', ko), g(P, 'round', 'Over 1.5 rounds', ko),
                 g(E, 'round', 'Over 2.5 rounds', dec), g(E, 'round', 'Under 2.5 rounds', dec),
                 g(Z, 'round', 'Under 0.5 rounds', sub), g(Z, 'round', 'Over 0.5 rounds', sub)],
        exact: [g(P, 'exact_round', 'Ends in round 2', ko), g(P, 'exact_round', 'Ends in round 1', ko),
                g(E, 'exact_round', 'Ends in round 3', dec)],
        void: [g('Jon Doe vs Jim Roe', 'moneyline', 'Jon Doe', nc), g('Jon Doe vs Jim Roe', 'distance', 'Goes the distance', nc)],
        words: [ufcOutcomeWords(ko), ufcOutcomeWords(dec), ufcOutcomeWords(nc), ufcOutcomeWords(sub),
                ufcOutcomeWords(blind)],
      };""")
    if got is None:
        return
    assert got["ml"] == ["won", "lost", "won", "won"], "who won needs no method"
    assert got["distance"] == ["won", "won", "lost", None], "not graded until the feed says how it ended"
    assert got["method"] == ["won", "lost", "won", "lost", None, "lost"], \
        "the loser's method bet is lost whatever the method; the winner's waits on it"
    assert got["finish"] == ["won", "won", "lost"]
    assert got["rounds"] == ["lost", "won", "won", "lost", "lost", "lost"], \
        "3:10 of round 2 is 1.63 rounds; a decision goes over every line; exactly on the line loses both ways"
    assert got["exact"] == ["won", "lost", "lost"], "a decision ends in no round"
    assert got["void"] == ["void", "void"], "a draw or a no contest voids, as the record does"
    assert got["words"] == ["Alex Pereira won by KO/TKO at 3:10 of round 2", "Tim Elliott won by decision",
                            "No winner: a draw or a no contest", "Zhang Weili won by submission at 2:30 of round 1",
                            "Ann Lee won"]


def test_the_live_poll_fills_each_finished_fight_s_slot():
    got = _node("""
      const mk = (f) => ({ dataset: { ufcResult: f }, innerHTML: '' });
      slots.push(mk('Alex Pereira vs Magomed Ankalaev'), mk('Kai Asakura vs Tim Elliott'),
                 mk("Sean O'Malley vs Merab Dvalishvili"), mk('Ann Lee vs Bo Kim'));
      UFC_TAB_ROWS = [{ fight: 'Alex Pereira vs Magomed Ankalaev', kind: 'pick', market: 'moneyline',
                        selection: 'Magomed Ankalaev', pick: 'Magomed Ankalaev' },
                      { fight: 'Kai Asakura vs Tim Elliott', kind: 'pass', market: 'moneyline', selection: 'Tim Elliott' },
                      { fight: 'Ann Lee vs Bo Kim', kind: 'pick', market: 'distance', selection: 'Goes the distance' }];
      ufcPaintResults();
      return slots.map((s) => s.innerHTML);""")
    if got is None:
        return
    assert got[0] == ('<span class="ufc-res-k">Final</span> Alex Pereira won by KO/TKO at 3:10 of round 2 '
                      '<span class="ufc-res-v lost">Our bet lost</span>'), got[0]
    assert got[1] == '<span class="ufc-res-k">Final</span> Tim Elliott won by decision', "a pass has no bet"
    assert got[2] == "", "still going: the slot stays empty"
    assert got[3] == '<span class="ufc-res-k">Final</span> Ann Lee won', "how it ended unsaid: the bet waits"
    assert MORE.count("${ufcResultSlot(p)}") == 1 and MORE.count("${ufcResultSlot(m)}") == 1
    assert "  UFC_LIVE = d;\n  ufcPaintResults();\n" in MORE, "every poll, finished bouts and all"
    assert "  ufcPaintResults();\n  // Each fight's path (js/extras.js)" in MORE, \
        "and once the cards land, if the live card came in first"
    assert ".ufc-res:empty { display: none; }" in (ROOT / "web" / "css" / "more.css").read_text(encoding="utf-8")


def test_the_card_and_the_slip_checker_never_disagree():
    """Every market, every way a bout can end: the card's grade is the slip
    checker's (engine/slipfight.result), the one ruling a fight leg anywhere."""
    from engine import slipfight
    fight = "Alex Pereira vs Magomed Ankalaev"
    bets = [("moneyline", "Alex Pereira", {"market": "moneyline"}, 0),
            ("moneyline", "Magomed Ankalaev", {"market": "moneyline"}, 1),
            ("distance", "Goes the distance", {"market": "fight_distance", "side": "yes"}, None),
            ("distance", "Doesn't go the distance", {"market": "fight_distance", "side": "no"}, None)]
    for name, corner in (("Alex Pereira", 0), ("Magomed Ankalaev", 1)):
        for label, leg in (("KO/TKO", "win_ko"), ("Submission", "win_sub"), ("Decision", "win_dec")):
            bets.append(("method", f"{name} by {label}", {"market": leg}, corner))
        bets.append(("fighter_finish", f"{name} by finish (KO or SUB)", {"market": "win_finish"}, corner))
    for x in (0.5, 1.5, 2.5):
        bets.append(("round", f"Under {x:g} rounds", {"market": "fight_rounds", "side": "under", "line": x}, None))
        bets.append(("round", f"Over {x:g} rounds", {"market": "fight_rounds", "side": "over", "line": x}, None))
    for r in (1, 2, 3):
        bets.append(("exact_round", f"Ends in round {r}", {"market": "fight_round", "line": float(r)}, None))
    outs = [(w, m, r, c) for w in (0, 1) for m in ("KO/TKO", "SUB", "DEC", None)
            for r in (1, 2, 3) for c in ("0:45", "2:30", "4:59", "5:00")]
    cases, want = [], []
    for market, sel, leg, corner in bets:
        for w, m, r, c in outs:
            cases.append([market, sel, w, m, r, c])
            want.append(slipfight.result(leg, corner, w, m, r, c))
    got = _node(f"""const fight = {json.dumps(fight)};
      return {json.dumps(cases)}.map(([market, selection, w, m, r, c]) => ufcGrade({{ fight, market, selection }},
        {{ winner: fight.split(' vs ')[w], corner: w, method: m || '', round: r, clock: c }}));""")
    if got is None:
        return
    off = [(cases[i], want[i], got[i]) for i in range(len(cases)) if want[i] != got[i]]
    assert not off, f"{len(off)} of {len(cases)} disagree, e.g. {off[:4]}"
    assert len(cases) > 1500


def test_the_record_journals_the_bet_the_card_shows():
    """The record journals each UFC pick as its fighter's moneyline at the
    moneyline's price (engine/ledger.log_ufc_picks). That is the bet the card
    shows, and so the bet its result grades, only while no prop price reaches
    the model: engine/ufc/model prices a method, finish, distance or round
    row only off a fight's prices["props"], and ufc_build sets none. If a
    props feed lands, the record must journal the card's own market and
    price first, or a card reading "Our bet lost" would count as a win."""
    from engine.ufc.model import evaluate_fight, win_probability
    base = {"age": 29, "division": "lightweight", "archetype": "pressure", "ufc_fights": 8, "fights": 14,
            "slpm": 4.5, "sapm": 3.5, "kd_per100": 1.2, "td_per15": 1.0, "td_acc": 0.40, "tdd": 0.65,
            "ctrl_per15": 2.0, "sub_att_per15": 0.4, "ko_losses": 1, "ko_losses_last3": 0, "times_finished": 2,
            "r3_decay": 0.12, "red_flags": []}
    a, b = dict(base, name="A", slpm=5.2, sapm=3.0), dict(base, name="B", age=33, sapm=4.0)
    p, _ = win_probability(a, b)

    def amer(x):
        return int(round(-100 * x / (1 - x))) if x > 0.5 else int(round(100 * (1 - x) / x))

    def prices(x, **more):
        return dict({"fighter_a": "A", "fighter_b": "B", "a_odds": amer(x), "b_odds": amer(1 - x - 0.04),
                     "book": "DK"}, **more)

    rows = [evaluate_fight(a, b, prices(p - d), "lightweight", 0) for d in (0.02, 0.04, 0.06, 0.08)]
    priced = [r for r in rows if r.get("market")]
    assert len(priced) == 4
    for r in priced:
        assert r["market"] == "moneyline" and r["selection"] == r["pick"], r
        assert r["best_market"]["odds"] == r["odds"], "the card's price is the one the record journals"
    props = {"A by KO/TKO": 450, "A by Decision": 250, "Doesn't go the distance": 120, "Goes the distance": -140}
    other = evaluate_fight(a, b, prices(p - 0.02, props=props), "lightweight", 0)
    assert other["market"] != "moneyline", "a prop price is what would make the card bet something else"
    build = (ROOT / "ufc_build.py").read_text(encoding="utf-8")
    assert '"props"' not in build and "'props'" not in build, \
        "a props feed: journal the card's own market and price first (engine/ledger.log_ufc_picks)"
    ledger = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")
    assert 'now, "ufc", date, p["pick"], "moneyline", "OVER", 0.5,' in ledger


def test_the_fight_report_s_call_says_right_or_wrong():
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return
    rep = {"game": "Alex Pereira vs Magomed Ankalaev", "minutes": 1, "sections": [
        {"key": "verdict", "title": "Who we think wins", "blocks": [
            {"type": "winner", "team": "Alex Pereira", "other": "Magomed Ankalaev", "name": "Alex Pereira",
             "other_name": "Magomed Ankalaev", "chance": 0.56, "word": "A lean"}]}]}
    js = ("const vm = require('vm'); const fs = require('fs');"
          "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, slugify: (s) => s, teamName: (t) => t,"
          " playerAvatar: () => '' }; vm.createContext(ctx);"
          f"vm.runInContext(fs.readFileSync({json.dumps(str(REPORT_JS))}, 'utf8'), ctx);"
          f"const rep = {json.dumps(rep)}; const R = ctx.window.QBReport;"
          "const r = (winner, how) => R.html(rep, { fight: true, results: { ufc: true, winner, how } });"
          "process.stdout.write(JSON.stringify([r('Alex Pereira', 'Alex Pereira won by KO/TKO at 3:10 of round 2'),"
          " r('Magomed Ankalaev', 'Magomed Ankalaev won by decision'), R.html(rep, { fight: true }),"
          " r('', 'No winner: a draw or a no contest'), r('Pereira Alex', 'Pereira Alex won'),"
          " r('Somebody Else', 'Somebody Else won')]));")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    right, wrong, before, draw, swapped, neither = json.loads(out.stdout)
    assert '<div class="gr-res-call won">Right: Alex Pereira won by KO/TKO at 3:10 of round 2</div>' in right
    assert '<div class="gr-res-call lost">Wrong: Magomed Ankalaev won by decision</div>' in wrong
    assert "gr-res-call" not in before
    assert '<div class="gr-res-call">No winner: a draw or a no contest</div>' in draw
    assert '<div class="gr-res-call won">Right: Pereira Alex won</div>' in swapped
    assert "gr-res-call" not in neither, "a winner the call doesn't name: no guess"
    assert "R.html(r, { fight: true, results })" in MORE


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
