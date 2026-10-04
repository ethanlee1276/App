/* Store and install-sheet screenshots from the LIVE site (roadmap #45).

   Captured from the real site rather than a local copy, so the boards in
   the listing are real ones and never a sample board. Phone at 1080x1920
   (390x693 CSS px at 2.77x) and desktop at 1280x800, the sizes Play and
   the browser install sheet accept.

     NODE_PATH=$(npm root -g) node tools/store_screenshots.cjs [https://qellysbook.com]

   Writes web/img/store/{phone,desktop}-<view>.png. Add them to
   manifest.webmanifest "screenshots" only after looking at each one. */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const BASE = process.argv[2] || "https://qellysbook.com";
const OUT = path.join(__dirname, "..", "web", "img", "store");
const VIEWS = ["recommended", "likely", "record", "mybets"];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  for (const [kind, opts] of [
    ["phone", { viewport: { width: 390, height: 693 }, deviceScaleFactor: 2.77, isMobile: true, hasTouch: true }],
    ["desktop", { viewport: { width: 1280, height: 800 } }],
  ]) {
    const p = await b.newPage(opts);
    for (const v of VIEWS) {
      await p.goto(`${BASE}/?sport=mlb#${v}`, { waitUntil: "networkidle" }).catch(() => {});
      await p.waitForTimeout(2000);
      const file = path.join(OUT, `${kind}-${v}.png`);
      await p.screenshot({ path: file });
      console.log("wrote", path.relative(path.join(__dirname, ".."), file));
    }
    await p.close();
  }
  await b.close();
})();
