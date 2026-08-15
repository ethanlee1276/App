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

## First time on a fresh box

```bash
# 1. a user that is not root, and a home for the app
sudo adduser --system --group --home /srv/qellys qellys
sudo -u qellys git clone <repo> /srv/qellys
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

# 4. the front door — edit the domain first
sudo apt install caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo $EDITOR /etc/caddy/Caddyfile
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
