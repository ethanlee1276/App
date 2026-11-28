"""The Record's finished picks and tickets wear their players' faces (step AIT, 28 November 2026).

Ethan, with a screenshot of a finished game on the Record (Cardinals at Chiefs, "The three-leg parlays", each
ticket wearing three drawn helmets with initials and no face on any leg): "Also fix how there is no headshots on
the game report record page here". The Record and Report Picks read a finished game's picks and tickets back off
the journal, and the journal keeps each leg's player, club, market and line, never its photo, so the page had
none to draw. What these hold:

  * the record's answer for a finished game (engine/reportoutcome.for_games, /api/report_tickets) gives every
    pick and every leg the photo its own report carried (the archived report and the tickets it kept at the
    start), its club's before its name's, else the sport's stored photo; a club's bet wears no face, a row that
    has one keeps it, and a name two photos claim with no club to settle it is left to the stored photos;
  * the Record's newest tickets (engine/ledger._game_parlay_record), the SGPX ones too, get their stored photos,
    and each leg says its club;
  * a failure says so and costs nothing else; a quiet record prints nothing;
  * each settled leg's box wears the face beside its bet (js/settled.js settledFaceHTML), a club's bet its club's
    mark, as the ticket's head does;
  * in the browser, at a phone's width, the face sits beside the bet and nothing runs off (QB_BROWSER_TESTS=1).

    python3 tests/test_the_record_wears_its_players_faces.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import boardfaces as BF  # noqa: E402
from engine import ledger  # noqa: E402
from engine import parlayledger as PL  # noqa: E402
from engine import reportarchive as RA  # noqa: E402
from engine import reportoutcome as O  # noqa: E402

SETTLED = (ROOT / "web" / "js" / "settled.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "settled.css").read_text(encoding="utf-8")
LEDGER = (ROOT / "engine" / "ledger.py").read_text(encoding="utf-8")

# Fixture photos (made-up addresses, not real files).
MAHOMES, RICE, MURRAY, OTHER = ("https://img.example/mahomes.png", "https://img.example/rice.png",
                                "https://img.example/murray.png", "https://img.example/someone-else.png")
#: A three-leg ticket on the fixture game, as the journal holds it (player, club, market, side, line, status, actual).
LEGS = [("Patrick Mahomes", "KC", "pass_yds", "OVER", 249.5, "won", 281),
        ("Rashee Rice", "KC", "receptions", "OVER", 5.5, "won", 7),
        ("Trey McBride", "ARI", "receptions", "OVER", 5.5, "won", 6)]


def _journal() -> str:
    path = os.path.join(tempfile.mkdtemp(), "ledger.db")
    conn = ledger.connect(path)
    PL.ensure_schema(conn)
    for player, market, side, line, status, actual, team in (
            ("Kyler Murray", "pass_yds", "UNDER", 229.5, "won", 160, "ARI"),
            ("KC", "spread", "OVER", 3.5, "won", 27, None)):
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, odds, status, actual, category, team)"
                     " VALUES ('nfl', '2026-W12', ?, ?, ?, ?, -110, ?, ?, 'report', ?)",
                     (player, market, side, line, status, actual, team))
    key = PL.legs_key([{"player": p, "market": m, "side": s, "line": ln} for p, _t, m, s, ln, _st, _a in LEGS])
    cur = conn.execute("INSERT INTO parlays (sport, date, legs_key, parlay_type, n_legs, grade, source, assumed_dec,"
                       " status, pnl_units, at_start) VALUES ('nfl', '2026-W12', ?, 'same_game', 3, 'ARI@KC',"
                       " 'game_three', 3.14, 'won', 2.14, 1)", (key,))
    for n, (player, team, market, side, line, status, actual) in enumerate(LEGS, 1):
        conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, team, market, side, line, status, actual)"
                     " VALUES (?,?,?,?,?,?,?,?,?)", (cur.lastrowid, n, player, team, market, side, line, status, actual))
    conn.commit()
    conn.close()
    return path


def _archive() -> Path:
    """The finished game's archived report: its picks with the board's photos, and the set it kept at the start,
    whose legs carry theirs (Mahomes'), one leg with none (Rice) and one with none anywhere (McBride)."""
    where = Path(tempfile.mkdtemp())
    kept = {"away": "ARI", "home": "KC", "kept": "kept before the start",
            "threes": [{"legs": [{"player": "Patrick Mahomes", "team": "KC", "market": "pass_yds", "side": "OVER",
                                  "line": 249.5, "headshot": MAHOMES},
                                 {"player": "Rashee Rice", "team": "KC", "market": "receptions", "side": "OVER",
                                  "line": 5.5},
                                 {"player": "Trey McBride", "team": "ARI", "market": "receptions", "side": "OVER",
                                  "line": 5.5}]}]}
    report = {"away": "ARI", "home": "KC", "sections": [{"key": "card", "blocks": [{"type": "picks", "items": [
        {"rank": 1, "player": "Kyler Murray", "team": "ARI", "headshot": MURRAY,
         "bet": {"player": "Kyler Murray", "market": "pass_yds", "side": "UNDER", "line": 229.5}}]}]}]}
    doc = {"sport": "nfl", "date": "2026-11-22", "label": "2026-W12", "away": "ARI", "home": "KC", "game": "ARI@KC",
           "final": {"away": 7, "home": 34}, "report": report, "parlays": kept, "results": {}}
    RA.write(RA.path_for(where, "nfl", "2026-11-22", "ARI", "KC"), doc)
    return where


def test_the_record_answer_gives_each_pick_and_leg_its_reports_face():
    got = O.for_games("nfl", [("2026-11-22", "ARI", "KC")], path=_journal(), where=_archive(),
                      faces={BF._norm("Rashee Rice"): RICE})["2026-11-22|ARI|KC"]
    legs = {leg["player"]: leg for leg in got["threes"][0]["legs"]}
    assert legs["Patrick Mahomes"]["headshot"] == MAHOMES, "the photo the report's own ticket carried"
    assert legs["Rashee Rice"]["headshot"] == RICE, "no photo on the report: the sport's stored one"
    assert "headshot" not in legs["Trey McBride"], "none anywhere: the page draws his club's helmet"
    picks = {p["player"]: p for p in got["picks"]}
    assert picks["Kyler Murray"]["headshot"] == MURRAY, "a pick wears the photo its report's card carried"
    assert "headshot" not in picks["KC"], "a club's bet wears its club's mark, not a face"
    # A reader without the membership sees what has settled, faces and all.
    free = O.for_games("nfl", [("2026-11-22", "ARI", "KC")], member=False, path=_journal(), where=_archive(),
                       faces={})["2026-11-22|ARI|KC"]
    assert free["threes"][0]["legs"][0]["headshot"] == MAHOMES


def test_the_reports_own_photo_first_its_clubs_before_its_names():
    known = BF.doc_faces({"x": [{"player": "Josh Allen", "team": "BUF", "headshot": "https://img.example/qb.png"},
                                {"player": "Josh Allen", "team": "JAX", "headshot": "https://img.example/lb.png"}]},
                         [{"player": "Saquon Barkley", "team": "PHI", "headshot": "https://img.example/sb.png"},
                          {"player": "No Photo", "team": "PHI", "headshot": "not a url"}])
    by_team, by_name = known
    assert by_team[(BF._norm("Josh Allen"), "JAX")] == "https://img.example/lb.png"
    assert BF._norm("Josh Allen") not in by_name, "two photos claim the name: only its club settles it"
    assert by_name[BF._norm("Saquon Barkley")] == "https://img.example/sb.png"
    assert BF._norm("No Photo") not in by_name, "only a real address is a photo"
    rows = [{"player": "Josh Allen", "team": "JAX", "market": "sacks"},
            {"player": "Josh Allen", "team": "", "market": "pass_yds"},
            {"player": "Saquon Barkley", "team": "PHI", "market": "rush_yds"},
            {"player": "Saquon Barkley", "market": "rush_yds", "headshot": OTHER},
            {"player": "PHI", "market": "moneyline", "game": True},
            {"player": "Over 44.5", "market": "total"}]
    stored = {BF._norm("Josh Allen"): "https://img.example/stored.png", BF._norm("PHI"): OTHER}
    assert BF.record_faces([(rows, known)], "nfl", stored=stored) == 3
    assert rows[0]["headshot"] == "https://img.example/lb.png", "its club's photo"
    assert rows[1]["headshot"] == "https://img.example/stored.png", "no club to settle it: the stored photo"
    assert rows[2]["headshot"] == "https://img.example/sb.png"
    assert rows[3]["headshot"] == OTHER, "a row that has a face keeps it"
    assert "headshot" not in rows[4] and "headshot" not in rows[5], "a club's bet and a total wear no face"


def test_the_records_newest_tickets_wear_their_stored_faces():
    rec = {"nfl": {"three": {"recent": [{"game": "ARI@KC", "legs": [
                {"player": "Patrick Mahomes", "team": "KC", "market": "pass_yds"},
                {"player": "KC", "market": "moneyline"}]}]},
                   "sgpx_props": {"recent": [{"game": "SGPX CLE@BAL, ARI@KC", "legs": [
                       {"player": "Rashee Rice", "market": "receptions"}]}]}},
           "nba": {"two": {"recent": [{"game": "BOS@SAC", "legs": [{"player": "Jayson Tatum", "market": "points"}]}]}},
           "error": "a key the page skips"}
    stored = {"nfl": {BF._norm("Patrick Mahomes"): MAHOMES, BF._norm("Rashee Rice"): RICE}}
    assert ledger._recent_faces(rec, stored) == 2
    legs = rec["nfl"]["three"]["recent"][0]["legs"]
    assert legs[0]["headshot"] == MAHOMES and "headshot" not in legs[1]
    assert rec["nfl"]["sgpx_props"]["recent"][0]["legs"][0]["headshot"] == RICE, "the SGPX tickets too"
    assert "headshot" not in rec["nba"]["two"]["recent"][0]["legs"][0], "a sport with no photos on file draws helmets"
    # Read after the SGPX parlays join the record, so theirs are given faces too.
    at = LEDGER.index("def _game_parlay_record(conn)")
    body = LEDGER[at:LEDGER.index("\ndef ", at + 10)]
    assert body.index("SGPX_SOURCES") < body.index("    _recent_faces(rec)\n") < body.index("    return rec")
    # Each newest leg says its club, so a face found by name, or the helmet drawn in its place, is its club's.
    src = (ROOT / "engine" / "parlayledger.py").read_text(encoding="utf-8")
    assert "SELECT parlay_id, leg_no, player, team, market, side, line" in src
    assert '**({"team": l["team"]} if l["team"] else {}),' in src


def test_a_failure_says_so_and_a_quiet_record_prints_nothing():
    buf = io.StringIO()
    was = BF._norm
    BF._norm = lambda _n: (_ for _ in ()).throw(RuntimeError("the name key is gone"))
    try:
        with contextlib.redirect_stdout(buf):
            assert BF.record_faces([([{"player": "Patrick Mahomes", "market": "pass_yds"}], None)], "nfl", stored={}) == 0
    finally:
        BF._norm = was
    said = buf.getvalue()
    assert "record faces skipped (nfl, RuntimeError" in said, said
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert BF.record_faces([([{"player": "Nobody Known", "market": "points"}], None)], "nba", stored={}) == 0
        assert BF.record_faces([], "nba") == 0
    assert buf.getvalue() == "", "a quiet record prints nothing"
    # No history on this box: no faces, and no empty file left behind.
    from engine import db
    missing = os.path.join(tempfile.mkdtemp(), "none.db")
    old = db.DEFAULT_DB
    db.DEFAULT_DB = Path(missing)
    try:
        assert BF._stored_read_only("nfl") == {} and not os.path.exists(missing)
    finally:
        db.DEFAULT_DB = old


def _node(script: str):
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        return None
    head = ("const vm = require('vm');"
            "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
            "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, MINUS: '\\u2212',"
            " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'),"
            " RES_GAME_MARKETS: new Set(['moneyline', 'total', 'spread', 'team_total']),"
            " RES_SCORE_MARKETS: new Set(['anytime_td', 'anytime_goal', 'goals', 'first_td']),"
            " marketWord: (m) => m, icon: (n) => '[' + n + ']',"
            " teamMark: (t, size) => '<i class=\"tm\" data-s=\"' + size + '\">' + t + '</i>',"
            " playerAvatar: (p, t, o) => '<i class=\"av\" data-p=\"' + p + '\" data-t=\"' + (t || '') + '\" data-s=\"'"
            " + o.size + '\" data-h=\"' + (o.headshot || '') + '\"></i>', teamsForSport: () => ({}),"
            " state: { sport: 'nfl' } };"
            "vm.createContext(ctx);"
            f"vm.runInContext({json.dumps(SETTLED)}, ctx);")
    out = subprocess.run([node, "-e", head + script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


G = {"sport": "nfl", "home": "KC", "away": "ARI", "final": {"home": 34, "away": 7}, "date": "2026-11-22"}
TICKET = {"title": "Three-leg parlay 1", "status": "won", "dec": 3.14, "units": 2.14, "legs": [
    {"bet": {"player": "Patrick Mahomes", "team": "KC", "market": "pass_yds", "side": "OVER", "line": 249.5,
             "headshot": MAHOMES}, "res": {"status": "won", "actual": 281}, "open": True},
    {"bet": {"player": "Trey McBride", "team": "ARI", "market": "receptions", "side": "OVER", "line": 5.5},
     "res": {"status": "won", "actual": 6}, "open": True},
    {"bet": {"team": "KC", "market": "spread", "game": True, "line": -3.5}, "res": {"status": "won"},
     "words": "Chiefs −3.5"}]}


def test_each_settled_legs_box_wears_its_face():
    got = _node(f"process.stdout.write(JSON.stringify([vm.runInContext('settledTicketHTML', ctx)({json.dumps(TICKET)},"
                f" {json.dumps(G)}), vm.runInContext('settledLegHTML', ctx)({{ bet: {{ market: 'total', line: 44.5,"
                f" side: 'OVER', game: true, team: 'KC' }}, res: {{ status: 'lost' }}, words: 'Over 44.5 total' }},"
                f" {json.dumps(G)})]));")
    if got is None:
        return
    ticket, total = got
    mahomes = f'<i class="av" data-p="Patrick Mahomes" data-t="KC" data-s="30" data-h="{MAHOMES}"></i>'
    assert ('<li class="st-leg won" data-open="player:patrick-mahomes"><span class="st-leg-face" aria-hidden="true">'
            + mahomes + '</span><span class="st-leg-text">') in ticket, "his photo, beside the bet, in its box"
    assert '<span class="st-leg-face" aria-hidden="true"><i class="av" data-p="Trey McBride" data-t="ARI" data-s="30"' \
           ' data-h=""></i></span>' in ticket, "no photo on file: the avatar draws his club's helmet"
    assert '<span class="st-leg-face" aria-hidden="true"><i class="tm" data-s="30">KC</i></span>' in ticket, \
        "a club's bet wears its club's mark"
    # The ticket's head wears the same three, smaller.
    head = ticket[:ticket.index('<ol class="st-legs">')]
    assert f'data-p="Patrick Mahomes" data-t="KC" data-s="22" data-h="{MAHOMES}"' in head
    assert '<i class="tm" data-s="22">KC</i>' in head
    assert "st-leg-face" not in total, \
        "a total is the game's, though the journal files it under a club (ARI at KC's under KC): no face, no mark"
    assert "function settledFaceHTML(b, g, size)" in SETTLED
    assert ".st-leg-face { display: grid; flex: none; line-height: 0; }" in CSS


def test_the_sweep_knows_the_record_faces_say_when_they_fail():
    src = (ROOT / "tests" / "test_silent_failures.py").read_text(encoding="utf-8")
    assert '"record_faces"' in src


SEE = """() => {
  const leg = document.querySelector('#ait .st-leg');
  const face = leg && leg.querySelector('.st-leg-face'), text = leg && leg.querySelector('.st-leg-text');
  const f = face && face.getBoundingClientRect(), t = text && text.getBoundingClientRect();
  return { photo: !!(face && face.querySelector('img.avatar-photo')), beside: !!(f && t && f.right <= t.left + 1),
           size: f ? Math.round(f.width) : 0,
           wide: [...document.querySelectorAll('#ait *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
             .map((e) => e.className).slice(0, 5) };
}"""


def test_in_the_browser_the_face_sits_beside_the_bet_and_nothing_runs_off():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(ROOT / "tests"))
    import rendercheck
    srv, port = rendercheck._serve()
    errs = []
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                ctx = browser.new_context(viewport={"width": 360, "height": 800}, service_workers="block")
                page = ctx.new_page()
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.route(lambda u: not u.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}"
                                     "catch(e){}")
                page.goto(f"http://127.0.0.1:{port}/index.html?sport=nfl", wait_until="load")
                page.wait_for_function("typeof loadRoom === 'function'", timeout=20000)
                page.evaluate("loadRoom('js/record.js', 'css/record.css')")
                page.wait_for_function("typeof settledTicketHTML === 'function'", timeout=20000)
                page.evaluate("""([g, t]) => { const box = document.createElement('div'); box.id = 'ait';
                    box.innerHTML = settledTicketHTML(t, g); document.body.prepend(box); }""", [G, TICKET])
                x = page.evaluate(SEE)
                ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()
    assert not errs, errs
    assert x["photo"] and x["beside"] and x["size"] == 30, x
    assert x["wide"] == [], x


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
