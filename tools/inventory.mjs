/* Preservation inventory — the safety net for the Night Form redesign.
 *
 * The redesign spec opens with a contract: "this is a re-skin, not a
 * rebuild. Every number, chip, expander, disclaimer, empty state, and
 * explanatory paragraph currently on the site must still exist afterward."
 *
 * A prose checklist cannot enforce that. This can. It renders every view of
 * every sport at two widths and records what actually reached the screen:
 * every visible string, every interactive affordance, every structural
 * class. Re-run it after any restyle and diff against the baseline. A
 * string that stops rendering shows up as a deletion, not as a surprise
 * three weeks later.
 *
 *   python3 generate.py && python3 generate_mlb.py      # deterministic
 *   node tools/inventory.mjs --out docs/inventory-baseline.json
 *   node tools/inventory.mjs --diff docs/inventory-baseline.json
 *
 * REGENERATE THE SAMPLE DATA FIRST, both times. The baseline records what
 * RENDERED, so it is a function of the code AND the slate it was rendered
 * from. The first baseline was taken against whatever fixture JSON happened
 * to be sitting in the scratchpad; the moment an engine change made those
 * files stale, a diff reported 7393 "lost" strings that were all just
 * different numbers. Both generators are deterministic — same input, same
 * bytes — so building from them makes the baseline reproducible from the
 * repo alone, and a diff then means what it says.
 *
 * When a diff is large and the entries are mostly NUMBERS, suspect the data
 * before the code: stash the change, regenerate, harvest, unstash,
 * regenerate, and diff those two. That isolates the code from the slate.
 *
 * Needs a static server over web/ on $QB_FIXTURE (default 8777) and
 * Playwright's Chromium. Both live in the scratchpad; this file is in the
 * repo because the BASELINE has to be versioned alongside the code it
 * describes.
 *
 * Node resolves `playwright` by walking up from THIS file looking for
 * node_modules, and ESM ignores NODE_PATH — so link the scratchpad's copy in
 * before running:
 *
 *   ln -sfn "$SCRATCH/node_modules" node_modules
 *
 * That link must stay untracked. `.gitignore` lists node_modules BOTH with
 * and without a trailing slash for exactly this reason: the trailing-slash
 * form matches directories only, a symlink is not a directory to git, and
 * the link duly got committed once — which broke `git pull` on every other
 * machine, because it pointed at a scratchpad path that existed on none of
 * them.
 */
import { chromium } from 'playwright';
import { readFileSync, writeFileSync } from 'fs';

const PORT = process.env.QB_FIXTURE || '8777';
const BROWSER = process.env.QB_CHROMIUM
  || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

/* Every view the app can reach, from VIEW_ORDER in web/js/app.js plus
   `game`, which has no nav tab of its own and is therefore the single
   easiest page on the site to forget. The redesign spec's own inventory
   listed ten; there are seventeen. */
export const VIEWS = ['recommended', 'live', 'edge', 'scanner', 'longshots',
  'parlays', 'trending', 'players', 'rosters', 'standings', 'record', 'intel',
  'fantasy', 'ufc', 'why', 'about', 'game'];
export const SPORTS = ['nfl', 'cfb', 'mlb', 'nba', 'wnba', 'ufc',
  'polymarket', 'fantasy'];
const WIDTHS = [1280, 390];

/* Elapsed-time strings change between two runs of this tool against
   IDENTICAL code. Left alone they reported 46 phantom deletions on a
   no-op diff — enough noise to bury a real one, which is the only way this
   tool can fail at its job. Canonicalise them: what has to survive the
   redesign is that the site still SAYS how stale it is, not the number.
   Deliberately narrow — masking more than this would hide real losses. */
const VOLATILE = [
  [/\b\d+(\.\d+)?\s*(s|sec|secs|seconds|m|min|mins|minutes|h|hr|hrs|hours|d|day|days)\s+ago\b/gi,
   '<elapsed> ago'],
  [/\bUpdated\s+<elapsed>\s+ago\b/gi, 'Updated <elapsed> ago'],
  /* The freshness chip has TWO mutually exclusive texts — "Updated <t> ago"
     while fresh, "Stale — built <t> ago" once it ages past the threshold —
     so a baseline taken while fresh reports the fresh string LOST when
     re-harvested later the same day. Nothing was lost; the build simply got
     older. What has to survive the redesign is that the site still says how
     fresh it is, not which side of the threshold it was on at harvest time.
     Same for an absolute ISO build stamp. */
  [/\b(?:Updated|Stale\s*[—-]\s*built)\b[^·.]*<elapsed> ago/gi, '<freshness>'],
  [/\bUpdated\s+\d{4}-\d\d-\d\dT[\d:]+/g, 'Updated <timestamp>'],
];

export const norm = s => {
  let t = String(s).replace(/\s+/g, ' ').trim();
  for (const [re, to] of VOLATILE) t = t.replace(re, to);
  return t;
};

/* Every page has to be a REAL navigation. Two URLs that differ only in
   their fragment are a same-document navigation: the browser fires
   hashchange and the app keeps running, so what gets recorded depends on
   which view was up a moment earlier. That made the whole inventory
   order-dependent — inserting one view into VIEWS shifted the sequence and
   reported 111 phantom losses on CFB's hidden views, while the same URLs
   loaded cold rendered identically before and after, four times each. The
   nonce forces a document load per page, which is also the honest thing to
   measure: the baseline should describe what a reader sees when they open
   the page, not what survives from the page before it. */
let nonce = 0;
const url = (sport, hash, n) =>
  `http://127.0.0.1:${PORT}/?sport=${sport}&_inv=${n}#${hash}`;

async function harvest() {
  const b = await chromium.launch({ executablePath: BROWSER });
  const out = { views: VIEWS, sports: SPORTS, widths: WIDTHS, pages: {} };
  for (const w of WIDTHS) {
    const p = await b.newPage({ viewport: { width: w, height: 1200 },
                                reducedMotion: 'reduce' });
    for (const s of SPORTS) for (const v of VIEWS) {
      /* `game` has no nav tab and no bare hash — it is reached as
         #game/<date>_<away>@<home>, so the id has to be discovered from the
         loaded slate first. It is the single easiest page on the site to
         forget, which is exactly why it is harvested rather than skipped:
         the redesign spec's own inventory omitted it entirely. */
      let hash = v;
      if (v === 'game') {
        await p.goto(url(s, 'recommended', nonce++), { waitUntil: 'networkidle' });
        await p.waitForTimeout(200);
        const gid = await p.evaluate(() => {
          const g = (typeof state !== 'undefined' && state.data
                     && state.data.games || [])[0];
          if (!g) return null;
          return `${g.date || ''}_${g.away}@${g.home}`
                 + ((g.game_number || 1) > 1 ? `_G${g.game_number}` : '');
        });
        if (!gid) continue;              // sport has no games in this slate
        hash = `game/${encodeURIComponent(gid)}`;
      }
      await p.goto(url(s, hash, nonce++), { waitUntil: 'networkidle' });
      /* A hidden view is routed twice — once by the hash handler on load,
         when state.sport is still the default and HIDDEN_VIEWS therefore
         says nothing is hidden, and again by applySport once the league's
         slate lands and the tab turns out not to exist for this sport.
         Snapshot between those two and you record whichever page happened
         to be up. Wait for the sport to actually be applied. Standalone
         modes (polymarket, fantasy) never set state.sport to their own
         name, so this is a short ceiling, not a barrier. */
      await p.waitForFunction(
        (want) => typeof state !== 'undefined' && state.sport === want,
        s, { timeout: 1200 }).catch(() => {});
      await p.waitForTimeout(240);
      /* WALK THE SUB-TABS BEFORE HARVESTING.
       *
       * The harvest records what is VISIBLE, and a sub-tab panel is
       * display:none until its tab is clicked. So the moment Record,
       * Players, Fantasy or Recommended grew rooms, every string in a
       * closed room read as a deletion — the net reporting the
       * reorganisation as data loss, which is the one failure that makes
       * a safety net get ignored.
       *
       * Behind a tab is still present. The contract is that the string
       * exists and is reachable, not that it is on screen at rest, so the
       * harvest opens each room in turn and unions what it finds. Strings
       * are a set already; the COUNTS deliberately stay as they are at
       * rest, because "how many cards does this page show" is a question
       * about the page you land on. */
      const roomHarvest = async (fn) => {
        const tabs = await p.$$('.view.active .subnav-btn');
        const acc = [];
        acc.push(await p.evaluate(fn));
        for (let i = 1; i < tabs.length; i++) {
          await tabs[i].click().catch(() => {});
          await p.waitForTimeout(90);
          acc.push(await p.evaluate(fn));
        }
        if (tabs.length > 1) {
          await tabs[0].click().catch(() => {});   // leave it as we found it
          await p.waitForTimeout(90);
        }
        return acc;
      };
      const collect = () => {
        const seen = new Set(), classes = new Set();
        const affordances = { buttons: [], expanders: [], inputs: [], links: [] };
        const root = document.querySelector('.view.active') || document.body;
        const visible = el => el.offsetParent !== null || el.offsetHeight > 0;
        for (const el of document.querySelectorAll('body *')) {
          if (!visible(el)) continue;
          if (typeof el.className === 'string')
            el.className.split(/\s+/).filter(Boolean).forEach(c => classes.add(c));
          const own = [...el.childNodes].filter(n => n.nodeType === 3)
            .map(n => n.textContent).join('').replace(/\s+/g, ' ').trim();
          if (own) seen.add(own);
        }
        for (const el of root.querySelectorAll('button')) if (visible(el))
          affordances.buttons.push(el.textContent.replace(/\s+/g,' ').trim());
        for (const el of root.querySelectorAll('summary')) if (visible(el))
          affordances.expanders.push(el.textContent.replace(/\s+/g,' ').trim());
        for (const el of root.querySelectorAll('input,select,textarea')) if (visible(el))
          affordances.inputs.push(el.placeholder || el.type || el.tagName);
        for (const el of root.querySelectorAll('a[href]')) if (visible(el))
          affordances.links.push(el.textContent.replace(/\s+/g,' ').trim());
        /* Sets lose multiplicity, and multiplicity is information: a page
           with eight `why?` chips that drops to one still contains the
           string "why?", so a set-difference reports nothing lost. Count
           the repeated structures too. */
        const tally = sel => [...root.querySelectorAll(sel)].filter(visible).length;
        const counts = {
          why: [...root.querySelectorAll('button')].filter(visible)
                 .filter(b => /^(why\?|hide)$/i.test(b.textContent.trim())).length,
          card: tally('.card'), chip: tally('.chip'), metric: tally('.metric'),
          tile: tally('.tile'), row: tally('tr'), summary: tally('summary'),
          reason: tally('.reasons li'), section: tally('.section-title'),
          svg: tally('svg'), button: tally('button'), link: tally('a[href]'),
        };
        return { strings: [...seen], classes: [...classes], affordances, counts,
                 nav: [...document.querySelectorAll('.nav-btn')]
                        .filter(visible).map(b => b.dataset.view) };
      };
      const rooms = await roomHarvest(collect);
      const r = rooms[0];                       // the page as you land on it
      const all = (pick) => [...new Set(
        rooms.flatMap(pick).map(norm))].sort();
      out.pages[`${w}|${s}|${v}`] = {
        strings: all((x) => x.strings),
        classes: [...new Set(rooms.flatMap((x) => x.classes))].sort(),
        buttons: all((x) => x.affordances.buttons),
        expanders: all((x) => x.affordances.expanders),
        inputs: all((x) => x.affordances.inputs),
        links: all((x) => x.affordances.links),
        nav: r.nav,
        // AT REST, not unioned. Summing card counts across rooms would
        // report a number no one ever sees on one screen.
        counts: r.counts,
      };
    }
    await p.close();
  }
  await b.close();
  return out;
}

function summarise(inv) {
  const all = k => new Set(Object.values(inv.pages).flatMap(p => p[k]));
  return {
    pages: Object.keys(inv.pages).length,
    strings: all('strings').size,
    classes: all('classes').size,
    buttons: all('buttons').size,
    expanders: all('expanders').size,
    inputs: all('inputs').size,
    links: all('links').size,
  };
}

const inv = await harvest();
const argOut = process.argv.indexOf('--out');
const argDiff = process.argv.indexOf('--diff');

if (argDiff > -1) {
  const base = JSON.parse(readFileSync(process.argv[argDiff + 1], 'utf8'));
  let lostS = 0, lostA = 0, missingPages = 0;
  const report = [];
  for (const [key, was] of Object.entries(base.pages)) {
    const now = inv.pages[key];
    if (!now) { missingPages++; report.push(`PAGE GONE  ${key}`); continue; }
    const gone = was.strings.filter(s => !now.strings.includes(s));
    if (gone.length) {
      lostS += gone.length;
      report.push(`${key}  -${gone.length} string(s)`);
      gone.slice(0, 6).forEach(s => report.push(`     - ${s.slice(0, 96)}`));
    }
    for (const k of ['buttons', 'expanders', 'inputs', 'links']) {
      const g = was[k].filter(x => !now[k].includes(x));
      if (g.length) { lostA += g.length; report.push(`${key}  -${g.length} ${k}: ${g.slice(0,4).join(' | ').slice(0,100)}`); }
    }
    const navGone = was.nav.filter(n => !now.nav.includes(n));
    if (navGone.length) report.push(`${key}  NAV LOST: ${navGone.join(',')}`);
    for (const [what, n] of Object.entries(was.counts || {})) {
      const got = (now.counts || {})[what];
      if (got < n) { lostA += n - got; report.push(`${key}  ${what}: ${n} -> ${got}`); }
    }
  }
  console.log(report.join('\n') || 'nothing lost');
  console.log(`\npages gone ${missingPages} · strings lost ${lostS} · affordances lost ${lostA}`);
  process.exit(missingPages || lostS || lostA ? 1 : 0);
}

if (argOut > -1) {
  writeFileSync(process.argv[argOut + 1], JSON.stringify(inv, null, 1));
  console.log('wrote', process.argv[argOut + 1]);
}
console.log(JSON.stringify(summarise(inv), null, 2));
