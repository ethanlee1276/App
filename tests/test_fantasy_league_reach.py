"""Your own start calendar was built, and it was not on the Calendar tab.

Ethan, 2026-09-10: "I want too be able to to sync my sleeper league, then
the calendar will show which players from MY league I should [start] that
day like I keep saying. … I wanna be able too link accounts and leagues
and see all the leagues and players and other peoples rosters on the
site."

THE FIRST HALF WAS ALREADY BUILT. `ffRosterCalendarHTML` shipped on
2026-09-09 and does exactly what he describes — the same calendar, scoped
to his roster. It drew inside `renderLeagueDesk`, which mounts into the
"Around the league" subtab, under the camp report and the offseason moves
and the draft kit. So a reader who opened Fantasy → Calendar got the
LEAGUE-WIDE board and no sign his own existed, which is why he asked
again with "like I keep saying".

Built, unreachable, asked for twice: the same shape as the touchdown
doors earlier this week, and the reason this file pins the LOCATION as
hard as it pins the arithmetic. A feature nobody can find has not
shipped.

THE SECOND HALF WAS COMPUTED AND THROWN AWAY. Both league-desk handlers
fetch every roster in the league — they have to, to build the other side
of the trade generator — and then returned none of them. "Other people's
rosters" was a value the server already had.

Run directly: `python3 tests/test_fantasy_league_reach.py`
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _windows                                             # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
SRV = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()


def _nocomments(src):
    """The code without its prose.

    These assertions are about what the page RENDERS, and a comment that
    quotes a retired sentence in order to explain why it was retired is
    not a render. Both of the assertions below first failed against the
    very notes that document them.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", src)


CODE = None                                  # filled on first use


def _code():
    global CODE
    if CODE is None:
        CODE = _nocomments(APP)
    return CODE


def _fn(name, src=None):
    """The body of one JS function, by name."""
    body = src if src is not None else APP
    i = body.index(f"function {name}(")
    return body[i:body.index("\n}", i) + 2]


# --- the calendar is where a reader looks for a calendar --------------------
def test_the_calendar_tab_carries_your_own_roster_first():
    """The whole report in one assertion. Before this the roster
    calendar was on a different subtab entirely."""
    i = APP.index('["days", "Calendar"')
    tab = APP[i:APP.index('["mock", "Mock draft"', i)]
    assert 'id="ffcal-mine"' in tab, "the Calendar tab has no place for yours"
    assert tab.index('id="ffcal-mine"') < tab.index("ffCalendarHTML(d)"), \
        "the league-wide calendar is still drawn above your own"


def test_the_desk_paints_it_there_and_not_inline():
    """One copy. The desk still BUILDS it — that is the function all
    three platforms come through, and it is what knows whose roster it
    is — but it no longer draws it where it was built."""
    desk = APP[APP.index("async function renderLeagueDesk("):]
    desk = desk[:desk.index("\n/* ----")]
    assert "paintMyCalendar(ffRosterCalendarHTML(" in desk
    assert "host.innerHTML = ffH2HHTML(d)" in desk
    inner = desk[desk.index("host.innerHTML = ffH2HHTML(d)"):]
    assert "ffRosterCalendarHTML" not in inner.split(";")[0], \
        "the calendar is still being drawn into the desk as well"


def test_every_way_out_of_the_desk_leaves_the_calendar_saying_something():
    """A blank rectangle where a calendar should be is the failure this
    whole file is about. Each exit either paints a real one or leaves a
    sentence — and the clear at the top is what makes the third and
    fourth exits safe without a line each."""
    desk = APP[APP.index("async function renderLeagueDesk("):]
    desk = desk[:desk.index("\n/* ----")]
    # EACH EXIT BY ITS OWN BLOCK, not a count of calls. A count only
    # says "enough of them exist somewhere"; when a fifth paint was added
    # (the loading line, 2026-09-10) `>= 4` went on passing with the
    # unlinked reader's paint deleted. Brace-matched, so the check cannot
    # expire the way a character window does.
    nolg = _windows.block(desk, "if (!leagueId) {")
    assert "paintMyCalendar(" in nolg, "an unlinked reader gets a blank tab"
    nome = _windows.until(desk, "if (!d.has_me) {", "\n  _ffDesk = d;")
    assert "paintMyCalendar(" in nome, "the wrong-league exit says nothing"
    assert desk.count("paintMyCalendar(") >= 4, desk.count("paintMyCalendar(")
    # THE CLEAR RIDES WITH `_ffDesk = null`, which is the line that
    # already exists to stop the previous league answering for this one.
    # Anchored there rather than "before the first return": the first
    # return is `if (!host) return`, which fires when there is no desk on
    # the page at all and has nothing to clear.
    # A STATEMENT, not the call text anywhere nearby: the first cut of
    # this assertion passed happily against `0 && paintMyCalendar(...)`.
    #
    # SLICED TO THE NEXT STATEMENT, not to 500 characters. The count was
    # a guess about how much comment would ever sit between the clear and
    # the paint, and it expired on 2026-09-10 when that comment grew to
    # record why the line there is a LOADING sentence rather than a
    # warning. `_windows.until` is the house answer to exactly this.
    clear = _windows.until(desk, "_ffDesk = null;", "if (!leagueId)")
    assert re.search(r"\n\s*paintMyCalendar\(", clear), \
        "the calendar is not cleared alongside the desk it is drawn from"


def test_a_reader_with_no_league_is_told_what_to_do():
    fn = _fn("ffCalMinePromptHTML")
    assert "switchView('account'" in fn, "no way to the form from here"
    assert "password" in fn, "the reader is not told what it costs him"


def test_the_prompt_says_reading_rather_than_link_it_when_one_is_linked():
    """A linked reader waiting on a fetch must not be told to link a
    league — that reads as the link having failed."""
    fn = _fn("ffCalMinePromptHTML")
    assert 'localStorage.getItem("ff_user")' in fn
    assert 'localStorage.getItem("ff_espn_league")' in fn
    assert fn.index("Reading your roster") < fn.index("Link a league")


def test_the_painter_is_the_only_writer_and_survives_a_missing_host():
    fn = _fn("paintMyCalendar")
    assert 'getElementById("ffcal-mine")' in fn
    # THE GUARD, however it is spelled. This pinned `if (host)`, which
    # became `if (!host) return;` when the painter grew the tentative
    # flag — the same guard, inverted, and the assertion could not tell.
    assert re.search(r"if \(!?host\)", fn), \
        "a page with no calendar tab would throw"
    # One writer: nothing else assigns to that element.
    assert APP.count('getElementById("ffcal-mine")') == 1


# --- a stand-in says what it is standing in for -----------------------------
def test_the_line_before_the_fetch_reads_as_loading_not_as_a_failure():
    """Ethan, 2026-09-10, photographing the Calendar tab: "It's still not
    showing the calendars in fantasy curated to the users specific draft
    lineup and league. It also says this" — over a warning triangle
    reading "Your own start calendar needs a league that answers".

    Nothing had failed. That sentence was painted BEFORE the fetch it
    describes, and it stood for the whole of a request that reads a
    league's scoring, its rosters and Sleeper's five-megabyte player
    dump. It was the loading state wearing an error's clothes."""
    code = _code()
    desk = code[code.index("async function renderLeagueDesk("):]
    first = _windows.until(desk, "_ffDesk = null;", "if (!leagueId)")
    assert 'class="loading"' in first, "the pre-fetch line is not a loading line"
    assert "needs a league that answers" not in code, \
        "the sentence that reads as a failure before anything failed"
    assert 'icon("warn")' not in first, "a warning triangle before the fetch"


def test_no_exit_sends_the_reader_to_another_tab_for_the_reason():
    """A reader on the Calendar tab was told to go read a message on
    Around the league, because the reason was written into the desk's own
    host and the calendar only got a pointer to it."""
    code = _code()
    desk = code[code.index("async function renderLeagueDesk("):
                code.index("function ffH2HHTML(")]
    assert "see the message on" not in desk, "the pointer is back"
    # THE CATCH IS THE EXIT THAT HAD NONE — three of the four said what
    # was missing and the fetch failure returned without repainting.
    catch = _windows.until(desk, "} catch (e) {", "\n  if (!d.has_me)")
    assert "paintMyCalendar(" in catch, "the fetch failure says nothing here"
    assert "escapeHtml(why)" in catch, "it does not name the reason"


def test_a_stand_in_never_overwrites_a_real_calendar():
    """Sleeper and ESPN each start their own desk and both draw this one
    calendar, finishing in whatever order the network decides. An ESPN
    league with no roster of his could land after Sleeper's real calendar
    and replace it with an apology."""
    fn = _fn("paintMyCalendar")
    assert "if (tentative && _ffCalReal) return;" in fn
    assert "_ffCalReal = !tentative;" in fn
    # THE RESET IS ON THE ELEMENT'S IDENTITY, which is exactly the event
    # that matters: a fresh renderFantasy rebuilt the page, so nothing is
    # on screen and the loading line should show again. No caller has to
    # remember to clear it.
    assert "host !== _ffCalHost" in fn


def test_only_the_real_calendar_is_final():
    """Every stand-in passes the flag; the one paint that does not is the
    calendar itself. A failure marked final would lock the tab."""
    desk = APP[APP.index("async function renderLeagueDesk("):]
    desk = desk[:desk.index("\n/* ----")]
    calls = re.findall(r"paintMyCalendar\((.*?)\);", desk, re.S)
    assert len(calls) >= 4, calls
    final = [c for c in calls if not c.rstrip().endswith("true")]
    assert len(final) == 1, [c[:60] for c in final]
    assert "ffRosterCalendarHTML(" in final[0]


# --- every roster in the league ---------------------------------------------
def test_both_platforms_publish_every_roster_through_one_formatter():
    """Two desks formatting one list two ways is how the ESPN reader
    ends up with a subtly different page."""
    assert "def _ff_team_rows(" in SRV
    assert SRV.count('out["teams"] = _ff_team_rows(') == 2, \
        "one of the two platforms is not publishing its rosters"


def test_the_rosters_cost_no_extra_call():
    """The point: they were already fetched for the trade generator.
    The Sleeper handler's own `rivals` is the same object handed to
    `fantasy_trade.generate` a few lines above."""
    i = SRV.index("def _league_desk(self, query: dict):")
    body = SRV[i:SRV.index("\n    def ", i + 10)]
    assert "fantasy_trade.generate(mine, rivals" in body
    assert "_ff_team_rows(rivals, mine" in body
    # SAME OBJECT, and that is the whole claim: `rivals` is built once
    # from the rosters fetched at the top of the handler, handed to the
    # trade generator, and now also published. Nothing re-reads it.
    #
    # NOT "no grab() appears below this line" — the handler legitimately
    # fetches the NFL state and this week's matchups further down for the
    # head-to-head block, and asserting otherwise would have failed for a
    # reason that has nothing to do with rosters.
    assert body.index("rivals[owner.get(") < body.index("_ff_team_rows(rivals")
    assert body.count("rivals = ") <= 1, "rivals is built more than once"


def test_the_position_table_is_a_module_constant():
    """A handler method calling a name that is not global is a
    NameError, swallowed by the handler's `except Exception`, and a 503
    — this file has paid for that lesson once already
    (`_squad_or_empty`, 2026-09-10)."""
    assert re.search(r"^_FF_POS_AT = \{", SRV, re.M), \
        "the ordering table is not at module level"


def test_your_own_team_leads_the_list_and_says_so():
    i = SRV.index("def _ff_team_rows(")
    fn = SRV[i:SRV.index("\ndef ", i + 10)] if "\ndef " in SRV[i + 10:] else SRV[i:]
    assert 'out.insert(0,' in fn and '"mine": True' in fn


def test_starters_sort_above_the_bench():
    i = SRV.index("def _ff_team_rows(")
    fn = SRV[i:i + 1400]
    assert 'not r.get("starting")' in fn, \
        "the roster is not ordered by who is actually playing"


def test_every_name_on_a_rivals_roster_opens_the_same_dossier():
    """A rival's roster is only useful if you can ask about the players
    on it — what he is starting against you, and what he is sitting."""
    fn = _fn("ffTeamsHTML")
    assert 'data-dossier="${escapeAttr(r.player)}"' in fn
    assert 'role="button"' in fn and 'tabindex="0"' in fn


def test_the_teams_list_is_drawn_on_the_desk():
    desk = APP[APP.index("async function renderLeagueDesk("):]
    assert "ffTeamsHTML(d)" in desk[:desk.index("\n/* ----")]


# --- all the leagues, not one behind a menu ---------------------------------
def test_every_league_is_visible_without_opening_a_menu():
    fn = _fn("renderSleeperPanel")
    assert "ffleagues" in fn, "the leagues are still only in a select"
    assert "data-league=" in fn


def test_both_league_controls_take_the_same_path():
    """The select and the chips write the same key and re-render the
    same way — three steps in two places is two places to drift."""
    fn = _fn("renderSleeperPanel")
    assert "const pickLeague = (id) =>" in fn
    assert fn.count('localStorage.setItem("ff_league"') == 1, \
        "a second place remembers which league is selected"
    assert "pickLeague(sel.value)" in fn
    assert "pickLeague(b.dataset.league)" in fn


def test_one_league_draws_no_chip_row():
    """A row of one chip is furniture, not information."""
    fn = _fn("renderSleeperPanel")
    assert "ctx.leagues.length < 2" in fn


def test_the_new_surfaces_have_their_styles():
    for sel in (".ffteams", ".ffteam-row", ".ffleagues", ".ffleague"):
        assert sel + " " in CSS or sel + "," in CSS or sel + "{" in CSS, sel


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails
          else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
