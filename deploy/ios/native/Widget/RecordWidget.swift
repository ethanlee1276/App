// The Home Screen widget: the record, last night, and how many picks each
// league has up today. It asks https://qellysbook.com/api/widget every half
// hour (engine/widgetfeed). A widget cannot sign in, so it shows only what
// the site shows everybody — never a pick. The JSON keys below are the
// feed's; tests/test_the_iphone_widget_and_lock_screen.py holds them equal.
//
// Needs iOS 17 (containerBackground). Not compiled here.

import SwiftUI
import WidgetKit

struct WidgetFeed: Decodable {
    struct Record: Decodable { let w: Int; let l: Int; let p: Int; let units: Double; let roi: Double }
    struct Night: Decodable { let date: String; let w: Int; let l: Int; let p: Int; let units: Double }
    struct Board: Decodable { let league: String; let sport: String; let picks: Int; let url: String }
    let record: Record?
    let last_night: Night?
    let tonight: [Board]
}

struct RecordEntry: TimelineEntry {
    let date: Date
    let feed: WidgetFeed?
}

struct RecordProvider: TimelineProvider {
    static let feedURL = URL(string: "https://qellysbook.com/api/widget")!

    func placeholder(in context: Context) -> RecordEntry { RecordEntry(date: .now, feed: nil) }

    func getSnapshot(in context: Context, completion: @escaping (RecordEntry) -> Void) {
        load(completion)
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<RecordEntry>) -> Void) {
        load { entry in
            completion(Timeline(entries: [entry], policy: .after(Date().addingTimeInterval(30 * 60))))
        }
    }

    private func load(_ done: @escaping (RecordEntry) -> Void) {
        URLSession.shared.dataTask(with: Self.feedURL) { data, _, _ in
            let feed = data.flatMap { try? JSONDecoder().decode(WidgetFeed.self, from: $0) }
            done(RecordEntry(date: .now, feed: feed))
        }.resume()
    }
}

private func units(_ u: Double) -> String { String(format: "%@%.1fu", u >= 0 ? "+" : "−", abs(u)) }

struct RecordWidgetView: View {
    @Environment(\.widgetFamily) var family
    let entry: RecordEntry

    var body: some View {
        let gold = Color(red: 1.0, green: 0.69, blue: 0.0)
        VStack(alignment: .leading, spacing: 4) {
            Text("QELLYS").font(.caption2.weight(.heavy)).foregroundStyle(gold)
            if let r = entry.feed?.record {
                Text("\(r.w)–\(r.l)\(r.p > 0 ? "–\(r.p)" : "")").font(.title2.weight(.bold)).monospacedDigit()
                Text(units(r.units)).font(.subheadline.weight(.semibold)).foregroundStyle(r.units >= 0 ? .green : .red)
            } else {
                Text("The record").font(.headline)
            }
            if let n = entry.feed?.last_night, family != .systemSmall || entry.feed?.record == nil {
                Text("Last night \(n.w)–\(n.l), \(units(n.units))").font(.caption).foregroundStyle(.secondary)
            }
            if family == .systemMedium, let boards = entry.feed?.tonight, !boards.isEmpty {
                Text(boards.map { "\($0.league) \($0.picks)" }.joined(separator: " · "))
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .widgetURL(URL(string: "https://qellysbook.com/?app=ios#record"))
    }
}

struct RecordWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "QellysRecord", provider: RecordProvider()) { entry in
            RecordWidgetView(entry: entry).containerBackground(Color.black, for: .widget)
        }
        .configurationDisplayName("Qellys record")
        .description("The record, last night, and today's boards. Never a pick.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
