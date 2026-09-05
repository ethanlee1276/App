"""Settings that stick, and the banner that says what you missed.

Ethan, 2026-08-25: *"Settings that stick: odds format (−110 vs 1.91),
units vs dollars, timezone, favorite teams first, which sports show in
nav"* and *"Welcome back — 3 of your bets settled since last night:
+1.8u. That one banner makes it feel like the site knows you."*

The three things that can quietly break here:

  * a preference that reaches SOME of the board. A price format applied
    to the card but not the table is worse than no setting at all, so
    the formatter has to be the only way a price is printed;
  * a section named on one side of the sync and not the other, which
    syncs in one direction and reads as a device that will not remember
    you;
  * a banner that counts wrong on its first run — with no previous
    snapshot every settled bet in the book looks new.

Run directly: `python3 tests/test_settings.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import accounts                                   # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
CSS = _read("web", "css", "styles.css")
SERVER = _read("server.py")


# --- the sync contract -------------------------------------------------------

def test_both_sides_of_the_sync_name_the_same_sections():
    """server.PROFILE_SECTIONS is the merge contract and
    accounts.SECTIONS is what the database will store. A section in one
    and not the other syncs in one direction only."""
    m = re.search(r"PROFILE_SECTIONS = \(([^)]*)\)", SERVER)
    assert m
    listed = set(re.findall(r'"([a-z]+)"', m.group(1)))
    assert listed == set(accounts.SECTIONS), \
        f"the two section lists disagree: {listed ^ set(accounts.SECTIONS)}"
    assert "settings" in listed


def test_settings_ride_the_same_last_writer_wins_rule():
    """No new endpoint, no new merge. Two devices disagreeing about a
    display preference should settle on whichever was set most recently,
    and there is nothing in here that can be lost the way a journaled bet
    can."""
    i = SERVER.index("def merge_sections")
    body = SERVER[i:SERVER.index("\ndef _public", i)]
    assert 'if key == "mybets"' in body
    assert "settings" not in body, \
        "settings has grown a merge rule of its own"


def test_an_untouched_account_never_pushes_defaults_over_a_real_copy():
    """A device that has never opened settings must not overwrite the
    phone's choices with a blob of house defaults."""
    i = APP.index("function acctGather()")
    body = APP[i:APP.index("\n}", i)]
    assert "if (ts.settings)" in body


def test_an_adopted_setting_redraws_the_whole_page():
    """Half-applied is the failure mode: an adopted odds format that only
    reached the next render sits wrong until something else moves."""
    i = APP.index('} else if (name === "settings") {')
    body = APP[i:i + 400]
    assert "settingsAdopt(d)" in body and "renderAll()" in body


def test_adopting_never_re_stamps():
    """The echo-loop rule every other section already keeps: adopting the
    server's copy must not look like a local change and push straight
    back."""
    i = APP.index("function settingsAdopt(data)")
    body = APP[i:APP.index("\n}", i)]
    assert "acctTouch" not in body


# --- the formatters ----------------------------------------------------------

def test_one_place_prints_a_price():
    """34 inline `${r.odds > 0 ? "+" : ""}${r.odds}` spellings is 34
    places a format setting could fail to reach."""
    i = APP.index("function oddsTxt(v)")
    body = APP[i:APP.index("\n}", i)]
    assert "1 + n / 100" in body and "1 + 100 / Math.abs(n)" in body
    assert 'settings().odds !== "decimal"' in body
    # The price surfaces all go through it: cards, tables, the game page,
    # the moneyline strip.
    for site in ('<span class="ml-odds">${oddsTxt(r.odds)}</span>',
                 '<span class="ml-odds">${oddsTxt(b.odds)}</span>',
                 '<td class="num">${oddsTxt(b.odds)}</td>',
                 '<td class="num">${escapeHtml(oddsTxt(b.odds))}</td>'):
        assert site in APP, f"a price surface still formats its own: {site}"
    # ON A LINE THAT RENDERS, not anywhere in the file. oddsTxt's own
    # comment quotes the spelling it replaced, and a naive search for it
    # fails on the sentence explaining why it is gone — the third time a
    # test in this repo has caught its own documentation.
    inline = [ln for ln in APP.split("\n")
              if '> 0 ? "+" : ""' in ln and ".odds" in ln
              and any(tag in ln for tag in ("<span", "<td", "<b "))]
    assert not inline, f"a price is still formatted inline: {inline[:2]}"


def test_dollars_with_no_bankroll_falls_back_to_units():
    """The setting says what you want to read, not what we are able to
    compute — and `$NaN` is what the alternative prints."""
    i = APP.index("function stakeText(units)")
    body = APP[i:APP.index("\n}", i)]
    assert "if (ud <= 0) return u;" in body
    assert 'how === "units"' in body and 'how === "dollars"' in body


def test_the_stake_default_is_exactly_what_the_site_did_before():
    """A settings pass that changes what everybody sees the moment it
    ships is a redesign wearing a preferences panel."""
    i = APP.index("const SETTINGS_DEFAULTS = {")
    body = APP[i:APP.index("};", i)]
    assert 'stake: "both"' in body
    assert 'odds: "american"' in body
    assert "leagues: []" in body, "an empty list has to mean every league"


def test_every_clock_reads_in_one_zone():
    """A site about first pitch and kickoff that prints some times in the
    browser's zone and some in a chosen one makes people do arithmetic to
    know whether they have missed a game."""
    assert "function tzTime(d, o)" in APP
    # One survivor by design: tzTime itself.
    assert APP.count("toLocaleTimeString") == 1, \
        "a clock is formatting itself outside tzTime"
    i = APP.index("function formatKickoff(kick)")
    body = APP[i:APP.index("\n}", i)]
    assert "tzTime(d)" in body


# --- favourites and the nav --------------------------------------------------

def test_favourites_reorder_the_schedule_and_never_the_ranking():
    """THE ONE THAT MATTERS. The picks are ordered by edge and that order
    IS the product: floating somebody's teams up a ranked board would say
    the model likes them more than it does."""
    i = APP.index("const fav = (g) => (isFavTeam(g.home)")
    body = APP[i:i + 400]
    assert "games.sort" in body, "the favourite sort is not on the games strip"
    for ranked in ("function renderRecommended", "function renderTopPicks"):
        j = APP.index(ranked)
        chunk = APP[j:j + 3000]
        assert "isFavTeam" not in chunk, \
            f"{ranked} reorders a ranked board by favourites"


def test_a_team_is_followed_per_league():
    """CIN is the Bengals and the Reds. A favourites list that mixed them
    would star the wrong games all baseball season."""
    i = APP.index("function isFavTeam(abbr, sport)")
    body = APP[i:APP.index("\n}", i)]
    assert "`${sport || state.sport}:${abbr}`" in body


def test_the_league_you_are_looking_at_is_never_hidden():
    """Landing on /cfb from a shared link with college football unticked
    would otherwise show a college board with no college chip lit — the
    page and its own navigation disagreeing about where you are."""
    i = APP.index("function applyNavLeagues()")
    body = APP[i:APP.index("\n}", i)]
    assert "code === state.sport" in body
    assert "!want.length" in body, "an empty list has to mean every league"


# --- the welcome-back banner -------------------------------------------------

def test_the_first_run_is_silent():
    """With no previous snapshot every settled bet in the book looks new,
    and "47 of your bets settled since last night" on a first visit is a
    lie with a number on it."""
    i = APP.index("function welcomeBackScan()")
    body = APP[i:APP.index("\n}\n", i)]
    assert "if (!prev || typeof prev !== \"object\") return _welcomeBack;" in body


def test_a_settle_is_announced_once():
    """The snapshot is written when the banner is COMPUTED, not when it
    is shown — otherwise a reader who never scrolls to the board is told
    the same news every load."""
    i = APP.index("function welcomeBackScan()")
    body = APP[i:APP.index("\n}\n", i)]
    write = body.index("localStorage.setItem(BETS_SEEN_KEY")
    count = body.index("_welcomeBack.n += 1")
    assert write < count
    assert "if (_welcomeBack !== null) return _welcomeBack;" in body


def test_it_diffs_the_results_rather_than_trusting_a_stamp():
    """A settled-at stamp only works if every writer sets it, and there
    are several — the result buttons, a CSV import, and the account sync
    adopting a grading done on another device. That last one is the whole
    point of accounts and the one most likely to be missed."""
    i = APP.index("function welcomeBackScan()")
    body = APP[i:APP.index("\n}\n", i)]
    assert "final(prev[id])" in body and "!final(now[id])" in body
    assert "settled_at" not in APP


def test_a_tab_flip_is_not_a_return():
    """The same 30-minute rule the board's own "since you last looked"
    line keeps, so the two banners cannot disagree about what counts as
    having been away."""
    i = APP.index("function welcomeBackHTML()")
    body = APP[i:APP.index("\n}", i)]
    assert "30 * 60000" in body
    assert "_welcomeDismissed" in body, "no way to dismiss it"


def test_the_banner_rides_the_allowlisted_zone_with_the_other_one():
    """test_board_order allows exactly the ids it names above the picks.
    Neither banner claims a new slot."""
    i = APP.index("async function renderDayCard()")
    body = APP[i:APP.index("\nfunction renderRecommended", i)]
    assert "welcomeBackHTML() + freshBannerHTML(d)" in body
    assert ".wb-banner" in CSS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
