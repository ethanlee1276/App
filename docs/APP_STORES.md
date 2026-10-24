# App stores: what is ready, what needs a person

Roadmap #45 (audit O27). This page says what has been built and what is
still undecided. **No build has been submitted and nothing here has been
reviewed by Apple or Google.** Whether either store accepts the app is a
guess [Guessing] until a person has read both policies in full and
decided.

## Update, 2026-10-24 (evening): both calls made, and what is left for you

Ethan: "do both from my call. we just need it to work with the app store",
then "make sure we can use logos and headshots ... make sure we're ready to
go". Both calls below are built and on the branch; nothing is submitted.

**Call 1 — the store builds open no sportsbook.** Built as the *store app*
(`web/js/boot.js` QB_STORE_APP), for Play *and* iOS: the fresh read added
Apple, whose 5.3.4 has refused odds apps that link out to licensed books.
The app is told apart by its start address (`?app=play`, which
`deploy/twa/twa-manifest.json` now uses), Chrome's `android-app://`
referrer, or the iOS shell's user agent (`QellysApp/<v> (ios)`). Inside it:

- no **Bet it** and no **Tail it** sheet — no sportsbook link anywhere;
- no **league logos or player photos** (below);
- no **Rocket Radar** (meme coins) and no **Prediction Market** pages —
  real-money venues, one of them on crypto (Apple 5.3.4 and 3.1.5, Play's
  gambling and financial-services policies);
- the **Play build sells nothing** for now: its paywall is a sign-in page
  with no price and no link (`QB_STORE_CHECKOUT = { ios: true, play: false }`).
  Apple's US storefront allows the link out to Stripe (3.1.1(a)); Play's US
  external-links programme needs enrolling in Play Console first, and
  reports and fees apply from 1 October 2026. Enrol, then flip `play` to
  true. Or leave it: members who joined on the website sign in and see
  everything.

The website keeps all of it. `?app=web` on a phone forgets the app.

**Call 2 — push alerts, the native feature for 4.2.** Built
(`engine/webpush.py`, `engine/pushalerts.py`, `web/sw.js`, the Alerts page's
"Alerts on this phone"): "This week's NFL picks are up — 6 picks on the
board" once per board, "Last night: 8–3–1, +3.6u" once per night, never a
pick's name, nothing from 23:00 to 09:00 Eastern. Web browsers and the Play
app (Chrome's notification delegation is now on in the TWA manifest) work
as soon as this deploys — no key to set, the box makes its own. The iOS app
needs Apple's push key: steps in `deploy/ios/README.md`.

**Logos and headshots — the answer.** Not in the store builds. Team logos
and player photos belong to the leagues, the clubs and the players (and,
for the photos the site uses, to ESPN, the NBA, the NHL and MLB, whose CDNs
serve them). Apple rejects apps under 5.2.1 and 4.1 for exactly this, and a
"not affiliated" line does not cure it. In the store app every logo and photo
gives way to the site's own drawn marks — helmets, caps and balls in team
colours with the player's initials — which were already what showed when a
photo failed to load. Team names and abbreviations are used to say which
team; that is ordinary. To have real logos and faces in the app, the path is
a licence: a sports-data provider whose plan includes logo and headshot
rights for app display (SportsDataIO, Sportradar and Genius Sports sell
these; headshot rights are often a separate Getty-backed add-on), or the
leagues' own licensing. Then `storeArt()` in `web/js/visuals.js` is the one
switch. **The website still hotlinks ESPN's logos and photos.** That is the
same question at lower odds of anyone asking; it is yours to decide whether
the site should use the drawn marks too.

**Also built today:** the first screen no longer jumps while it loads
(measured on a throttled phone: layout shift 0.78 → 0.02, blocked time
765 → ~370 ms; tests/test_the_first_screen_holds_still.py); Liquid Glass on
the open Duo and a glass tab bar on phones (styles.css "LIQUID GLASS ON THE
DUO", no blur); the app opens on the league you were last on (or the one in
season), not on baseball all winter; a monochrome notification badge; the
iOS shell's config (`deploy/ios/`).

### Before you submit: the checklist

| | Play | App Store |
|---|---|---|
| Developer account | Play Console ($25 once) | Apple Developer Program ($99/yr) |
| Build | `bubblewrap` (below), start URL `/?app=play#recommended`, notifications on | `deploy/ios/README.md`, on a Mac |
| Sportsbook links | off in the app ✓ | off in the app ✓ |
| Logos / photos | drawn marks in the app ✓ | drawn marks in the app ✓ |
| Native feature | push alerts ✓ | push alerts ✓ once the APNs key is set |
| Selling | off until US external-links enrolment | Stripe link allowed on the US storefront |
| Where | **United States only** (the site is US, 21+, and both stores' payment rules differ outside it) | United States only |
| Age rating | IARC questionnaire: gambling themes, no real-money gambling *in* the app → expect Mature/18+ | 18+ (frequent gambling themes) |
| Data forms | Data safety: account email (account management), purchase history (Stripe, on the web), crash diagnostics (not linked to the user), push token (app functionality); no ads, no tracking, data deletable (in-app and the web page) | Privacy "nutrition" labels: the same four; "Data not used to track you" |
| Account deletion | in the app, and `https://qellysbook.com/privacy.html#delete-account` ✓ | in the app ✓ |
| Screenshots | `tools/store_screenshots.cjs` against the live site; phone, 7″, 10″, foldable | 6.9″ iPhone, 13″ iPad |
| Review notes | "A picks and analysis app. It takes no bets, links to no sportsbook, and holds no money. Members who joined on the website sign in." Give a test login with a membership. | same, plus: "Push alerts are the native feature: Alerts → Alerts on this phone." |

## Update, 2026-10-24: what changed, what was built, what is yours to decide

Ethan: "we need to optimize it for the App Store and the Google Play Store
as well". Read fresh (through search summaries; neither store's policy
page loads from the build machine, so the exact wording still needs a
person's read at submission):

**Built:**

- **Every screen size and posture** (styles.css "EVERY FOLD AND FLIP",
  tests/test_every_fold_and_flip.py): phones from 280px covers up,
  Flip and Razr covers, the inner screens of every Fold, the Duo,
  tablets either way up, list beside detail on wide open screens, the
  panes split at a book-folded hinge, Flex Mode's controls in the bottom
  half. This is what Play's large-screen quality bar asks for.
- **No portrait lock.** The manifest and `deploy/twa/twa-manifest.json`
  now say `"orientation": "any"`. Google Play has required apps to target
  Android 16 (API 36) since August 2026, and Android 16 ignores portrait
  and landscape locks and aspect-ratio limits on any screen 600dp or wider
  (foldables open, tablets): the app has to work turned either way, and
  now does. When building, check the generated `app/build.gradle` says
  `targetSdkVersion 36` (a current Bubblewrap does).
- **Account deletion, both ways the stores ask:** in the app (Account →
  Delete my account), and a public page for Play's data-deletion form:
  `https://qellysbook.com/privacy.html#delete-account` (the steps, and an
  email route for anyone who cannot sign in).
- **Crash reports** (engine/bugscan, privacy policy 2.6): a script error
  on anyone's screen reaches the box with its page, screen size and
  browser family, no identifier. Declare it on both forms as diagnostics,
  not linked to the user, not used for tracking.
- **Store screenshots for every size class** (`tools/store_screenshots.cjs`):
  Play phone, 7- and 10-inch tablets and an open foldable; App Store 6.9-
  inch iPhone and 13-inch iPad; the desktop install sheet. Run it against
  the live site, look at each, then upload.

**Settled since the last read:**

- **Apple, payments.** Since 1 May 2025 (a US court order), apps on the
  **US storefront** may show buttons and links to buy outside the App Store
  (guideline 3.1.1(a)), so the Stripe checkout can be linked from a US
  iOS app. Everywhere else, still no. Apple's commission on such
  purchases has been litigated; check the current terms at submission.
- **Google, gambling.** The Real-Money Gambling, Games, and Contests
  policy admits approved gambling apps (an application, licences, geo-
  restriction, and since 28 January 2026 age-screening tools) and, for
  every other app, generally does not permit content that facilitates
  wagering. A picks app that takes no bets is not a gambling app — but
  the **Bet it** buttons open a sportsbook's bet slip with the bet filled
  in (engine/betlinks), and that is the thing a reviewer is most likely to
  read as facilitating.

**Yours to decide before a Play build:**

1. **The Bet it links in the app.** Either ship the Play build without the
   sportsbook bet-slip links (the website keeps them; the app is told
   apart by its start address), or apply to Play's gambling programme,
   which needs licences the site does not hold. The first is a small
   change; it is not made, because it changes what members see.
2. **The listing's category and rating:** Sports, adults only, gambling
   themes declared in the content-rating questionnaire; the site's own
   floor is 21+.

**Yours to decide before an iOS build:** 4.2 (minimum functionality) is
still the likely rejection for a site in a wrapper. The native features
that would carry it, in order of value: push alerts when a pick posts or
settles, a home-screen widget with tonight's top pick and the record, and
the iPhone Duo's own layouts through Apple's native fold APIs (the web
build already lays out for the Duo by its shape).

## What the app would be

It would be the same site in a store wrapper, not a new codebase:

- **Android:** a Trusted Web Activity (TWA), built with Bubblewrap from
  `deploy/twa/twa-manifest.json`. It opens qellysbook.com full-screen,
  and every change to the site reaches the app with no store update.
- **iOS:** a WebView shell (Capacitor or a plain WKWebView). This one has
  not been started. Read the Apple section below first, because it is the
  harder of the two.

The site already does most of what a wrapper needs: a web manifest with
`id`, `lang`, maskable and standard icons, standalone display and
shortcuts; a service worker; the 21+ notice and helpline in the footer
of every page with a pick or a bet, and on the paywall, checkout and
Ask (the extra line above every view came off on 2026-10-01 at
Ethan's call); and zoom that is not locked (O18).

## Apple: a read of the App Review Guidelines (fetched 2026-10-01)

Guidelines quoted below are verbatim.

- **5.3.4.** "Apps that offer real money gaming (e.g. sports betting,
  poker, casino games, horse racing) or lotteries must have necessary
  licensing and permissions in the locations where the app is used, must
  be geo-restricted to those locations, and must be free on the App
  Store. Illegal gambling aids, including card counters, are not
  permitted on the App Store."
  - Qellys Book takes no wagers, so the licensing and geo-restriction
    clause should not apply. That conclusion is our reading, not Apple's.
  - "Illegal gambling aids" is the sentence a reviewer could point at.
    Sports betting analysis is legal, and the site's books are licensed
    US operators. But a reviewer decides that case by case.
- **5.3.3.** "Apps may not use in-app purchase to purchase credit or
  currency for use in conjunction with real money gaming of any kind."
  - The subscription buys analysis, not credit. Separately, Apple
    generally requires its own in-app purchase for digital subscriptions
    bought inside an iOS app. Selling through Stripe on the web, with no
    purchase button in the app, is the usual workaround. Its exact rules
    change often and need a fresh read at submission time.
- **4.2 / 4.2.2 (minimum functionality).** "Your app should include
  features, content, and UI that elevate it beyond a repackaged website",
  and apps should not primarily be "web clippings, content aggregators,
  or a collection of links."
  - A plain WebView of the site is exactly what this rejects. To make the
    iOS case, the app would need at least one native feature, such as
    push alerts when a pick settles or a home-screen widget showing
    tonight's record. That is real work and not yet scoped.
- **Age rating.** The guidelines page has no gambling rating table; the
  rating comes from the questionnaire in App Store Connect. Answer
  "Frequent/Intense" for gambling themes or simulated gambling as
  applicable, which yields 17+. The site's own floor is 21+, so the
  listing text and first screen should say 21+ anyway.

**Recommendation:** do Android first. The iOS case depends on a native
feature that does not exist yet, and 4.2 is the likely rejection.

## Google Play: still to be read

The gambling policy (support.google.com/googleplay/android-developer
answer 9877032, "Real-Money Gambling, Games, and Contests") could not be
fetched from the build machine, so **it has not been read for this
page**. Before building, a person should read it and answer:

1. Does an app that **links to** licensed sportsbooks, without taking
   wagers, fall under the real-money gambling programme? That programme
   needs an application form and country-by-country licences.
2. Do the "ads for gambling" rules cover the sportsbook links (venue
   links go through `EXTERNAL_MARKET_LINKS`), and in which countries?
3. Does the target-audience setting need to be "18+ only", and does the
   content-rating questionnaire need a gambling answer?
4. Does the Kalshi and Polymarket material (prediction markets) or the
   meme-coin radar fall under the financial-services or crypto
   declarations? (Settled 2026-10-24: the store app leaves the radar and
   the prediction markets out, and the manifest no longer mentions them.)

## Android build steps (laptop, not the droplet)

These are also listed in `docs/WHEN_YOU_ARE_HOME.md` as P45-a.

```
npm i -g @bubblewrap/cli
cd deploy/twa && bubblewrap init --manifest https://qellysbook.com/manifest.webmanifest
#   it reads the WEBSITE's manifest, so when it asks: start URL /?app=play#recommended
#   (the store app's mark), notification delegation yes; afterwards its
#   twa-manifest.json should match the one in the repo. It creates the upload key.
bubblewrap build
keytool -list -v -keystore qellys-upload.keystore | grep SHA256
python3 ../../tools/assetlinks.py <that SHA256>    # writes web/.well-known/assetlinks.json
```

Then:

1. Commit `web/.well-known/assetlinks.json` and deploy.
2. Check it is served:
   `curl -sI https://qellysbook.com/.well-known/assetlinks.json` should
   show `application/json`.
3. Upload the `.aab` to a Play **internal testing** track.
4. Once Play App Signing is on, add Play's SHA-256 as a second argument
   to `tools/assetlinks.py` and deploy again.

The keystore must never be committed: `*.keystore` is in `.gitignore`.
Losing it means the app can never be updated under the same listing, so
keep a copy off the laptop.

## Store screenshots

Run `tools/store_screenshots.cjs` against the live site (its header lists
every size class and the store each is for). Look at every image first,
then upload them and list the phone and desktop ones in the manifest's
`screenshots`. Screenshots are not captured from a local copy, because a
local copy can show a sample board.
