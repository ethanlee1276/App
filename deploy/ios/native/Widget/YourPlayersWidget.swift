// Your players: the players the account follows, each with his line in
// today's game ("Ja'Marr Chase · 6 rec, 94 yds, 1 TD · 3rd 4:12"), on the
// Home Screen and the lock screen. It asks
// https://qellysbook.com/api/widget/mine?k=<key> (engine/widgetfeed.mine)
// with the key the app left in the App Group (Shared/WidgetKey.swift), every
// fifteen minutes while one of them is playing and hourly otherwise. Without
// a key it says how to turn it on. Public box scores and the account's own
// follows; never a pick. The JSON keys below are the feed's;
// tests/test_the_iphone_widget_and_lock_screen.py holds them equal.
//
// Needs iOS 17 (containerBackground). Not compiled here.

import SwiftUI
import WidgetKit

struct MineFeed: Decodable {
    struct Line: Decodable {
        let player: String
        let team: String
        let opp: String
        let line: String
        let status: String
        let live: Bool
        let url: String
    }
    let players: [Line]
    let following: Int
}

struct MineEntry: TimelineEntry {
    let date: Date
    let feed: MineFeed?
    let hasKey: Bool
}

struct MineProvider: TimelineProvider {
    func placeholder(in context: Context) -> MineEntry { MineEntry(date: .now, feed: nil, hasKey: true) }

    func getSnapshot(in context: Context, completion: @escaping (MineEntry) -> Void) {
        load(completion)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<MineEntry>) -> Void) {
        load { entry in
            let live = entry.feed?.players.contains { $0.live } ?? false
            let next = Date().addingTimeInterval(live ? 15 * 60 : 60 * 60)
            completion(Timeline(entries: [entry], policy: .after(next)))
        }
    }

    private func load(_ done: @escaping (MineEntry) -> Void) {
        guard let key = WidgetKey.value,
              var parts = URLComponents(string: "https://qellysbook.com/api/widget/mine") else {
            done(MineEntry(date: .now, feed: nil, hasKey: false))
            return
        }
        parts.queryItems = [URLQueryItem(name: "k", value: key)]
        guard let url = parts.url else {
            done(MineEntry(date: .now, feed: nil, hasKey: false))
            return
        }
        URLSession.shared.dataTask(with: url) { data, response, _ in
            // A 404 is a key that was replaced or turned off: say how to turn it on.
            if (response as? HTTPURLResponse)?.statusCode == 404 {
                done(MineEntry(date: .now, feed: nil, hasKey: false))
                return
            }
            let feed = data.flatMap { try? JSONDecoder().decode(MineFeed.self, from: $0) }
            done(MineEntry(date: .now, feed: feed, hasKey: true))
        }.resume()
    }
}

struct YourPlayersView: View {
    @Environment(\.widgetFamily) var family
    let entry: MineEntry

    private var rows: Int {
        switch family {
        case .systemMedium: return 4
        case .accessoryRectangular: return 2
        case .accessoryInline: return 1
        default: return 3
        }
    }

    var body: some View {
        let gold = Color(red: 1.0, green: 0.69, blue: 0.0)
        let lines = Array((entry.feed?.players ?? []).prefix(rows))
        Group {
            if family == .accessoryInline {
                if let l = lines.first {
                    Text("\(l.player) · \(l.line)")
                } else {
                    Text(entry.hasKey ? "No player of yours on yet" : "Turn on in Qellys")
                }
            } else {
                VStack(alignment: .leading, spacing: family == .accessoryRectangular ? 1 : 4) {
                    if family != .accessoryRectangular {
                        Text("YOUR PLAYERS").font(.caption2.weight(.heavy)).foregroundStyle(gold)
                    }
                    if !entry.hasKey {
                        Text("Settings → iPhone widget in the Qellys app").font(.caption)
                    } else if lines.isEmpty {
                        Text((entry.feed?.following ?? 0) > 0 ? "None of yours is playing right now."
                             : "Follow players in Qellys to see them here.").font(.caption)
                    } else {
                        ForEach(lines, id: \.player) { l in
                            VStack(alignment: .leading, spacing: 0) {
                                HStack(spacing: 4) {
                                    if l.live { Circle().fill(.red).frame(width: 5, height: 5) }
                                    Text(l.player).font(.caption.weight(.bold)).lineLimit(1)
                                }
                                Text(l.line).font(.caption2).monospacedDigit().lineLimit(1)
                                if family == .systemMedium {
                                    Text("\(l.team)\(l.opp.isEmpty ? "" : " vs \(l.opp)") · \(l.status)")
                                        .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                                }
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
        }
        .widgetURL(URL(string: "https://qellysbook.com/?app=ios#live"))
    }
}

struct YourPlayersWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "QellysYourPlayers", provider: MineProvider()) { entry in
            YourPlayersView(entry: entry).containerBackground(Color.black, for: .widget)
        }
        .configurationDisplayName("Your players")
        .description("The players you follow, with their lines in today's games. Never a pick.")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryRectangular, .accessoryInline])
    }
}
