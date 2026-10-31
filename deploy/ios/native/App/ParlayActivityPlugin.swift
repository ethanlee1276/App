// "On my lock screen" (web/js/slip.js lockHTML): the page asks this plugin
// to start a Live Activity for a saved parlay, and gets back the activity's
// own push token, which the page hands the box (POST /api/push/activity).
// The box's slip watch then updates it (engine/pushmine.activity_update)
// and ends it when the box score settles the ticket.
//
// Registered by MainViewController.swift. Needs iOS 16.2 and, in the app's
// Info.plist, NSSupportsLiveActivities = YES.
//
// Not compiled here: nothing in this repository can run Xcode.

import ActivityKit
import Capacitor
import Foundation

@objc(ParlayActivityPlugin)
public class ParlayActivityPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "ParlayActivityPlugin"
    public let jsName = "ParlayActivity"
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
        let state = ParlayAttributes.ContentState(
            title: s["title"] as? String ?? "Following",
            status: s["status"] as? String ?? "open",
            legs: s["legs"] as? Int ?? 0,
            left: s["left"] as? Int ?? 0,
            won: s["won"] as? Int ?? 0,
            leg: s["leg"] as? String ?? "",
            line: s["line"] as? String ?? "")
        let attributes = ParlayAttributes(betId: call.getString("betId") ?? "",
                                          name: call.getString("title") ?? "Your parlay")
        do {
            let activity = try Activity.request(attributes: attributes,
                                                content: .init(state: state, staleDate: nil),
                                                pushType: .token)
            Task {
                // The first token is what the box needs; Apple may rotate it
                // later, and the page sends a new one the next time it asks.
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
        let betId = call.getString("betId") ?? ""
        Task {
            for activity in Activity<ParlayAttributes>.activities where activity.attributes.betId == betId {
                await activity.end(nil, dismissalPolicy: .immediate)
            }
            call.resolve()
        }
    }
}
