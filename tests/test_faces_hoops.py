"""NBA and WNBA player faces, taken from the box score we already fetch.

Ethan, 2026-08-08: "can we also get every players face photo for when we
display the props we can show there face with it."

WHY THESE TWO SPORTS AND NOT THE OTHERS. NFL was free — nflverse ships a
`headshot_url` column. Every other sport holds a NAME where the CDN wants an
ID, and `player_game_logs` has never stored an identifier. NBA and WNBA turn
out to be free too, for a reason worth writing down: ESPN's box-score summary
already carries `athlete.id` and `athlete.headshot.href` in the same payload
the stat line comes from. The parser read that dict and threw both away. So
this is one field kept, not a second feed.

MLB is still open and deliberately not attempted here — we ingest statsapi,
which gives MLB's own player ids, not ESPN's, so it needs a name→id join
before any ESPN path means anything.

THE URL IS TAKEN, NEVER RECONSTRUCTED. Building
`.../headshots/{league}/players/full/{id}.png` by hand is the same class of
guess that produced `limit=400` and the User-Agent 403 earlier in this
project. A href the feed handed us cannot be wrong about its own shape. The
id is stored anyway, because it is the only stable handle if a payload ever
omits the href.

Run directly: `python3 tests/test_faces_hoops.py`
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import db
from engine.sources import espnhoops as eh

HREF = "https://a.espncdn.com/i/headshots/wnba/players/full/3149391.png"


def _summary(athletes):
    """An ESPN summary payload, shaped the way the real one is."""
    return {"boxscore": {"players": [{
        "team": {"abbreviation": "LV"},
        "statistics": [{"names": ["MIN", "PTS", "REB", "AST", "3PT"],
                        "athletes": athletes}]}]}}


def _ath(name, **kw):
    info = {"displayName": name}
    info.update(kw)
    return {"starter": True, "athlete": info,
            "stats": ["34", "27", "11", "3", "1-2"]}


# --- the parse ---------------------------------------------------------------
def test_the_box_score_row_carries_the_photo_and_the_id():
    rows = eh.parse_summary(_summary([
        _ath("A'ja Wilson", id=3149391, headshot={"href": HREF})]))
    assert len(rows) == 1
    assert rows[0]["headshot"] == HREF
    assert rows[0]["espn_id"] == "3149391"


def test_the_url_is_the_one_the_feed_gave_us():
    """Not rebuilt from the id. If ESPN moves its headshot path tomorrow, a
    taken href follows it and a reconstructed one 404s every face."""
    odd = "https://a.espncdn.com/some/other/path/x.png"
    rows = eh.parse_summary(_summary([_ath("P", id=99, headshot={"href": odd})]))
    assert rows[0]["headshot"] == odd, "the URL is being reconstructed"


def test_a_missing_photo_block_is_a_blank_not_a_crash():
    """Bench players and recent call-ups routinely have no headshot key. A
    KeyError here would take down the whole game's stat ingest with it."""
    rows = eh.parse_summary(_summary([_ath("No Photo", id=42)]))
    assert rows[0]["headshot"] == ""
    assert rows[0]["espn_id"] == "42"
    assert rows[0]["stats"]["pts"] == 27.0, "the stat line must survive intact"


def test_a_headshot_that_is_a_bare_string_still_works():
    """Defensive: `headshot` is a dict on every payload seen, but the parse
    costs nothing to make tolerant and a TypeError here is silent data loss."""
    rows = eh.parse_summary(_summary([_ath("S", id=1, headshot=HREF)]))
    assert rows[0]["headshot"] == HREF


# --- the store ---------------------------------------------------------------
def test_the_sports_do_not_share_a_face_table():
    """Per-sport isolation is a hard rule in this repo, and names collide
    across leagues more often than people expect."""
    conn = db.connect(":memory:")
    db.upsert_player_assets(conn, [
        {"sport": "wnba", "player": "Same Name", "espn_id": "1",
         "headshot": HREF, "seen": "2026-08-08"}])
    assert db.player_assets(conn, "wnba")["Same Name"]["headshot"] == HREF
    assert db.player_assets(conn, "nba") == {}


def test_a_blank_never_erases_a_photo_we_already_have():
    """THE BUG THIS TABLE WOULD OTHERWISE HAVE. Not every box score carries
    a headshot block, and backfills do not run in date order — so a player
    with a good photo can be written again from a game that has none. Plain
    INSERT OR REPLACE would blank the face. Same fix `upsert_games` uses."""
    conn = db.connect(":memory:")
    db.upsert_player_assets(conn, [
        {"sport": "nba", "player": "P", "espn_id": "7",
         "headshot": HREF, "seen": "2026-01-02"}])
    db.upsert_player_assets(conn, [
        {"sport": "nba", "player": "P", "espn_id": "7",
         "headshot": "", "seen": "2026-01-01"}])
    assert db.player_assets(conn, "nba")["P"]["headshot"] == HREF


def test_a_real_new_url_does_replace_the_old_one():
    """The guard above must not freeze the first value forever — ESPN
    reissues photos, and a stale URL eventually 404s."""
    conn = db.connect(":memory:")
    for url, day in ((HREF, "2026-01-02"), ("http://x/new.png", "2026-02-01")):
        db.upsert_player_assets(conn, [
            {"sport": "nba", "player": "P", "espn_id": "7",
             "headshot": url, "seen": day}])
    assert db.player_assets(conn, "nba")["P"]["headshot"] == "http://x/new.png"


def test_writing_no_rows_is_not_an_error():
    """`ingest_day` calls this unconditionally, including on a scores-only
    backfill day where no box score was fetched at all."""
    conn = db.connect(":memory:")
    assert db.upsert_player_assets(conn, []) == 0


def test_a_database_from_before_this_table_reads_as_no_faces():
    """Ethan's DB predates the table. `connect()` creates it, but anything
    holding a raw sqlite3 handle does not — and the correct answer there is
    an empty map and the initials chip, not a stack trace on his board."""
    raw = sqlite3.connect(":memory:")
    assert db.player_assets(raw, "nba") == {}


# --- the ingest --------------------------------------------------------------
def test_identity_is_collected_once_per_player_per_game():
    """The same person appears in this loop for points, rebounds and assists.
    An id does not vary between markets, and three identical writes per
    player per game is 300k pointless statements over a six-season backfill."""
    import inspect
    src = inspect.getsource(eh.ingest_day)
    i = src.index("for row in parse_summary(summary):")
    j = src.index("for market, value in row[\"stats\"].items():")
    assert "arows.append" in src[i:j], (
        "the asset write moved inside the per-market loop")


def test_a_player_with_neither_id_nor_photo_is_not_written():
    """A row of two empty strings is not a fact about anyone."""
    import inspect
    src = inspect.getsource(eh.ingest_day)
    assert 'if row.get("espn_id") or row.get("headshot"):' in src


def test_the_ingest_reports_what_it_stored():
    """`assets` sits in the result dict beside `games` and `player_logs`, so
    a run that silently captured zero faces is visible in the output rather
    than discovered weeks later on an empty board."""
    import inspect
    src = inspect.getsource(eh.ingest_day)
    assert '"assets": 0' in src, "the counter is not initialised"
    assert 'result["assets"] = db.upsert_player_assets(conn, arows)' in src


# --- the board ---------------------------------------------------------------
def test_the_recommendation_carries_the_face():
    """This field has been on the shared record since NBA shipped and
    nothing ever filled it — every NBA and WNBA prop drew the initials
    avatar while ESPN was handing us the photo in the same payload."""
    import inspect
    from engine.nba import pipeline as np
    src = inspect.getsource(np.shared_recommendations)
    assert "assets" in inspect.signature(np.shared_recommendations).parameters
    assert '"headshot": ""' not in src, "still hardcoded empty"
    assert '(assets or {}).get(r["player"], {}).get("headshot", "")' in src


def test_the_build_actually_passes_the_map():
    """The parameter defaults to None, so forgetting the call site is a
    silent no-op — the exact failure mode that would look like 'ESPN has no
    photos for these players'."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "nba_build.py"), encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("recs = shared_recommendations(")
    call = src[i:i + 400]
    assert "assets=" in call, "the build still builds recommendations faceless"
    assert "player_assets(conn, args.league)" in call, (
        "the faces must be read for the league being built, or a WNBA board "
        "looks up NBA players and finds none")


def test_the_face_reads_for_the_league_being_built_not_a_fixed_one():
    """This build runs as BOTH leagues off one call site — the same reason
    the journal had to be filed under args.league rather than 'nba'."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "nba_build.py"), encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("recs = shared_recommendations(")
    call = src[i:i + 400]
    assert '"nba"' not in call and "'nba'" not in call


def test_the_espn_url_is_passed_through_untouched_by_the_face_resizer():
    """`facePreview` splices a Cloudinary transform into the path. ESPN is
    not Cloudinary — a transform spliced into an ESPN path would 404 every
    face on these two boards."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "web", "js", "visuals.js"), encoding="utf-8") as fh:
        js = fh.read()
    i = js.index("function facePreview(")
    body = js[i:i + 700]
    assert "indexOf(marker) < 0" in body and "return url" in body


def test_the_avatar_still_falls_back_when_a_photo_is_missing():
    """Most of a bench will have no href. Those props must draw the chip
    that shipped before, not an empty box — `playerAvatar` branches on a
    truthy headshot, so an empty string takes the old path."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "web", "js", "visuals.js"), encoding="utf-8") as fh:
        js = fh.read()
    i = js.index("function playerAvatar(")
    assert "if (opts.headshot) {" in js[i:i + 200]


# --- is it actually there? ---------------------------------------------------
def test_the_census_counts_the_photos_it_captured():
    """THE GAP ETHAN'S RUN EXPOSED. He re-ingested NBA and WNBA, and the
    census reported games and player-log rows and said nothing about faces —
    so a run that captured zero photos and a run that captured thousands
    print identically, and the board looks the same either way because a
    missing photo correctly falls back to the initials chip."""
    import io
    from contextlib import redirect_stdout
    import ingest
    conn = db.connect(":memory:")
    _seed_game(conn, "nba")
    db.upsert_player_assets(conn, [
        {"sport": "nba", "player": "A", "espn_id": "1",
         "headshot": HREF, "seen": "2026-01-02"},
        {"sport": "nba", "player": "B", "espn_id": "2",
         "headshot": "", "seen": "2026-01-02"}])
    buf = io.StringIO()
    with redirect_stdout(buf):
        ingest.print_summary(conn)
    line = next(l for l in buf.getvalue().splitlines() if "photos" in l)
    assert "NBA 1/2" in line, line


def test_an_empty_photo_table_is_stated_not_omitted():
    """An absent line reads as "that is not a thing here", which is a
    different fact from "this is empty and here is how to fill it"."""
    import io
    from contextlib import redirect_stdout
    import ingest
    conn = db.connect(":memory:")
    _seed_game(conn, "wnba")
    buf = io.StringIO()
    with redirect_stdout(buf):
        ingest.print_summary(conn)
    out = buf.getvalue()
    assert "none stored" in out, out
    assert "Re-ingest" in out, "no instruction for how to fill it"


def test_a_database_without_the_table_still_prints_a_census():
    """`print_summary` runs at the end of every ingest. A pre-migration
    database must not turn a report into a stack trace."""
    import io
    import sqlite3
    from contextlib import redirect_stdout
    import ingest
    conn = db.connect(":memory:")
    _seed_game(conn, "nba")
    conn.execute("DROP TABLE player_assets")
    buf = io.StringIO()
    with redirect_stdout(buf):
        ingest.print_summary(conn)
    assert "NBA:" in buf.getvalue()


def _seed_game(conn, sport):
    db.upsert_games(conn, [{
        "sport": sport, "season": 2025, "period": "2026-01-02",
        "game_id": "1", "home": "BOS", "away": "LAL",
        "home_score": 1.0, "away_score": 2.0, "spread": 0.0, "total": None,
        "roof": "indoor", "surface": "hardwood", "temp": None, "wind": None,
        "extra": None}])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
