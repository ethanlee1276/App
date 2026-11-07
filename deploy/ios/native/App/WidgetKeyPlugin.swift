// "iPhone widget" in Settings (web/js/account.js widgetRowHTML): the page
// asks the box for the account's widget key (POST /api/widget/key) and hands
// it here; this puts it in the App Group (Shared/WidgetKey.swift) and asks
// iOS to redraw the widgets. Signing out in the app calls `clear`, so a
// shared phone stops showing the last person's players.
//
// Registered by MainViewController.swift. Not compiled here: nothing in
// this repository can run Xcode.

import Capacitor
import Foundation
import WidgetKit

@objc(WidgetKeyPlugin)
public class WidgetKeyPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "WidgetKeyPlugin"
    public let jsName = "WidgetKey"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "set", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clear", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "status", returnType: CAPPluginReturnPromise),
    ]

    @objc func set(_ call: CAPPluginCall) {
        guard let key = call.getString("key"), !key.isEmpty else {
            call.reject("No key.")
            return
        }
        WidgetKey.set(key)
        WidgetCenter.shared.reloadAllTimelines()
        call.resolve(["on": true])
    }

    @objc func clear(_ call: CAPPluginCall) {
        WidgetKey.set(nil)
        WidgetCenter.shared.reloadAllTimelines()
        call.resolve(["on": false])
    }

    @objc func status(_ call: CAPPluginCall) {
        call.resolve(["on": WidgetKey.value != nil])
    }
}
