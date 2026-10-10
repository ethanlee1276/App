"""A college table under one heading is a wall, and it said nothing.

Measured in Chromium at 390x844 on 2026-09-10, walking the site the way
Ethan asked ("look at every single page … think of just your average
user"): the CFB standings page is 14,735px — 17.5 phone screens — and
10,430px of that is ONE card holding 188 teams under a single "League"
heading. That is 71% of the page in one block, 12.4 phone screens.

It is one group because `cfb_conferences()` came back empty, and it came
back empty silently. The function's own docstring records it failing this
way once before — it read a filename no builder has ever written, and
`except: return {}` swallowed that for as long as it lasted. The filename
was fixed. The FIELD names never were: it wants `home_conference` or
`home_conf` on each game in `web/data/cfb.json`, and the board writes
neither (`away, date, home, kickoff, label, live, park_name, spread,
total, weather, weather_checked`). So it returns `{}` on every build, and
every team lands in the `rec.conference or "League"` bucket.

`_live_table`, forty lines below it in the same file, states the rule
this file now keeps: "Failure is a STRING, not a silence."

WHAT THIS PINS is the reporting, not the grouping. The grouping cannot be
fixed here: there is no conference source on this box to fix it against —
`cfb.json`'s `teams` map is empty, the games table has no conference
column, and the league's own feed is refused by this environment's
network policy. Naming the symptom in the build log is what stops it
hiding for a third stretch.

Run directly: `python3 tests/test_standings_one_group.py`
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(ROOT, "standings_build.py"), encoding="utf-8").read()


def _nocomments(src):
    return re.sub(r"(?m)^\s*#.*$", "", src)


def test_a_one_group_college_table_is_reported():
    """The condition is the symptom a reader meets, not the input that
    caused it."""
    code = _nocomments(SRC)
    assert 'sport == "cfb" and len(b.get("groups") or []) < 2' in code, \
        "nothing notices that college standings came out as one group"


def test_it_warns_on_the_symptom_and_not_the_empty_map():
    """When the league's own feed answers, it carries each team's
    conference itself and the map is only an override — so an empty map
    is harmless there. Warning on the map would print on good builds,
    and a warning that cries wolf is one nobody reads."""
    code = _nocomments(SRC)
    assert 'if sport == "cfb" and not b.get("conf_map")' not in code, \
        "the warning fires on the input again, so a good build warns too"


def test_the_map_size_reaches_the_caller():
    """`conf_seen` is counted where the map is built and carried out on
    the payload, so the log can say how many teams it covered rather than
    only that something was wrong."""
    code = _nocomments(SRC)
    assert "conf_seen = len(confs or {})" in code
    assert 'table["conf_map"] = conf_seen' in code, \
        "the count is taken and then thrown away"


def test_the_message_names_where_to_look():
    """A warning that does not say which file and which field is a
    warning somebody has to re-derive. This one has been re-derived
    twice already."""
    i = SRC.index("college standings are ONE group")
    msg = SRC[i:i + 700]
    assert "cfb.json" in msg, "the message does not name the file it reads"
    assert "home_conference" in msg, "the message does not name the field"
    assert "conference map covered" in msg


def test_the_stamp_is_college_only():
    """Every other sport groups by division from the feed and has never
    had this problem; a `conf_map` on an NBA payload would be a field
    that means nothing."""
    code = _nocomments(SRC)
    i = code.index('table["conf_map"]')
    assert 'if sport == "cfb":' in code[max(0, i - 120):i], \
        "the conference stamp is written for every sport"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:
                fails += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{ran - fails} of {ran} tests passed.")
    sys.exit(1 if fails else 0)
