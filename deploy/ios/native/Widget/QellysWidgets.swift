// The widget extension's two widgets: the Home Screen record, and the
// parlay on the lock screen and in the Dynamic Island.
//
// Not compiled here: nothing in this repository can run Xcode.

import SwiftUI
import WidgetKit

@main
struct QellysWidgets: WidgetBundle {
    var body: some Widget {
        RecordWidget()
        ParlayLiveActivity()
    }
}
