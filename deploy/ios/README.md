# The iOS app: a shell around qellysbook.com

Built on a Mac with Xcode, never on the droplet. Nothing here runs on the box.

What the shell is: Capacitor's iOS project, opening `https://qellysbook.com/?app=ios`
with a user agent ending `QellysApp/1.0 (ios)`. The site recognises that
(`web/js/boot.js` QB_STORE_APP) and becomes the store app: no sportsbook links,
no league logos or player photos, no meme-coin or prediction-market pages. The
native part is **push alerts** (Apple's own, through Capacitor's
PushNotifications plugin): tonight's picks are up, last night is graded
(`engine/pushalerts.py`). That native feature is what guideline 4.2 asks a
wrapped site to have.

## Once, on the Mac

    cd deploy/ios
    npm install                      # pulls the current Capacitor; commit the lock file it writes
    npx cap add ios
    npx cap sync ios
    npx cap open ios                 # opens Xcode

In Xcode:

1. Signing & Capabilities → your team (needs the Apple Developer Program).
2. **+ Capability → Push Notifications.** And Background Modes → Remote notifications.
3. Bundle identifier `com.qellysbook.app` (the Play app's package id too).
4. App icon: `web/icon-512.png` scaled to 1024×1024 with no transparency.
5. Product → Archive → Distribute → App Store Connect.

## The Apple key, so the box can send

In the Apple Developer site: Certificates, IDs & Profiles → Keys → **+** →
Apple Push Notifications service (APNs). Download the `.p8` file once (Apple
never shows it again) and note its **Key ID** and your **Team ID**.

Copy the `.p8` to the box (for example `/srv/qellys/secrets/AuthKey.p8`,
readable only by the `qellys` user), then set, with `sudo ./deploy/setenv.sh`:

    QB_APNS_KEY_FILE=/srv/qellys/secrets/AuthKey.p8
    QB_APNS_KEY_ID=<the key id>
    QB_APNS_TEAM_ID=<the team id>
    QB_APNS_TOPIC=com.qellysbook.app
    QB_APNS_ENV=development          # only while testing from Xcode; leave unset for TestFlight and the store

`python3 -m engine.pushalerts` then says "Apple key: set". Until it is set,
iPhone-app subscriptions are kept and skipped, never errors.

## What Capacitor itself says about `server.url`

Capacitor's documentation describes `server.url` as meant for live reload.
Apps that load their own site this way do ship, and the store-app mode plus
native push is the case for this one, but it is the part of the build a
reviewer is most likely to question (docs/APP_STORES.md). The fallback, if it
is refused: bundle the site's files into `www/` at build time and point its
requests at `https://qellysbook.com` — a bigger change, not started.
