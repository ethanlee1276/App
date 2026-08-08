"""The key checker, and the one property that makes it safe to paste.

Ethan, 2026-08-08: "can u make sure we have all the keys in there. there
should be the anthropics key, 2 odds api keys, and a cfb key."

I cannot check `secrets.local` — it is gitignored, so it exists only on the
machine that has it, which is the whole point of the file. What can be built
is the thing that answers the question from his side in one command.

THE PROPERTY THAT MATTERS MORE THAN ANY OTHER HERE: it must be impossible
for this to print a key. Not the value, not a prefix, not the last four
characters. The output is meant to be pasted into a chat, and anything in a
chat log should be treated as exposed — so "it only prints a few characters"
is not a defence, it is a smaller leak. The test below feeds it distinctive
fake keys and asserts no fragment of any of them reaches stdout.

AND IT MUST NOT SPEND ANYTHING. The Odds API's `/sports` is documented as
free and returns the remaining balance in a header, so one request both
proves the key works and reports what is left. Anthropic is checked for
PRESENCE ONLY — every call to that API costs money, and a key validation
that bills you is not a diagnostic.

Run directly: `python3 tests/test_keycheck.py`
"""

import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import keycheck

#: Distinctive enough that any leak is unambiguous, and shaped like the real
#: things so a prefix-printing bug would still be caught.
FAKE = {
    "ODDS_API_KEY": "oddsAAAAAAAAAAAAAAAAAAAAAAAAAAAA1111",
    "ODDS_API_KEY_2": "oddsBBBBBBBBBBBBBBBBBBBBBBBBBBBB2222",
    "CFBD_API_KEY": "cfbdCCCCCCCCCCCCCCCCCCCCCCCCCCCC3333",
    "ANTHROPIC_API_KEY": "sk-ant-DDDDDDDDDDDDDDDDDDDDDDDD4444",
}


def _run(env=None, secrets_exists=False):
    """Run the checker with fake keys and no network, capturing stdout."""
    env = FAKE if env is None else env
    saved = {k: os.environ.get(k) for k in FAKE}
    real_file = keycheck.SECRETS
    real_load = keycheck.load_local_secrets
    for k in FAKE:
        os.environ.pop(k, None)
    os.environ.update(env)
    keycheck.load_local_secrets = lambda *a, **k: None
    if not secrets_exists:                 # don't read the real machine's file
        keycheck.SECRETS = keycheck.ROOT / "secrets.local.does-not-exist"
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            keycheck.main()
    finally:
        keycheck.SECRETS = real_file
        keycheck.load_local_secrets = real_load
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    return buf.getvalue()


# --- the property that makes it safe to paste --------------------------------
def test_no_key_value_reaches_the_output():
    out = _run()
    for name, value in FAKE.items():
        assert value not in out, f"{name} printed in full"


def test_not_even_a_fragment_of_a_key_reaches_the_output():
    """"Only the last four characters" is a smaller leak, not a defence —
    and four characters plus a provider name is a real head start."""
    out = _run()
    for name, value in FAKE.items():
        for n in (4, 6, 8):
            assert value[:n] not in out, f"{name}: first {n} chars printed"
            assert value[-n:] not in out, f"{name}: last {n} chars printed"


def test_a_key_a_provider_echoes_back_at_us_is_taken_out_again():
    """The one leak path the tests above cannot see. A failed request prints
    the response body, and a provider is entitled to say "invalid API key:
    abc123" in it — putting the key in the output through a route no other
    check here covers."""
    assert keycheck._scrub("invalid API key: " + FAKE["ODDS_API_KEY"],
                           FAKE["ODDS_API_KEY"]) == "invalid API key: <key>"


def test_scrubbing_does_not_redact_something_that_is_not_a_key():
    """An empty or one-character value would otherwise match everywhere and
    turn a useful error message into a row of placeholders."""
    for junk in ("", " ", "x", "abc"):
        assert keycheck._scrub("a plain message", junk) == "a plain message"


def test_the_length_is_reported_because_it_is_useful_and_harmless():
    """A key of the wrong length is the commonest paste error, and the
    number tells you that without telling you anything else."""
    out = _run()
    assert f"{len(FAKE['CFBD_API_KEY'])} chars" in out, out


def test_a_pasted_key_with_a_space_in_it_is_called_out():
    """The failure that looks like a dead key and is not."""
    env = dict(FAKE, CFBD_API_KEY="cfbd AAAA BBBB")
    out = _run(env)
    assert "CONTAINS A SPACE" in out
    assert "cfbd AAAA BBBB" not in out, "the broken value was echoed"


# --- it must not cost anything -----------------------------------------------
def test_anthropic_is_never_called():
    """Every request to that API costs money. A validation that bills you is
    not a diagnostic — presence is all this checks."""
    import inspect
    src = inspect.getsource(keycheck._check_anthropic)
    # The property is "makes no network call", not "avoids a word" — the
    # first version of this grepped for "request" and tripped over the prose
    # explaining why there is no request.
    for call in ("urlopen", "urllib", "http.client", "socket"):
        assert call not in src, f"{call} in the Anthropic check: {src}"
    assert "NOT CALLED" in _run()


def test_the_odds_check_uses_the_endpoint_that_is_free():
    """/sports does not count against quota and returns the balance in a
    header, so proving the key works and reading what is left are one
    request. Any priced endpoint here would burn credits on a health check."""
    import inspect
    src = inspect.getsource(keycheck._check_odds)
    assert "/sports?apiKey=" in src
    assert "odds?" not in src and "/events" not in src


def test_the_balance_is_read_from_the_reply():
    import inspect
    src = inspect.getsource(keycheck._check_odds)
    assert "x-requests-remaining" in src


# --- what it tells you when something is missing -----------------------------
def test_a_missing_key_names_the_exact_variable_to_set():
    """The failure this exists for is a key set under a name the code does
    not read. "Missing" without the name is the same dead end."""
    out = _run({})
    for name in ("ODDS_API_KEY", "CFBD_API_KEY", "ANTHROPIC_API_KEY"):
        assert name in out, name


def test_it_says_which_names_the_odds_ring_was_found_under():
    """Two plans is the whole point of the ring, and a second key under a
    name the ring does not read looks exactly like having one plan."""
    out = _run()
    assert "ODDS_API_KEY_2" in out
    assert "2 key(s) in the ring" in out


def test_one_odds_key_reads_as_one_not_as_two():
    out = _run({"ODDS_API_KEY": FAKE["ODDS_API_KEY"]})
    assert "1 key(s) in the ring" in out


def test_a_missing_secrets_file_says_so_rather_than_reporting_four_misses():
    """Four "missing" lines with no explanation sends you checking four
    names when the file itself is not there."""
    out = _run({})
    assert "NOT FOUND" in out


def test_the_closing_note_states_that_nothing_was_printed():
    """The output is meant to be pasted. Saying so is what makes someone
    comfortable pasting it, and it is a claim the tests above enforce."""
    assert "No key value is printed above" in _run()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
