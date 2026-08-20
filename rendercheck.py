#!/usr/bin/env python3
"""Does the site still LOOK like the renders — and if not, which part moved?

Ethan, 2026-08-18, with the four Zenos render images: "i really love the
graphics and layouts of these renders so i wanna follow that pixel for
pixel." Every screen in that pack shipped over the two days that followed
and `docs/RENDER_SPEC.md` writes down what each one is.

**Prose cannot fail.** The spec says the Prediction Markets page is a
two-column layout with a sticky detail panel, and the Fantasy Calendar is
three columns. Nothing stopped a refactor from making either of them one
column — the test suite would stay green, because no test knew. That is
the gap this closes: the spec's structural claims become measurements,
taken from a real browser at the widths the renders were drawn at.

    python3 rendercheck.py                 # 1280 and 390
    python3 rendercheck.py --width 1280
    python3 rendercheck.py --shots out/    # + screenshots and a contact sheet

THE THIRD VERDICT IS THE WHOLE DESIGN. A layout can be absent for two
completely different reasons, and a tool that confuses them is one nobody
runs twice:

    the layout was REMOVED        → DRIFT, someone should look
    the board has NO DATA today   → not a finding at all

The site already distinguishes these itself: a screen with nothing to show
draws `.empty-slate` or `.loading` rather than a broken half-layout. So a
screen whose structure is missing *and* whose honest-empty state is
showing reports `no data`, and the run says how many screens that was.

**And "no data" has to be provable, or it becomes the bug.** A nav click
that silently lands on the wrong screen would find someone else's empty
state and file a clean "no data" for a page never visited — the cry-wolf
failure inverted, and worse, because it reads as reassurance. Every screen
therefore names a `proof` element that exists whether or not the board has
anything on it. No proof, no verdict: that is a nav failure and says so.
Which matters, because a machine with no schedule cache — a laptop, this
container — can skip most of the pack. **Coverage is part of the result**:
the number that means something is how many screens were actually
MEASURED, and the honest place to run this is the droplet.

WRITING A CHECK ON AN EMPTY BOARD WRITES A CHECK ABOUT EMPTINESS. Both
of the first two false alarms this tool produced were mine, and both had
the same cause: the machine I authored them on had no data, so the number
I saw was the number I pinned.

    four stat tiles       counted 4 where one tab had data,
                          12 on a fed board with three
    one condition row     counted 1 where there were no alerts,
                          6 on a board with six

Neither was drift. Both were a check measuring today's data instead of
the design. The defences, in order of how much they help:

  * name the thing the claim is about (`.pm-tiles`, not every `.stats`
    on the page) rather than reaching for it positionally;
  * for anything that REPEATS, use `each` — the count is a fact about
    tonight, the one-per-row relationship is the design;
  * and read a `n == 1` on a repeating element as a smell, not a check.

WHAT IT DOES NOT DO. It does not diff pixels against the render images.
Those live in the chat of 2026-08-18; a cloud session cannot persist them,
which is why `RENDER_SPEC.md` exists as prose in the first place. `--shots`
writes a contact sheet with an empty slot beside each screen so the images
can be dropped in and compared by eye — the comparison stays Ethan's, the
structure is mine.

Read-only. It serves `web/` on a scratch port, drives Chromium, and writes
nothing except what `--shots` asks for.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

#: Widths the render pack was drawn at: a desktop and a phone. Both, by
#: default — half the render notes are about what the phone stacks, and a
#: desktop-only check would have passed every one of them.
WIDTHS = (1280, 390)


# --- the spec, as measurements ----------------------------------------------
# Each screen: (name, [nav clicks], present-selector, [checks], widths)
#
#   name     what RENDER_SPEC.md calls it
#   url      the page to load. Defaults to index.html; the 404 and
#            maintenance screens are standalone pages with no shell and no
#            way in from the app, so they name their own.
#   clicks   selectors to click in order to reach it from a cold load
#   proof    an element that exists on this screen whether or not it has
#            data — the container, not the content. Its absence means the
#            nav went somewhere else, and no other verdict is trustworthy.
#   present  the element that proves the screen's LAYOUT mounted. Missing,
#            with proof present and an honest-empty state showing = "no
#            data" rather than drift.
#   checks   (id, sentence, selector, op, want, widths[, needs]) — the
#            sentence is what the spec claims, in the spec's own words
#            where it can be, and `widths` is which widths the claim
#            applies at. A three-column grid is not a claim about a phone,
#            so the width list lives on the CHECK rather than on the
#            screen.
#
#            `needs` is the optional precondition: a selector that must be
#            on the page for the claim to MEAN anything. The pricing cards
#            only render once subscriptions are switched on, and a check
#            that fails for that reason is reporting a business decision
#            as a design regression. With `needs` the claim stays written
#            down, reads as "off" rather than broken, and starts holding
#            by itself the day the feature turns on.
#
# `op` is one of:
#   n     count of matching elements
#   cols  number of grid tracks on the first match
#   pos   computed `position` of the first match
#   above the first match of `selector` sits above the first match of `want`
#   each  count(selector) == count(`want` selector), and both non-zero —
#         for a claim about a REPEATING element ("every row carries the
#         condition that fired it"). A fixed number cannot express that:
#         the count is however many rows there are today.
SCREENS = [
    ("Prediction Markets",
     ['[data-sport="intel"]'],
     "#intel-body",
     ".pm-layout",
     [("two-column", "left the market table, right a sticky detail panel",
       ".pm-layout", "cols", 2, (1280,)),
      ("sticky-detail", "the detail panel is sticky, not a second scroll",
       ".pm-detail", "pos", "sticky", (1280,)),
      ("chip-row", "category chip row above the table",
       ".pm-cats", "n", 1, (1280, 390)),
      # Scoped to the screen: `.stats` is the shared tile strip and every
      # board has one. Four is the render's count and they draw with
      # zeros on an empty feed, so this is a layout claim rather than a
      # data one — it holds on a machine that cannot reach Kalshi.
      # SCOPED TO THE BOARD'S OWN STRIP. `.stats` is shared, and this
      # page has three of them once it has data — board, flow, proof. The
      # first version counted `#intel-body .stats > *` and pinned 4,
      # because the machine it was written on had data for exactly one of
      # the three. Ethan's first fed run counted 12 and called it drift.
      ("four-tiles", "four stat tiles: tracked, priced, average gap, volume",
       ".pm-tiles > *", "n", 4, (1280, 390)),
      ("phone-stack", "phone: detail stacks ABOVE the table",
       ".pm-detail", "above", ".pm-layout > :first-child", (390,))],
     ),
    ("Fantasy Calendar",
     ['[data-sport="fantasy"]', '[data-subnav="fantasy"] [data-subtab="days"]'],
     '[data-subgroup="days"]',
     ".ffcal-layout",
     [("three-column", "calendar+summary / ranked cards / sticky panel",
       ".ffcal-layout", "cols", 3, (1280,)),
      ("month-grid", "month grid card with dot/star day markers",
       ".ffcal-month", "n", 1, (1280, 390)),
      ("legend", "legend (Elite/Top/Good day)",
       ".ffcal-legend", "n", 1, (1280, 390))],
     ),
    ("Dashboard",
     [],
     "#view-recommended",
     ".qt-row",
     [("quick-tools", "Quick Tools row of four doors above the perf grid",
       ".qt-row", "cols", 4, (1280,)),
      ("perf-grid", "the performance grid it sits above",
       ".perf-grid", "n", 1, (1280, 390))],
     ),
    # 12 in the pack. The summary strip already existed as the My Bets
    # tiles; the render's dense table shipped as a Cards/Table switch over
    # the same rows.
    ("Bet Tracker",
     ['[data-sport="mybets"]'],
     "#mybets-body",
     ".mbc-views",
     [("view-switch", "Cards/Table view switch over the same filtered rows",
       ".mbc-views > *", "n", 2, (1280, 390)),
      ("filter-chips", "the filter chips above the rows",
       ".mbc-chips", "n", 1, (1280,))],
     ),
    # 14 in the pack. The render's per-row toggle and "Create New Alert"
    # never cross — this page is a digest of three feeds we already hold,
    # and a switch that turns nothing on is a lie you can click.
    ("Alerts Center",
     ['[data-view="alerts"]'],
     "#alerts-body",
     ".al-cats",
     [("filter-chips", "filter chips with counts over the rows",
       ".al-cats", "n", 1, (1280, 390)),
      # `each`, not a number. The claim is that EVERY row carries its
      # condition, and how many rows exist is a fact about today's feeds.
      # Pinned as 1 it passed on an empty board and failed on a real one
      # with six alerts — the check measuring the data instead of the
      # design.
      ("condition-rows", "every row carries the CONDITION that fired it",
       ".al-c", "each", ".al-row", (1280, 390))],
     ),
    # 8/9 in the pack. The compact dossier card opens statically; the
    # FULL profile is an upgrade that arrives when /api/players/fantasy
    # answers, so every claim about it is gated on `.ffd-full`. Against a
    # plain file server those read "not in force" rather than broken —
    # which is the truth: this screen needs the app server, not just the
    # web directory.
    ("Player Profile",
     ['[data-sport="fantasy"]', ".dl-row, .dk-row, [onclick*='openFfDossier']"],
     "#ffd-overlay",
     ".ffd-card",
     [("opens", "the dossier opens over the page",
       "#ffd-overlay.open", "n", 1, (1280, 390)),
      # Selectors read off the rendered profile, not guessed from a grep:
      # the hero is `.ffp-head` and the tiles are `.ffp-tile` inside
      # `.ffp-tiles`, each carrying its own `.ffp-rank`.
      ("hero", "photo left; name + pos · team · number",
       ".ffp-head", "n", 1, (1280,), ".ffd-full"),
      ("season-tiles", "season-stats card, each tile with a league rank",
       ".ffp-tile", "each", ".ffp-rank", (1280,), ".ffd-full"),
      ("projection", "the projection tile with its confidence dots",
       ".ffp-proj", "n", 1, (1280,), ".ffd-full"),
      ("overview-grid", "one scrolling overview grid, not a tab strip",
       ".ffp-grid", "n", 1, (1280,), ".ffd-full")],
     ),
    # 23 in the pack. A standalone page: it skips `.shell` deliberately —
    # there is no sidebar to reserve room for — so the check is that it
    # STAYS standalone as well as that it draws.
    ("404",
     [], "body", ".stub",
     [("no-shell", "it skips the shell — no sidebar to reserve",
       ".shell", "n", 0, (1280, 390)),
      ("wordmark", "the brand mark links home",
       ".stub-brand", "n", 1, (1280, 390)),
      ("quick-links", "quick links back into the board",
       ".stub-links a", "n", 4, (1280,)),
      ("one-cta", "one brand CTA, not a wall of choices",
       ".stub-cta", "n", 1, (1280, 390))],
     "404.html"),
    # 24 in the pack. It quotes no ETA — it says what is true and when to
    # go look at the machine — so it has a note the 404 does not.
    ("Maintenance",
     [], "body", ".stub",
     [("no-shell", "it skips the shell too",
       ".shell", "n", 0, (1280, 390)),
      ("wordmark", "the brand mark links home",
       ".stub-brand", "n", 1, (1280, 390)),
      ("one-cta", "one CTA back to the board",
       ".stub-cta", "n", 1, (1280, 390)),
      ("the-note", "the honest note: nothing settled is touched",
       ".stub-note", "n", 1, (1280, 390))],
     "maintenance.html"),
    # Reached through the account nav item rather than a sport chip — it
    # is not a board. The first cut clicked the My Bets chip, landed on a
    # different screen, found ITS empty state and filed a tidy "no data"
    # for a page it had never opened. That is the bug `proof` exists for,
    # and it was in this file before the file was an hour old.
    ("Sign-in & Pricing",
     ["#nav-acct"],
     "#account-body",
     ".acct-hero",
     [("hero", "wordmark + tagline hero over the sign-in card",
       ".acct-hero", "n", 1, (1280, 390)),
      # Subscriptions are not switched on yet (docs/BILLING.md), so the
      # slot shows a note instead of the cards. The claim is still the
      # claim; it is simply not in force.
      ("two-plans", "TWO cards, not three — there is one real plan",
       ".plan-grid > *", "n", 2, (1280,), ".plan-grid")],
     ),
]

#: The site's own two ways of saying "nothing to show here yet". A screen
#: whose layout is missing while one of these is on the page has no data;
#: it has not lost its layout.
EMPTY_MARKS = (".empty-slate", ".loading")


_JS = r"""
import { chromium } from 'playwright';
const PORT = process.argv[2];
const PLAN = JSON.parse(process.argv[3]);
const WIDTH = Number(process.argv[4]);
const SHOTS = process.argv[5] || "";
const EMPTY = JSON.parse(process.argv[6]);

// FINDING THE BROWSER IS PART OF THE CHECK — same lesson --sweep paid for.
// Playwright's default resolution wants a headless-shell build under its
// own versioned directory; this project's container puts Chromium
// somewhere else entirely. Each candidate is tried and the LAST failure
// is re-thrown, so the message names the path actually attempted.
// CONTAINER FLAGS, not superstition. Without --disable-dev-shm-usage
// Chromium puts its shared buffers in /dev/shm and dies with "Page
// crashed" on the first navigation when that fill; --no-sandbox is
// required where the process cannot create user namespaces, which is
// most containers. Both were paid for here: the run that produced this
// comment crashed on page one, twice in a row.
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
// Long enough for the chart animations to finish before a screenshot —
// see the comment at the screenshot call.
const ANIM_SETTLE_MS = 900;
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium',
                    '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', undefined]) {
  if (path === null) continue;
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;

for (const s of PLAN) {
  const out = { name: s.name, width: WIDTH, nav: true, proof: false,
                present: false, empty: false, settled: true, checks: [],
                errs: [] };
  const p = await b.newPage({ viewport: { width: WIDTH, height: 1200 } });
  p.on('pageerror', e => out.errs.push(e.message.slice(0, 140)));
  try {
    // `domcontentloaded`, NOT `networkidle`. The real app handler serves
    // live endpoints the board polls on a timer, so the network never goes
    // idle and goto times out at 30s on a page that rendered fine in two.
    // The settle-wait below is what actually decides when to measure.
    await p.goto(`http://127.0.0.1:${PORT}/${s.url}`, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(1200);
    for (const c of s.clicks) {
      const hit = await p.evaluate((sel) => {
        const e = document.querySelector(sel);
        if (!e) return false;
        e.click();
        return true;
      }, c);
      if (!hit) { out.nav = false; out.missing_nav = c; break; }
      await p.waitForTimeout(1400);
    }
    if (out.nav) {
      // WAIT FOR THE SCREEN TO SETTLE, do not sleep and hope. A fixed
      // pause raced under load — the suite running this alongside
      // everything else reported "Prediction Markets: layout gone" once,
      // on a page whose layout was fine and merely slower to arrive. A
      // check that fires at random is worse than no check, because the
      // first false alarm is what teaches you to skip the real one.
      //
      // Settled = the layout is up, or the screen has said it has nothing
      // to draw. Either answer is a real answer; only "neither, yet" is
      // worth waiting on.
      //
      // SCOPED TO THIS SCREEN, exactly like the measurement below. The
      // first version waited on a page-wide `document.querySelector` for
      // the empty marks, which resolved the moment ANY view in the shell
      // had an empty state — including one belonging to a different
      // screen still in the DOM. Under suite load that fired before this
      // screen had drawn, and the scoped measure then found neither a
      // layout nor an empty state and called it "layout gone". A waiter
      // that asks a wider question than the check it guards does not
      // guard it.
      try {
        await p.waitForFunction(([proof, present, empties]) => {
          const root = document.querySelector(proof);
          if (!root) return false;
          return !!document.querySelector(present)
            || empties.some((e) => root.querySelector(e));
        }, [s.proof, s.present, EMPTY], { timeout: 10000 });
      } catch (e) {
        // Neither arrived inside the window. That is NOT drift: a slow
        // machine and a deleted layout look identical from here, and
        // guessing between them is how a check earns its first false
        // alarm. It is measured anyway and reported as inconclusive.
        out.settled = false;
      }
      const m = await p.evaluate(([proof, present, checks, empties]) => {
        // The empty state has to be INSIDE this screen. Anywhere on the
        // page is not the same claim: the shell keeps other views in the
        // DOM, and one of them being empty says nothing about this one.
        const root = document.querySelector(proof);
        const r = { proof: !!root,
                    present: !!document.querySelector(present),
                    empty: !!root && empties.some((e) => root.querySelector(e)),
                    got: {} };
        for (const [id, , sel, op, want, needs] of checks) {
          if (needs && !document.querySelector(needs)) { r.got[id] = "|off"; continue; }
          const els = document.querySelectorAll(sel);
          const e = els[0];
          if (op === "n") r.got[id] = els.length;
          else if (!e) r.got[id] = null;
          else if (op === "cols") {
            const t = getComputedStyle(e).gridTemplateColumns;
            r.got[id] = t === "none" ? 0 : t.split(" ").length;
          } else if (op === "pos") r.got[id] = getComputedStyle(e).position;
          else if (op === "each") {
            // NOTHING TO REPEAT IS NOT A BROKEN REPEAT. The Alerts page
            // says so itself — "a quiet page means a quiet slate, not a
            // broken one" — and a check that called a quiet night a
            // regression is the exact cry-wolf failure the no-data
            // verdict exists to prevent. Zero rows is zero rows.
            const n = els.length, m = document.querySelectorAll(want).length;
            r.got[id] = m === 0 ? "|none"
                      : n === m ? "|each-ok"
                      : `${n} of ${m}`;
          }
          else if (op === "above") {
            const o = document.querySelector(want);
            r.got[id] = o ? (e.getBoundingClientRect().top
                             <= o.getBoundingClientRect().top) : null;
          }
        }
        return r;
      }, [s.proof, s.present, s.checks, EMPTY]);
      Object.assign(out, m);
      if (SHOTS) {
        // A CHART THAT IS STILL DRAWING IS NOT THE CHART. ECharts eases
        // its lines in over `animationDuration: 500` (visuals.js), and a
        // screenshot taken inside that window catches a line that stops
        // halfway across an empty plot. That picture cost real time
        // once: the price tape's data was verified correct while three
        // screenshots of it disagreed, and the disagreement was the
        // clock. Measured on the tape — 4 of 10 sampled points painted at
        // 80ms, 6 at 250ms, all 10 by 500ms. The contact sheet exists to
        // be compared against the renders by eye, so it waits.
        // ANIM_SETTLE_MS is pinned above visuals.js's duration by
        // tests/test_price_tape.py.
        await p.waitForTimeout(ANIM_SETTLE_MS);
        const f = `${SHOTS}/${s.slug}-${WIDTH}.png`;
        await p.screenshot({ path: f, fullPage: true });
        out.shot = f;
      }
    }
  } catch (e) {
    const msg = String(e);
    out.errs.push(msg.slice(0, 140));
    // A DEAD BROWSER IS NOT SITE DRIFT. Once Chromium crashes every
    // remaining screen fails identically with "browser has been closed",
    // and a report of twelve regressions from one infrastructure fault is
    // a report nobody can act on. Say what happened once and stop.
    if (/Page crashed|browser has been closed|Target page/.test(msg)) {
      out.crashed = true;
      console.log(JSON.stringify(out));
      try { await p.close(); } catch (e2) {}
      break;
    }
  }
  console.log(JSON.stringify(out));
  await p.close();
}
await b.close();
"""


def _slug(name: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in name.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def _plan(width: int) -> list[dict]:
    """The screens that have anything to say at this width."""
    out = []
    for row in SCREENS:
        name, clicks, proof, present, checks = row[:5]
        url = row[5] if len(row) > 5 else "index.html"
        keep = [c for c in checks if width in c[5]]
        if not keep:
            continue
        out.append({"name": name, "slug": _slug(name), "clicks": clicks,
                    "url": url, "proof": proof, "present": present,
                    "checks": [[c[0], c[1], c[2], c[3], c[4],
                                c[6] if len(c) > 6 else ""] for c in keep]})
    return out


def _serve() -> tuple[ThreadingHTTPServer, int]:
    """A quiet server on whatever port the OS hands out.

    Port 0 rather than a fixed number, for the reason --sweep records: two
    runs at once, or one left half-finished, must not fail on "address
    already in use".
    """
    # THE REAL HANDLER, not a file server. Several render-spec screens are
    # not static: the Player Profile is an upgrade that arrives when
    # /api/players/fantasy answers, so against `python3 -m http.server`
    # every claim about it reads "not in force" forever — a check that can
    # never run is not a check. `launch.py --check`'s sweep already reuses
    # this handler for the same reason; production runs the identical one.
    #
    # It degrades rather than fails: if server.py cannot be imported (a
    # missing optional dependency, a half-installed checkout) the plain
    # file server still measures every static screen, and the API-gated
    # claims go back to reading "not in force" — which is then true.
    try:
        from server import Handler as _AppHandler

        class Handler(_AppHandler):
            def log_message(self, *a, **kw):
                pass
    except Exception:                                          # noqa: BLE001
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(WEB), **kw)

            def log_message(self, *a, **kw):
                pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.live_mode = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _have_node() -> bool:
    try:
        r = subprocess.run(
            ["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
            capture_output=True, cwd=str(ROOT), timeout=30)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def run(width: int, port: int, shots: str = "") -> list[dict]:
    plan = _plan(width)
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     dir=str(ROOT)) as fh:
        fh.write(_JS)
        script = fh.name
    try:
        proc = subprocess.run(
            ["node", script, str(port), json.dumps(plan), str(width),
             shots, json.dumps(list(EMPTY_MARKS))],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    finally:
        Path(script).unlink(missing_ok=True)
    rows = []
    for line in proc.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    if not rows:
        # THE LAST LINE IS THE LEAST USEFUL ONE. A node crash dump ends
        # with its own version banner, so taking stderr's tail reports
        # "Node.js v22" and throws away the message above it.
        noise = ("at ", "^", "node:internal", "Node.js v", "triggerUncaught")
        said = [ln.strip() for ln in (proc.stderr or "").splitlines()
                if ln.strip() and not ln.strip().startswith(noise)]
        raise RuntimeError(said[0] if said else "no output on stderr either")
    return rows


def verdicts(rows: list[dict]) -> dict:
    """Fold the raw measurements into the three verdicts, per check."""
    spec = {row[0]: {c[0]: c for c in row[4]} for row in SCREENS}
    out = {"measured": 0, "nodata": 0, "off": 0, "slow": 0,
           "crashed": False, "drift": [], "lines": []}
    for r in rows:
        head = f"{r['name']} @ {r['width']}"
        if r.get("crashed"):
            # Infrastructure, not the site. Reported once, loudly, and
            # never as a claim about a layout.
            out["crashed"] = True
            out["lines"].append(
                ("crash", head, f"the BROWSER died here — {r['errs'][0]}. "
                                f"Nothing after this was measured."))
            continue
        if r.get("errs"):
            out["drift"].append(f"{head}: page error")
            out["lines"].append(("drift", head,
                                 f"the page threw — {r['errs'][0]}"))
        if not r.get("nav"):
            out["lines"].append(
                ("nav", head, f"no way in — {r.get('missing_nav')} is not on "
                              f"the page"))
            out["drift"].append(f"{head}: nav")
            continue
        if not r.get("settled") and not r.get("present"):
            # Slow machine or deleted layout — indistinguishable from
            # here, so say so rather than pick one.
            out["slow"] += 1
            out["lines"].append(
                ("slow", head, "the screen had drawn neither its layout nor "
                               "an empty state when the clock ran out — "
                               "inconclusive, not a finding"))
            continue
        if not r.get("proof"):
            # No verdict is trustworthy from here. The nav reported
            # success — every selector was found and clicked — and the
            # screen still is not the one on the page.
            out["drift"].append(f"{head}: wrong screen")
            out["lines"].append(
                ("drift", head, "the nav clicked through but this screen "
                                "never mounted — nothing below it can be "
                                "believed"))
            continue
        if not r.get("present"):
            if r.get("empty"):
                out["nodata"] += 1
                out["lines"].append(
                    ("nodata", head, "no data on this board — the screen is "
                                     "drawing its honest empty state"))
            else:
                out["drift"].append(f"{head}: layout gone")
                out["lines"].append(
                    ("drift", head, "the layout is gone, and nothing says the "
                                    "board is empty"))
            continue
        out["measured"] += 1
        for cid, got in (r.get("got") or {}).items():
            c = spec[r["name"]][cid]
            say, sel, op, want = c[1], c[2], c[3], c[4]
            if got == "|off":
                out["off"] += 1
                out["lines"].append(
                    ("off", head, f"{say} — not in force yet "
                                  f"({c[6]} is not on the page)"))
                continue
            if op == "each" and got == "|none":
                out["nodata"] += 1
                out["lines"].append(
                    ("nodata", head, f"{say} — nothing on this board to "
                                     f"repeat over ({want} is empty)"))
                continue
            if op == "each":
                ok = got == "|each-ok"
                got = "one per row" if ok else got
                want = "one per row"
            else:
                ok = (got == want) if op != "above" else (got is True)
            out["lines"].append(
                ("ok" if ok else "drift", head,
                 f"{say} — {sel} {op}={got}" + ("" if ok else f", want {want}")))
            if not ok:
                out["drift"].append(f"{head}: {cid}")
    return out


CONTACT_HEAD = """<!doctype html><meta charset="utf-8">
<title>Qellys — render contact sheet</title>
<style>
 body{background:#0b0b12;color:#e8e8f0;font:14px/1.5 system-ui,sans-serif;margin:0;padding:24px}
 h1{font-size:20px;margin:0 0 4px} p.sub{color:#a0a0b8;margin:0 0 24px}
 .pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:0 0 32px}
 .pair h2{grid-column:1/-1;font-size:15px;margin:0;color:#c4b5fd}
 figure{margin:0} figcaption{color:#a0a0b8;font-size:12px;margin:0 0 6px}
 img{max-width:100%;border:1px solid #2a2a3a;border-radius:8px;display:block}
 .slot{border:1px dashed #3a3a52;border-radius:8px;min-height:220px;
       display:grid;place-items:center;color:#6b6b85;font-size:12px;
       text-align:center;padding:16px}
</style>
<h1>Render contact sheet</h1>
<p class="sub">Left: what the site draws now. Right: drop the matching
render image in beside it. Nothing here is a diff — the comparison is
yours; the structure checks are in <code>rendercheck.py</code>.</p>
"""


def contact_sheet(rows: list[dict], out_dir: Path) -> Path:
    """One page, each screen beside an empty slot for its render image.

    Deliberately NOT a pixel diff. The render images live in a chat, not
    in the repo, so the honest tool is one that puts our screen next to
    where theirs goes and lets a person look.
    """
    parts, found = [CONTACT_HEAD], 0
    for r in rows:
        if not r.get("shot"):
            continue
        rel = Path(r["shot"]).name
        # The render image, if it has been dropped in. Named for the
        # screenshot beside it so there is nothing to configure: run once,
        # read the filename off the empty slot, save the render under it,
        # run again and the pair is there.
        want = f"render-{Path(rel).stem}.png"
        theirs = (f'<img src="{want}" alt="the render for {r["name"]}">'
                  if (out_dir / want).exists() else
                  f'<div class="slot">drop the render image here and name it'
                  f'<br><code>{want}</code></div>')
        found += (out_dir / want).exists()
        parts.append(
            f'<div class="pair"><h2>{r["name"]} — {r["width"]}px</h2>'
            f'<figure><figcaption>ours</figcaption>'
            f'<img src="{rel}" alt="{r["name"]} at {r["width"]}px"></figure>'
            f'<figure><figcaption>the render</figcaption>{theirs}</figure>'
            f'</div>')
    path = out_dir / "contact.html"
    path.write_text("".join(parts), encoding="utf-8")
    contact_sheet.found = found
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--width", type=int, action="append",
                    help="only this width (repeatable); default 1280 and 390")
    ap.add_argument("--shots", default="",
                    help="write screenshots + a contact sheet into this dir")
    a = ap.parse_args(argv)
    widths = a.width or list(WIDTHS)

    if not _have_node():
        print("\n  rendercheck needs Node and Playwright.")
        print("    npm install playwright && npx playwright install chromium")
        return 1

    shots_dir = None
    if a.shots:
        shots_dir = Path(a.shots).resolve()
        shots_dir.mkdir(parents=True, exist_ok=True)

    print("\n  DOES IT STILL LOOK LIKE THE RENDERS?")
    print("  docs/RENDER_SPEC.md, measured in a real browser. Three "
          "verdicts:\n  the claim holds, the claim broke, or this board has "
          "no data to draw.")

    srv, port = _serve()
    all_rows = []
    try:
        for w in widths:
            try:
                all_rows += run(w, port, str(shots_dir) if shots_dir else "")
            except RuntimeError as exc:
                print(f"\n  {w}px: the browser said nothing — {exc}")
                if "Executable doesn't exist" in str(exc):
                    print("    Point CHROMIUM_PATH at a Chromium, or run "
                          "`npx playwright install chromium`.")
                return 1
    finally:
        srv.shutdown()

    v = verdicts(all_rows)
    mark = {"ok": "  ✅", "drift": "  ❌", "nodata": "  · ", "off": "  · ",
            "slow": "  ⏳", "nav": "  ❌", "crash": "  💥"}
    last = None
    for kind, head, say in v["lines"]:
        if head != last:
            print(f"\n  {head}")
            last = head
        print(f"{mark[kind]} {say}")

    checked = len({(r["name"], r["width"]) for r in all_rows})
    print(f"\n  {v['measured']} of {checked} screen-widths measured; "
          f"{v['nodata']} skipped for want of data"
          + (f"; {v['off']} claim(s) not in force yet" if v["off"] else "")
          + (f"; {v['slow']} inconclusive (too slow to settle)"
             if v["slow"] else "") + ".")
    if v["nodata"]:
        print("  A skipped screen is not a pass. Run this on the droplet, "
              "where the boards are fed.")
    if v["crashed"]:
        print("\n  THE BROWSER CRASHED — this run says nothing about the "
              "site.")
        print("  Check DISK first (`df -h /`): a full filesystem is what "
              "caused this the")
        print("  one time it happened here — Chromium cannot write its "
              "profile and dies")
        print("  on the first navigation. Then memory, then /dev/shm. "
              "Re-run before")
        print("  reading anything into it.")
        return 1
    if v["drift"]:
        print(f"\n  DRIFT: {len(v['drift'])} — "
              + ", ".join(v["drift"][:6])
              + (" …" if len(v["drift"]) > 6 else ""))
    else:
        print("\n  No drift in anything that could be measured.")

    if shots_dir:
        page = contact_sheet(all_rows, shots_dir)
        n = getattr(contact_sheet, "found", 0)
        print(f"\n  Contact sheet: {page}")
        if n:
            print(f"  {n} render image(s) paired. The rest have empty slots "
                  f"naming the file they want.")
        else:
            print("  Every slot is empty — each one names the filename to "
                  "save its render as. Save them there and run this again.")
    print()
    return 2 if v["drift"] else 0


if __name__ == "__main__":
    sys.exit(main())
