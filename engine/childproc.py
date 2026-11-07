"""How the app starts a child process: below the web server, twice over.

Every child — a board build, a chores lane, a detached fitter or chart
fill — was already NICED, so on the box's one core the server that
answers page loads and searches goes first. This adds the other half:
the child also volunteers to be what the kernel kills when the service
runs out of memory.

WHY. The unit caps the whole service at 1,600 MB (deploy/qellys.service),
and the cap is shared: the server, every build and every chore child
count against it together. When it is reached the kernel kills the
process it scores highest, and that score is mostly size — so a server
that has grown a cache can lose to a child that is only slightly smaller.
The server is the one process whose death takes the site down: search,
every paid board, the account pages (Ethan, 2026-10-14: "no most likely
bets ... no edge bets ... no players showing up in the search page",
the day two chart backfills each held most of a gigabyte). A child dying
costs one board one cycle, or one chore one rest.

HOW. `/proc/self/oom_score_adj` is the kernel's own dial for exactly
this. Raising one's own needs no privilege (lowering it would), and a
child's value is inherited by anything it starts, so a lane's harvest and
a build's helpers are covered too. Written with raw os calls between fork
and exec: the less a `preexec_fn` does in a threaded parent, the fewer
locks it can trip on. Where there is no /proc (a laptop) it is skipped;
the nice still applies.
"""

from __future__ import annotations

import os

#: What every child writes to its oom_score_adj (-1000..1000; the server
#: keeps 0). Half the scale: among children the biggest still goes first,
#: and a child is chosen over the server unless the server is the far
#: larger of the two.
CHILD_OOM_ADJ = 500
#: The CPU niceness every child already had.
CHILD_NICE = 10

OOM_ADJ_PATH = "/proc/self/oom_score_adj"


def lower_self(nice: int = CHILD_NICE, oom_adj: int = CHILD_OOM_ADJ, path: str = OOM_ADJ_PATH) -> None:
    """Nice this process and raise its OOM score. Never raises."""
    try:
        os.nice(int(nice))
    except (OSError, AttributeError):
        pass
    try:
        fd = os.open(path, os.O_WRONLY)
    except OSError:
        return
    try:
        os.write(fd, str(int(oom_adj)).encode())
    except OSError:
        pass
    finally:
        os.close(fd)


def below_server():
    """The `preexec_fn` for a child: nice it and put it ahead of the
    server in the kernel's choice of what to kill. None where there is no
    fork (Windows), as the old niceness lambda was."""
    return lower_self if hasattr(os, "nice") else None
