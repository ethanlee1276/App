# Backups — getting a copy off the box

Two databases cannot be rebuilt if the droplet dies:

| | |
|---|---|
| `data/accounts.db` | other people's accounts, and who has paid |
| `data/ledger.db` | the bet journal and the public record — the evidence the whole positioning rests on |

Everything else regenerates from the pipeline.

`./deploy/backup.sh` already snapshots both nightly and keeps 14 of each.
**On the same disk as the databases.** That survives a mistake and does
not survive a dead server, and the dead server is the case you are
actually buying insurance against.

---

## Pick a destination

`QB_BACKUP_REMOTE` takes three shapes. The script tells them apart by
whether there is an `@` in it.

| Shape | Tool | When |
|---|---|---|
| `b2:qellys-backups/db` | rclone | **object storage — recommended** |
| `root@other-box:/srv/backups` | rsync over ssh | you own a second machine |
| `/mnt/volume/backups` | rsync | an attached volume on this droplet |

**Use object storage, and not on DigitalOcean.** The whole point is
surviving the loss of the box, and "the box" includes losing access to
the account the box is in. A DigitalOcean Space is one billing problem
away from being as gone as the droplet.

**Backblaze B2 is free at this size.** The two databases compress to a
couple of megabytes; B2's free tier is 10 GB. It is a different company,
a different login and a different bill, which is the property you want.

---

## Backblaze B2, start to finish

### 1. Make the bucket

🌐 **Browser:**

1. Sign up at **backblaze.com** → B2 Cloud Storage
2. **Buckets** → **Create a Bucket**
   - name: `qellys-backups` (must be globally unique — add digits if taken)
   - files: **Private**
   - encryption: **Enable** (server-side, free)
   - object lock: off
3. **App Keys** → **Add a New Application Key**
   - name: `qellys-droplet`
   - allow access to: **just `qellys-backups`**, not all buckets
   - access: **Read and Write**
4. Copy the **keyID** and the **applicationKey**. **The key is shown
   once.** If you lose it, delete the key and make another.

Restricting the key to one bucket matters: this key lives on a web
server, and a key that can only write one backup bucket is a much smaller
problem if that server is ever compromised.

### 2. Install rclone

🖥️ **Droplet:**

```bash
apt update && apt install -y rclone
```

### 3. Configure it

🖥️ **Droplet:**

```bash
rclone config create b2 b2 account YOUR_KEY_ID key YOUR_APPLICATION_KEY
```

Paste your two values in place of `YOUR_KEY_ID` and
`YOUR_APPLICATION_KEY`.

> That does put the key in your shell history. To avoid it:
> ```bash
> rclone config
> ```
> and answer: `n` (new remote) → name `b2` → storage `b2` → paste the key
> id → paste the application key → Enter through the rest → `q` to quit.

Check it can see the bucket:

```bash
rclone lsd b2:
```

You should see `qellys-backups`.

### 4. Point the backup at it

🖥️ **Droplet:**

```bash
cd /srv/qellys
sudo ./deploy/setenv.sh QB_BACKUP_REMOTE b2:qellys-backups/db
```

### 5. Prove it works

**This is the step that separates "configured" from "working".**

```bash
QB_BACKUP_REMOTE=b2:qellys-backups/db ./deploy/backup.sh --test-remote
```

It writes a file, reads it back, compares it and deletes it. You want:

```
  ok — wrote a file, read it back, and it matched.
```

Then run a real backup and confirm it lands:

```bash
QB_BACKUP_REMOTE=b2:qellys-backups/db ./deploy/backup.sh
rclone ls b2:qellys-backups/db
```

### 6. Make it nightly

🖥️ **Droplet:**

```bash
crontab -e
```

Add:

```
0 4 * * *  cd /srv/qellys && QB_BACKUP_REMOTE=b2:qellys-backups/db ./deploy/backup.sh >> /var/log/qellys-backup.log 2>&1
```

Cron does not read `/etc/qellys/env`, which is why the variable is on the
line.

---

## Checking on it

🖥️ **Droplet:**

```bash
cd /srv/qellys && ./deploy/backup.sh --check
```

It restores the newest copy of each database into a scratch file, asks
SQLite whether it is intact, reports how old it is, and looks at the
offsite copy. It **fails** if there is no offsite destination at all, if
a backup is corrupt, or if the newest one is more than 48 hours old —
which is how you find out the nightly job stopped.

A backup nobody has restored is a hope. This restores one every time.

---

## Restoring, when it comes to that

```bash
cd /srv/qellys
sudo systemctl stop qellys

# from the offsite copy
rclone copy b2:qellys-backups/db/accounts-20260821T040000Z.db.gz /tmp/
gunzip -c /tmp/accounts-20260821T040000Z.db.gz > data/accounts.db

sudo systemctl start qellys
```

Same for `ledger.db`. Stop the service first — restoring under a running
writer gets you a file neither version agrees with.

---

## What is not backed up, and why

* **`data/history.db`** — large, and rebuilds from `ingest.py`. Backing
  it up would dominate the archive to protect something reproducible.
* **`web/data/*.json`** — rebuilds from the pipeline on the next run.
* **Stripe** — holds its own records. If the box is lost, subscriptions
  keep billing and keep their history; what is lost on our side is the
  mapping from a Stripe customer to an account, which is in
  `accounts.db`. That is one of the two reasons it is on this list.

---

## The one thing this does not solve

An encrypted-at-rest copy in someone else's bucket is still a copy of
your users' email addresses. Passwords are scrypt hashes and card details
were never here, so the exposure is bounded — but if you want it sealed,
`rclone` has a `crypt` remote that encrypts client-side before upload.

It is deliberately not set up here, because a client-side key is one more
thing that can be lost, and a backup you cannot decrypt is worse than one
you never made. Do it when there is somewhere safe for the key to live.
