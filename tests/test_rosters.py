"""Active rosters, and trades found without a news feed.

The roster page answers "who is on this team right now" from the players
blob the fantasy layer already fetches — no new source, no new request.

The part worth guarding is what makes it honest rather than merely
present:

* a free agent is not on a roster, and must not appear on one;
* an unavailable player (IR, PUP, suspended) is SHOWN with his status —
  a roster with the injuries quietly filtered reads as a healthy team;
* depth order is the coaching staff's opinion, so an unranked player
  sorts after the ranked ones rather than to the top, where he would read
  as the starter;
* and transactions come from diffing our own daily snapshots, which means
  a player appearing for the FIRST time is not a signing — we can't tell
  that from the feed adding someone it didn't carry yesterday.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import rosters


def _p(full, team, pos="WR", order=None, status="Active", exp=3, age=25):
    return {"full_name": full, "team": team, "position": pos,
            "depth_chart_order": order, "status": status,
            "years_exp": exp, "age": age}


def _blob(*players):
    return {str(i): p for i, p in enumerate(players)}


def test_a_free_agent_is_on_no_roster():
    out = rosters.build_rosters(_blob(_p("Signed Guy", "SF"),
                                      _p("Free Agent", None),
                                      _p("Also Free", "")))
    assert out["player_count"] == 1
    assert list(out["teams"]) == ["SF"]


def test_the_injured_are_listed_not_hidden():
    out = rosters.build_rosters(_blob(
        _p("Healthy", "SF", order=1),
        _p("Hurt", "SF", order=2, status="Injured Reserve")))
    sf = out["teams"]["SF"]
    assert sf["count"] == 2, "an IR player is still on the roster"
    assert sf["unavailable"] == 1
    names = [p["player"] for p in sf["players"]]
    assert "Hurt" in names
    hurt = next(p for p in sf["players"] if p["player"] == "Hurt")
    assert hurt["unavailable"] and hurt["status"] == "Injured Reserve"
    # …and sorted below the available players at his position.
    assert names.index("Healthy") < names.index("Hurt")


def test_unranked_players_sort_below_ranked_ones():
    out = rosters.build_rosters(_blob(
        _p("No Slot", "SF", "QB"),
        _p("Starter", "SF", "QB", order=1),
        _p("Backup", "SF", "QB", order=2)))
    assert [p["player"] for p in out["teams"]["SF"]["players"]] == \
        ["Starter", "Backup", "No Slot"], "an unlisted slot read as QB1"


def test_positions_group_in_depth_chart_order():
    out = rosters.build_rosters(_blob(
        _p("Kicker", "SF", "K", order=1),
        _p("Corner", "SF", "CB", order=1),
        _p("Quarterback", "SF", "QB", order=1)))
    assert [p["player"] for p in out["teams"]["SF"]["players"]] == \
        ["Quarterback", "Corner", "Kicker"]
    assert rosters.group_of("QB") == "Offense"
    assert rosters.group_of("CB") == "Defense"
    assert rosters.group_of("K") == "Special teams"


def test_rookies_are_counted():
    out = rosters.build_rosters(_blob(_p("Rook", "SF", exp=0),
                                      _p("Vet", "SF", exp=8)))
    assert out["teams"]["SF"]["rookies"] == 1
    rook = next(p for p in out["teams"]["SF"]["players"] if p["player"] == "Rook")
    assert rook["rookie"] and rook["years_exp"] == 0


def test_no_feed_is_not_an_empty_league():
    assert rosters.build_rosters(None) == {"teams": {}, "team_count": 0,
                                           "player_count": 0}
    assert rosters.build_rosters({}) == {"teams": {}, "team_count": 0,
                                         "player_count": 0}


# --- transactions -----------------------------------------------------------
def test_a_trade_is_the_day_the_answer_changed():
    store = {"2026-07-30": {"Deebo Samuel Sr.": "WAS", "Brock Purdy": "SF"},
             "2026-07-31": {"Deebo Samuel Sr.": "SF", "Brock Purdy": "SF"}}
    tx = rosters.transactions(store)
    assert tx["moves"] == [{"player": "Deebo Samuel Sr.", "from": "WAS",
                            "to": "SF", "date": "2026-07-31"}]


def test_a_new_name_is_not_a_signing():
    # He might be a signing; he might be a player the feed didn't carry
    # yesterday. Nothing distinguishes them, so neither is claimed.
    store = {"2026-07-30": {"Old Guy": "SF"},
             "2026-07-31": {"Old Guy": "SF", "New Name": "SF"}}
    assert rosters.transactions(store)["moves"] == []


def test_both_legs_of_a_double_move_are_kept():
    store = {"2026-07-29": {"Journeyman": "SF"},
             "2026-07-30": {"Journeyman": "KC"},
             "2026-07-31": {"Journeyman": "BUF"}}
    moves = rosters.transactions(store)["moves"]
    assert len(moves) == 2, "only the net move survived"
    assert [(m["from"], m["to"]) for m in moves] == [("KC", "BUF"), ("SF", "KC")]


def test_one_snapshot_has_nothing_to_diff():
    assert rosters.transactions({"2026-07-31": {"A": "SF"}})["moves"] == []
    assert rosters.transactions({})["moves"] == []


def test_the_window_limits_how_far_back_it_looks():
    store = {f"2026-07-{d:02d}": {"Guy": "SF" if d < 20 else "KC"}
             for d in range(1, 32)}
    assert rosters.transactions(store, days=3)["moves"] == [], \
        "a move outside the window was reported as recent"
    assert len(rosters.transactions(store, days=30)["moves"]) == 1


def test_the_snapshot_covers_more_than_fantasy_positions():
    # The camp watch only snapshots fantasy positions with a depth slot. A
    # trade is a trade whether or not the player is on somebody's board.
    snap = rosters.team_snapshot(_blob(_p("Left Tackle", "SF", "OT"),
                                       _p("Long Snapper", "SF", "LS")))
    assert snap == {"Left Tackle": "SF", "Long Snapper": "SF"}


def test_history_survives_the_cache_pruner():
    # The pruner works from an ALLOWLIST of prefixes; this file matches
    # none of them, which is what keeps accumulated history alive.
    from engine.maintenance import PRUNABLE_CACHE_PREFIXES
    assert not rosters.SNAPSHOT_FILE.startswith(PRUNABLE_CACHE_PREFIXES)


def test_the_roster_page_carries_a_face_for_every_player_it_can():
    """Ethan, 2026-08-13: "we are not showing player headshots or logos on
    the roster page either."

    He was right and it was not a rendering bug: NO roster producer had
    ever emitted a `headshot` key, so the page had nothing to draw even
    when `player_assets` held the photo. All three producers emit it now,
    and a producer that emits nothing is the failure this pins.
    """
    from engine import rosters
    faces = {"Signed Guy": "https://x/face.png"}
    out = rosters.build_rosters(_blob(_p("Signed Guy", "SF")), faces=faces)
    row = out["teams"]["SF"]["players"][0]
    assert row["headshot"] == "https://x/face.png"
    # And a player with no photo gets the empty string, never a missing
    # key — `undefined` and "" render the same but debug very differently.
    out2 = rosters.build_rosters(_blob(_p("Faceless", "SF")), faces=faces)
    assert out2["teams"]["SF"]["players"][0]["headshot"] == ""


def test_the_face_join_survives_the_punctuation_two_feeds_disagree_on():
    """The photo table is keyed by one feed's spelling and the roster rows
    carry another's. An exact-string join is why 100 of 105 WNBA photos
    were ingested on 2026-08-10 and every card still drew initials.

    `face_of` folds case, accents, punctuation and suffixes — and NOTHING
    else, so two different players can never collide into one face.
    """
    from engine.rosters import face_of
    faces = {"aja wilson": "https://x/aja.png"}
    assert face_of(faces, "A'ja Wilson") == "https://x/aja.png"
    # Different people stay different people.
    assert face_of(faces, "Jordan Wilson") == ""
    # No map, no name, no crash.
    assert face_of(None, "Anyone") == "" and face_of(faces, "") == ""


def test_mlb_faces_come_from_the_person_id_not_the_assets_table():
    """The first cut pointed every sport at `player_assets` and shipped
    with the MLB logos working and every face still an initials chip.

    Only the hoops ingest writes that table: ESPN's box score hands over a
    photo href, so NBA/WNBA faces are TAKEN. The Stats API publishes no
    photo URL, so MLB's is CONSTRUCTED from the person id — the path the
    MLB prop board has used since the splits work. Baseball was reading a
    table nothing had ever written a baseball row into.
    """
    from engine import rosters
    from engine.mlb.sources import mlbstats
    feed = {"CHC": [{"name": "Pete Crow-Armstrong", "position": "CF",
                     "number": "4", "status": "Active", "person_id": 691718}]}
    out = rosters.mlb_feed_rosters(feed)
    row = out["teams"]["CHC"]["players"][0]
    assert row["headshot"] == mlbstats.headshot_url(691718)
    assert "691718" in row["headshot"]
    # A player the feed has no id for gets "", never a malformed URL
    # pointing at nobody.
    out2 = rosters.mlb_feed_rosters({"CHC": [{"name": "No Id", "person_id": 0}]})
    assert out2["teams"]["CHC"]["players"][0]["headshot"] == ""


def test_the_appearance_fallback_still_finds_baseball_faces():
    """The fallback builds rows from game logs, which carry no person id
    at all — so its faces have to come from the league feed's ids, joined
    on the normalised name. This pins the join, not the fetch."""
    from engine.rosters import face_of, _norm_key
    from engine.mlb.sources.mlbstats import headshot_url
    faces = {_norm_key("Pete Crow-Armstrong"): headshot_url(691718)}
    assert face_of(faces, "Pete Crow-Armstrong") == headshot_url(691718)
    # The log spelling and the feed spelling disagree about punctuation
    # more often in baseball than anywhere else.
    faces2 = {_norm_key("Jose Ramirez"): headshot_url(608070)}
    assert face_of(faces2, "José Ramírez") == headshot_url(608070)


def test_the_page_shows_why_it_fell_back_instead_of_a_short_roster():
    """Ethan's MLB roster page, 2026-08-13: 18 Cubs, every one of them a
    position player, and nothing anywhere saying so.

    `rosters_build` writes the reason into `note` — "built from
    appearances because the league feed failed (...) — pitchers don't bat,
    so they are missing from this view". The page then rendered that note
    ONLY when feed == "unavailable", and the appearance fallback is
    stamped feed:"live" because it IS live data from another source. So
    the explanation was computed on every build and displayed on none of
    them.

    A missing pitcher that announces itself is a known gap. A silent one
    is a wrong roster, which is the more expensive kind of wrong.
    """
    import os
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read() if "ROOT" in globals() else open(
        os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "web", "js", "app.js"),
        encoding="utf-8").read()
    assert 'const stale = d.feed === "unavailable"' not in app
    assert 'const stale = (d.note || "")' in app


def test_the_fallback_note_names_the_blind_spot_it_creates():
    """Saying "the feed failed" is only half of it — the reader needs to
    know what that costs them on THIS page."""
    import inspect
    import rosters_build
    src = inspect.getsource(rosters_build.payload_for)
    assert "pitchers don" in src and "missing from this" in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
