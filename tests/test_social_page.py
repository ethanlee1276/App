"""Social, the page: Ethan's render, and one profile for the whole site.

Ethan, 2026-10-07, with a render of the page: "The social page looks
cluttered … Here is renders you must follow for the social page and
profile page. Also the account page on the feed page and the main account
page should be one page … it should all be one main profile for the
whole site."

These pin what the render asks for and what "one profile" means in the
code, so neither quietly drifts back:

  - the render's three columns: the Social nav (Post, Feed, Following,
    My Posts, Trending, Top Bettors, Tags, then the sports through UFC
    and soccer), the banner and the composer over the feed, and the rail
    (Trending Picks, Top Bettors with Win % / Units / Followers, Popular
    Sports, Community Stats, the Discord);
  - the banner is Ethan's own backdrop render (his crown and wordmark in
    the art, no athlete's likeness), the profile cover is that arena
    without the logo, and the tagline promises no wins;
  - the composer's tools are Parlay, Poll and Link; there is no Image
    tool, deliberately (uploads need moderation the site does not have);
  - ONE PROFILE: the Account page mounts the Social profile header, your
    own handle and the old #feed/edit both land on the Account page, and
    the top-bar chip, the sync strip, the chat avatar and the streak board
    all read the profile.

Run directly: `python3 tests/test_social_page.py`
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


SOC = _read("web", "js", "social.js")
CSS = _read("web", "css", "social.css")
APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")


def _fn(src, name):
    i = src.index(f"function {name}(")
    j = src.find("\n  function ", i + 10)
    k = src.find("\nfunction ", i + 10)
    ends = [x for x in (j, k) if x > 0]
    return src[i:min(ends)] if ends else src[i:]


# --- the render's layout ------------------------------------------------------

def test_the_nav_column_carries_the_renders_doors_and_sports():
    for door in ('"Feed"', '"Following"', '"My Posts"', '"Trending"', '"Top Bettors"', '"Tags"'):
        assert door in SOC, door
    for sport in ('["ufc", "UFC"]', '["soccer", "Soccer"]', '["wnba", "WNBA"]', '["nhl", "NHL"]'):
        assert sport in SOC, sport
    assert 'class="fd-postbtn"' in SOC and "<span>Post</span>" in SOC


def test_the_rail_is_the_renders_five_cards():
    rail = _fn(SOC, "railHTML")
    for card in ("trendCardHTML", "bettorsCardHTML", "Popular Sports", "statsCardHTML", "Join the Qellys Book Discord"):
        assert card in rail, card
    assert '"Win %"' in SOC and '"Units"' in SOC and '"Followers"' in SOC
    assert '["7", "7D"], ["30", "30D"], ["all", "All"]' in SOC
    assert "Trending Picks" in SOC and "View All" in SOC and "Community Stats" in SOC


def test_the_chips_lead_with_for_you_then_following_then_the_sports():
    chips = _fn(SOC, "chipsHTML")
    assert chips.index('"For You"') < chips.index('"Following"') < chips.index("SPORTS.map")


def test_three_columns_on_a_desktop_one_on_a_phone_measured_on_the_box():
    """Container queries on the Social box itself — the site's sidebar comes
    and goes, so the window's width is the wrong ruler — and they sit LAST
    in the sheet: the first cut put them above the rules they override and
    the phone tabs showed on a desktop."""
    assert "container: fd / inline-size" in CSS
    wide = CSS.index("@container fd (min-width: 1040px)")
    assert '"nav hero hero" "nav main rail"' in CSS[wide:wide + 400]
    assert wide > CSS.index(".fd-tabs {") and wide > CSS.index(".fd-mtrend {")


def test_the_banner_never_combines_aspect_ratio_with_a_minimum_height():
    """aspect-ratio + min-height turns the floor into a minimum WIDTH: a
    150px floor at 5:1 made the hero 750px wide and the phone page scrolled
    sideways. Fixed height on a phone, the 5:1 band from 800px."""
    rule = CSS[CSS.index(".fd-hero { position:"):]
    rule = rule[:rule.index("}")]
    assert "aspect-ratio" not in rule and "height: 150px" in rule and "min-width: 0" in rule
    assert "aspect-ratio: 5 / 1" in CSS[CSS.index("@container fd (min-width: 800px)"):]


# --- the banner and the composer ----------------------------------------------

def test_the_banner_is_ethans_backdrop_and_promises_no_wins():
    """Ethan, 2026-10-07, with a render of the backdrop he circled on the
    page render. The crown and the wordmark are IN his art, so the banner
    draws nothing over them — a second, drawn logo on top was the old
    banner's. Profile covers use the same arena with the logo cut out
    (cover.webp: his art's two sides, blended), so a person's name is
    never under a second Qellys Book."""
    for name, cap in (("banner.webp", 220_000), ("banner@900.webp", 80_000),
                      ("cover.webp", 140_000), ("cover@900.webp", 70_000)):
        path = os.path.join(ROOT, "web", "img", "social", name)
        assert os.path.exists(path), name
        assert os.path.getsize(path) < cap, f"{name} is {os.path.getsize(path)} bytes"
    hero = _fn(SOC, "heroInner")
    assert "img/social/banner.webp" in hero and 'alt="Qellys Book"' in hero
    assert "fd-word" not in hero and "CROWN" not in hero
    tag = re.search(r'class="fd-hero-tag">([^<]+)<', hero).group(1)
    assert "win" not in tag.lower(), tag
    assert "Post your plays" in tag
    head = _fn(SOC, "profileHeaderHTML")
    assert "img/social/cover@900.webp" in head and "banner" not in head


def test_the_composer_offers_parlay_poll_and_link_and_no_image():
    tools = _fn(SOC, "toolsHTML")
    for k in ('"parlay"', '"poll"', '"link"'):
        assert k in tools, k
    # No Image: an upload is a picture nobody screened, and the site has no
    # moderation service for pictures. Said in the report, not silently left out.
    assert "image" not in tools.lower()


def test_a_parlay_is_picked_off_todays_board_and_sent_as_rows_not_numbers():
    send = _fn(SOC, "send")
    assert 'api("post"' in send
    legs = send[send.index("legs: c.legs.map"):send.index("})) });")]
    assert "odds" not in legs and "book" not in legs and "links" not in legs
    assert "api(`legs?sport=" in SOC


def test_what_people_type_is_escaped_before_anything_becomes_a_link():
    rich = _fn(SOC, "rich")
    assert rich.index("escapeHtml(") < rich.index(".replace(")
    link = _fn(SOC, "linkHTML")
    assert 'href="${safeHref(p.link)}"' in link and "nofollow ugc" in link


# --- one profile for the whole site -------------------------------------------

def test_the_account_page_is_the_profile_page():
    fn = APP[APP.index("function renderAccount()"):]
    fn = fn[:fn.index("\n}\n")]
    assert '<div id="acct-prof" class="acct-prof"></div>' in fn
    assert "S.mountAccount(el, u)" in fn
    assert 'data-acct-tab="friends"' in fn and 'data-acct-tab="settings"' in fn
    assert "mountAccount" in SOC and "window.QBSocial = {" in SOC
    assert "profileHeaderHTML(p, { mine: true })" in SOC


def test_your_own_handle_and_the_old_edit_page_land_on_the_account_page():
    render = SOC[SOC.index("async function render(append)"):]
    assert 'if (kind === "edit") { window._acctEdit = true; switchView("account", true); return; }' in render
    assert 'if (isMe(arg)) { switchView("account", true); return; }' in render
    assert '"#feed/edit"' not in SOC


def test_the_site_draws_you_from_the_profile_everywhere():
    mark = APP[APP.index("function acctMark(u)"):]
    mark = mark[:mark.index("\n}\n")]
    assert "u.profile" in mark and "PF_TINT[" in mark
    assert "acctChipPaint();" in APP
    strip = APP[APP.index("function acctStripHTML()"):]
    assert "acctMark(u)" in strip[:600]
    chat = APP[APP.index("function msgMyAvatar()"):]
    assert "acctMark(u)" in chat[:400]
    # The screen behind the profile no longer draws a second identity disc.
    screen = APP[APP.index("function acctScreenHTML()"):]
    signed_in = screen[:screen.index("// Signed out.")]
    assert "acct-avatar" not in signed_in


def test_the_streak_board_plays_under_the_profile():
    assert 'id="stk-name-in"' not in APP
    assert "me && me.profile" in APP
    assert "Make your profile to appear on the board" in APP


def test_the_nav_calls_it_social():
    btn = HTML[HTML.index('data-view="feed"'):]
    btn = btn[:btn.index("</button>")]
    assert btn.rstrip().endswith("Social")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
            n += 1
    print(f"\n{n} tests passed.")
