# App stores: what is ready, what needs a person

Roadmap #45 (audit O27). This page says what has been built and what is
still undecided. **No build has been submitted and nothing here has been
reviewed by Apple or Google.** Whether either store accepts the app is a
guess [Guessing] until a person has read both policies in full and
decided.

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
   declarations? The manifest's description mentions the radar.

## Android build steps (laptop, not the droplet)

These are also listed in `docs/WHEN_YOU_ARE_HOME.md` as P45-a.

```
npm i -g @bubblewrap/cli
cd deploy/twa && bubblewrap init --manifest https://qellysbook.com/manifest.webmanifest
#   accept the values twa-manifest.json already holds; it creates the upload key
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

Run `tools/store_screenshots.cjs` against the live site. Look at every
image first, then list them in the manifest's `screenshots`. Screenshots
are not captured from a local copy, because a local copy can show a
sample board.
