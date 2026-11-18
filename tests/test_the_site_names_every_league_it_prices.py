"""Every page that lists the site's leagues lists all eight (USEREYES1,
18 November 2026).

Walking the About page, My Bets and the shop as a reader: About said "Six
leagues priced nightly" over six cards with no NHL and no college
basketball, and its disclaimer named every league body but the NHL's; the
shop's breadth row, the plan's "Every sport:" line and the page's search
description stopped at the leagues of September; My Bets let you file a bet
under NFL, CFB, MLB, NBA, WNBA or UFC, so a hockey or college basketball bet
went under Other. The same walk found My Bets saying "Syncing to" your
account above a footer that said the log "lives only in this browser", the
Lab's empty page saying it runs "once a week ... as part of the nightly
maintenance pass", and Line Shopping sending readers to a "Recommended"
page the menu has not had since September. What these hold:

  * the league codes the app's own strip uses (LEAGUE_LABEL) are all on the
    shop's row, in the plan's line and in the bet log's sport list;
  * About counts eight leagues, has a card for hockey and for college
    basketball, and its disclaimer names the NHL;
  * the page's search and share descriptions name college basketball;
  * My Bets says where the log lives by whether you are signed in, and its
    empty page no longer says it stays on this device;
  * the Lab says weekly once, and Line Shopping links the Edge Picks page;
  * the Status page's UFC row says what the card holds (its fights and
    picks), as the seven other leagues' rows say what their boards hold.

    python3 tests/test_the_site_names_every_league_it_prices.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "js"
APP = (JS / "app.js").read_text(encoding="utf-8")
ACCOUNT = (JS / "account.js").read_text(encoding="utf-8")
MORE = (JS / "more.js").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def _labels():
    m = re.search(r"const LEAGUE_LABEL = \{(.*?)\};", APP, re.S)
    assert m, "LEAGUE_LABEL moved"
    return dict(re.findall(r'(\w+): "([^"]+)"', m.group(1)))


def test_the_strips_eight_leagues_are_the_shops_the_plans_and_the_bet_logs():
    labels = _labels()
    assert set(labels) == {"nfl", "mlb", "nba", "wnba", "nhl", "cfb", "ufc", "cbb"}, labels
    chips = re.search(r"const PW_SPORTS = \[(.*?)\n\];", ACCOUNT, re.S).group(1)
    plan = re.search(r'"Every sport: ([^"]+)"', APP).group(1)
    log = re.search(r'<select id="mb-sport">\$\{\s*\[([^\]]+)\]', ACCOUNT).group(1)
    for code in labels.values():
        assert f'["{code}",' in chips, f"the shop's row leaves out {code}"
        assert re.search(rf"\b{code}\b", plan), f"the plan's line leaves out {code}: {plan}"
        assert f'"{code}"' in log, f"My Bets cannot file a bet under {code}: {log}"


def test_about_counts_eight_and_has_a_card_for_each():
    assert "Eight leagues priced nightly" in MORE and "Six leagues" not in MORE
    assert "not one formula wearing eight logos" in MORE
    for card in ('card("NHL — Scalpy NHL"', 'card("College basketball"', 'card("College football"',
                 'card("NBA + WNBA — Scalpy hoops"', 'card("UFC — Scalpy MMA"'):
        assert card in MORE, card
    assert "not with the NFL, MLB, NBA, WNBA, NHL, UFC, the NCAA" in MORE


def test_the_search_and_share_descriptions_name_college_basketball():
    desc = re.search(r'<meta name="description" content="([^"]+)"', INDEX).group(1)
    og = re.search(r'<meta property="og:description" content="([^"]+)"', INDEX).group(1)
    assert "college basketball" in desc and "NHL" in desc, desc
    assert "NCAAB" in og and "NHL" in og, og


def test_my_bets_says_where_the_log_lives_by_whether_you_are_signed_in():
    i = ACCOUNT.index("This is a manual log for the bets YOU place")
    foot = ACCOUNT[i:ACCOUNT.index("</p>`;", i)]
    assert "_acctUser.signed_in ?" in foot, "the footer reads the sign-in state"
    assert '"It syncs to your account; Export keeps a copy of your own."' in foot
    assert "Data lives only in this browser" in foot, "a signed-out reader is still warned"
    assert "It stays on this\n        device" not in ACCOUNT and "stays on this device" not in ACCOUNT


def test_the_lab_says_weekly_once_and_line_shopping_links_edge_picks():
    assert "as part of the nightly maintenance pass" not in MORE
    assert "once a week, on its own, and appears here after its first run." in MORE
    assert "<b>Recommended</b>" not in MORE
    assert '<a href="#edge" data-view="edge">Edge Picks</a> page' in MORE


def test_the_status_pages_ufc_row_says_what_the_card_holds():
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())
    import launch
    path = os.path.join(tempfile.mkdtemp(), "ufc.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"counts": {"fights": 21, "picks": 3, "passes": 18}, "picks": []}, fh)
    assert launch._card_counts(path) == {"card": {"fights": 21, "picks": 3}}
    assert launch._card_counts(path + ".missing") == {}
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert 'elif name == "ufc":\n        _BOARD_RUNS[name].update(_card_counts(UFC_OUT))' in src
    assert 'sub("Fight card", `${n(card.fights, "fight", "fights")} · ${n(card.picks, "pick", "picks")}`' in MORE


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
