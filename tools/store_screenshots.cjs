/* Store and install-sheet screenshots from the LIVE site (roadmap #45).

   Captured from the real site rather than a local copy, so the boards in
   the listing are real ones and never a sample board. Every size class the
   two stores ask for (2026-10-24, with every fold and flip):

     play-phone       1080x1920   Google Play phone
     play-tablet7     1200x1920   Play 7-inch tablet (large-screen listing)
     play-tablet10    1600x2560   Play 10-inch tablet (large-screen listing)
     play-foldable    2208x1840   a Pixel Fold's inner screen, open: the list
                                  beside its pick (tablet slot; Play caps a
                                  side at 3840 and the ratio at 2:1)
     ios-iphone69     1320x2868   App Store 6.9-inch iPhone (required)
     ios-ipad13       2064x2752   App Store 13-inch iPad (if iPad is offered)
     desktop          1280x800    the browser's install sheet ("wide")

     NODE_PATH=$(npm root -g) node tools/store_screenshots.cjs [https://qellysbook.com] [nfl]

   Writes web/img/store/<class>-<view>.png. Look at every image before it
   goes in a listing or the manifest's "screenshots". */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const BASE = process.argv[2] || "https://qellysbook.com";
const SPORT = process.argv[3] || "nfl";
const OUT = path.join(__dirname, "..", "web", "img", "store");
const VIEWS = ["recommended", "likely", "record", "mybets"];
const touch = { isMobile: true, hasTouch: true };
const CLASSES = [
  ["play-phone", { viewport: { width: 390, height: 693 }, deviceScaleFactor: 2.77, ...touch }],
  ["play-tablet7", { viewport: { width: 600, height: 960 }, deviceScaleFactor: 2, ...touch }],
  ["play-tablet10", { viewport: { width: 800, height: 1280 }, deviceScaleFactor: 2, ...touch }],
  ["play-foldable", { viewport: { width: 841, height: 701 }, deviceScaleFactor: 2.625, ...touch }, "split"],
  ["ios-iphone69", { viewport: { width: 440, height: 956 }, deviceScaleFactor: 3, ...touch }],
  ["ios-ipad13", { viewport: { width: 1032, height: 1376 }, deviceScaleFactor: 2, ...touch }, "split"],
  ["desktop", { viewport: { width: 1280, height: 800 } }],
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch();
  for (const [kind, opts, extra] of CLASSES) {
    const p = await b.newPage(opts);
    for (const v of VIEWS) {
      await p.goto(`${BASE}/?sport=${SPORT}#${v}`, { waitUntil: "networkidle" }).catch(() => {});
      await p.waitForTimeout(2000);
      const file = path.join(OUT, `${kind}-${v}.png`);
      await p.screenshot({ path: file });
      console.log("wrote", path.relative(path.join(__dirname, ".."), file));
    }
    // The open screens' own layout: a pick opened beside its board.
    if (extra === "split") {
      await p.goto(`${BASE}/?sport=${SPORT}#likely`, { waitUntil: "networkidle" }).catch(() => {});
      await p.waitForTimeout(2000);
      const card = await p.$("#view-likely .ob-card .ob-who");
      if (card) {
        await card.click();
        await p.waitForTimeout(1500);
        const file = path.join(OUT, `${kind}-likely-split.png`);
        await p.screenshot({ path: file });
        console.log("wrote", path.relative(path.join(__dirname, ".."), file));
      }
    }
    await p.close();
  }
  await b.close();
})();
