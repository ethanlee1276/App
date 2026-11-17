"""A fighter has a page of their own (2026-11-17).

Ethan, asked whether UFC should have a full fighter page like every other
league's player page: "yes full fighter page". What these hold:

  * the server builds it from what is kept (engine/ufc/fighterpage): the
    dossier's record, age, division and team, ESPN's published facts from the
    copy the dossier's draft cached (never fetched), the measured career rates
    each in words (shares as percents; control time, which ESPN does not
    publish, left out), every tracked fight newest first with how it ended and
    both fighters' numbers, the record by method, by rounds and by the round it
    ended, and the next bout on the card (a fact, from the full board);
  * /api/players/page answers for sport=ufc, free like every page;
  * the page is the player page's frame with a fighter's menus (Overview,
    Fights, Stats, Bio, News), a fighter's hero line (division and record;
    nickname, height, reach and age), and our read of a fighter (archetype,
    red flags) nowhere on it;
  * a searched fighter opens it, and in a browser it draws every menu;
  * every fighter with a dossier is read, not only the coming card's (seen
    live 2026-11-17: Islam Makhachev's page had no face, facts or fights):
    the night's read takes them off the card, the deepest records first,
    within a budget, keeps ESPN's facts beside the read, and reads a fighter
    again after a month; the page and the search take the face and facts
    from it; `python3 -m engine.ufc.history --all` reads them all at once.

Run directly: `python3 tests/test_a_fighter_has_a_page_of_their_own.py`
(the browser check with QB_BROWSER_TESTS=1 and /usr/bin/python3).
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import db as DB  # noqa: E402
from engine.ufc import fighterpage as FP  # noqa: E402
from engine.ufc import history as H  # noqa: E402

PAGE = (ROOT / "web" / "js" / "playerpage.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "playerpage.css").read_text(encoding="utf-8")

NAME = "Ilia Topuria"
DOSSIER = {NAME: {"name": NAME, "age": 29, "division": "featherweight", "record": "16-0-0", "slpm": 4.4,
                  "sapm": 3.1, "str_def": 0.62, "kd_per100": 2.1, "td_per15": 1.9, "td_acc": 0.6, "tdd": 0.92,
                  "ctrl_per15": 2.0, "sub_att_per15": 0.8, "archetype": "pressure_striker",
                  "red_flags": ["a flag only the model reads"], "ufc_fights": 8, "career_fights": 16,
                  "gym": "Climent Club", "first_fight": "2020-10-10", "last_fight": "2026-06-28"}}
BIO = {"nickname": "El Matador", "displayHeight": "5' 7\"", "displayWeight": "145 lbs", "reach": 69,
       "stance": {"text": "Orthodox"}, "citizenship": "Spain", "dateOfBirth": "1997-01-21T08:00Z",
       "birthPlace": {"city": "Halle", "country": "Germany"}}


def _fight(comp, date, opp, result, method, rnd, clock, secs, rounds, ssl, ssa, tdl, tda, kd):
    return (NAME, "4096", comp, "e" + comp, date, opp, "o" + comp, result, method, rnd, clock, secs, rounds,
            "featherweight", ssl, ssa, tdl, tda, kd, 0, 30, 70, 0, 3, 0, 0)


FIGHTS = [_fight("c1", "2026-06-28", "Max Holloway", "W", "KO/TKO", 3, "2:44", 744, 5, 52, 98, 1, 2, 2),
          _fight("c2", "2025-10-26", "Alexander Volkanovski", "W", "KO/TKO", 2, "3:32", 512, 5, 31, 60, 0, 0, 1),
          _fight("c3", "2025-02-17", "Josh Emmett", "W", "DEC", 3, "5:00", 900, 3, 98, 190, 2, 5, 0)]


def _world(with_next=True):
    d = Path(tempfile.mkdtemp())
    conn = DB.connect(d / "h.db")
    conn.executemany(f"INSERT INTO ufc_fights ({', '.join(H.COLS)}) VALUES ({', '.join('?' * len(H.COLS))})", FIGHTS)
    conn.commit()
    conn.close()
    (d / "dossiers.json").write_text(json.dumps(DOSSIER))
    cache = d / "cache"
    cache.mkdir()
    (cache / "espn_mma_ath_4096.json").write_text(json.dumps(BIO))
    board = {"status": "card", "event_date": "2026-12-12",
             "picks": [{"fight": "Max Holloway vs Ilia Topuria", "division": "featherweight"}] if with_next else [],
             "pass_list": []}
    (d / "ufc.json").write_text(json.dumps(board))
    return d


def _page(d, name=NAME):
    return FP.page(name, db_path=d / "h.db", dossier_path=str(d / "dossiers.json"), cache_dir=d / "cache",
                   board_path=d / "ufc.json")


def test_the_server_builds_it_from_what_is_kept():
    d = _world()
    p = _page(d, "ilia topuria")
    assert p["player"] == NAME and p["sport"] == "ufc" and p["face"].endswith("/full/4096.png")
    b = p["bio"]
    assert (b["record"], b["division"], b["age"], b["team"]) == ("16-0-0", "Featherweight", 29, "Climent Club")
    assert FP.division_words("women's_strawweight") == "Women's Strawweight"
    assert FP.division_words("light_heavyweight") == "Light Heavyweight"
    assert (b["nickname"], b["height"], b["weight"], b["reach"], b["stance"], b["country"], b["born"]) == \
        ("El Matador", "5' 7\"", "145 lbs", "69\"", "Orthodox", "Spain", "1997-01-21"), b
    assert b["birthplace"] == "Halle, Germany"
    assert "archetype" not in json.dumps(p) and "red_flags" not in json.dumps(p) and "a flag only" not in json.dumps(p), \
        "our read of a fighter stays with the picks"
    rates = {r["key"]: r for r in p["rates"]}
    assert "ctrl_per15" not in rates, "a stand-in, not a measure"
    assert rates["str_def"]["value"] == 62.0 and rates["str_def"]["pct"] and rates["slpm"]["value"] == 4.4
    assert [r["key"] for r in p["rates"] if r["lead"]] == ["slpm", "str_def", "td_per15", "tdd"]
    assert [f["opp"] for f in p["fights"]] == ["Max Holloway", "Alexander Volkanovski", "Josh Emmett"], "newest first"
    assert p["tracked"] == 3 and p["line"]["w"] == 3 and p["line"]["ko_w"] == 2
    assert {m["key"]: m["w"] for m in p["by_method"]} == {"KO/TKO": 2, "SUB": 0, "DEC": 1}
    assert p["next"] == {"opponent": "Max Holloway", "date": "2026-12-12", "division": "Featherweight"}


def test_a_name_nobody_keeps_is_no_page_and_no_card_is_no_next_fight():
    d = _world(with_next=False)
    assert _page(d, "Nobody At All") == {}
    assert _page(d)["next"] is None
    (d / "cache" / "espn_mma_ath_4096.json").unlink()
    assert "height" not in _page(d)["bio"], "no cached page, no facts invented"


def test_a_fighter_with_no_tracked_fight_takes_the_id_from_the_kept_search():
    """Seen live 2026-11-17: Islam Makhachev's page had the record and rates and no face, no height and no
    reach, because the ESPN id was read only off a tracked fight's photo. The dossier's draft keeps ESPN's
    name search; the id comes from it, never from a fetch."""
    from engine.sources import espnmma
    d = _world(with_next=False)
    name = "Islam Makhachev"
    dossiers = json.loads((d / "dossiers.json").read_text())
    dossiers[name] = {"name": name, "age": 34, "division": "welterweight", "record": "28-1-0", "slpm": 2.6}
    (d / "dossiers.json").write_text(json.dumps(dossiers))
    hit = {"results": [{"type": "player", "contents": [
        {"displayName": "Islam Makhachev", "description": "MMA",
         "link": {"web": "https://www.espn.com/mma/fighter/_/id/3332412/islam-makhachev"}},
        {"displayName": "Islam Makhachev", "description": "Soccer", "link": {"web": "https://x.test/_/id/99"}}]}]}
    (d / "cache" / espnmma._search_name(name)).write_text(json.dumps(hit))
    (d / "cache" / "espn_mma_ath_3332412.json").write_text(json.dumps({"displayHeight": "5' 10\"", "reach": 70.5,
                                                                         "stance": {"text": "Southpaw"}}))
    p = _page(d, name)
    assert p["tracked"] == 0 and p["face"].endswith("/full/3332412.png"), p["face"]
    assert (p["bio"]["height"], p["bio"]["reach"], p["bio"]["stance"]) == ("5' 10\"", '70.5"', "Southpaw"), p["bio"]
    assert espnmma.cached_athlete_id("Someone Unsearched", d / "cache") is None, "nothing kept, nothing fetched"


def test_a_dossier_keeps_the_id_and_the_facts_so_no_cache_is_needed():
    """Kept at the draft since 2026-11-17 (espnmma.fetch_dossier): the cache the page used to read is pruned after
    a month, and a fighter not on a recent card lost the face and the facts with it."""
    from engine.sources import espnmma
    d = _world(with_next=False)
    for f in (d / "cache").iterdir():
        f.unlink()
    name = "Merab Dvalishvili"
    dossiers = json.loads((d / "dossiers.json").read_text())
    dossiers[name] = {"name": name, "age": 35, "division": "bantamweight", "record": "21-4-0", "espn_id": "3155424",
                      "facts": espnmma.bio_facts({"nickname": "The Machine", "displayHeight": "5' 6\"",
                                                  "reach": 68, "stance": {"text": "Orthodox"},
                                                  "citizenship": "Georgia"})}
    (d / "dossiers.json").write_text(json.dumps(dossiers))
    p = _page(d, name)
    assert p["face"].endswith("/full/3155424.png"), p["face"]
    assert (p["bio"]["nickname"], p["bio"]["height"], p["bio"]["reach"], p["bio"]["stance"], p["bio"]["country"]) == (
        "The Machine", "5' 6\"", '68"', "Orthodox", "Georgia"), p["bio"]
    src = (ROOT / "engine" / "sources" / "espnmma.py").read_text(encoding="utf-8")
    draft = src[src.index("def fetch_dossier("):]
    assert 'out["espn_id"] = str(aid)' in draft and 'out["facts"] = facts' in draft


def test_every_dossier_fighter_is_read_and_the_facts_are_kept():
    """The night's read: every dossier fighter off the card (by the file's own key, the spelling the card's read
    uses), the deepest records first, within a count and a clock; ESPN's facts kept beside the read; a fighter
    ESPN cannot find read as nothing found; a fighter read again a month on, keeping the facts a failed read
    did not bring."""
    import datetime as dt
    d = Path(tempfile.mkdtemp())
    book = {"_readme": "not a fighter", "_unfound": {"Ghost": {"attempts": 1}},
            "Islam Makhachev": {"name": "Islam Makhachev", "ufc_fights": 16},
            "Jon Jones": {"name": "Jon Jones", "ufc_fights": 22},
            "Ghost": {"name": "Ghost", "ufc_fights": 0},
            "Kaue Fernandes": {"name": "Kauê Fernandes", "ufc_fights": 1}}
    (d / "dossiers.json").write_text(json.dumps(book))
    names = H.dossier_names(d / "dossiers.json")
    assert names == ["Jon Jones", "Islam Makhachev", "Kaue Fernandes", "Ghost"], names
    assert H.dossier_names(d / "missing.json") == []
    conn = DB.connect(d / "h.db")
    day = dt.date(2026, 11, 18)
    ids = {"Jon Jones": "2335639", "Islam Makhachev": "3332412", "Kaue Fernandes": "4567"}
    facts = {"3332412": {"height": "5' 10\"", "reach": '70.5"'}, "2335639": {"height": "6' 4\""}}
    asked = []

    def fetch(n):
        asked.append(n)
        return (ids[n], []) if n in ids else None
    got = H.nightly(conn, names, day, limit=3, fetch_fn=fetch, facts_fn=lambda aid: dict(facts.get(aid, {})))
    assert got == {"read": 3, "fights": 0, "missing": 0, "left": 1}, got
    assert asked == ["Jon Jones", "Islam Makhachev", "Kaue Fernandes"], asked
    assert H.kept(conn, "Islam Makhachev") == {"aid": "3332412", "facts": {"height": "5' 10\"", "reach": '70.5"'}}
    assert H.kept(conn, "Kauê Fernandes") == {"aid": "4567", "facts": {}}, "a spelling the read was not keyed by"
    assert H.kept(conn, "Nobody") == {"aid": "", "facts": {}}
    got = H.nightly(conn, names, day, fetch_fn=fetch)
    assert got == {"read": 1, "fights": 0, "missing": 1, "left": 0}, got
    assert H.kept(conn, "Ghost") == {"aid": "", "facts": {}}
    assert H.nightly(conn, names, day + dt.timedelta(days=H.OFF_CARD_DAYS - 1), fetch_fn=fetch)["read"] == 0
    later = day + dt.timedelta(days=H.OFF_CARD_DAYS)
    got = H.nightly(conn, ["Islam Makhachev"], later, fetch_fn=fetch, facts_fn=lambda aid: {})
    assert got["read"] == 1 and H.kept(conn, "Islam Makhachev")["facts"]["reach"] == '70.5"', "kept, not wiped"
    assert H.nightly(conn, ["Jon Jones"], later, budget_s=0, fetch_fn=fetch) == \
        {"read": 0, "fights": 0, "missing": 0, "left": 1}, "no fighter started after the night's clock"
    # A caller that brings its own fights never reaches ESPN for the facts.
    was = H._athlete_facts
    H._athlete_facts = lambda aid: (_ for _ in ()).throw(AssertionError("fetched"))
    try:
        H.fill(conn, ["Jon Jones"], later, fetch_fn=fetch)
    finally:
        H._athlete_facts = was
    assert (H.NIGHTLY, H.NIGHT_S, H.OFF_CARD_DAYS, H.STALE_DAYS) == (40, 900.0, 30, 3)


def test_a_fighter_with_no_fight_on_file_has_the_face_and_facts_the_read_kept():
    d = _world(with_next=False)
    for f in (d / "cache").iterdir():
        f.unlink()
    name = "Islam Makhachev"
    dossiers = json.loads((d / "dossiers.json").read_text())
    dossiers[name] = {"name": name, "age": 34, "division": "welterweight", "record": "28-1-0"}
    (d / "dossiers.json").write_text(json.dumps(dossiers))
    assert _page(d, name)["face"] == "", "nothing read, nothing kept: no face"
    conn = DB.connect(d / "h.db")
    H.fill(conn, [name], fetch_fn=lambda n: ("3332412", []),
           facts_fn=lambda aid: {"height": "5' 10\"", "stance": "Southpaw"})
    conn.close()
    p = _page(d, name)
    assert p["tracked"] == 0 and p["face"].endswith("/full/3332412.png"), p["face"]
    assert (p["bio"]["height"], p["bio"]["stance"], p["bio"]["record"]) == ("5' 10\"", "Southpaw", "28-1-0"), p["bio"]


def test_a_searched_fighter_has_a_face():
    from engine import playersearch as PS
    from engine.ufc import fighters as F
    d = _world(with_next=False)
    dossiers = json.loads((d / "dossiers.json").read_text())
    dossiers["Merab Dvalishvili"] = {"name": "Merab Dvalishvili", "record": "21-4-0", "espn_id": "3155424"}
    dossiers["Islam Makhachev"] = {"name": "Islam Makhachev", "record": "28-1-0"}
    dossiers["Islam Dulatov"] = {"name": "Islam Dulatov", "record": "11-1-0"}
    (d / "dossiers.json").write_text(json.dumps(dossiers))
    conn = DB.connect(d / "h.db")
    H.fill(conn, ["Islam Makhachev"], fetch_fn=lambda n: ("3332412", []))
    conn.close()
    hits = {h["player"]: h["headshot"] for h in F.search("a", limit=20, path=str(d / "dossiers.json"))}
    assert hits["Merab Dvalishvili"].endswith("/full/3155424.png") and hits["Islam Makhachev"] == "", hits
    got = {h["player"]: h["headshot"] for h in PS.search("islam", ufc_path=str(d / "dossiers.json"),
                                                          db_path=d / "h.db") if h["sport"] == "ufc"}
    assert got["Islam Makhachev"].endswith("/full/3332412.png") and got["Islam Dulatov"] == "", got


def test_a_database_read_before_the_facts_gets_the_column():
    d = Path(tempfile.mkdtemp())
    old = sqlite3.connect(d / "h.db")
    old.execute("CREATE TABLE ufc_fighters_read (fighter TEXT PRIMARY KEY, fighter_id TEXT, fetched TEXT, "
                "fights INTEGER)")
    old.execute("INSERT INTO ufc_fighters_read VALUES ('Jon Jones', '2335639', '2026-11-01', 22)")
    old.commit()
    old.close()
    conn = DB.connect(d / "h.db")
    assert "facts" in [r[1] for r in conn.execute("PRAGMA table_info(ufc_fighters_read)")]
    assert H.kept(conn, "Jon Jones") == {"aid": "2335639", "facts": {}}


def test_the_night_reads_them_and_a_command_reads_them_all():
    src = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    i = src.index("# EVERY FIGHTER'S PAGE")
    block = src[i:i + 1600]
    assert '_uh.dossier_names(ROOT / "data" / "ufc_dossiers.json")' in block, block
    assert "_uh.nightly(_uc, _names, today=today)" in block and "ufc fighter pages failed" in block
    assert src.index("mlb full lines failed") < i < src.index("n = ledger.settle_from_history(lconn, hconn)")
    assert H.main([]) == 2, "no --all, nothing read"
    runnext = (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")
    assert "python3 -m engine.ufc.history --all" in runnext


def test_the_page_endpoint_answers_for_a_fighter():
    assert 'if sport not in playerpage.SPORTS and sport != "ufc":' in SERVER
    assert "from engine.ufc import fighterpage\n                made = fighterpage.page(player)" in SERVER


def test_the_page_is_the_player_pages_frame_with_a_fighters_menus():
    assert 'const PLR_SPORTS = ["nfl", "cfb", "nba", "wnba", "cbb", "nhl", "mlb", "ufc"];' in PAGE
    assert ('const PLR_TABS_UFC = [["overview", "Overview"], ["fights", "Fights"], ["stats", "Stats"], ["bio", "Bio"], '
            '["news", "News"]];') in PAGE
    assert 'if (page._plr.sport === "ufc") return plrFillUfc(page, d);' in PAGE
    hero = PAGE[PAGE.index("function plrHeroHTML("):PAGE.index("function plrTabsHTML(")]
    assert "const line = (ufc ? [(bio && bio.division) || pos, bio && bio.record]" in hero
    assert 'bio.nickname ? `“${bio.nickname}”` : "", bio.height, bio.reach ? `${bio.reach} reach` : ""' in hero
    fill = PAGE[PAGE.index("function plrFillUfc("):]
    fill = fill[:fill.index("\n}\n")]
    for sel in ('set(".plr-season", plrUfcRatesHTML(d));', 'set(".plr-next", plrUfcNextHTML(d));',
                'set(".plr-recent", plrUfcFightsHTML(d, 5));', 'set("[data-plr-panel=\\"fights\\"]", plrUfcFightsHTML(d));',
                'set("[data-plr-panel=\\"stats\\"]", plrUfcStatsHTML(d));', 'set("[data-plr-panel=\\"bio\\"]", plrUfcBioHTML(d));'):
        assert sel in fill, sel
    assert "archetype" not in PAGE and "red_flags" not in PAGE, "no read of ours on a free page"
    i = APP.index('if (m.sport === "ufc") {')
    assert 'renderPlayerPage(host, m.player, "ufc");' in APP[i:i + 160], "a searched fighter opens the page"
    assert "function ufcProfileHTML(" not in APP, "the card it replaces is gone"
    for sel in (".plr-res {", ".plr-w {", ".plr-l {", ".plr-ufc-next {"):
        assert sel in CSS, sel


def test_in_a_browser_the_fighters_page_draws_every_menu():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    d = _world()
    page_json = json.dumps(_page(d))
    hit = json.dumps({"players": [{"player": NAME, "sport": "ufc", "team": "", "position": "featherweight",
                                   "games": 3, "fighter": {"record": "16-0-0", "division": "featherweight"}}]})
    srv, port = rendercheck._serve()
    got = {}
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                          service_workers="block")
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.add_init_script("try { localStorage.setItem('qb-seen-intro', '1'); localStorage.setItem('qb_intro_v1', '1');"
                                     " localStorage.setItem('qb.tour', 'done'); } catch (e) {}")
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
                page.route("**/api/players/page*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                       body=page_json))
                page.route("**/api/players/search*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                         body=hit))
                page.goto(f"http://127.0.0.1:{port}/index.html#player/ufc/ilia-topuria", wait_until="load")
                page.wait_for_selector(".plr .plr-fight, .plr [data-plr-panel=\"fights\"] table", state="attached",
                                       timeout=20000)
                page.wait_for_timeout(300)
                got["tabs"] = page.locator(".plr-tab").all_inner_texts()
                got["hero"] = page.locator(".plr-hero").inner_text()
                got["season"] = page.locator(".plr-season").inner_text()
                got["next"] = page.locator(".plr-next").inner_text()
                got["recent_rows"] = page.locator(".plr-recent tbody tr").count()
                got["fight_rows"] = page.locator("[data-plr-panel=\"fights\"] tbody tr").count()
                got["first_win"] = page.locator("[data-plr-panel=\"fights\"] tbody tr .plr-w").count()
                got["stats"] = page.locator("[data-plr-panel=\"stats\"]").inner_html()
                got["bio"] = page.locator("[data-plr-panel=\"bio\"]").inner_html()
                got["errs"] = list(errs)
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert [t.strip() for t in got["tabs"]] == ["Overview", "Fights", "Stats", "Bio", "News"], got["tabs"]
    hero = got["hero"]
    assert "Topuria" in hero and "featherweight · 16-0-0" in hero.lower() and "El Matador" in hero and "69\" reach" in hero, hero
    season = got["season"].upper()
    assert "RECORD" in season and "16-0-0" in season and "SLPM" in season and "62%" in season, got["season"]
    assert "Max Holloway" in got["next"] and "Dec 12" in got["next"] and "Featherweight" in got["next"], got["next"]
    assert got["recent_rows"] == 3 and got["fight_rows"] == 3 and got["first_win"] == 3
    assert "Striking" in got["stats"] and "Grappling" in got["stats"] and "How the fights ended" in got["stats"]
    assert "Orthodox" in got["bio"] and "Climent Club" in got["bio"] and "5' 7" in got["bio"]
    assert not got["errs"], got["errs"]


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
