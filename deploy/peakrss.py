#!/usr/bin/env python3
"""Peak memory of one command, without GNU time.

    python3 deploy/peakrss.py python3 mlb_build.py 2026-09-02 --cached-odds --out /tmp/m.json

Prints exit code, wall time and the child tree's peak resident size in MB
(resource.getrusage on the children). The droplet has no /usr/bin/time;
this is the four lines that replace it. Added 2026-09-02 while chasing the
memory ceiling that was killing builds part-way.
"""
import resource, subprocess, sys, time
t = time.time()
p = subprocess.run(sys.argv[1:], capture_output=True, text=True)
ru = resource.getrusage(resource.RUSAGE_CHILDREN)
print(f"exit={p.returncode} elapsed={time.time()-t:.0f}s peak_rss_mb={ru.ru_maxrss/1024:.0f}")
print((p.stdout + p.stderr).strip().splitlines()[-1][:200] if (p.stdout + p.stderr).strip() else "")
