# Deploying

Four files. Read `docs/LAUNCH.md` first — **Phase 0 comes before any of
this**, because its answers can change what gets deployed.

| | |
|---|---|
| `Caddyfile` | the public front door: TLS, static files, proxy to the app |
| `qellys.service` | systemd unit — runs the app as an unprivileged user |
| | (it runs `launch.py`, not `server.py` — see **What keeps the data fresh** below) |
| `deploy.sh` | pull → **test** → restart → verify, with a rollback printed |
| `backup.sh` | the two irreplaceable databases, plus a restore drill |

## Before the box exists: the key and the DNS

**An SSH key, on the Mac.** DigitalOcean asks for one at droplet creation,
and a droplet made with a key never has password login enabled at all —
which matters more than it sounds, because a public IP starts getting
password-guessing attempts within minutes of existing.

```bash
ls ~/.ssh/id_ed25519.pub          # already have one? use it, do not make another
ssh-keygen -t ed25519             # only if that came back "No such file"
```

If `ssh-keygen` says **"already exists. Overwrite (y/n)?"** the answer is
**n**. Overwriting is irreversible and breaks every other thing that key
opens — GitHub, any server you have ever logged into. If you need a
separate key rather than the existing one, give it its own name
(`ssh-keygen -t ed25519 -f ~/.ssh/qellys`) and connect with
`ssh -i ~/.ssh/qellys`.

Then paste the **public** half into DigitalOcean:

```bash
cat ~/.ssh/id_ed25519.pub         # one line, starts "ssh-ed25519 AAAA…"
ssh-add --apple-use-keychain ~/.ssh/id_ed25519   # macOS: type the passphrase once, ever
```

The file to share always ends in `.pub`. Its pair — same name, no
extension — is the private key: never paste it, never mail it, never
commit it. Anything beginning `-----BEGIN OPENSSH PRIVATE KEY-----` is
the wrong one, and the recovery is to generate a new pair, not to
apologise for it.

**Two DNS records**, at Cloudflare, once the droplet has an IP:

| Type | Name | Value | Proxy |
|---|---|---|---|
| A | `@` | the droplet's IPv4 | DNS only (grey) |
| A | `www` | the droplet's IPv4 | DNS only (grey) |

**Grey cloud, not orange, at least to begin with.** Cloudflare's proxy
terminates TLS itself, which means Caddy cannot complete its own
certificate challenge, and the app stops seeing real client IPs — and
those IPs are what the rate limiter and the local-only guards are built
on. Turn the proxy on later if you want it, deliberately, and re-check
both of those.

`www` gets a record even though it never serves anything: the Caddyfile
redirects it to the bare name, and a redirect still needs the name to
resolve.

## First time on a fresh box

### A deploy key first — the repo is private

`git clone` of a private repo needs credentials on the server, and the
right kind is a **deploy key**: an SSH key that GitHub accepts for this
one repository, read-only. Not your personal key, which opens every repo
you can reach, and not a personal access token, which is a bearer secret
that ends up sitting in `.git/config`.

```bash
# ON THE SERVER, as root
ssh-keygen -t ed25519 -f /root/.ssh/qellys_deploy -N "" -C "qellys droplet"
cat /root/.ssh/qellys_deploy.pub
```

Paste that line into GitHub → the repo → **Settings → Deploy keys → Add
deploy key**. Title it `qellys droplet`. **Leave "Allow write access"
UNCHECKED** — the server only ever needs to read. A read-only key that
leaks costs you a copy of the source; a writable one lets whoever has it
push code that this box then runs as a service.

Then tell git to use it, for that host only:

```bash
cat >> /root/.ssh/config <<'EOF'
Host github-qellys
  HostName github.com
  User git
  IdentityFile /root/.ssh/qellys_deploy
  IdentitiesOnly yes
EOF
chmod 600 /root/.ssh/config
```

`IdentitiesOnly yes` matters: without it ssh offers every key it can find
and GitHub rejects the connection after too many wrong ones, which reads
as "permission denied" rather than "you sent five keys".

```bash
# 0. prove the key works before it is load-bearing
ssh -T git@github-qellys      # expect: "Hi ethanlee1276/App! You've successfully authenticated"
```

That greeting says authentication worked. It also says *"but GitHub does
not provide shell access"* — which is not an error and is what success
looks like here.

```bash
# 1. the code, then the user that runs it
#    CLONE FIRST: adduser creates /srv/qellys, and git refuses to clone
#    into a directory that already has anything in it. Done this way
#    round, adduser finds the directory, says so, and carries on.
git clone github-qellys:ethanlee1276/App.git /srv/qellys
sudo adduser --system --group --home /srv/qellys qellys

#    THE APP USER DOES NOT OWN ITS OWN CODE. Only the two directories it
#    writes to. A service that can rewrite the files it executes turns
#    any bug that writes a path into remote code execution, and the
#    systemd unit's ReadWritePaths already says these are the only two.
#    It also keeps `git pull` clean: deploy.sh runs as root, and git
#    refuses to operate on a repo owned by someone else ("dubious
#    ownership") — which reads like a permissions bug and is not one.
sudo mkdir -p /srv/qellys/data /srv/qellys/web/data
sudo chown -R qellys:qellys /srv/qellys/data /srv/qellys/web/data
cd /srv/qellys

# 2. secrets, readable only by root and the app
sudo mkdir -p /etc/qellys
sudo cp secrets.local.example /etc/qellys/env
sudo chmod 600 /etc/qellys/env
sudo $EDITOR /etc/qellys/env          # real keys go in here

# 3. SWAP FIRST, or the first start is killed before it finishes.
#    Measured on a 1GB droplet, 2026-08-16: the cold build ran for seven
#    minutes of CPU and was then taken by the OOM killer, having never
#    reached the point where it binds the port. `launch.py` builds every
#    board for every sport before it serves anything, and that peak is
#    well above 1GB even though the steady state afterwards is small.
#    2G of swap is cheaper than a bigger droplet and enough.
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab   # survives a reboot
free -h                                            # expect: Swap 2.0Gi

# 4. the app
sudo cp deploy/qellys.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qellys
systemctl status qellys

# 5. the front door — the domain is already qellysbook.com in the file
#
#    CADDY IS NOT IN UBUNTU'S REPOSITORIES. Plain `apt install caddy`
#    answers "Unable to locate package caddy", which reads like a typo
#    and is not one. Add Caddy's own repository first; these four lines
#    are from their install page and the key is what makes apt trust it.
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy

#    THE LOG DIRECTORY FIRST. The Caddyfile writes an access log to
#    /var/log/caddy; the package does not create that directory, and
#    Caddy runs as the unprivileged `caddy` user, so it cannot create it
#    either. Skip this and the reload fails with "open
#    /var/log/caddy/qellys.log: permission denied" — which sounds like a
#    Caddy problem and is a mkdir.
#
#    -R, NOT THE BARE DIRECTORY. If anything has already run as root the
#    log FILE exists and belongs to root, and opening an existing
#    root-owned file for append fails exactly the same way — same error,
#    after a chown that looked like it worked.
sudo mkdir -p /var/log/caddy
sudo chown -R caddy:caddy /var/log/caddy
sudo chmod 750 /var/log/caddy

#    Installing it starts it on a default "Caddy works!" page. Replacing
#    that file is the whole configuration step.
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile

#    AS THE CADDY USER, not root. `validate` does not merely parse: it
#    provisions the config, which OPENS the log file — so running it
#    under sudo creates that file owned by root and causes the very
#    permission error the step above exists to prevent. Run as the user
#    that will actually run it and the check tests the right identity.
sudo -u caddy caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
journalctl -u caddy -n 30 --no-pager                # watch the certificate arrive

# 6. backups, nightly, and prove a restore works
#
#    NOT INSIDE THE CHECKOUT. backup.sh defaults to ./backups, which on
#    this box is /srv/qellys/backups — and the app user deliberately does
#    not own /srv/qellys (see step 1). The nightly job would fail at
#    `mkdir`, as the app user, at 4am, with nobody reading the output.
#    Give it a directory it owns, outside the repo, where `git clean`
#    also cannot reach it.
sudo mkdir -p /var/backups/qellys
sudo chown qellys:qellys /var/backups/qellys
sudo chmod 750 /var/backups/qellys

#    TAKE ONE BEFORE CHECKING ONE. --check restores the newest backup and
#    verifies it; against an empty directory it correctly reports
#    "MISSING: no backup of accounts", which reads like a broken script
#    and is an empty shelf.
sudo -u qellys env QB_BACKUP_DIR=/var/backups/qellys /srv/qellys/deploy/backup.sh
sudo -u qellys env QB_BACKUP_DIR=/var/backups/qellys /srv/qellys/deploy/backup.sh --check

#    Then nightly. The variable has to be IN the cron line — cron runs
#    with almost no environment and nothing exported in this shell
#    survives into it. The redirect matters too: without it cron mails
#    the output, and a box with no mail server drops that on the floor,
#    so a job failing every night looks exactly like a job working.
#    `crontab -l | …` appends rather than replacing whatever is there.
( sudo -u qellys crontab -l 2>/dev/null; \
  echo '0 4 * * * QB_BACKUP_DIR=/var/backups/qellys /srv/qellys/deploy/backup.sh >> /var/backups/qellys/backup.log 2>&1' \
) | sudo -u qellys crontab -
sudo -u qellys crontab -l          # read it back
```

### Offsite is the half this does not do

Everything above puts the backups on the same disk as the databases.
That survives a mistake — a bad migration, a wrong `DELETE` — and it does
not survive losing the droplet, which is the case you are actually
insuring against.

The cheapest real fix is **DigitalOcean's own droplet backups**, enabled
in their control panel: weekly images of the whole box, about 20% of the
droplet price, no code and no credential to leak. Turn it on.

`backup.sh` also takes `QB_BACKUP_REMOTE` and rsyncs there when set, for
a second copy somewhere you control. Do not point it at the Mac: a
laptop that is asleep when the job runs is a backup that silently stops
without ever failing.

### Two things the Caddy reload will tell you, and one of them is fine

**`caddy validate` says "Valid configuration" and the reload can still
fail.** Validate checks that the file parses and adapts — it does not
check that the running service can reach what the file points at.

Worse, under `sudo` it **creates the problem it cannot see**. Validate
provisions the config rather than merely reading it, and provisioning a
log block opens the log file — so `sudo caddy validate` leaves
`/var/log/caddy/qellys.log` owned by root, and the service, running as
`caddy`, then cannot append to it. That is why the step above says
`chown -R`: chowning only the directory leaves the root-owned file
inside it and the reload fails with the identical error, after a fix
that appeared to work. Run validate as the caddy user and neither
happens.

A failed reload is not an outage. Caddy loads the new config and only
swaps if it comes up cleanly, so the previous config keeps serving —
which is why the box stays on the default "Caddy works!" page rather
than going dark while you fix it.

**Three "Unnecessary header_up" warnings are expected. Do not act on
them.** Caddy points out that `reverse_proxy` forwards
`X-Forwarded-For`/`-Proto`/`-Host` by default. Writing them out is
deliberate for a reason the warning cannot see: `header_up
X-Forwarded-For {remote_host}` **replaces** the header instead of
appending to it, so the list the app reads has exactly one entry — the
peer Caddy actually saw. The default appends, which leaves whatever the
client claimed sitting in front of it. `_client_ip()` reads the last
entry and is safe either way, but with the override it is safe under
first-entry parsing too, and that is the refactor most likely to happen
by accident.

### The certificate, and the three ways it fails

Reloading Caddy makes it go and ask Let's Encrypt for a certificate, and
that is the one step in this list that depends on the outside world
agreeing with you. The journal says `certificate obtained successfully`
when it works. When it does not, it is almost always one of these:

* **The name does not point here.** Let's Encrypt resolves
  `qellysbook.com` itself and connects back to whatever it finds. Check
  from somewhere that is not this box: `dig +short qellysbook.com`. If
  Cloudflare's proxy is on (orange cloud), what answers is Cloudflare, not
  you, and the challenge cannot reach this machine at all.
* **Port 80 is shut.** The challenge arrives on plain HTTP even though
  everything afterwards is HTTPS. `ufw status` must list 80 as well as
  443 — closing 80 "because the site is HTTPS" breaks renewal too, three
  months later, which is a much worse time to find out.
* **Both names must resolve.** The Caddyfile serves `qellysbook.com` and
  redirects `www.qellysbook.com`, and Caddy gets a certificate for each.
  A missing `www` record fails that half and the log names it.

Failed attempts are rate-limited (five per hostname per hour), so fix the
cause before reloading again rather than retrying into the limit.

## The nightly, on the server

`tools/install-nightly.sh` is **macOS only** — it writes a launchd job,
because a laptop that is shut at 6am skips a cron and skipped ingest is
the failure it exists to prevent. None of that applies to a box that never
sleeps, so the server gets a plain cron line and nothing else.

Without it the site still serves and still settles — `launch.py` runs the
15-minute auto-settle and the first-of-day ingest in-process — but the
model stops LEARNING: no refit of the recency dial or the player memory,
no postmortems, no new calibration. The board keeps working and quietly
stops improving, which is the same shape of silence as the blank brain
below.

```bash
( sudo -u qellys crontab -l 2>/dev/null; \
  echo '30 9 * * * cd /srv/qellys && /usr/bin/python3 launch.py --nightly >> /var/backups/qellys/nightly.log 2>&1' \
) | sudo -u qellys crontab -
sudo -u qellys crontab -l
```

09:30 UTC is roughly 05:30 Eastern — after the last West Coast game has
finished and graded, before anybody is looking at the board. It logs
beside the backups because that directory is already the app user's; cron
mail goes nowhere on a box with no mail server.

## Seeding a new box — git does not carry the model

**A fresh clone has the code and nothing else, and it does not look
broken.** Every database and every fitted model is gitignored, correctly:
they are large and derived. But that means a new server starts with

* **no `history.db`** — backtests, comps, team ratings and player logs all
  read empty, and none of the fitters below can be refitted without it;
* **no `data/models/*`** — player memory, the recency dial, probability
  calibration and the blind-spot miner all return their neutral defaults;
* **a fresh `ledger.db`** — so the Record, which is the evidence the
  subscription is sold on, shows none of the history.

The picks still appear. They are simply the uncorrected ones, and the
Record is simply empty. That is why this has its own heading: the failure
is invisible from the outside, and it went unnoticed for a day after the
first live deploy until the missing player memory was spotted on the page.

```bash
# ON THE MAC, where the real data lives
python3 launch.py --settle all      # grade anything still open first
./deploy/seed.sh root@143.198.169.53
```

It stops the app, rsyncs `ledger.db`, `history.db`, `data/models/` and the
UFC dossiers, fixes ownership, starts it again, and prints the server's
own learned-model check so you can see it took.

**It overwrites the server's `ledger.db`.** That file has been journaling
since the box came up, so settle locally first and check
`/var/backups/qellys` on the server before answering the prompt.

`python3 launch.py --check` reports this on any machine, under **The
learned model** — each fitter, and what running without it actually
means.

## Every deploy after that

```bash
cd /srv/qellys && ./deploy/deploy.sh
```

It backs up first, pulls, **runs the full suite and refuses to restart if
anything is red**, then checks the site actually answers before calling it
done. If it does not come up it prints the rollback command.

## What keeps the data fresh

The unit runs **`launch.py`**, not `server.py`. Both serve the identical
site — launch.py does `from server import Handler` — but only launch.py
carries the loop that keeps the site *true*: ~60s page rebuilds, the
faster UFC and meme-coin clocks, the first-of-day ingest, and the
15-minute auto-settle that grades finished games.

This was wrong in the first draft of these files, and it is worth naming
because the failure is quiet. Running `server.py` alone, the site comes
up, answers every request, passes the smoke check in `deploy.sh` and
looks entirely healthy — while `web/data/*.json` stays frozen at whatever
the deploy wrote. A public board still labelled "live" over a slate that
is three weeks old is worse than one that is honestly down, because down
is visible and stale is not.

If you ever do want the serve-only process (a read-only mirror, say):

```bash
python3 server.py --live --bind 127.0.0.1 8000
```

…but then something else has to run the pipeline, or the mirror is a
museum.

## Installing it to a phone's home screen

Once the site is on HTTPS this works with nothing else to do: **iPhone**
Share → *Add to Home Screen*; **Android** the browser offers *Install app*
by itself, or ⋮ → *Install app*. It then launches full-screen with its own
icon, no address bar, and its own entry in the app switcher.

**All of it requires TLS and none of it works before that.** On plain
`http://` the manifest is ignored and the service worker cannot register,
so testing this on the LAN address or over Tailscale will show nothing —
that is the browser being correct, not a bug to chase.

Two things this Caddyfile does for it, both easy to miss:

* `.webmanifest` is not in Caddy's MIME table, so it is given an explicit
  `Content-Type`. Served as `text/plain` the install prompt simply never
  appears — no error, no console message.
* `/sw.js` is sent `Cache-Control: no-cache`. The service worker is the
  one file that can make every other file stale, and a cached worker
  keeps serving its own old shell — while the fix, shipping a new worker,
  is exactly what the cache stops arriving.

**The worker is network-first on purpose**, which is the opposite of the
usual PWA advice. This site's value is that its numbers are current, and
the standard "serve the cache, refresh in the background" pattern would
show last night's board inside a window with no address bar to hint that
anything was wrong. `/data/` and `/api/` are never cached at all; the
cache holds the shell only, so an offline launch shows the app and its own
honest empty states rather than stale prices. See `web/sw.js`.

## Three things that are easy to get wrong

**Rotate the keys.** Everything currently in `secrets.local` has lived in
a development environment. Generate new ones for production and leave the
dev keys for the laptop.

**`--bind 127.0.0.1` is not optional.** It is in the systemd unit for a
reason: bound to all interfaces, the plain-HTTP port is reachable from
outside too, and the TLS in front becomes something an attacker can walk
around.

**`X-Forwarded-For` is load-bearing.** The app reads it to find the real
caller. Strip it and every request looks like it came from 127.0.0.1 —
which makes `_local_only()` true for the whole internet, and that is the
guard stopping strangers creating profiles and posting passwords over
cleartext. Caddy sets it by default and the shipped Caddyfile says so
explicitly so it does not get "tidied away".

## Restoring

```bash
sudo systemctl stop qellys
gunzip -c /var/backups/qellys/accounts-<stamp>.db.gz > data/accounts.db
sudo systemctl start qellys
```

`./deploy/backup.sh --check` restores the newest of each into a scratch
file and runs `PRAGMA integrity_check` against it. **Run it before you
need it.** A backup nobody has restored is a hope, and the check also
fails if the newest copy is more than 48 hours old — which is how you find
out the nightly job stopped.
