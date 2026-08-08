"""The UFC card must fill itself in.

Two things used to be commands a person had to remember: drafting fighter
dossiers, and typing in weigh-in results. Both were load-bearing — "no
dossier, no bet" meant a 34-bout card with 8 dossiers modelled 8 fights,
and the weigh-in was the one fight-week fact the grade could see. A model
whose coverage depends on somebody running a script is a model that is
usually uncovered.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.ufc import weighin, weighin_feed


# --- weigh-in feed ----------------------------------------------------------
def _event(weights):
    """An ESPN-shaped MMA event carrying `weights` = [(name, field, value)]."""
    return {"name": "UFC Test", "competitions": [{
        "type": {"text": "Lightweight Bout"},
        "competitors": [
            {"athlete": {"displayName": n}, field: v}
            for n, field, v in weights
        ]}]}


def test_a_recorded_weight_is_read_and_graded_like_a_typed_one():
    ev = _event([("Alpha Fighter", "weighIn", 155.0),
                 ("Beta Fighter", "weighIn", 157.5)])
    rows = weighin_feed.scan_event(ev)
    assert {r["name"] for r in rows} == {"Alpha Fighter", "Beta Fighter"}
    assert all(r["division"] == "lightweight" for r in rows)
    # 155.0 makes the 156.0 non-title limit; 157.5 does not.
    a = weighin.evaluate(155.0, "lightweight")
    b = weighin.evaluate(157.5, "lightweight")
    assert a["state"] == "made" and b["state"] == "missed"


def test_an_implausible_weight_is_refused_rather_than_recorded():
    """A bad number is worse than no number: it manufactures a "missed
    weight" red flag that blocks a real bet."""
    for bad in (70.0, 0, 900.0, "n/a", None):
        w, _f = weighin_feed.read_weight({"weight": bad})
        assert w is None, f"{bad!r} was accepted as a fighting weight"
    kg = weighin_feed.read_weight({"weight": 70.3})       # kilograms
    assert kg[0] is None


def test_an_explicit_weigh_in_field_beats_a_generic_weight():
    """On some payloads `weight` is the fighter's listed walk-around
    weight, not what the scale said."""
    w, field = weighin_feed.read_weight({"weight": 170.0, "weighIn": 155.5})
    assert (w, field) == (155.5, "weighIn")


def test_a_card_with_no_weights_yet_reports_that_instead_of_guessing():
    ev = _event([])
    assert weighin_feed.scan_event(ev) == []


def test_divisions_survive_the_words_around_them():
    for text, want in (("Women's Flyweight Title Bout", "flyweight"),
                       ("Light Heavyweight Bout", "light heavyweight"),
                       ("Catchweight (178 lbs)", "Catchweight (178 lbs)")):
        assert weighin_feed._division_text(text) == want


def test_light_heavyweight_is_not_read_as_heavyweight():
    """Substring matching, longest-first — otherwise a 205er is checked
    against the 265 limit and every miss goes unseen."""
    assert weighin_feed._division_text("Light Heavyweight Bout") \
        == "light heavyweight"
    assert weighin.limit_for("light heavyweight") == 206.0


def test_refresh_records_every_weight_the_card_carries(monkeypatch=None):
    tmp = os.path.join(tempfile.mkdtemp(), "wi.json")
    ev = _event([("Alpha Fighter", "weighIn", 155.0),
                 ("Beta Fighter", "weighIn", 157.5)])
    orig = weighin_feed.fetch_card
    weighin_feed.fetch_card = lambda date=None: {"events": [ev]}
    try:
        res = weighin_feed.refresh(store_path=tmp, today="2026-08-01")
    finally:
        weighin_feed.fetch_card = orig
    assert res["recorded"] == 2 and res["made"] == 1 and res["missed"] == 1
    store = json.loads(open(tmp).read())
    assert weighin.state_for("Alpha Fighter", store)["state"] == "made"
    assert weighin.state_for("Beta Fighter", store)["state"] == "missed"


def test_an_empty_feed_is_reported_not_silently_swallowed():
    orig = weighin_feed.fetch_card
    weighin_feed.fetch_card = lambda date=None: {"events": []}
    try:
        res = weighin_feed.refresh(store_path=os.path.join(
            tempfile.mkdtemp(), "wi.json"))
    finally:
        weighin_feed.fetch_card = orig
    assert res["recorded"] == 0 and res["note"]


def _dated_event(date, weights=None):
    ev = _event(weights or [])
    ev.update({"id": "600", "date": date})
    return ev


def test_the_probe_says_which_reason_a_blank_result_has():
    """"Nothing found" has two causes with opposite meanings — the scale
    has not happened yet, or this feed does not carry weights at all. A
    diagnostic you still have to guess after is not a diagnostic."""
    orig_fetch, orig_deep = weighin_feed.fetch_card, weighin_feed.deep_scan
    weighin_feed.deep_scan = lambda eid, limit=6: []
    try:
        weighin_feed.fetch_card = lambda date=None: {
            "events": [_dated_event("2026-08-09T23:00Z")]}
        early = "\n".join(weighin_feed.probe("2026-08-01"))
        weighin_feed.fetch_card = lambda date=None: {
            "events": [_dated_event("2026-08-01T23:00Z")]}
        onday = "\n".join(weighin_feed.probe("2026-08-01"))
    finally:
        weighin_feed.fetch_card, weighin_feed.deep_scan = orig_fetch, orig_deep

    assert "nothing published yet and nothing wrong" in early
    assert "does not publish weigh-in results" not in early, \
        "a card that has not weighed in yet was called a dead feed"
    assert "does not publish weigh-in results" in onday
    for text in (early, onday):
        assert "--weigh-in" in text, "the manual escape hatch must stay offered"
        assert "camp.py" in text, "the probe must say the board is not blocked"


def test_the_probe_checks_the_fuller_record_before_giving_a_verdict():
    """The scoreboard is a SUMMARY shape. "The summary has no weights" and
    "ESPN has no weights" are different findings, and the second one is
    the one worth acting on."""
    orig_fetch, orig_deep = weighin_feed.fetch_card, weighin_feed.deep_scan
    called = []
    weighin_feed.fetch_card = lambda date=None: {
        "events": [_dated_event("2026-08-01T23:00Z")]}
    weighin_feed.deep_scan = lambda eid, limit=6: (
        called.append(eid) or [{"name": "Deep Guy", "weight": 155.0,
                                "field": "weighIn", "keys": [],
                                "division": "lightweight",
                                "title_fight": False}])
    try:
        lines = "\n".join(weighin_feed.probe("2026-08-01"))
    finally:
        weighin_feed.fetch_card, weighin_feed.deep_scan = orig_fetch, orig_deep
    assert called == ["600"], "the deeper record was never checked"
    assert "155.0 lbs" in lines
    assert "does not publish weigh-in results" not in lines, \
        "found weights in the core API and still called the feed dead"


# --- dossier auto-draft -----------------------------------------------------
def test_hand_written_dossiers_are_never_overwritten():
    import ufc_dossiers as UD
    book = {"Hand Made": {"archetype": "wrestler", "source": "ethan"},
            "Auto Made": {"archetype": "striker", "source": "espn-auto",
                          "career_fights": 12}}
    assert UD.needs_draft(book, "Hand Made") is False
    assert UD.needs_draft(book, "Hand Made", refresh=True) is False, \
        "--refresh must not clobber a human's work"
    assert UD.needs_draft(book, "Auto Made") is False
    assert UD.needs_draft(book, "Auto Made", refresh=True) is True
    assert UD.needs_draft(book, "Never Seen") is True


def test_a_stale_auto_draft_is_redrafted_without_being_asked():
    import ufc_dossiers as UD
    old = {"Old Auto": {"archetype": "striker", "source": "espn-auto"}}
    assert UD.needs_draft(old, "Old Auto") is True


def test_the_launcher_drafts_dossiers_and_pulls_weighins_on_its_own():
    """The whole point: neither is a command you have to remember."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    fn = src[src.index("def refresh_ufc("):src.index("def refresh_all(")]
    assert "_auto_dossiers(" in fn, "dossiers are still a manual chore"
    assert "_auto_weighins(" in fn, "weigh-ins are still typed in by hand"
    # And the draft must be paced, or one refresh stalls for half an hour.
    draft = src[src.index("def _auto_dossiers("):src.index("def _auto_weighins(")]
    assert "limit=" in draft, "an unpaced draft blocks the refresh loop"
    # Neither may ever take the card down.
    for block in (draft, src[src.index("def _auto_weighins("):
                              src.index("def refresh_ufc(")]):
        assert "except Exception" in block


def test_the_probe_is_dispatched_not_just_defined():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    assert '"--probe-weighins" in argv' in src



# --- the livelock, seen in the wild -----------------------------------------
def test_a_fighter_espn_cannot_find_stops_eating_the_budget():
    """Observed on a real card as "drafted 0, 7 still to draft, 4 not on
    ESPN" — every single refresh. Failures were never recorded, so an
    unfindable name needed drafting forever, sat at the front of the card,
    and consumed the whole per-tick allowance. The seven real fighters
    behind it were never drafted at all."""
    import ufc_dossiers as UD
    book = {"_unfound": {"Debut Guy": {"last_tried": "2026-08-01T10:00:00",
                                       "attempts": 1}}}
    assert UD.needs_draft(book, "Debut Guy", now="2026-08-01T11:00:00") is False
    # …but not forever: he may be added to their database later in the week.
    assert UD.needs_draft(book, "Debut Guy", now="2026-08-03T11:00:00") is True
    # And an explicit refresh always retries.
    assert UD.needs_draft(book, "Debut Guy", refresh=True,
                          now="2026-08-01T11:00:00") is True


def test_a_corrupt_timestamp_retries_rather_than_blocking_forever():
    import ufc_dossiers as UD
    book = {"_unfound": {"X": {"last_tried": "not a date"}}}
    assert UD.needs_draft(book, "X", now="2026-08-01T11:00:00") is True


def test_the_budget_counts_drafts_not_attempts():
    """A name ESPN cannot find costs one quick search; a name it can costs
    ~50 requests and half a minute. Charging both to the same allowance
    let the cheap failures crowd out the expensive successes."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ufc_dossiers.py"), encoding="utf-8").read()
    fn = src[src.index("def draft("):src.index("def _fighters(")]
    assert "len(drafted) >= limit" in fn, "failures still consume the budget"
    assert "max_attempts" in fn, "a card of unfindable names could spin"


def test_a_fighter_found_at_last_stops_being_skipped():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ufc_dossiers.py"), encoding="utf-8").read()
    assert "unfound.pop(name, None)" in src


def test_the_unfound_list_is_not_mistaken_for_a_dossier():
    """It lives in the same file, so anything walking fighters has to skip
    it or the review tool will try to review a bookkeeping record."""
    import ufc_dossiers as UD
    book = {"_readme": "x", "_unfound": {"A": {}},
            "Real Guy": {"archetype": "wrestler"}}
    assert [k for k, _v in UD._fighters(book)] == ["Real Guy"]


# --- the port that was already in use ---------------------------------------
def test_an_already_running_site_is_explained_not_traced():
    """"Address already in use" is the most ordinary thing that can
    happen — the site is open in another window. A traceback for that
    teaches somebody to be afraid of their own tool."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    # Anchor on the bind and read forward past the handler — the block is
    # long because it explains what to do, which is the point.
    # The LIVE server, not the health-check sweep's — there are two binds
    # and only one of them is the site.
    i = src.index('ThreadingHTTPServer(("0.0.0.0"')
    block = src[src.rindex("try:", 0, i):src.index("server.live_mode", i)]
    assert "except OSError" in block
    assert "48" in block and "98" in block, "only one platform's errno"
    assert "already running" in block
    assert "lsof" in block, "no way to find the other process"
    # A different OSError must still surface.
    assert "raise" in block


def test_the_health_check_does_not_fight_over_a_fixed_port():
    """A fixed port meant two --check runs at once, or one left
    half-finished, failed on "address already in use" during a HEALTH
    CHECK — the worst possible moment to hand somebody an error about our
    own plumbing."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    i = src.index("Page render sweep (headless browser)")
    block = src[i:i + 900]
    assert "port = 0" in block, "the sweep still binds a hard-coded port"
    assert "server.server_address[1]" in src, \
        "the OS-chosen port is never read back, so the browser gets the wrong one"


def test_the_build_can_say_why_every_bout_passed():
    """"12 passes" and "why 12 passes" are different questions and only the
    second is actionable. Two cards in a row produced nothing, and the
    counts alone could not distinguish missing data from a model correctly
    refusing — opposite problems with opposite fixes."""
    src = open(os.path.join(ROOT, "ufc_build.py"), encoding="utf-8").read()
    assert '"--why"' in src
    # To the END of the block, not a fixed window — the window version
    # broke the first time the block grew, which is a test failing on
    # formatting rather than on meaning.
    i = src.index("if args.why:")
    body = src[i:src.index('if __name__ ==', i)]
    for code in ("no_data", "no_price", "gated"):
        assert code in body, f"{code} is not explained in the reading"

    # THE KEY IT READS MUST BE THE KEY THE MODEL WRITES. The first version
    # read `out["passes"]` — which is a COUNT inside `counts`, not a list —
    # so on a real 12-bout card it printed a header with no rows under it.
    # Asserting the string "reason_code" appears proved only that I had
    # typed it. Ask the model what it actually returns.
    import inspect
    from engine.ufc import model as M
    ret = inspect.getsource(M.run_card)
    ret = ret[ret.rindex("return {"):]
    assert '"pass_list": passes' in ret, ret[:200]
    assert 'out.get("pass_list"' in body, "the breakdown reads the wrong key"
    # and the records it groups on carry the field it groups by
    assert '"reason_code"' in inspect.getsource(M), "no reason_code is set"


def test_the_breakdown_names_the_bouts_it_is_talking_about():
    """A count of data gaps is not a to-do list; the names are. The first
    version guessed `fighter`/`bout` — neither of which the model writes —
    and printed "?" for every row, which is the one part of the line you
    cannot act on without."""
    import inspect
    from engine.ufc import model as M
    src = open(os.path.join(ROOT, "ufc_build.py"), encoding="utf-8").read()
    i = src.index("if args.why:")
    body = src[i:src.index('if __name__ ==', i)]
    # The field the model actually sets on every pass record.
    ev = inspect.getsource(M.evaluate_fight)
    assert '"fight": f"{name_a} vs {name_b}"' in ev, ev[:200]
    assert body.count("p.get('fight'") >= 2, "the rows are still unnamed"
    assert "'fighter'" not in body and "'bout'" not in body, \
        "guessed field names are back"


def test_the_data_gaps_are_listed_not_just_counted():
    """no_dossier and no_data are the two the model cannot price through,
    and they are the only ones a person can actually go and fix."""
    src = open(os.path.join(ROOT, "ufc_build.py"), encoding="utf-8").read()
    i = src.index("if args.why:")
    body = src[i:src.index('if __name__ ==', i)]
    assert '"no_dossier", "no_data"' in body, \
        "the fixable passes are not singled out"


# --- the empty-cache trap that produced two blank cards ----------------------
def test_an_empty_cached_event_list_is_a_miss_not_an_answer():
    """THE BUG, measured 2026-08-08. `cache_only` serves a cached copy at ANY
    age and only raises when the file is ABSENT — so an empty list comes back
    happily forever. A thirty-day-old empty file was served without complaint.

    For a sport with a continuous season that is harmless. For UFC it is
    fatal: between cards this endpoint legitimately returns [], that [] is
    cached, every later read is cache_only and never goes to the wire, so
    `card_fighters` finds nobody, the auto-drafter returns early, no dossier
    is ever written — and when a card finally is priced, every bout hits
    "no dossier, no bet".

    Same knot `refresh_ufc` untied for the BUILD, left tied on the event
    list. The endpoint is FREE, so trying the wire costs nothing."""
    import os
    import pathlib
    import tempfile
    import time
    from engine.sources import oddsapi

    real_dir, real_req = oddsapi.CACHE_DIR, oddsapi._request
    oddsapi.CACHE_DIR = pathlib.Path(tempfile.mkdtemp())
    stale = oddsapi.CACHE_DIR / "odds_events_ufc.json"
    stale.write_text("[]")
    os.utime(stale, (time.time() - 86400 * 30,) * 2)
    seen = []

    def fake(url, name, ttl=300, timeout=30, cache_only=False):
        seen.append("cache" if cache_only else "wire")
        if cache_only:
            return real_req(url, name, ttl=ttl, cache_only=True)
        return [{"id": "1", "home_team": "A", "away_team": "B"}], oddsapi.Quota()

    oddsapi._request = fake
    try:
        got = oddsapi.list_events("k", sport="ufc", cache_only=True)
    finally:
        oddsapi.CACHE_DIR, oddsapi._request = real_dir, real_req
    assert got, "a stale empty event list is still being served as an answer"
    assert seen == ["cache", "wire"], seen


def test_a_cache_with_events_in_it_still_costs_no_request():
    """The fallback must not turn every read into a wire call. A caller
    asking for cache_only is asking not to spend, and a populated cache is
    a real answer."""
    import pathlib
    import tempfile
    from engine.sources import oddsapi

    real_dir, real_req = oddsapi.CACHE_DIR, oddsapi._request
    oddsapi.CACHE_DIR = pathlib.Path(tempfile.mkdtemp())
    (oddsapi.CACHE_DIR / "odds_events_ufc.json").write_text(
        '[{"id": "9", "home_team": "X", "away_team": "Y"}]')
    seen = []

    def fake(url, name, ttl=300, timeout=30, cache_only=False):
        seen.append("cache" if cache_only else "wire")
        return real_req(url, name, ttl=ttl, cache_only=cache_only)

    oddsapi._request = fake
    try:
        got = oddsapi.list_events("k", sport="ufc", cache_only=True)
    finally:
        oddsapi.CACHE_DIR, oddsapi._request = real_dir, real_req
    assert len(got) == 1
    assert seen == ["cache"], f"went to the wire on a good cache: {seen}"


def test_offline_still_answers_with_an_empty_card():
    """The fallback must not become a new way for the build to raise."""
    import pathlib
    import tempfile
    from engine.sources import oddsapi

    real_dir, real_req = oddsapi.CACHE_DIR, oddsapi._request
    oddsapi.CACHE_DIR = pathlib.Path(tempfile.mkdtemp())

    def dead(url, name, ttl=300, timeout=30, cache_only=False):
        raise oddsapi.OddsAPIError("offline")

    oddsapi._request = dead
    try:
        assert oddsapi.list_events("k", sport="ufc", cache_only=True) == []
    finally:
        oddsapi.CACHE_DIR, oddsapi._request = real_dir, real_req


def test_the_clamp_kills_are_named_too():
    """MEASURED ON THE 2026-08-08 CARD: 3 gate, 2 clamp_kill, 1 no_data, 1
    no_dossier. The gated bouts were named by the near-miss section and
    the data gaps by the section above; the two clamp kills were the only
    passes on the card with nothing but a tally.

    They are the ones most worth naming. A clamp kill is the model
    claiming a bigger edge than the humility clamp will let it act on,
    which is either the best read on the card or a dossier that is wrong
    about somebody — opposite problems, invisible from the number 2."""
    src = open(os.path.join(ROOT, "ufc_build.py"), encoding="utf-8").read()
    i = src.index("if args.why:")
    body = src[i:src.index('if __name__ ==', i)]
    assert '"clamp_kill"' in body, "clamp kills are still only counted"
    j = body.index('== "clamp_kill"')
    assert "p.get('fight'" in body[j:j + 400], "named by count, not by name"
    assert "p.get('why'" in body[j:j + 400], "the clamp's reason is dropped"


def test_the_clamp_kill_reason_code_is_the_one_the_model_writes():
    """The `--why` block has now twice read a key next to the one that
    exists. Ask the model rather than the memory."""
    import inspect
    from engine.ufc import model as M
    ev = inspect.getsource(M.evaluate_fight)
    assert '"reason_code": "clamp_kill"' in ev, ev[:200]


def test_a_clamp_kill_carries_a_reason_a_person_can_read():
    """Naming a bout and then printing an empty line under it is the same
    "?" bug in a different costume."""
    import inspect
    from engine.ufc import model as M
    ev = inspect.getsource(M.evaluate_fight)
    i = ev.index('"reason_code": "clamp_kill"')
    assert '"why": clamp_note' in ev[i:i + 200], ev[i:i + 200]


# --- the skip list, and why it has to be resettable --------------------------
def test_a_name_espn_could_not_find_can_be_retried_on_demand():
    """The 24-hour skip is load-bearing — an unfindable name at the front
    of a card used to eat the launcher's whole per-tick budget every
    cycle. But the reason a name lands there is sometimes OURS.

    Carlos Diego Ferreira went on that list because our loose matcher only
    worked when ESPN carried the longer name. With the matcher fixed he
    would still have sat there unqueried until tomorrow, and the card was
    tonight."""
    import ufc_dossiers
    assert hasattr(ufc_dossiers, "forget_unfound")
    src = open(os.path.join(ROOT, "ufc_dossiers.py"), encoding="utf-8").read()
    assert '"--retry-unfound"' in src
    i = src.index("if args.retry_unfound:")
    assert "forget_unfound()" in src[i:i + 400]


def test_forgetting_the_skip_list_keeps_every_dossier():
    """It clears the skip list, not the book. Wiping drafted fighters
    would turn a one-line convenience into half an hour of refetching —
    and, on a card night, into no dossiers at all."""
    import json, tempfile, pathlib
    import ufc_dossiers
    book = {"_readme": "x",
            "_unfound": {"Carlos Diego Ferreira": {"attempts": 3}},
            "Diego Lopes": {"name": "Diego Lopes", "ufc_fights": 8}}
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "ufc_dossiers.json"
        p.write_text(json.dumps(book))
        orig = ufc_dossiers.DOSSIERS
        ufc_dossiers.DOSSIERS = p
        try:
            forgotten = ufc_dossiers.forget_unfound()
            after = json.loads(p.read_text())
        finally:
            ufc_dossiers.DOSSIERS = orig
    assert forgotten == ["Carlos Diego Ferreira"]
    assert after["_unfound"] == {}
    assert after["Diego Lopes"]["ufc_fights"] == 8, "it ate a real dossier"
    assert after["_readme"] == "x"


def test_forgetting_an_empty_skip_list_is_not_an_error():
    """Run on a clean book it must say nothing happened, not crash — this
    is a thing typed at 6pm on a card night."""
    import json, tempfile, pathlib
    import ufc_dossiers
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "ufc_dossiers.json"
        p.write_text(json.dumps({"_readme": "x"}))
        orig = ufc_dossiers.DOSSIERS
        ufc_dossiers.DOSSIERS = p
        try:
            assert ufc_dossiers.forget_unfound() == []
        finally:
            ufc_dossiers.DOSSIERS = orig


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
