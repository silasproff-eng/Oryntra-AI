import SwiftUI
import WidgetKit

private let appGroup = "group.com.oryntraai.shared"

struct OryntraEntry: TimelineEntry {
  let date: Date
  let ticker: String
  let signal: String
  let price: String
  let quality: String
}

struct OryntraProvider: TimelineProvider {
  func placeholder(in context: Context) -> OryntraEntry {
    OryntraEntry(date: Date(), ticker: "AAPL", signal: "WATCH", price: "$—", quality: "—")
  }

  func getSnapshot(in context: Context, completion: @escaping (OryntraEntry) -> Void) {
    completion(readEntry())
  }

  func getTimeline(in context: Context, completion: @escaping (Timeline<OryntraEntry>) -> Void) {
    let entry = readEntry()
    let nextRefresh =
      Calendar.current.date(byAdding: .minute, value: 30, to: Date())
      ?? Date().addingTimeInterval(1800)
    completion(Timeline(entries: [entry], policy: .after(nextRefresh)))
  }

  private func readEntry() -> OryntraEntry {
    let defaults = UserDefaults(suiteName: appGroup)
    return OryntraEntry(
      date: Date(),
      ticker: defaults?.string(forKey: "ticker") ?? "Oryntra AI",
      signal: defaults?.string(forKey: "signal") ?? "Run a scan",
      price: defaults?.string(forKey: "price") ?? "—",
      quality: defaults?.string(forKey: "quality") ?? "—"
    )
  }
}

struct OryntraWidgetView: View {
  var entry: OryntraProvider.Entry

  var body: some View {
    ZStack {
      LinearGradient(
        colors: [
          Color.black, Color(red: 0.02, green: 0.10, blue: 0.18),
          Color(red: 0.06, green: 0.16, blue: 0.27),
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
      )
      VStack(alignment: .leading, spacing: 6) {
        HStack {
          Text(entry.ticker)
            .font(.headline)
          Spacer()
          Image(systemName: "chart.line.uptrend.xyaxis")
            .foregroundStyle(Color(red: 0.22, green: 0.81, blue: 0.95))
        }
        Text(entry.signal)
          .font(.title3.bold())
          .foregroundStyle(Color(red: 0.22, green: 0.81, blue: 0.95))
          .lineLimit(1)
        HStack {
          Text(entry.price)
          Spacer()
          Text("Q: \(entry.quality)")
        }
        .font(.caption)
        .foregroundStyle(.secondary)
        Spacer(minLength: 0)
        Text("Educational analysis only")
          .font(.caption2)
          .foregroundStyle(.secondary)
      }
      .padding()
    }
    .widgetURL(URL(string: "oryntra://scanner"))
  }
}

struct OryntraWidget: Widget {
  let kind = "OryntraWidget"

  var body: some WidgetConfiguration {
    StaticConfiguration(kind: kind, provider: OryntraProvider()) { entry in
      if (17.0, *) {
        OryntraWidgetView(entry: entry)
          .containerBackground(.clear, for: .widget)
      } else {
        OryntraWidgetView(entry: entry)
      }
    }
    .configurationDisplayName("Latest Oryntra AI Scan")
    .description("Shows the most recent ticker scan saved from Oryntra AI.")
    .supportedFamilies([.systemSmall, .systemMedium])
  }
}

@main
struct OryntraWidgetBundle: WidgetBundle {
  var body: some Widget {
    OryntraWidget()
  }
}
