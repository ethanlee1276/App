// "On my lock screen" on a game (web/js/detail.js lockGameHTML): the page
// asks this plugin to start a Live Activity for the game, and gets back the
// activity's own push token, which the page hands the box
// (POST /api/push/game-activity). The box then sends the score and clock as
// the game runs (engine/gameactivity.update_pass) and ends it at the final.
//
// Registered by MainViewController.swift. Needs iOS 16.2 and, in the app's
// Info.plist, NSSupportsLiveActivities = YES (the parlay card set it).
//
// Not compiled here: nothing in this repository can run Xcode.

import ActivityKit
import Capacitor
import Foundation

@objc(GameActivityPlugin)
public class GameActivityPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "GameActivityPlugin"
    public let jsName = "GameActivity"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "start", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "end", returnType: CAPPluginReturnPromise),
    ]

    @objc func start(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.reject("The lock screen needs iOS 16.2 or later.")
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.reject("Live Activities are off for Qellys in Settings.")
            return
        }
        let s = call.getObject("state") ?? [:]
        let state = GameAttributes.ContentState(
            away: s["away"] as? Int ?? 0,
            home: s["home"] as? Int ?? 0,
            status: s["status"] as? String ?? "pre",
            clock: s["clock"] as? String ?? "",
            last: s["last"] as? String ?? "",
            poss: s["poss"] as? String ?? "")
        let attributes = GameAttributes(
            league: call.getString("league") ?? "",
            event: call.getString("event") ?? "",
            away: call.getString("away") ?? "",
            home: call.getString("home") ?? "",
            awayColor: call.getString("awayColor") ?? "#888888",
            homeColor: call.getString("homeColor") ?? "#888888")
        do {
            let activity = try Activity.request(attributes: attributes,
                                                content: .init(state: state, staleDate: nil),
                                                pushType: .token)
            Task {
                for await data in activity.pushTokenUpdates {
                    let hex = data.map { String(format: "%02x", $0) }.joined()
                    call.resolve(["token": hex, "id": activity.id])
                    break
                }
            }
        } catch {
            call.reject("Couldn't start it: \(error.localizedDescription)")
        }
    }

    @objc func end(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.resolve()
            return
        }
        let event = call.getString("event") ?? ""
        Task {
            for activity in Activity<GameAttributes>.activities where activity.attributes.event == event {
                await activity.end(nil, dismissalPolicy: .immediate)
            }
            call.resolve()
        }
    }
}
