"""The account screens, the plans and an empty night read like an app (2026-10-25).

Ethan: "we want it to look more like an app. We want it to feel like an
app. It needs to work like an app ... Even like the sign-in page and the
paywall page and all that stuff, like it needs to be curated to work for an
app."

  * The league row (NFL, CFB, MLB ...) leaves the screens that are about no
    league: signing up, the plans, checkout, resetting a password, your own
    bets and your messages. A store app shows no sport tabs above them.
  * The plans screen keeps its one button pinned above the tab bar on a
    phone until the plans themselves are on screen.
  * The sign-up screen's two paragraphs became two promise rows.
  * An empty Edge page says "nothing qualified" once, not twice.

Run directly: `python3 tests/test_the_app_screens_are_app_screens.py`
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
ACCOUNT_CSS = (ROOT / "web" / "css" / "account.css").read_text(encoding="utf-8")
STYLES = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(src, name):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def test_the_account_screens_carry_no_league_row():
    m = re.search(r"const OFF_LEAGUE_VIEWS = \[(.*?)\];", APP, re.S)
    views = set(re.findall(r'"([a-z]+)"', m.group(1)))
    for v in ("account", "signup", "paywall", "checkout", "reset", "mybets", "messages"):
        assert v in views, v
    for board in ("recommended", "likely", "edge", "props", "live", "record", "game", "pbp"):
        assert board not in views, f"{board} is about a league and keeps its row"
    assert "body.off-league .sportbar { display: none; }" in STYLES


def test_the_plans_screen_keeps_its_button_in_reach_on_a_phone():
    assert "pwDock(host);" in _fn(ACCOUNT, "renderPaywall")
    dock = _fn(ACCOUNT, "pwDock")
    assert 'host.querySelector(".pw-cta-go")' in dock, "the hero's own button, nothing new"
    assert 'data-act="pwToPlans"' in dock
    assert 'dock.classList.toggle("away", seen.some((e) => e.isIntersecting));' in dock
    assert "if (!go || !plans) return;" in dock, "no plan to offer, no dock"
    assert ".pw-dock { display: none; }" in ACCOUNT_CSS
    phone = ACCOUNT_CSS[ACCOUNT_CSS.index("@media (max-width: 720px) {\n  .pw-dock"):]
    assert "position: fixed" in phone and "bottom: calc(74px + env(safe-area-inset-bottom, 0px));" in phone
    assert ".pw-dock.away { opacity: 0; transform: translateY(10px); pointer-events: none; }" in phone


def test_the_sign_up_screen_says_its_promises_as_rows():
    # The account room's since 2026-10-25, when sign-up became the first
    # screen a stranger sees (js/account.js).
    body = _fn(ACCOUNT, "signupHTML")
    promises = body[body.index('<ul class="acct-promises">'):]
    promises = promises[:promises.index("</ul>")]
    assert promises.count("<li>") == 2, "the welcome's three free things are their own list"
    assert "one-way" in body and "scramble" in body and "sportsbook or ESPN password" in body
    assert "it takes no card and subscribes you to nothing" in body
    assert ".acct-promises li { display: grid;" in STYLES


def test_an_empty_edge_page_says_nothing_qualified_once():
    echo = _fn(APP, "quietBoardEcho")
    assert "no qualifying plays" in echo and "Nothing cleared the model’s bars tonight" in echo
    assert "echo.remove()" in echo
    assert "quietBoardEcho();" in _fn(APP, "renderRecommended")
    best = APP[APP.index("async function renderBestBets("):APP.index("function prePriceHeadline(")]
    assert "quietBoardEcho();" in best, "whichever of the two lands second makes the check"
    # The breakdown stays: only the repeated sentence goes.
    assert "${censusFunnelHTML()}`;\n    quietBoardEcho();" in APP


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
