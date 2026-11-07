// A live game on the lock screen: shared by the app (which starts it) and
// the widget extension (which draws it). Add this file to BOTH targets.
//
// ContentState's field names are the JSON keys the box sends in every
// update (engine/gameactivity.state): change one side, change the other —
// tests/test_a_live_game_on_the_lock_screen.py holds them equal.
//
// Not compiled here: nothing in this repository can run Xcode. Built on
// the Mac with the rest of deploy/ios (README.md, "The widget and the lock
// screen").

import ActivityKit
import Foundation

public struct GameAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        public var away: Int
        public var home: Int
        /// "pre", "live" or "final".
        public var status: String
        /// "Q3 4:12", "Top 7th", "Final", or the start time before it starts.
        public var clock: String
        /// The feed's own line on the situation ("2nd & 7 at DEN 45").
        public var last: String
        /// The team with the ball (football), "" otherwise.
        public var poss: String
    }

    /// "nfl", "cfb", "nba", "wnba", "nhl" or "mlb".
    public var league: String
    /// The scoreboard's own id for the game.
    public var event: String
    public var away: String
    public var home: String
    /// Each side's colour, "#RRGGBB".
    public var awayColor: String
    public var homeColor: String
}
