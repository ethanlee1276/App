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
    body = js[i:i + 1800]
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
