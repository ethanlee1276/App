// Where the app leaves the account's widget key for the widget extension to
// read: an App Group both targets share. Add this file to BOTH targets, and
// the App Group capability ("group.com.qellysbook.app") to both
// (README.md, "Your players on the widget").
//
// The key comes from POST /api/widget/key (engine/widgetfeed.key_for). It
// is the widget's address, not a password: what it opens is the account's
// followed players and their box-score lines, never a pick, and turning the
// widget off in Settings stops it answering.
//
// Not compiled here: nothing in this repository can run Xcode.

import Foundation

enum WidgetKey {
    static let group = "group.com.qellysbook.app"
    static let name = "widgetKey"

    static var value: String? {
        UserDefaults(suiteName: group)?.string(forKey: name)
    }

    static func set(_ key: String?) {
        let store = UserDefaults(suiteName: group)
        if let key, !key.isEmpty {
            store?.set(key, forKey: name)
        } else {
            store?.removeObject(forKey: name)
        }
    }
}
