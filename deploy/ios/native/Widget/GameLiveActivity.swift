// A live game on the lock screen and in the Dynamic Island. The box sends
// it the new score and clock as the game runs (engine/gameactivity) and
// ends it at the final. The public score, the clock and the situation —
// never a pick.
//
// Add Shared/GameAttributes.swift to this target too. Not compiled here.

import ActivityKit
import SwiftUI
import WidgetKit

private func hex(_ s: String) -> Color {
    let h = s.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
    guard h.count == 6, let v = UInt32(h, radix: 16) else { return .gray }
    return Color(red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255,
                 blue: Double(v & 0xFF) / 255)
}

private struct Side: View {
    let abbr: String
    let score: Int
    let color: String
    let ball: Bool
    let lead: Bool
    var body: some View {
        VStack(spacing: 2) {
            HStack(spacing: 4) {
                Circle().fill(hex(color)).frame(width: 10, height: 10)
                Text(abbr).font(.headline)
                if ball { Image(systemName: "football.fill").font(.caption2) }
            }
            Text("\(score)").font(.system(size: 30, weight: lead ? .heavy : .semibold)).monospacedDigit()
        }
    }
}

struct GameLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: GameAttributes.self) { ctx in
            VStack(spacing: 6) {
                HStack {
                    Side(abbr: ctx.attributes.away, score: ctx.state.away, color: ctx.attributes.awayColor,
                         ball: ctx.state.poss == ctx.attributes.away, lead: ctx.state.away > ctx.state.home)
                    Spacer()
                    Text(ctx.state.clock).font(.subheadline.weight(.bold))
                        .foregroundStyle(ctx.state.status == "final" ? Color.secondary : Color(red: 1.0, green: 0.69, blue: 0.0))
                    Spacer()
                    Side(abbr: ctx.attributes.home, score: ctx.state.home, color: ctx.attributes.homeColor,
                         ball: ctx.state.poss == ctx.attributes.home, lead: ctx.state.home > ctx.state.away)
                }
                if !ctx.state.last.isEmpty {
                    Text(ctx.state.last).font(.caption).lineLimit(1).foregroundStyle(.secondary)
                }
            }
            .padding()
            .activityBackgroundTint(Color.black.opacity(0.85))
            .activitySystemActionForegroundColor(.white)
            .widgetURL(URL(string: "https://qellysbook.com/?app=ios#pbp/\(ctx.attributes.league)/\(ctx.attributes.event)"))
        } dynamicIsland: { ctx in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Side(abbr: ctx.attributes.away, score: ctx.state.away, color: ctx.attributes.awayColor,
                         ball: ctx.state.poss == ctx.attributes.away, lead: ctx.state.away > ctx.state.home)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Side(abbr: ctx.attributes.home, score: ctx.state.home, color: ctx.attributes.homeColor,
                         ball: ctx.state.poss == ctx.attributes.home, lead: ctx.state.home > ctx.state.away)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(ctx.state.clock).font(.caption.weight(.bold))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text(ctx.state.last).font(.caption).lineLimit(1)
                }
            } compactLeading: {
                Text("\(ctx.attributes.away) \(ctx.state.away)").monospacedDigit()
            } compactTrailing: {
                Text("\(ctx.state.home) \(ctx.attributes.home)").monospacedDigit()
            } minimal: {
                Text("\(ctx.state.away)-\(ctx.state.home)").monospacedDigit().font(.caption2)
            }
            .widgetURL(URL(string: "https://qellysbook.com/?app=ios#pbp/\(ctx.attributes.league)/\(ctx.attributes.event)"))
        }
    }
}
