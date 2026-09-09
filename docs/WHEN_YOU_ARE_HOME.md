# Run these when you're home

Ethan, 2026-09-09, from work: *"please save all the code you need me too
run for when I'm home."*

Short list, in order. Everything is copy-paste. **Block 1 is the only one
that changes anything** — the rest are read-only and just tell me what
the box is actually doing, which is the half I cannot see from here.

Paste the output back with the block number and I can carry on.

The long history of one-off checks lives in `DROPLET_CHECKS.md`; this
file is only what is outstanding right now, and lines get deleted from it
as they are done.

---

## 1. The one thing that needs your hands (2 minutes)

A `git pull` does not install a systemd unit. The auto-updater restarts
the service; it does not re-copy the file. So the allocator setting that
landed today is sitting in the repo doing nothing until you run this.

What it is: glibc hands every thread its own malloc arena and never
reuses a freed block across arenas. `hashlib.scrypt` — the password hash
— asks for 16MB a call, so a burst of sign-ins used to leave one retained
16MB block per thread that ever hashed, and memory followed the number of
CALLERS rather than the number running at once. Measured here: 64
concurrent sign-ins peaked at 963MB against your `MemoryMax=1600M`. With
this set it is 219MB, and slightly faster.

```bash
cd /srv/qellys && git pull --ff-only
sudo cp deploy/qellys.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl restart qellys
```

Then confirm it actually took — this reads the live process's own
environment, so it cannot be fooled by an edit that did not get applied:

```bash
tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value qellys)/environ \
  | grep -E 'MALLOC|TZ'
```

Expected: `MALLOC_ARENA_MAX=2` and `TZ=America/New_York`. If MALLOC is
missing, the copy or the daemon-reload did not happen.

---

## 2. What the box is actually doing (read-only)

This is the block I most want back. I have been reasoning about a 2GB
droplet with a 1600M cap from what the unit file says; these say what is
true.

```bash
free -m
uptime
systemctl status qellys --no-pager | head -20
```

Whether the memory cap has ever been approached or hit — the dangerous
case is the kernel reclaiming rather than killing, which leaves no OOM
line at all, so both counts matter:

```bash
journalctl -u qellys --since "7 days ago" | grep -ci oom
journalctl -k --since "7 days ago" | grep -icE "out of memory|killed process"
systemctl show qellys -p MemoryCurrent -p MemoryPeak -p MemoryMax
```

`MemoryPeak` is the one to read: if it is anywhere near 1600M, the cap is
doing more than sitting there.

---

## 3. Are the four sign-ups actually working? (read-only)

Accounts, sessions, and whether anyone has saved anything. No emails or
verifiers are printed — counts and dates only.

```bash
cd /srv/qellys && python3 - <<'PY'
import sqlite3, time
c = sqlite3.connect("data/accounts.db")
c.row_factory = sqlite3.Row
n = lambda q: c.execute(q).fetchone()[0]
print("users            ", n("SELECT COUNT(*) FROM users"))
print("sessions live    ", n("SELECT COUNT(*) FROM sessions WHERE expires_at > %f" % time.time()))
print("sessions expired ", n("SELECT COUNT(*) FROM sessions WHERE expires_at <= %f" % time.time()))
print("saved sections   ", n("SELECT COUNT(*) FROM user_data"))
print("\nsign-ups by day:")
for r in c.execute("SELECT date(created_at,'unixepoch','localtime') d, COUNT(*) k"
                   " FROM users GROUP BY d ORDER BY d DESC LIMIT 10"):
    print("  %s  %d" % (r["d"], r["k"]))
print("\nlast seen (most recent 10, no addresses):")
for r in c.execute("SELECT id, datetime(last_seen,'unixepoch','localtime') s"
                   " FROM users ORDER BY last_seen DESC NULLS LAST LIMIT 10"):
    print("  user %-4s %s" % (r["id"], r["s"] or "never"))
PY
```

---

## 4. What the traffic looks like (read-only)

Caddy's log is the only place the real request pattern exists. Requests
per hour, the busiest paths, and whether anybody is being turned away.

```bash
sudo awk -F'"' '{print $0}' /var/log/caddy/qellys.log 2>/dev/null | tail -1 >/dev/null \
  && echo "log readable" || echo "log NOT readable — try with sudo -i"

# requests per hour today
sudo python3 - <<'PY'
import json, collections, glob, gzip, io
c = collections.Counter(); status = collections.Counter(); paths = collections.Counter()
for p in sorted(glob.glob("/var/log/caddy/qellys.log*")):
    op = gzip.open if p.endswith(".gz") else open
    try:
        for line in op(p, "rt", errors="ignore"):
            try: e = json.loads(line)
            except Exception: continue
            ts = e.get("ts")
            if not ts: continue
            import datetime
            h = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:00")
            c[h] += 1
            status[e.get("status")] += 1
            paths[(e.get("request") or {}).get("uri","")[:60]] += 1
    except OSError:
        pass
print("requests per hour (last 12):")
for h, k in sorted(c.items())[-12:]:
    print("  %s  %5d" % (h, k))
print("\nstatus codes:", dict(status.most_common(8)))
print("\ntop paths:")
for p, k in paths.most_common(12):
    print("  %6d  %s" % (k, p))
PY
```

Two numbers I care about in that output:

* **`429`** — anybody hitting the rate limit. A real subscriber
  refreshing hard should never see one. If they do, `RATE_READ_PER_MIN`
  (server.py, currently 300/min per IP) is too tight for how the app
  actually polls, and I will raise it.
* **`503`** — the load shedder firing. Should be zero at this traffic.
  Anything above zero means `MAX_INFLIGHT` is binding and I want to know.

---

## 4b. The code box is gone from the two paying screens — check the third

Removed 2026-09-09 at your ask: the "Have a code?" box is off the PLANS
page and off the CHECKOUT page, which are the two you circled.

It is still on the ACCOUNT page, deliberately. That box never took a
Stripe discount code and never could — those go in Stripe's own field on
Stripe's page. It takes a COMP code, which writes free access here with
no card at all. If I had deleted all three, any code you have already
handed out would have stopped working with nothing to say so.

I could not verify the account page from here because it needs a signed-in
session. Two minutes on your phone, signed in:

1. Open the account page. There should still be a **Have a code?** box.
2. Type any nonsense and press Apply — it should say the code is not
   valid, not throw or go blank.
3. Plans page and checkout page: **no** code box anywhere. The FAQ entry
   "I have a code." now says to use the account page, and says plainly
   that a discount code for a paid plan is a different thing that goes in
   on Stripe's page.

If you would rather comp codes went away entirely, say so and I will take
the account box out too — it is one line. I did not do it unasked because
it is a working capability you did not mention, and losing it is the kind
of thing you find out about from a friend who cannot get in.

---

## 5. Board health, same as always (read-only)

```bash
cd /srv/qellys && python3 -c "import launch; launch.show_boards()"
cd /srv/qellys && python3 launch.py --why-empty nfl | head -40
```

---

## 6. If the site ever feels slow while you are on it

Run this WHILE it feels slow, not after — it is a snapshot:

```bash
systemctl show qellys -p MemoryCurrent -p TasksCurrent
uptime
ps -o pid,rss,pcpu,etime,cmd -p $(systemctl show -p MainPID --value qellys)
sudo tail -50 /var/log/caddy/qellys.log | python3 -c "
import sys, json
for l in sys.stdin:
    try: e = json.loads(l)
    except Exception: continue
    print('%6.0fms  %3s  %s' % (1000*e.get('duration',0), e.get('status'),
          (e.get('request') or {}).get('uri','')[:70]))
"
```

The last one prints how long each recent request actually took. Anything
over ~200ms on an `/api/` path is worth me seeing.
