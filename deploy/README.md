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

# 3. the app
sudo cp deploy/qellys.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qellys
systemctl status qellys

# 4. the front door — the domain is already qellysbook.com in the file
sudo apt install caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy

# 5. backups, nightly, and prove a restore works
echo '0 4 * * * /srv/qellys/deploy/backup.sh' | sudo -u qellys crontab -
sudo -u qellys ./deploy/backup.sh --check
```

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
gunzip -c backups/accounts-<stamp>.db.gz > data/accounts.db
sudo systemctl start qellys
```

`./deploy/backup.sh --check` restores the newest of each into a scratch
file and runs `PRAGMA integrity_check` against it. **Run it before you
need it.** A backup nobody has restored is a hope, and the check also
fails if the newest copy is more than 48 hours old — which is how you find
out the nightly job stopped.
