# 🌐 Hosting checklist — turning this into a public website (someday)

**This is NOT for now.** First we make sure it runs live, the data is real,
fresh and correct, and you've lived with it. This doc is just the map so you can
see the real steps — and the real gates — when you're ready.

The good news: the app is already built the way a public site needs (the data is
fetched **once, centrally** and everyone reads the same files — see `launch.py`),
so the *technical* leap is small. The harder parts aren't code.

---

## Part 0 — settle these BEFORE you host anything

These don't go away because the site works. They're the actual gate.

- [ ] **Data rights.** The free feeds are fine for personal use, not public
      redistribution:
  - **Odds** — the free Odds API tier is for personal/dev use. Serving odds to
    the public generally needs a **paid commercial plan** (check their terms).
  - **Stats/scores** — MLB Stats API, ESPN and nflverse are great for personal
    use but aren't licensed for commercial redistribution. A real product usually
    pays for a licensed feed (Sportradar, Genius Sports, official league data) —
    which is the expensive part.
- [ ] **Gambling rules.** A public betting-picks site typically needs:
  - **Age gate** (21+ confirmation before entry),
  - **Geo-restriction** (limit to regions where it's allowed),
  - **Responsible-gambling disclaimers** (you already have the footer),
  - and a check of the specific rules where you'd launch. This is a
    talk-to-someone-who-knows-the-local-rules step, not a coding step.
- [ ] **You take no bets and touch no money.** Staying an *information/analytics*
      site (which this is) is a much lighter lane than an actual sportsbook.
      Keep it that way unless you're prepared for the full licensed-operator path.

> If any of Part 0 isn't settled, keep it **private** (just you / a few friends).
> Everything below still works for a small private deploy.

---

## Part 1 — the technical checklist

- [ ] **Pick a host.** A small always-on service — Render, Fly.io, or Railway are
      the friendliest; a $5–10/mo VPS (DigitalOcean/Hetzner) also works. *Not*
      your home laptop (it'd need to run 24/7 and isn't built to be exposed).
- [ ] **Run it as a service.** Start `python3 launch.py` (or `server.py --live`
      plus a scheduled refresh) as the always-on process. It's pure standard
      library, so there's nothing to install on the box beyond Python 3.9+.
- [ ] **Set the environment.** Put `ODDS_API_KEY` in the host's env vars (never
      commit it). `secrets.local` stays local-only.
- [ ] **Central data refresh — already done.** `launch.py` refreshes both leagues
      on a schedule and everyone reads the same JSON, so API usage doesn't grow
      with visitors. On a commercial odds plan, tune the refresh interval to your
      request budget.
- [ ] **Ingest on the box.** Run `ingest.py` there too (or ship the SQLite file)
      so the game-level bets have team ratings.
- [ ] **Domain + HTTPS.** Buy a domain (~$12/yr), point it at the host, enable
      TLS (most hosts do this automatically). Betting content should be HTTPS.
- [ ] **Compliance UI.** Add the age-gate modal + geo-check + keep the
      disclaimer. (Small frontend work — I can do this when the time comes.)
- [ ] **Basics for a real audience.** Rate-limiting, a health check, error logging,
      and a caching layer/CDN in front of the static files if traffic grows.

---

## Part 2 — rough monthly cost (ballpark)

| Item | Personal / private | Real public product |
|------|--------------------|---------------------|
| Hosting | $0–10 | $10–50+ |
| Domain | ~$1/mo | ~$1/mo |
| Odds data | free tier | **paid plan — $$ (varies)** |
| Licensed stats feed | not needed | **$$$ (the big one)** |

The infrastructure is cheap. **Licensed data is what makes it expensive** — so
scale the ambition to what the data rights cost.

---

## Part 3 — a sane rollout order

1. **Private, just you** — deploy as-is to a host, keep it unlisted. Low stakes,
   validates the hosted setup.
2. **A few friends** — share the link, still small scale.
3. **Public** — only after Part 0 is genuinely handled (licensed data + age/geo +
   local rules). This is the step that turns a hobby into a product.

---

## What I can do when you're ready

- Add a **PWA manifest + icon** so it installs to a phone home screen (great for
  step 1–2, needs no licensing since it's for you).
- Write the **deploy config** for a specific host (Render/Fly/Railway).
- Build the **age-gate + geo-check** UI.
- Add the **central-scheduler/health-check** niceties for an always-on box.

None of it needs doing until the live version has proven itself. First: make it
work, make the data correct. Then this.
