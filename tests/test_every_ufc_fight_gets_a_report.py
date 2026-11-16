"""Every fight on the UFC card gets a written report, like every game report.

Ethan, 2026-11-16, asked whether UFC should get a written fight report: "Yes".
engine/ufc/report.build turns each row the card writes (its picks and its
pass list) into a report in the game reports' own shape. ufc_build attaches
them as `fight_reports`, a paid key (engine/gate.PAID_KEYS), and the UFC tab
folds each one into its fight's card, drawn by js/report.js when opened. The
call follows the price, our fight model's chance beside it; the case for
each corner comes from the card's own measured numbers.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.ufc import report as U  # noqa: E402

REPORT_JS = ROOT / "web" / "js" / "report.js"
MORE_JS = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
MORE_CSS = (ROOT / "web" / "css" / "more.css").read_text(encoding="utf-8")


def _brief(name, **kw):
    out = {"name": name, "has_dossier": True, "record": "15-3", "age": 30, "archetype": "pressure", "slpm": 4.0,
           "sapm": 3.5, "tdd": 0.75, "td_per15": 0.5, "sub_att_per15": 0.2, "covered": 8, "red_flags": []}
    out.update(kw)
    return out


def _pick(**kw):
    row = {"fight": "Alex Pereira vs Magomed Ankalaev", "division": "light_heavyweight", "kind": "pick",
           "fighters": [_brief("Alex Pereira", age=38, archetype="counter", slpm=5.1, sapm=3.4, tdd=0.7),
                        _brief("Magomed Ankalaev", age=32, archetype="wrestler", slpm=3.6, sapm=2.4, tdd=0.86,
                               red_flags=["missed weight in 2024"])],
           "pick": "Magomed Ankalaev", "odds": 120, "book": "DraftKings", "p_model": 0.52, "p_market": 0.44,
           "p_final": 0.47, "method": {"a_ko": 0.33, "a_sub": 0.02, "a_dec": 0.21, "b_ko": 0.12, "b_sub": 0.04,
                                       "b_dec": 0.28, "distance": 0.49},
           "e_minutes": 17.6, "scheduled_rounds": 5, "weigh_in": {"a": {"state": "made"}, "b": {"state": "unrecorded"}},
           "environment": {"venue": "T-Mobile Arena", "city": "Las Vegas", "why": ["a 30-foot arena cage"]},
           "market": "moneyline", "selection": "Magomed Ankalaev", "best_market": {"odds": 120, "edge": 0.0245},
           "grade_score": 71, "grade_label": "B", "stake_units": 0.5,
           "kill_if": "missed weight, late replacement, or visible cut damage at weigh-ins → automatic void",
           "style_notes": ["Style: no strong style read"]}
    row.update(kw)
    return row


def _sec(rep, key):
    return next((s for s in rep["sections"] if s["key"] == key), None)


def _items(sec):
    return [i for b in sec["blocks"] if b["type"] == "list" for i in b["items"]]


def test_a_picked_fight_is_written_out_in_the_reports_order():
    rep = U.build(_pick())
    assert [s["key"] for s in rep["sections"]] == ["verdict", "fighters", "ends", "camp", "bet", "kill"]
    assert rep["title"] == "Alex Pereira vs Magomed Ankalaev" and rep["sport"] == "ufc" and rep["minutes"] >= 1
    call = _sec(rep, "verdict")
    win = call["blocks"][0]
    assert (win["type"], win["team"], win["word"], win["chance"]) == ("winner", "Alex Pereira", "A lean", 0.56), win
    items = _items(call)
    assert items[0].startswith("Alex Pereira to win, a 56% chance by the books' moneyline with their cut taken out")
    assert items[1] == "Our fight model: Magomed Ankalaev 52%, the other corner from the price."
    assert items[2] == "The chance our bet is priced at, held near the price: Magomed Ankalaev 47%."
    assert "Alex Pereira is 38, past the sport's peak years (27 to 32); Magomed Ankalaev is 32." in items
    assert "Magomed Ankalaev's red flags: missed weight in 2024." in items
    ends = _items(_sec(rep, "ends"))
    assert ends[0] == "Alex Pereira: by knockout or TKO 33%, by submission 2%, on the judges' cards 21%."
    assert ends[2] == "It goes the distance 49%; about 17.6 of its 25 minutes expected."
    camp = _items(_sec(rep, "camp"))
    assert camp[:3] == ["Alex Pereira: made weight.", "Magomed Ankalaev: not weighed in on our record yet.",
                        "The fight is at T-Mobile Arena, Las Vegas."], camp
    bet = _sec(rep, "bet")["blocks"][0]["text"]
    assert bet == ("Magomed Ankalaev to win at +120 (DraftKings): an edge of 2.5 points over the price, "
                   "grade 71 (B), 0.5 unit(s)."), bet
    table = _sec(rep, "fighters")["blocks"][0]
    assert table["head"] == ["", "Alex Pereira", "Magomed Ankalaev"]
    assert ["Style", "a counter striker", "a wrestler"] in table["rows"]
    assert ["Takedown defense", "70%", "86%"] in table["rows"]


def test_the_case_for_each_corner_reads_the_models_own_inputs():
    fs = [_brief("Merab Dvalishvili", archetype="wrestler", td_per15=6.2, slpm=4.4, sapm=2.2, sub_att_per15=0.4),
          _brief("Sean O'Malley", archetype="striker_poor_tdd", tdd=0.55, slpm=6.1, sapm=3.7, sub_att_per15=1.2,
                 age=36)]
    row = _pick(fight="Merab Dvalishvili vs Sean O'Malley", fighters=fs, pick="Merab Dvalishvili", p_market=0.62,
                p_model=0.7, p_final=0.66, selection="Merab Dvalishvili",
                style_notes=["Style: wrestler vs poor TDD — control decision or GnP TKO",
                             "Sean O'Malley on short notice — no camp, no path analysis"])
    ev = U.reasons(row)
    m = ev["Merab Dvalishvili"]
    assert m[0] == ("The style matchup: a wrestler against a striker with weak takedown defense, wrestler vs poor "
                    "TDD — control decision or GnP TKO"), m
    assert "Merab Dvalishvili averages 6.2 takedowns per 15 minutes; Sean O'Malley stops 55% of them" in m
    assert "Sean O'Malley is 36, past the sport's peak years (27 to 32); Merab Dvalishvili is 30" in m
    assert "Sean O'Malley took the fight on short notice: no full camp" in m
    # Net strikes 2.2 a minute against 2.4: no striking edge to either. His submission tries do count.
    assert not any("significant strikes" in r for r in m + ev["Sean O'Malley"])
    assert ev["Sean O'Malley"] == []  # 1.2 tries, but against a 75% defense
    fs[0]["tdd"] = 0.6
    assert U.reasons(row)["Sean O'Malley"] == ["Sean O'Malley tries 1.2 submissions per 15 minutes, against "
                                               "Merab Dvalishvili's 60% takedown defense"]


def test_an_underdog_the_numbers_favor_is_the_case_for_an_upset():
    fs = [_brief("A Fighter", slpm=6.0, sapm=2.5, td_per15=2.5), _brief("B Fighter", slpm=3.5, sapm=4.5, tdd=0.5)]
    row = _pick(fight="A Fighter vs B Fighter", fighters=fs, pick="A Fighter", p_market=0.38, p_model=0.5,
                p_final=0.44, selection="A Fighter", style_notes=[])
    call = _sec(U.build(row), "verdict")
    assert call["blocks"][0]["team"] == "B Fighter", "the call follows the price"
    said = [b.get("text") for b in call["blocks"] if b["type"] == "p"]
    assert said == ["More of this report points to A Fighter than to B Fighter (2 reasons to 0): the case for an "
                    "upset, against the price."], said


def test_a_fight_the_card_could_not_read_still_says_why():
    no_price = {"fight": "Kai Asakura vs Tim Elliott", "division": "flyweight", "kind": "pass",
                "reason_code": "no_price", "fighters": [_brief("Kai Asakura"), _brief("Tim Elliott")],
                "why": "no two-sided price posted yet — books open MMA lines closer to the card"}
    rep = U.build(no_price)
    assert [s["key"] for s in rep["sections"]] == ["fighters", "bet"], "no price, no call"
    assert _sec(rep, "bet")["blocks"][0]["text"] == ("No bet on this fight: no two-sided price posted yet — books "
                                                     "open MMA lines closer to the card.")
    bare = {"fight": "New Guy vs Other Guy", "kind": "pass", "reason_code": "no_dossier",
            "fighters": [{"name": "New Guy", "has_dossier": False, "covered": 0},
                         {"name": "Other Guy", "has_dossier": False, "covered": 0}],
            "why": "no dossier for New Guy and Other Guy — no bet"}
    assert [s["key"] for s in U.build(bare)["sections"]] == ["bet"]
    assert U.build({"fight": "no corners"}) is None and U.build(None) is None


def test_the_build_attaches_one_for_every_fight_and_the_gate_keeps_them_paid():
    out = {"picks": [_pick()], "pass_list": [{"fight": "Kai Asakura vs Tim Elliott", "kind": "pass",
                                              "fighters": [_brief("Kai Asakura"), _brief("Tim Elliott")],
                                              "why": "no price"}]}
    assert U.attach(out) == "Fight reports: 2 fight(s)"
    assert [r["fight"] for r in out["fight_reports"]] == ["Alex Pereira vs Magomed Ankalaev", "Kai Asakura vs Tim Elliott"]
    broken = {"picks": "not rows"}
    assert U.attach(broken) == "Fight reports: 0 fight(s)" and broken["fight_reports"] == []
    from engine import gate
    assert "fight_reports" in gate.PAID_KEYS
    public = gate.redact(dict(out, status="card", event_date="UFC 323"), "ufc.json")
    assert public["fight_reports"] == [] and public["locked"]["fight_reports"] == 2, \
        "a reader without a plan gets none, and is told how many are locked"
    build = (ROOT / "ufc_build.py").read_text(encoding="utf-8")
    assert build.index('_clock.lap("the card", "line moves", _ct)') < build.index("print(_ufr.attach(out))") \
        < build.index('_clock.mark("the card")'), "after every row is complete"


def test_the_tab_folds_each_report_into_its_fights_card():
    assert MORE_JS.count("${fightReportHTML(p)}") == 1 and MORE_JS.count("${fightReportHTML(m)}") == 1
    assert '<details class="ufc-report" data-ufc-report="${escapeAttr(m.fight)}"><summary>The fight report' in MORE_JS
    # With the finished bout's result for its call (test_a_finished_fight_says_how_our_bet_went).
    assert "R.html(r, { fight: true, results })" in MORE_JS and 'document.addEventListener("toggle", (e) => {' in MORE_JS
    assert ".ufc-report { margin-top: 12px; }" in MORE_CSS


def _node(script):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    head = ("const vm = require('vm'); const fs = require('fs');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc,"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " teamName: (t) => t, playerAvatar: (p) => '<i class=av></i>' };"
            "vm.createContext(ctx);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(REPORT_JS))}, 'utf8'), ctx);"
            "const R = ctx.window.QBReport;")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def test_the_renderer_draws_a_fight_without_page_wide_ids_or_a_share_button():
    rep = U.build(_pick())
    got = _node(f"const rep = {json.dumps(rep, ensure_ascii=False)};"
                "process.stdout.write(JSON.stringify([R.html(rep, { fight: true }), R.html(rep), R.toText(rep)]));")
    if got is None:
        return
    fight, game, text = got
    assert "The fight report" in fight and 'class="gr-winner"' in fight and "Alex Pereira" in fight
    assert ' id="' not in fight, "several reports share one page"
    assert "data-gr-share" not in fight and "data-gr-copy" in fight
    assert 'id="gp-sec-report"' in game and "data-gr-share" in game, "a game's report as before"
    assert "A lean: Alex Pereira — 56% to win" in text, text[:300]


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
