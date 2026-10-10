"""The paywall: an honest first button, the price before the proof, one
sentence on what is free, and Ask locked before anyone types.

Audit 2026-09-30, V-20 / O24 (roadmap #41).
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 3]


def _node(expr, pre=""):
    js = (pre + "const escapeHtml = (s) => String(s);\n"
          + APP[APP.index("const FREE_VS_PLAN = "):APP.index("function freeVsPlanHTML(")]
          + _fn("freeVsPlanHTML") + _fn("pwHeroCtaHTML") + _fn("askLocked") + _fn("askLockedHTML")
          + f"\nconsole.log(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_first_button_never_ends_on_a_dead_plan():
    body = _fn("paywallHTML")
    assert "pwHeroCtaHTML(trialOK && sellable(trialPlan) ? trialDays : 0," in body
    assert "PLANS.some((p) => sellable(p.id)))" in body
    got = _node("[pwHeroCtaHTML(3, true), pwHeroCtaHTML(0, true), pwHeroCtaHTML(3, false)]")
    assert "Start 3 days free" in got[0] and "See the plans" in got[1]
    assert "pwToPlans" not in got[2] and "See the record" in got[2], "nothing on sale: the record leads"
    assert 'sellable("sixmonth") ?' in body, "the FAQ's button asks too"


def test_the_page_reads_hero_price_proof_questions_then_the_rest():
    """Hero (with the receipts strip, which stays above the price — see
    test_paywall_proof), then the price, the proof, the questions, and only
    then the feature grid and the Ask demo that used to sit before the price."""
    body = _fn("paywallHTML")
    at = [body.index(m) for m in ('<section class="pw-hero">', "${pwResultsHTML(rec)}", "Simple pricing",
                                  "${paywallProofHTML(rec)}", "Questions</h2>", "${pwAskHTML()}",
                                  "<em>Everything</em> you need")]
    assert at == sorted(at), at


def test_one_sentence_on_what_is_free_on_the_paywall_ask_and_why():
    line = _node("FREE_VS_PLAN")
    assert line.startswith("Free: the Record") and "The plan adds" in line
    assert '${freeVsPlanHTML("pw")}' in _fn("paywallHTML")
    assert '${freeVsPlanHTML("why")}' in APP
    assert 'freeVsPlanHTML("ask")' in _fn("askLockedHTML")
    assert 'No "premium tier"' not in APP, "the Why page no longer contradicts the paywall"


def test_ask_is_locked_before_typing_when_the_wall_is_up():
    pre = "let _pwStatus = %s;\n"
    assert _node("askLocked()", pre % json.dumps({"paywall": True, "entitled": False})) is True
    assert _node("askLocked()", pre % json.dumps({"paywall": True, "entitled": True})) is False
    assert _node("askLocked()", pre % json.dumps({"paywall": False})) is False
    assert _node("askLocked()", pre % "null") is False, "an unanswered status never locks"
    html = _node("askLockedHTML()", pre % json.dumps({"paywall": True, "signed_in": False}))
    assert "Sign in with a subscription to ask." in html and "See the plans" in html and "Log in" in html
    assert "${askLocked() ? askLockedHTML() : `<form class=\"ask-form\"" in _fn("renderAsk")


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
