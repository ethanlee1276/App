"""The site is live for anyone. It must not hand them the operator's job.

Ethan, 2026-08-23, with a card circled on qellysbook.com that told the
reader to register a developer app, paste two values into a config file
and restart the server:

    "lets get all the little things like this telling ME what to do off
    the website since this website is live for anyone to use."

THE FAULT IS NOT UNTIDINESS. Every one of these strings was written when
the only reader was the person who could act on it — a laptop, a terminal
beside it, one user. They kept rendering after the site went public, so a
visitor's empty state was somebody else's to-do list, complete with the
names of the settings the server reads and the commands that change them.
It reads as broken, it is useless to the person seeing it, and it names
internals to an audience that has no business with them.

The rule this file pins: **rendered copy may say what is true and what
happens next; it may not issue an instruction the reader cannot carry
out.** "This fills once the season's stats are ingested" is fine — it
tells a reader what they are waiting on. "Run `python3 ingest.py nfl`
once" is not.

Operator instructions still exist, and should: they print in the terminal
during a build, where the person who can act is standing. What changed is
which audience gets them.

SCOPED TO WHAT RENDERS. Source comments are not covered — this repo
documents itself heavily and those comments are how the next reader
understands the code. Only string literals that reach a screen are
checked, and the scanner below says how it tells the difference.

Run directly: `python3 tests/test_no_operator_copy.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Things that only mean something to whoever runs the server. A rendered
#: string containing one of these is, by construction, addressed to the
#: wrong person.
FORBIDDEN = (
    "python3 ",
    "launch.py",
    "ingest.py",
    "LAUNCH.md",
    "secrets.local",
    "YAHOO_CLIENT",
    "ANTHROPIC_API_KEY",
    "QB_ALLOW_INSECURE_LOGIN",
    "tailscale",
    "Restart the server",
    "restart the server",
    "backtest_lab.py",
    "hypotheses.py",
    "standings_build.py",
    "rosters_build.py",
    "ufc_dossiers.py",
    "generate.py",
)


def _js():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def _strip_comments(src: str) -> str:
    """Everything that is NOT a // or /* */ comment.

    Deliberately crude in the safe direction: it can leave a comment in
    (a false ALARM, which a human then reads and dismisses) but it cannot
    remove a rendered string, which would be a false all-clear. A regex
    that tried to be clever about `//` inside a string literal would fail
    the other way — every URL in the file contains one.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    out = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        # Only whole-line comments, and the continuation lines of a block
        # comment, are dropped. A trailing `//` after code is left alone
        # rather than risk cutting a string that contains one.
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        out.append(line)
    return "\n".join(out)


def test_no_rendered_string_tells_the_reader_to_run_something():
    code = _strip_comments(_js())
    hits = []
    for i, line in enumerate(code.split("\n"), start=1):
        for bad in FORBIDDEN:
            if bad in line:
                hits.append((bad, line.strip()[:90]))
    assert not hits, ("operator instructions are rendering to the public:\n"
                      + "\n".join(f"  {b} → {t}" for b, t in hits))


def test_the_markup_does_not_carry_them_either():
    html = open(os.path.join(ROOT, "web", "index.html"),
                encoding="utf-8").read()
    # HTML comments are documentation, same as the JS ones, and are
    # dropped for the same reason.
    body = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    for bad in FORBIDDEN:
        assert bad not in body, f"{bad} renders in the markup"


def test_the_yahoo_setup_card_does_not_render_to_a_visitor():
    """The one Ethan circled. A panel explaining how to register a
    developer app is a setup step, not a feature — a person who cannot
    act on an instruction should not be shown one, so until Yahoo is
    connectable the panel does not exist."""
    js = _js()
    i = js.index("if (!s.app_registered) {")
    block = js[i:js.index("if (!s.connected) {", i)]
    assert 'zone.innerHTML = "";' in block, "the setup card is back"
    assert "developer.yahoo.com" not in js, (
        "the registration walkthrough is still in the file")


def test_the_build_payloads_carry_no_commands():
    """A shell line put into JSON is a shell line put onto the page. This
    is the leak that is easiest to reintroduce, because it happens one
    layer away from anything that looks like copy."""
    for name in ("nba_build.py",):
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        # Only what goes into an `out[...]` payload dict, not the prints.
        for m in re.finditer(r'out\["[a-z_]+"\] = \{', src):
            block = src[m.start():src.index("}", m.start())]
            assert "python3" not in block, (
                f"{name} puts a command in a payload the site serves")


def test_the_instructions_still_exist_where_they_are_useful():
    """This was a MOVE, not a deletion. An operator who breaks a build
    still needs to be told what to run — in the terminal, which no
    visitor is reading."""
    build = open(os.path.join(ROOT, "nba_build.py"), encoding="utf-8").read()
    assert 'print(f"    Fix: python3 ingest.py' in build


def test_the_replacements_say_what_is_true_rather_than_going_quiet():
    """The lazy version of this fix is deleting the sentence and leaving a
    blank. An empty state that explains nothing is a worse page than one
    that over-explains, so each of these still tells a reader what they
    are waiting on."""
    js = _js()
    for phrase in (
        "This fills once the season",           # fantasy usage
        "have not been built yet",              # standings / rosters
        "fills on the refresh",                 # the history gap
        "rebuilds on a refresh cycle",          # the unbuilt slate
        "fills again when it recovers",         # the meme feeds
    ):
        assert phrase in js, f"the empty state lost its explanation: {phrase}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
