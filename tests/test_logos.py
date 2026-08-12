"""Real team logos, and the fallback that makes them safe to add.

Ethan, 2026-08-08: "i want to include having real team logos and shit like
that for all sports."

VERIFIED BEFORE BUILT, which is the only reason this is not another guess.
`assets.py --probe`, run from Ethan's machine, returned HTTP 200 image/png
for all five league keys — nfl, mlb, nba, wnba and ncaa. The container this
was written in cannot reach a.espncdn.com at all (tunnel 403), so nothing
here could have been checked from the inside.

THE COMBINER PATH, NOT THE RAW ONE. `/combiner/i?img=…&w=&h=` resizes
server-side and the saving is large: measured, the raw 500px NFL mark is
40,228 bytes against 11,537 for the combiner, MLB 20,024 against 7,739. A
board draws twenty marks, so it is ~800KB of logo against ~230KB.

THE FALLBACK IS THE POINT. ESPN spells some teams differently from us, and
the map is recalled for everything the probe did not individually test. So
the <img> is layered OVER the monogram chip that shipped before, with
`onerror="this.remove()"`. A wrong abbreviation, a dead CDN, or a laptop on
a train all land on exactly the previous behaviour — verified by rendering
this whole board with the host blocked, where all 14 MLB marks and all 17
NFL marks came back as chips at identical size with no reflow.

`assets.py --audit` fetches the logo for EVERY abbreviation in every
teams_*.js and names the misses, so the map gets corrected from a
measurement instead of from memory.

Run directly: `python3 tests/test_logos.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _js():
    return _read("web", "js", "visuals.js")


# --- the URL ----------------------------------------------------------------
def test_every_sport_the_site_renders_has_a_league_key():
    """A missing key is not a broken image — `logoUrl` returns "" and no
    <img> is emitted at all — but it is a whole sport silently keeping the
    old chip, which nobody notices on a board they do not open."""
    js = _js()
    m = re.search(r"const ESPN_LEAGUE = \{([^}]*)\}", js)
    assert m, "the league map is gone"
    for sport in ("nfl", "cfb", "mlb", "nba", "wnba"):
        assert re.search(rf"\b{sport}:", m.group(1)), sport


def test_it_asks_the_combiner_for_a_sized_image():
    """Measured: raw 500px NFL mark 40,228 bytes, combiner 11,537. Twenty
    marks a board makes that ~800KB against ~230KB."""
    js = _js()
    i = js.index("function logoUrl(")
    body = js[i:i + 700]
    assert "combiner/i?img=" in body, "back to the raw path — 3.5x the bytes"
    assert "&w=" in body and "&h=" in body, "no size asked for"


def test_the_url_is_built_from_the_abbreviation_not_hardcoded():
    js = _js()
    i = js.index("function logoUrl(")
    body = js[i:i + 700]
    assert "encodeURIComponent" in body, "an abbreviation goes into a URL unescaped"


def test_the_known_spelling_differences_are_mapped():
    """The ones ESPN genuinely spells differently. WAS/wsh and LA/lar are
    the two this repo already had to handle for live scores."""
    js = _js()
    m = re.search(r"const ESPN_ABBR = \{(.*?)\n\};", js, re.S)
    assert m, "the abbreviation map is gone"
    body = m.group(1)
    assert re.search(r'WAS:\s*"wsh"', body), "NFL Washington will 404"
    assert re.search(r'LA:\s*"lar"', body), "NFL Rams will 404"
    assert re.search(r'CWS:\s*"chw"', body), "White Sox will 404"


# --- the fallback, which is what makes it safe ------------------------------
def test_the_monogram_is_still_drawn_underneath():
    """Not replaced — layered under. This is the whole safety argument: a
    wrong abbreviation or no network is the OLD behaviour, not a hole."""
    js = _js()
    i = js.index("function teamMark(")
    # To the end of the function, not a fixed window: a comment added above
    # the markup used to push `${img}` out of the slice and fail this.
    body = js[i:js.index("\n/* ", i)]
    assert "team-mark-wrap" in body
    assert "<svg" in body and "team-mark" in body, "the chip is gone"
    assert body.index("<svg") < body.index("${img}"), \
        "the image must sit OVER the monogram, or the chip covers the logo"


def test_a_failed_image_removes_itself():
    js = _js()
    i = js.index("function teamMark(")
    body = js[i:i + 1800]
    assert 'onerror="this.remove()"' in body, (
        "without this a broken logo leaves a browser's own broken-image "
        "glyph sitting on every card")


def test_the_image_is_lazy_and_async():
    """Twenty of these on a board, most below the fold."""
    js = _js()
    body = js[js.index("function teamMark("):][:1800]
    assert 'loading="lazy"' in body
    assert 'decoding="async"' in body


def test_the_wrapper_reserves_the_space():
    """The fallback and the logo must occupy identical space, or a row
    reflows the moment a logo arrives — and they arrive one at a time."""
    js = _js()
    body = js[js.index("function teamMark("):][:1800]
    assert "width:${size}px;height:${size}px" in body
    css = _read("web", "css", "styles.css")
    i = css.index(".team-mark-wrap {")
    block = css[i:i + 400]
    assert "position: relative" in block
    assert "inline-block" in block


def test_the_logo_is_contained_not_cropped():
    """These marks are not one aspect ratio — a Boston B is near-square and
    a Texans bull is wide. `cover` would cut the part people recognise."""
    # ALL occurrences, not the first. That selector appears twice — once in
    # a shared rule with `.team-mark` for position/inset, and once alone
    # for object-fit — and `.index()` found the shared one, reporting a
    # rule that is present as missing.
    css = _read("web", "css", "styles.css")
    blocks = [css[m.end():m.end() + 200] for m in
              re.finditer(r"\.team-mark-wrap > \.team-logo \{", css)]
    assert blocks, "the logo rule is gone"
    assert any("object-fit: contain" in b for b in blocks), blocks


def test_the_alt_text_is_on_the_wrapper_not_the_image():
    """An empty alt on the <img> plus a labelled wrapper reads the team
    once. Both labelled reads it twice; neither reads it as nothing."""
    js = _js()
    body = js[js.index("function teamMark("):][:1800]
    assert 'alt=""' in body
    assert 'role="img"' in body and "aria-label" in body


# --- the audit that replaces my memory --------------------------------------
def test_the_audit_reads_the_map_out_of_the_javascript():
    """Two copies of the abbreviation map would drift, and the drift would
    be invisible — a miss renders the old chip. The audit parses the real
    one instead of keeping a second."""
    import assets
    m = assets._js_abbr_map()
    assert m, "the audit can no longer read ESPN_ABBR out of visuals.js"
    assert m.get("nfl", {}).get("WAS") == "wsh"
    assert m.get("wnba", {}).get("CON") == "conn"


def test_the_audit_covers_every_team_the_site_can_render():
    """Keyed off the same teams_*.js the page reads, so it cannot check a
    list that has fallen behind the site."""
    import assets
    for sport, want in (("nfl", 30), ("mlb", 30), ("nba", 30), ("wnba", 12)):
        got = assets._teams_for(sport)
        assert len(got) >= want, f"{sport}: only found {len(got)} teams"


def test_the_measurement_sits_next_to_the_decision_it_made():
    """The combiner path costs an extra query string and looks like
    over-engineering without the number beside it. It lives in visuals.js,
    where the URL is built — not in the probe, which only reported it."""
    js = _js()
    i = js.index("function logoUrl(")
    why = js[max(0, i - 1600):i]
    assert "40,228" in why or "40228" in why, \
        "the byte measurement that chose the combiner path is gone"
    assert "11,537" in why or "11537" in why



# --- player faces ------------------------------------------------------------
def test_the_face_is_requested_at_the_size_it_is_drawn():
    """THE MEASUREMENT THAT FORCED THIS. nflverse ships full resolution, and
    full resolution is 3,797,822 / 3,145,446 / 4,307,894 bytes — measured on
    Ethan's machine for the first three roster players. Twelve props drawn
    at 40px would pull ~45MB. That is not a polish feature, it is a stall."""
    js = _js()
    assert "function facePreview(" in js
    i = js.index("function facePreview(")
    body = js[i:i + 700]
    assert "/image/upload/" in body, "no Cloudinary transform is applied"
    assert "px * 2" in body, "no retina multiple — a 40px avatar wants 80px"


def test_a_wrong_transform_falls_back_to_the_original_not_to_nothing():
    """The transform is a GUESS — which Cloudinary transforms this account
    permits is what `assets.py --probe` asks. So it is built to fail open:
    the first error swaps to the untransformed URL that is known to work,
    and only a second error reveals the initials underneath.

    Wrong transform costs one 404 and a heavy image, which is exactly the
    behaviour that shipped before. There is no path where this is worse."""
    js = _js()
    i = js.index("function playerAvatar(")
    body = js[i:i + 1600]
    assert "data-full" in body, "the original URL is not carried as a fallback"
    assert "this.src=this.dataset.full" in body, "no swap to the original"
    assert "this.remove()" in body, "no final give-up to the initials avatar"


def test_a_non_cloudinary_url_is_left_alone():
    """Other sports will not be nfl.com. A transform spliced into an ESPN
    path would 404 every face on those boards."""
    js = _js()
    i = js.index("function facePreview(")
    body = js[i:i + 700]
    assert "indexOf(marker) < 0" in body and "return url" in body


def test_an_espn_face_is_resized_the_way_an_espn_logo_is():
    """MEASURED ON ETHAN'S MACHINE, 2026-08-08: one ESPN full headshot is
    196,283 bytes. The NBA and WNBA boards take that href straight out of
    the box score — correct, and a dozen props is ~2.4MB of face drawn at
    56px. The combiner is the same server-side resize the logos already use
    (40,228 against 11,537 there), so faces go through it too."""
    js = _js()
    assert "function espnFacePreview(" in js
    i = js.index("function espnFacePreview(")
    body = js[i:i + 700]
    assert "combiner/i?img=" in body
    assert "&w=" in body and "&h=" in body


def test_the_face_combiner_request_matches_the_call_that_was_verified():
    """`logoUrl` passes the path in raw, slashes and all — that is the form
    that answered 200. Percent-encoding the whole path is the obvious tidy
    version and would encode the slashes with it."""
    js = _js()
    body = js[js.index("function espnFacePreview("):][:700]
    assert "encodeURIComponent(path)" not in body, (
        "the path is being escaped; the verified call does not escape it")
    assert "img=${path}" in body


def test_an_already_sized_face_is_not_sized_twice():
    """Nesting a combiner URL inside a combiner URL is a 404 that would
    look exactly like 'ESPN has no photo for this player'."""
    js = _js()
    body = js[js.index("function espnFacePreview("):][:700]
    assert '"/combiner/"' in body


def test_the_untransformed_espn_href_is_still_the_fallback():
    """The combiner serving /i/headshots the way it serves /i/teamlogos is
    NOT verified — the probe only measured the logo path. So the resized URL
    is a guess, and it fails onto the raw href, which the probe DID verify
    at 196,283 bytes, and then onto the initials chip."""
    js = _js()
    i = js.index("function playerAvatar(")
    body = js[i:i + 1600]
    assert "data-full" in body and "this.src=this.dataset.full" in body


def test_a_cloudinary_face_still_takes_the_cloudinary_path():
    """NFL and MLB faces are Cloudinary; only ESPN's go to the combiner.
    Routing everything one way would break the other two sports."""
    js = _js()
    i = js.index("function facePreview(")
    body = js[i:i + 700]
    assert body.index("a.espncdn.com") < body.index('"/image/upload/"'), \
        "the ESPN branch must be checked before the Cloudinary marker"
    assert "FACE_TRANSFORM" in body


def test_the_roster_carries_a_face_for_the_current_season():
    """Weekly stats do not exist until games are played, so on a Week 1
    board they are empty. The roster is the only current-season source.

    HONEST SCOPE: this changed nothing on today's board — measured, Week 1
    2026 was already 293/293, because the carry only builds props for
    players who HAVE prior-season stats, so every one of them is in last
    season's file by construction. It is insurance for rookies and
    practice-squad promotions, who have a photo and no stat line."""
    from engine.sources import nflverse as nv
    idx = nv.roster_index(2026)
    if not idx:
        return                       # no cached roster in this checkout
    have = sum(1 for v in idx.values() if v.get("headshot"))
    assert have > len(idx) * 0.8, f"only {have}/{len(idx)} roster faces"


def test_the_stats_source_still_wins_over_the_roster():
    """Order matters: this season's stats, then the roster, then last
    season. A face from a played game is the most current thing available."""
    import inspect
    from engine.sources import nflverse as nv
    src = inspect.getsource(nv.build_slate)
    i = src.index("headshots: dict[str, str] = {}")
    block = src[i:i + 900]
    assert block.index("for r in list(stats)") < block.index("for name, row in roster.items()")
    assert block.index("for name, row in roster.items()") < block.index("prior_stats")


# --- which mark a bet wears -------------------------------------------------
def test_a_bet_wears_the_mark_of_whatever_it_belongs_to():
    """Ethan, 2026-08-12: "head shots or team logos next to the props
    depending on if they are a player prop or team prop. if its a game
    total or something, we can show the sports logo."

    One decider, `betMark`, so the picks list, the Game Lines room and the
    open-bet tracker can never disagree about who a bet belongs to. The
    rule: a side (moneyline / spread / team total) wears its team, a game
    total wears the league, anything else is a player prop and wears the
    face."""
    js = _read("web", "js", "app.js")
    i = js.index("function betMark(")
    body = js[i:i + 900]
    assert 'market === "total"' in body and "leagueMark(" in body, \
        "a game total must wear the league mark"
    assert "TEAM_SIDE_MARKETS" in body and "teamMark(" in body, \
        "a team side must wear its team logo"
    assert "playerAvatar(" in body, "a player prop must wear the face"
    m = re.search(r"const TEAM_SIDE_MARKETS = new Set\(\[(.*?)\]\)", js, re.S)
    assert m, "the team-side market list is gone"
    for market in ("moneyline", "spread", "team_total"):
        assert market in m.group(1), market
    # "total_bases" is a PROP and must never be read as the game total.
    assert '"total"' in body and "total_bases" not in body


def test_every_board_reads_that_one_decider():
    """Three surfaces show bets: the recommended list, the Game Lines
    room, and the open-bet tracker. Each must call betMark rather than
    deciding for itself — the previous inline version drifted the moment
    a fourth market appeared."""
    js = _read("web", "js", "app.js")
    assert js.count("betMark(") >= 5, "a board is deciding its own mark again"
    # The tracker's rows and the picks list both carry the identity slot.
    assert js.count('class="pick-id"') >= 2


def test_the_tracker_never_prints_a_journal_key_as_a_name():
    """A game total is journaled under "AWAY@HOME" and a team market under
    an abbreviation. Printing either verbatim reads as a name — which is
    what the row did before the marks landed beside it."""
    js = _read("web", "js", "app.js")
    i = js.index("const betTxt = (r) =>")
    body = js[i:i + 1200]
    assert 'r.market === "total"' in body, "the game total still prints its key"
    assert "market_label" in body
    assert body.count("teamName(r.player)") >= 3, \
        "team markets must resolve their abbreviation to a name"


def test_the_league_mark_falls_back_to_a_drawn_chip():
    """Same contract as the team logos: the image is layered OVER a drawn
    monogram, so a dead CDN lands on a chip rather than a gap. No emoji —
    the drawn-art module is emoji-free and its suite enforces it."""
    js = _js()
    i = js.index("function leagueMark(")
    body = js[i:i + 1400]
    assert "onerror=" in body and "this.remove()" in body, "no fallback"
    assert "<svg" in body, "nothing underneath the image"
    assert "combiner/i?img=" in body, "raw path — 3.5x the bytes"



# --- the drawing is a fallback, not a backdrop -------------------------------
def test_the_drawn_chip_leaves_when_a_real_image_lands():
    """Ethan, 2026-08-12, circling the picks list and the live board: "the
    logos overlap whatever is underneath the logos ... the team logos are
    behind the head shots."

    Every logo and headshot these CDNs serve is a transparent PNG, and the
    drawn art sat under them PERMANENTLY — so the monogram's diagonal
    band, colour block and abbreviation showed straight through the
    artwork, and the helmet showed through every face. The image's own
    onload is the fix: the drawing is a fallback, so it must be visible in
    exactly the case it exists for, and gone in the other."""
    js = _js()
    for fn_name in ("function teamMark(", "function leagueMark("):
        i = js.index(fn_name)
        body = js[i:i + 1600]
        assert "onload=" in body and "art-on" in body, fn_name
        assert "onerror=" in body, f"{fn_name} lost its fallback"
    av = js[js.index("function playerAvatar("):]
    av = av[:av.index("\n  const t = team(")]
    assert "onload=" in av and "art-on" in av, "the helmet still shows through faces"

    css = _read("web", "css", "styles.css")
    assert ".team-mark-wrap.art-on > .team-mark { display: none; }" in css
    assert ".avatar-stack.art-on > .avatar { display: none; }" in css
    # A cut-out face with the helmet gone needs ground, or it floats.
    assert ".avatar-stack.art-on { background:" in css


def test_a_dead_cdn_still_lands_on_the_drawn_chip():
    """The half that must NOT change: onerror removes only the image, and
    nothing marks art-on, so an unreachable host renders exactly the chip
    that shipped before real logos existed."""
    js = _js()
    i = js.index("function teamMark(")
    body = js[i:i + 1600]
    assert 'onerror="this.remove()"' in body
    # art-on is set by onload ALONE — never at build time, or the chip
    # would be hidden under an image that never arrives.
    assert "classList.add('art-on')" in body
    assert body.count("art-on") == 1, "art-on must come from onload only"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
