// The app's own plugins, registered with Capacitor's bridge. In Xcode, set
// Main.storyboard's view controller class to MainViewController (module:
// App) so Capacitor loads through it.
//
// Not compiled here: nothing in this repository can run Xcode.

import Capacitor
import UIKit

class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(ParlayActivityPlugin())
        bridge?.registerPluginInstance(GameActivityPlugin())
        bridge?.registerPluginInstance(WidgetKeyPlugin())
    }
}
