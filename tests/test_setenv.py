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
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
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


def test_the_cli_tools_read_the_file_the_server_actually_uses():
    """THE ONE THAT WASTED AN EVENING.

    On the droplet the keys live in /etc/qellys/env and nowhere else —
    there is no secrets.local on that box. systemd reads it as
    `EnvironmentFile=` when it starts the SERVICE, and injects it into
    nothing else. So `python3 launch.py --stripe`, `--stripe-setup` and
    `--todo`, all of which are run by hand over ssh, saw an empty
    environment and reported five things missing that were correctly
    configured three inches away.

    The advice that report then gives — "put the key in the file" — is
    advice to redo the thing that already worked, which is how somebody
    ends up convinced the setup is broken when it is fine.
    """
    import importlib
    with Env() as e:
        with open(e.path, "w", encoding="utf-8") as fh:
            fh.write("STRIPE_SECRET_KEY=sk_test_fromthesystemfile\n")
        got = subprocess.run(
            [sys.executable, "-c",
             "from engine import secrets; secrets.load_local_secrets();"
             "import os; print(os.environ.get('STRIPE_SECRET_KEY',''))"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
            env=dict(os.environ, QB_ENV_FILE=e.path))
        assert "sk_test_fromthesystemfile" in got.stdout, (
            "the secrets loader does not read the production env file, so "
            "every CLI check reports config missing that is set: "
            + (got.stdout + got.stderr)[:400])


def test_the_real_environment_still_wins():
    """Additive only. The service already has these from systemd, and a
    file that could overwrite them would let a stale line on disk beat
    what the unit was actually started with."""
    with Env() as e:
        with open(e.path, "w", encoding="utf-8") as fh:
            fh.write("STRIPE_SECRET_KEY=sk_test_fromfile\n")
        got = subprocess.run(
            [sys.executable, "-c",
             "from engine import secrets; secrets.load_local_secrets();"
             "import os; print(os.environ.get('STRIPE_SECRET_KEY',''))"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
            env=dict(os.environ, QB_ENV_FILE=e.path,
                     STRIPE_SECRET_KEY="sk_test_fromenviron"))
        assert "sk_test_fromenviron" in got.stdout


def test_an_unreadable_env_file_is_a_quiet_miss_not_a_crash():
    """/etc/qellys/env is mode 600 and root-owned. A developer running a
    script as themselves gets a PermissionError, and that must not be a
    traceback in every tool that touches a key."""
    with Env() as e:
        with open(e.path, "w", encoding="utf-8") as fh:
            fh.write("STRIPE_SECRET_KEY=sk_test_x\n")
        os.chmod(e.path, 0o000)
        try:
            got = subprocess.run(
                [sys.executable, "-c",
                 "from engine import secrets; secrets.load_local_secrets();"
                 "print('survived')"],
                capture_output=True, text=True, cwd=ROOT, timeout=60,
                env=dict(os.environ, QB_ENV_FILE=e.path))
        finally:
            os.chmod(e.path, 0o600)
        # Running as root reads it anyway; either way it must not throw.
        assert "survived" in got.stdout, got.stderr[:400]


def test_the_wizard_exists_and_is_runnable():
    path = os.path.join(ROOT, "deploy", "golive.sh")
    assert os.path.isfile(path), "deploy/golive.sh is gone"
    assert os.access(path, os.X_OK), "golive.sh is not executable"
    got = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
    assert got.returncode == 0, "golive.sh has a syntax error: " + got.stderr


def test_the_wizard_refuses_to_run_without_a_terminal():
    """It is a conversation. Piped or from cron, every prompt returns
    immediately and it charges through eight steps answering nothing."""
    got = subprocess.run(["bash", os.path.join(ROOT, "deploy", "golive.sh")],
                         capture_output=True, text=True, stdin=subprocess.DEVNULL,
                         timeout=60, env=dict(os.environ, QB_ENV_FILE="/tmp/nope"))
    assert got.returncode != 0
    assert "terminal" in got.stdout.lower() + got.stderr.lower()


def test_the_wizard_cannot_loop_for_ever_on_a_bad_value():
    """The first version did. `setenv.sh` fails on a rejected value AND
    on end-of-input with the same code, so a closed stdin spun it at full
    speed printing "try again" until the terminal filled."""
    with open(os.path.join(ROOT, "deploy", "golive.sh"), encoding="utf-8") as fh:
        src = fh.read()
    assert "tries < 3" in src, "the retry loop has no cap again"
    assert "while true" not in src.split("ask()")[1].split("\n}")[0],         "ask() is an unbounded loop again"


def test_the_wizard_passes_the_env_file_through_sudo():
    """`sudo` strips the environment, so `QB_ENV_FILE=x sudo cmd` writes
    to /etc/qellys/env instead — fine in production and wrong everywhere
    else, including in a test, which is how it was found."""
    with open(os.path.join(ROOT, "deploy", "golive.sh"), encoding="utf-8") as fh:
        src = fh.read()
    assert 'env QB_ENV_FILE="$ENV_FILE"' in src
    # …and nothing calls setenv.sh past the helper.
    body = re.sub(r"(?m)^\s*#.*$", "", src)
    assert 'sudo "$SETENV"' not in body,         "a direct sudo call would lose the env override"


def test_the_wizard_writes_the_price_ids_rather_than_asking_for_them():
    """Transcribing three price ids is where a swapped pair comes from,
    and a swapped pair charges the wrong amount without failing."""
    with open(os.path.join(ROOT, "deploy", "golive.sh"), encoding="utf-8") as fh:
        src = fh.read()
    assert "--stripe-setup --print-env" in src
    for key in ("STRIPE_PRICE_MONTHLY", "STRIPE_PRICE_SIXMONTH",
                "STRIPE_PRICE_YEARLY"):
        assert f'ask {key}' not in src, f"the wizard asks for {key} by hand"


def test_the_only_thing_that_has_to_be_typed_is_the_stripe_key():
    """Ethan, 2026-08-21: "Idk how to plug that shit in can I just give
    you all the information so you can plug it in for me."

    No — nobody can write to that box from here, and a live key that can
    move money should not travel through a chat log. The answerable half
    is to make almost nothing need typing. Nine settings end up in the
    file; exactly one of them is a value a human has to fetch and paste.

    This pins that ratio, because the natural drift is back the other
    way: somebody adds a setting and adds a prompt for it.
    """
    with open(os.path.join(ROOT, "deploy", "golive.sh"), encoding="utf-8") as fh:
        src = fh.read()
    code = re.sub(r"(?m)^\s*#.*$", "", src)

    # Prompted for, with no default: the paste-it-yourself list.
    prompted = set(re.findall(r"(?m)^\s*ask ([A-Z_]+)", code))
    assert prompted == {"STRIPE_SECRET_KEY"}, (
        "the wizard prompts for more than the Stripe key now: "
        f"{sorted(prompted)}. Anything with a known correct value should "
        "use ask_or_default, and anything Stripe can tell us should be "
        "fetched rather than asked for.")

    # Offered with a default: Enter accepts.
    defaulted = set(re.findall(r"ask_or_default ([A-Z_]+)", code))
    assert {"QB_DISCORD_INVITE", "QB_COMP_EMAILS"} <= defaulted, defaulted


def test_the_webhook_is_created_by_the_api_not_by_hand():
    """The hardest step in the dashboard — a URL pasted exactly, five
    checkboxes out of about a hundred and fifty, and a `whsec_` string
    that looks like the API key. Every part of it is an API call."""
    with open(os.path.join(ROOT, "deploy", "golive.sh"), encoding="utf-8") as fh:
        src = fh.read()
    assert "--stripe-webhook --print-env" in src
    assert "ask STRIPE_WEBHOOK_SECRET" not in src, \
        "the wizard asks for the signing secret by hand again"

    from engine import billing, stripeset
    # The event list comes from the module that READS the events, so an
    # endpoint cannot be subscribed to a different set than we handle.
    src_ss = open(os.path.join(ROOT, "engine", "stripeset.py"),
                  encoding="utf-8").read()
    fn = src_ss[src_ss.index("def create_webhook("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "BI.HANDLED" in fn, \
        "the webhook's event list is typed out separately from the one " \
        "read_event acts on, so the two can drift"
    assert len(billing.HANDLED) == 5


def test_a_pasted_key_is_checked_against_stripe_immediately():
    """At a silent prompt, "not echoed" and "the paste did not take" look
    identical, and the difference otherwise surfaces two steps later as
    an error about something else."""
    with open(os.path.join(ROOT, "deploy", "golive.sh"), encoding="utf-8") as fh:
        src = fh.read()
    assert "SS.verify_key" in src, "the key is not checked when it is pasted"
    assert "would not accept that key" in src, "there is no failure branch"
    from engine import stripeset
    assert callable(stripeset.verify_key)


def test_an_existing_webhook_is_never_silently_replaced():
    """Stripe reveals a signing secret only at creation, so an endpoint
    that already exists cannot have its secret recovered — replacing it
    is the only way forward, and it is destructive enough to ask about."""
    src = open(os.path.join(ROOT, "engine", "stripeset.py"),
               encoding="utf-8").read()
    fn = src[src.index("def ensure_webhook("):]
    fn = fn[:fn.index("\n\n\n")]
    assert "recreate: bool = False" in fn, \
        "ensure_webhook now deletes an existing endpoint by default"
    wiz = open(os.path.join(ROOT, "deploy", "golive.sh"), encoding="utf-8").read()
    assert "[y/N]" in wiz.split("3 of 8")[1].split("4 of 8")[0], \
        "the wizard replaces an existing endpoint without asking"


def test_the_runbook_says_which_machine_each_command_is_for():
    """The whole reason this page was rewritten. A command with no
    location on it gets run wherever the reader happens to be."""
    with open(os.path.join(ROOT, "docs", "GOLIVE.md"), encoding="utf-8") as fh:
        doc = fh.read()
    for marker in ("Mac Terminal", "Droplet", "Browser"):
        assert marker in doc, f"the runbook never says {marker}"
    assert "root@ubuntu" in doc,         "it does not show what the droplet prompt looks like"
    assert "ethancarson@Ethans-MacBook-Air" in doc,         "it does not show what the Mac prompt looks like"


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
