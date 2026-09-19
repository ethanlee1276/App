#!/usr/bin/env python3
"""Run every tests/test_*.py (stdlib only — no pytest needed) and summarize.

    python3 run_tests.py            # parallel, workers picked for the box
    python3 run_tests.py -j 4       # four at a time
    python3 run_tests.py --serial   # one at a time, the old behaviour
    python3 run_tests.py --slowest  # …and list where the time went

Each test file runs itself as a script (exit non-zero on failure). Used by
the deploy and handy locally.

WHY PARALLEL. Ethan, 2026-08-22, mid-deploy: "its been like 50 mins". The
droplet is one vCPU, and a serial run is 336 interpreter startups plus
about two dozen files that boot a real HTTP server and wait for it. Almost
none of that is CPU — it is process startup and sleeping on a socket — so
the box was idle for most of an hour while the deploy it was gating held
a live site on old code.

That is the dangerous part, not the minutes: a suite slow enough to skip
gets skipped, and `--no-tests` is right there in the deploy's help text.

WHAT MAKES IT SAFE. Every file already runs as its own process, binds port
0 rather than a fixed port, and puts its fixtures under TMPDIR — which is
sandboxed below. The one file that wrote into the repo (test_service_worker
appended a line to styles.css and restored it) was fixed to work against a
copy in the same commit as this. If a future test needs to mutate the tree,
it does not belong in a parallel run and this comment is the reason to
find another way.

OUTPUT IS STILL IN FILE ORDER. Results are held and printed sorted, so a
parallel run and a serial run produce the same transcript. `doctor.py` and
the nightly read the summary line, and tests/test_runner.py pins it.

AND IT SAYS SO WHILE IT WORKS. The first cut held every line until the
last file finished, which on the droplet — 337 files, three at a time, one
vCPU — was eleven minutes of a blinking cursor. Ethan, watching a deploy:
"this has been sitting frozen like this for 10 mins." It was not frozen,
which is exactly the problem: a gate that looks hung gets killed, and a
killed gate is a deploy that ships untested.

So failures print the moment they happen, and a counter ticks in between.
The ordered report still comes at the end; the counter is aggregate, so
nothing is printed twice.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))

#: No file should take this long. A hung server boot used to stall the
#: whole run with nothing to say; now it fails that one file and names it.
FILE_TIMEOUT = 900


#: Below this much physical memory the suite runs one file at a time.
#:
#: MEASURED, NOT GUESSED. deploy.sh ran this runner on the 1 GB droplet on
#: 2026-09-04 with the default three workers, and the kernel log has the
#: result: seven python3 test children killed by the OOM killer between
#: 22:18 and 23:25, at 254 to 807 MB resident each. Three of those at once
#: is more than the box has. The children showed a few `ok` lines and then
#: nothing — no traceback, no TIMED OUT — which the gate reported as seven
#: failures in files that pass here in under five seconds each.
#:
#: The comment this replaced said the droplet's 1 GB was there "to spend
#: on them". It was spent.
MIN_RAM_FOR_PARALLEL = 2 * 2 ** 30


def _pinned(argv):
    """The worker count the command line asked for, or None."""
    if "--serial" in argv:
        return 1
    for i, a in enumerate(argv):
        if a == "-j" and i + 1 < len(argv):
            return max(1, int(argv[i + 1]))
        if a.startswith("-j") and a[2:].isdigit():
            return max(1, int(a[2:]))
    return None


def _ram_bytes():
    """Physical memory, or None where the box will not say."""
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):
        return None


def _workers(argv, ram_bytes=None) -> int:
    pinned = _pinned(argv)
    if pinned is not None:
        return pinned
    ram = _ram_bytes() if ram_bytes is None else ram_bytes
    if ram is not None and ram < MIN_RAM_FOR_PARALLEL:
        return 1
    # MORE THAN THE CORE COUNT, on purpose. The work is dominated by
    # process startup and by waiting on sockets, so a one-vCPU box still
    # gains from several in flight — when it has the memory for them. It
    # is capped at 8 because each worker can spawn a server of its own.
    return min(8, max(2, (os.cpu_count() or 1) * 3))


#: The suite runs ON the droplet, DURING a deploy, while the site is
#: serving — and the droplet has one core. A full run is ~340 processes,
#: several of which do real arithmetic (test_isotonic fits calibration
#: grids; test_ledger bootstraps four AUCs at 2000 reps), and for ten
#: minutes they were competing on equal terms with the refresher and with
#: Caddy answering subscribers.
#:
#: That is backwards twice over. The site must win, because somebody is
#: reading it; and a heavy test file killed for LOSING that race is a red
#: gate that says nothing about the code — which is how test_ledger has
#: failed three deploys running while passing in nine seconds anywhere
#: else.
#:
#: `nice` fixes the first half at no cost: the kernel hands the core to
#: the service and the tests fill the gaps. The second half is below.
_NICE = shutil.which("nice")


def _child(path):
    """The command for one test file. -u so a killed process has already
    flushed what it printed; nice so the live site outranks the run."""
    cmd = [sys.executable, "-u", path]
    return [_NICE, "-n", "10"] + cmd if _NICE else cmd


def _timeout() -> int:
    """The per-file ceiling, scaled to how contended the box is.

    A fixed 900s was chosen when this ran serially on an idle machine. On
    a loaded single-core box the same file legitimately takes many times
    longer, and killing it reports a failure that is really a queue.

    Load average over CPU count IS the contention, measured rather than
    assumed, and it is read once at the start so every file in a run gets
    the same ceiling. Floored at 1 so an idle box keeps the old number,
    and capped so a genuinely hung file still dies inside an hour.
    """
    try:
        load = os.getloadavg()[0]
    except (OSError, AttributeError):
        return FILE_TIMEOUT
    pressure = max(1.0, load / max(1, os.cpu_count() or 1))
    return int(min(FILE_TIMEOUT * pressure, FILE_TIMEOUT * 4))


def _run_one(path, env, ceiling=None):
    name = os.path.basename(path)
    ceiling = ceiling or FILE_TIMEOUT
    t0 = time.monotonic()
    try:
        # -u: UNBUFFERED, and it is the whole reason a timeout can say
        # anything. Python buffers stdout when it is not a tty, so every
        # `ok <name>` a hung file had printed sat in an 8KB buffer and
        # died with the process — three timeouts on the droplet reported
        # nothing but the word TIMED OUT, and each one cost an afternoon
        # of guessing at which test was stuck. Unbuffered, the partial
        # output survives the kill and the last line names the test that
        # finished before the one that hung.
        r = subprocess.run(_child(path), capture_output=True,
                           text=True, cwd=ROOT, env=env, timeout=ceiling)
        out, code = r.stdout, r.returncode
        err = r.stderr
    except subprocess.TimeoutExpired as exc:
        def _text(v):
            if v is None:
                return ""
            return v.decode("utf-8", "replace") if isinstance(v, bytes) else v
        out = _text(exc.stdout)
        done = [ln for ln in out.splitlines() if ln.strip().startswith("ok ")]
        where = (f"\n  last test to finish: {done[-1].strip()[3:].strip()}"
                 f"\n  ({len(done)} passed before it hung — the next one in "
                 f"the file is the suspect)"
                 if done else
                 "\n  it printed nothing at all, so it hung before the "
                 "first test — an import, or module-level work")
        try:
            load = f" · load {os.getloadavg()[0]:.1f} on " \
                   f"{os.cpu_count()} cpu(s)"
        except (OSError, AttributeError):
            load = ""
        err = _text(exc.stderr) + f"TIMED OUT after {ceiling}s{load}{where}"
        code = 1
    return name, code, out, err, time.monotonic() - t0


def main() -> int:
    # Every fixture's tempfile.mkdtemp() outlives its test — a full run
    # leaves thousands of orphan directories, and repeated runs filled a
    # machine's /tmp to ENOSPC. Sandbox the children's TMPDIR for the run
    # and sweep it once at the end, whatever the verdict.
    sandbox = tempfile.mkdtemp(prefix="qellys-tests-")
    env = dict(os.environ, TMPDIR=sandbox, TEMP=sandbox, TMP=sandbox)

    # THE SUITE MUST NOT READ THE BOX IT IS RUNNING ON.
    #
    # Two failures on the droplet, 2026-08-23, that pass everywhere else:
    #
    #   test_stripe_plans  pops STRIPE_PRICE_YEARLY and asks billing to
    #                      refuse. billing._env() calls load_local_secrets,
    #                      which reads /etc/qellys/env and puts it straight
    #                      back — so the pop was undone by the very call
    #                      under test.
    #   test_backup_remote runs `backup.sh --check` with no remote set and
    #                      expects it to fail. The script reads the same
    #                      file and found the real rclone destination.
    #
    # Both were the gate judging the BOX rather than the code, and the
    # direction is dangerous rather than merely annoying: a suite that
    # inherits a live STRIPE_SECRET_KEY is a suite one careless test away
    # from touching a real account. A test run gets a clean environment,
    # the same one the dev container has, so green here means green there.
    for name in list(env):
        if name.startswith(("STRIPE_", "ODDS_API_KEY", "QB_")):
            env.pop(name)
    # Set after the sweep, not before it, so the sweep cannot eat it.
    env["QB_ENV_FILE"] = os.path.join(sandbox, "no-such-env")
    # Same doctrine, second door. Four modules persist what they have
    # measured under data/feedstate/ — the correlation priors, the CFB
    # team map, the hold watch and the game-line calibration — and that
    # directory is gitignored, so it exists on the droplet and not in a
    # fresh clone. The game-line calibration decides how much of a
    # disagreement with the closing number a spread is allowed to keep,
    # which decides whether it grades Play. A suite that reads it is a
    # suite whose verdict depends on which machine ran it, in BOTH
    # directions. Point the fitters at the sandbox: green here is then
    # green in a clone, which is the only kind of green worth having.
    env["QB_FEEDSTATE_DIR"] = os.path.join(sandbox, "feedstate")
    # THE SAME DOCTRINE, THIRD DOOR — and this one was open until
    # 2026-08-27, when GitHub Actions went red on three consecutive
    # commits this suite had called green. `data/models/` is gitignored
    # for the same good reason feedstate is, and ten modules keep a
    # fitted model in it. One of them is the calibration store: a fitted
    # temperature LIFTS a modelled probability, which pushed a fixture's
    # quotes over the EV bar, so a test asserted picks that existed only
    # because of a file no clone contains.
    #
    # The direction is the dangerous one. A local run that passes because
    # the box is richer than a clone keeps passing right up until it is
    # deployed somewhere that never fitted anything.
    env["QB_MODELS_DIR"] = os.path.join(sandbox, "models")
    try:
        return _run(env, sys.argv[1:])
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def _run(env, argv) -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    jobs = _workers(argv)
    started = time.monotonic()
    if jobs > 1:
        print(f"  {len(files)} files, {jobs} at a time\n")
    elif _pinned(argv) is None:
        # SAID ON THE SCREEN, beside the ceiling notice below, for the
        # same reason: a serial run on a box that used to run three
        # reads as a hang unless the runner says why it chose to.
        ram = _ram_bytes() or 0
        print(f"  {ram / 2 ** 30:.1f} GB of memory — one file at a time, "
              f"so the gate cannot OOM-kill its own children "
              f"(seven were, on 2026-09-04)\n")

    # Threads, not processes: each one only waits on a subprocess, so the
    # GIL is never the thing holding anything up.
    #
    # Collected in completion order and REPORTED in file order. The
    # progress ticks below are the only thing that happens while it runs,
    # and they exist because a silent gate reads as a hung one.
    got, done, failed_now, last = {}, 0, 0, time.monotonic()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        ceiling = _timeout()
        if ceiling > FILE_TIMEOUT:
            print(f"  busy box — per-file ceiling raised to {ceiling}s\n")
        futs = {pool.submit(_run_one, f, env, ceiling): f for f in files}
        for fut in as_completed(futs):
            res = fut.result()
            got[futs[fut]] = res
            done += 1
            name, code = res[0], res[1]
            if code != 0:
                # Straight out, in the order they happen. Waiting until
                # the end to mention a failure is how somebody sits
                # through eleven more minutes of a run that is already
                # going to fail.
                failed_now += 1
                print(f"  ❌ {name} failed ({done}/{len(files)} run)",
                      flush=True)
                last = time.monotonic()
            elif jobs > 1 and (done % 25 == 0
                               or time.monotonic() - last > 20):
                note = f", {failed_now} failed" if failed_now else ""
                print(f"     …{done}/{len(files)} files{note}", flush=True)
                last = time.monotonic()
    results = [got[f] for f in files]

    if jobs > 1:
        print()
    failed, skipped, total, times = [], [], 0, []
    for name, code, out, err, secs in results:      # back in file order
        times.append((secs, name))
        m = re.search(r"(\d+) tests passed", out)
        n = int(m.group(1)) if m else 0
        # A file may bow out when the machine can't give it what it needs
        # (Pillow, for the hand-run venue intake tool). It says so on a
        # SKIP line and exits 0. Report that as a skip, never as a green
        # zero: a file that stops running and still shows ✅ is how
        # coverage disappears without anyone noticing.
        why = re.search(r"^SKIP (.+)$", out, re.M)
        if code == 0 and not why and n == 0:
            # …and the same argument applies one step further in. A file
            # that exited 0 while reporting no count still printed ✅
            # with a 0 beside it. Fourteen files were doing exactly that
            # — their runners printed "all good" instead of "N tests
            # passed", so 142 real tests were absent from the headline.
            # The dangerous part was never the miscount: a file whose
            # tests had stopped running altogether would have printed the
            # identical line. Zero passing tests and no stated reason is
            # not a pass.
            failed.append(name)
            print(f"  ❌ {name:28} ran no tests and gave no SKIP reason")
        elif code == 0:
            total += n
            if why:
                skipped.append(name)
                print(f"  ⏭️  {name:27} skipped — {why.group(1).strip()}")
            else:
                print(f"  ✅ {name:28} {n} tests")
        else:
            failed.append(name)
            print(f"  ❌ {name:28} FAILED")
            print((out + err)[-800:])

    took = time.monotonic() - started
    if "--slowest" in argv:
        print(f"\n{'—' * 40}\nSlowest files:")
        for secs, name in sorted(times, reverse=True)[:12]:
            print(f"  {secs:6.1f}s  {name}")

    print(f"\n{'—' * 40}")
    if failed:
        print(f"FAILED: {', '.join(failed)}  ({total} passed before failure)")
        return 1
    # The skip note rides on the summary line because that line is what
    # doctor.py reports and what the nightly shows.
    note = f"  {len(skipped)} skipped: {', '.join(skipped)}." if skipped else ""
    print(f"All green: {total} tests across "
          f"{len(files) - len(skipped)} files.{note}")
    print(f"  {took:.0f}s wall, {jobs} at a time.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
