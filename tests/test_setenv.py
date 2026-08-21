"""`deploy/setenv.sh` — the script that exists because a runbook lied.

On 2026-08-21 the go-live page said "sudo nano /etc/qellys/env" and then
showed the lines to add. Every one of them was pasted into the bash
prompt instead. Bash read `STRIPE_SECRET_KEY=sk_test_...` as a variable
assignment, set it in that one SSH session, and did nothing else — the
service reads the FILE. So `--stripe` reported five things missing, the
webhook URL line was run as a command ("No such file or directory"), and
one pasted value was the literal placeholder from the docs.

Nothing broke. Nothing worked. An editor step in the middle of a list of
commands is a trap, and the fix was to remove the step rather than to
write the instruction more loudly.

What is tested here is the part that makes the script worth trusting:
that it refuses the specific wrong values somebody will actually paste,
that a second run replaces rather than appends, and that it never prints
a secret.

    python3 tests/test_setenv.py
"""

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "deploy", "setenv.sh")


def run(*args, env_file=None):
    env = dict(os.environ, QB_ENV_FILE=env_file)
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True,
                          text=True, env=env, timeout=60)


class Env:
    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="qb-env-")
        self.path = os.path.join(self.dir, "env")
        return self

    def __exit__(self, *a):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def read(self):
        if not os.path.isfile(self.path):
            return ""
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()


def test_the_script_is_executable_and_has_a_shebang():
    assert os.access(SCRIPT, os.X_OK), \
        "setenv.sh is not executable, so `sudo ./deploy/setenv.sh` fails"
    with open(SCRIPT, encoding="utf-8") as fh:
        assert fh.readline().startswith("#!"), "no shebang"


def test_a_placeholder_from_the_docs_is_refused():
    """THE ONE THAT HAPPENED. `sk_test_...` was pasted verbatim. Without
    this it would be written to the file and Stripe would answer 401 with
    a message about authentication that says nothing about the cause."""
    with Env() as e:
        got = run("STRIPE_SECRET_KEY", "sk_test_...", env_file=e.path)
        assert got.returncode != 0
        assert "placeholder" in got.stderr
        assert e.read() == "", "the placeholder was written anyway"


def test_the_wrong_stripe_string_in_the_right_slot_is_refused():
    """Every one of these is a real mix-up with an identical-looking
    value: the API key where the webhook secret goes, the product id
    where the price id goes, a test key that reads as live."""
    with Env() as e:
        for key, bad, why in (
                ("STRIPE_SECRET_KEY", "whsec_abc", "webhook secret as the key"),
                ("STRIPE_WEBHOOK_SECRET", "sk_test_abc", "API key as the secret"),
                ("STRIPE_PRICE_MONTHLY", "prod_abc", "product id as the price"),
                ("QB_SITE_URL", "qellysbook.com", "no scheme"),
                ("QB_DISCORD_INVITE", "https://example.com/x", "not an invite"),
        ):
            got = run(key, bad, env_file=e.path)
            assert got.returncode != 0, f"{why} was accepted"
        assert e.read() == ""


def test_the_right_values_are_accepted():
    with Env() as e:
        for key, good in (
                ("STRIPE_SECRET_KEY", "sk_test_abcdef"),
                ("STRIPE_WEBHOOK_SECRET", "whsec_abcdef"),
                ("STRIPE_PRICE_MONTHLY", "price_abcdef"),
                ("QB_SITE_URL", "https://qellysbook.com"),
                ("QB_DISCORD_INVITE", "https://discord.gg/abc"),
                ("QB_CODES", "USFARATHANE:12:100"),
                ("QB_PAYWALL", "1"),
        ):
            got = run(key, good, env_file=e.path)
            assert got.returncode == 0, f"{key} refused {good}: {got.stderr}"
            assert f"{key}={good}" in e.read()


def test_running_it_twice_replaces_rather_than_appends():
    """Two lines for one key is the worst outcome: the file looks right,
    the last one silently wins, and which one that is depends on the
    order they were added."""
    with Env() as e:
        run("STRIPE_SECRET_KEY", "sk_test_first", env_file=e.path)
        run("STRIPE_SECRET_KEY", "sk_test_second", env_file=e.path)
        body = e.read()
        assert body.count("STRIPE_SECRET_KEY=") == 1, body
        assert "sk_test_second" in body and "sk_test_first" not in body


def test_a_value_with_slashes_survives_intact():
    """A URL and a key both contain characters sed would interpret. The
    replacement is literal for exactly this reason."""
    with Env() as e:
        url = "https://discord.gg/aB3/x&y"
        run("QB_DISCORD_INVITE", "https://discord.gg/first", env_file=e.path)
        run("QB_DISCORD_INVITE", url, env_file=e.path)
        assert f"QB_DISCORD_INVITE={url}" in e.read()


def test_show_never_prints_a_value():
    """A key in a terminal is a key in a scrollback buffer, a screenshot
    and a support thread."""
    with Env() as e:
        run("STRIPE_SECRET_KEY", "sk_test_SECRETVALUE", env_file=e.path)
        got = run("--show", env_file=e.path)
        assert got.returncode == 0
        assert "SECRETVALUE" not in got.stdout, got.stdout
        assert "STRIPE_SECRET_KEY" in got.stdout
        assert "set" in got.stdout


def test_show_calls_out_a_placeholder_that_got_through():
    """If one was ever written by hand, --show is where it is noticed."""
    with Env() as e:
        with open(e.path, "w", encoding="utf-8") as fh:
            fh.write("STRIPE_SECRET_KEY=sk_test_...\n")
        got = run("--show", env_file=e.path)
        assert "PLACEHOLDER" in got.stdout.upper()


def test_unset_removes_the_line():
    with Env() as e:
        run("QB_PAYWALL", "1", env_file=e.path)
        run("QB_CODES", "X:1:1", env_file=e.path)
        got = run("--unset", "QB_PAYWALL", env_file=e.path)
        assert got.returncode == 0
        body = e.read()
        assert "QB_PAYWALL" not in body
        assert "QB_CODES=X:1:1" in body, "unset took a neighbour with it"


def test_the_file_is_not_world_readable():
    """It holds the key that can charge cards."""
    with Env() as e:
        run("STRIPE_SECRET_KEY", "sk_test_abc", env_file=e.path)
        mode = os.stat(e.path).st_mode & 0o777
        assert mode == 0o600, f"mode is {oct(mode)}, should be 0600"


def test_a_secret_can_be_given_without_putting_it_in_history():
    """With no value argument it prompts and reads silently. That is the
    difference between a key in ~/.bash_history and a key nowhere."""
    with open(SCRIPT, encoding="utf-8") as fh:
        src = fh.read()
    assert "read -rsp" in src, \
        "the prompt no longer reads silently, so the value is echoed"
    assert "$# -ge 2" in src, "there is no prompt path any more"


def test_the_runbook_has_no_editor_step_left():
    """The trap was an editor step inside a list of commands. If one comes
    back, this is where it gets caught."""
    with open(os.path.join(ROOT, "docs", "GOLIVE.md"), encoding="utf-8") as fh:
        doc = fh.read()
    assert "nano" not in doc, \
        "GOLIVE.md asks the reader to open an editor again"
    assert "setenv.sh" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
