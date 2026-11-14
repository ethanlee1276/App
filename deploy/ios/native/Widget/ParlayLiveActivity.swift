// A saved parlay on the lock screen and in the Dynamic Island. The box
// updates it as the games run (engine/pushmine.activity_update) and ends
// it when the box score settles the ticket. It shows the member's ticket
// and the public score — never our chance.
//
// Add Shared/ParlayAttributes.swift to this target too. Not compiled here.

import ActivityKit
import SwiftUI
import WidgetKit

private func tint(_ status: String) -> Color {
    switch status {
    case "won": return .green
    case "lost": return .red
    default: return Color(red: 1.0, green: 0.69, blue: 0.0)
    }
}

struct ParlayLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ParlayAttributes.self) { ctx in
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(ctx.attributes.name).font(.headline).lineLimit(1)
                    Spacer()
                    Text("\(ctx.state.won)/\(ctx.state.legs)").font(.headline).monospacedDigit()
                }
                Text(ctx.state.title).font(.subheadline.weight(.bold)).foregroundStyle(tint(ctx.state.status))
                if !ctx.state.leg.isEmpty {
                    Text("\(ctx.state.leg): \(ctx.state.line)").font(.caption).lineLimit(2)
                }
            }
            .padding()
            .activityBackgroundTint(Color.black.opacity(0.85))
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { ctx in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text("\(ctx.state.won)/\(ctx.state.legs)").monospacedDigit()
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(ctx.state.title).foregroundStyle(tint(ctx.state.status))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text(ctx.state.leg.isEmpty ? ctx.attributes.name : "\(ctx.state.leg): \(ctx.state.line)")
                        .font(.caption).lineLimit(1)
                }
            } compactLeading: {
                Text("\(ctx.state.won)/\(ctx.state.legs)").monospacedDigit()
            } compactTrailing: {
                Text(ctx.state.left > 0 ? "\(ctx.state.left) left" : ctx.state.title)
                    .foregroundStyle(tint(ctx.state.status))
            } minimal: {
                Text("\(ctx.state.left)").foregroundStyle(tint(ctx.state.status))
            }
            .widgetURL(URL(string: "https://qellysbook.com/?app=ios#live"))
        }
    }
}
