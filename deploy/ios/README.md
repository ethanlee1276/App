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

## The widget and the lock screen (docs/IDEAS.md 11)

The Swift is written and waiting in `native/`; **nothing here has compiled
it** (this repository cannot run Xcode), so expect Xcode to point at a line
or two the first time. After the steps above:

1. **The lock screen.** Drag `native/App/ParlayActivityPlugin.swift`,
   `native/App/MainViewController.swift` and `native/Shared/ParlayAttributes.swift`
   into the App target. In `Main.storyboard`, set the view controller's class
   to `MainViewController` (module App). In the App's `Info.plist` add
   `NSSupportsLiveActivities` = YES. Deployment target iOS 16.2 or later.
2. **The widget extension.** File → New → Target → **Widget Extension**,
   named `QellysWidgets`, "Include Live Activity" unticked (ours is in
   `native/`). Delete the files Xcode made, then drag in everything in
   `native/Widget/` plus `native/Shared/ParlayAttributes.swift` (tick the
   widget target for it too). Deployment target iOS 17.
3. Build to a phone. The Home Screen widget is "Qellys record" (the record,
   last night, today's pick counts — from `/api/widget`, no sign-in, never a
   pick). The lock screen: open the Live tab with a saved parlay and tap
   **On my lock screen**.

## Your players on the widget (2026-10-25)

A second widget, **Your players**, shows the players the account follows
with their lines in today's games, on the Home Screen (small, medium) and
the lock screen (the rectangle and the line above the clock). A widget
cannot sign in, so the app hands it a key through an App Group:

1. In Xcode, select the **App** target → Signing & Capabilities → **+
   Capability** → **App Groups**, and add `group.com.qellysbook.app`. Do the
   same on the **QellysWidgets** target, with the same group ticked.
2. Drag `native/Shared/WidgetKey.swift` into the project with **both**
   targets ticked, `native/App/WidgetKeyPlugin.swift` into the App target,
   and `native/Widget/YourPlayersWidget.swift` into the widget target.
   (`MainViewController.swift` and `QellysWidgets.swift` already list them.)
3. Build to a phone, sign in, follow a player or two, then Settings →
   **iPhone widget** → on. Long-press the Home Screen → **+** → Qellys →
   **Your players**; for the lock screen, long-press it → Customize → the
   widget row under the clock.

Turning it off in Settings deletes the key on the box (the widget then says
how to turn it on); signing out in the app clears it from the phone.

The lock screen is updated by the box with the same Apple key as the alerts
(`QB_APNS_*` above): push type `liveactivity`, topic
`com.qellysbook.app.push-type.liveactivity` (engine/webpush.apns_live). No
second key. Until the key is set, the activity starts and simply is not
updated.

## What Capacitor itself says about `server.url`

Capacitor's documentation describes `server.url` as meant for live reload.
Apps that load their own site this way do ship, and the store-app mode plus
native push is the case for this one, but it is the part of the build a
reviewer is most likely to question (docs/APP_STORES.md). The fallback, if it
is refused: bundle the site's files into `www/` at build time and point its
requests at `https://qellysbook.com` — a bigger change, not started.
