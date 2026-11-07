// The widget extension's widgets: the Home Screen record, your players (on
// the Home Screen and the lock screen), and the parlay on the lock screen and
// in the Dynamic Island, and a live game there too.
//
// Not compiled here: nothing in this repository can run Xcode.

import SwiftUI
import WidgetKit

@main
struct QellysWidgets: WidgetBundle {
    var body: some Widget {
        RecordWidget()
        YourPlayersWidget()
        ParlayLiveActivity()
        GameLiveActivity()
    }
}
