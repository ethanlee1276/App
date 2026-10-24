// The lock screen's parlay: shared by the app (which starts it) and the
// widget extension (which draws it). Add this file to BOTH targets.
//
// ContentState's field names are the JSON keys the box sends in every
// update (engine/pushmine.activity_state): change one side, change the
// other — tests/test_the_iphone_widget_and_lock_screen.py holds them equal.
//
// Not compiled here: nothing in this repository can run Xcode. Built on
// the Mac with the rest of deploy/ios (README.md, "The widget and the lock
// screen").

import ActivityKit
import Foundation

public struct ParlayAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        /// "Two legs left", "One leg left", "Won", "Lost", "Pushed".
        public var title: String
        /// "open", "won", "lost" or "push".
        public var status: String
        public var legs: Int
        public var left: Int
        public var won: Int
        /// The leg that decides it, once one does ("Chiefs ML").
        public var leg: String
        /// Where that leg stands: the score, the clock, his number so far.
        public var line: String
    }

    /// The My Bets entry's id: the box finds the ticket by it.
    public var betId: String
    /// The member's own name for the ticket.
    public var name: String
}
