import CalBarCore
import SwiftUI

extension CalendarColor {
    var color: Color { Color(red: red, green: green, blue: blue) }
}

enum Format {
    private static let japanese = Locale(identifier: "ja_JP")

    /// "14:05"
    static func clock(_ date: Date) -> String {
        date.formatted(Date.FormatStyle(date: .omitted, time: .shortened).locale(japanese))
    }

    /// "10月2日"
    static func monthDay(_ date: Date) -> String {
        let parts = Calendar.current.dateComponents([.month, .day], from: date)
        return "\(parts.month ?? 0)月\(parts.day ?? 0)日"
    }

    /// "木曜日"
    static func weekday(_ date: Date) -> String {
        date.formatted(Date.FormatStyle().weekday(.wide).locale(japanese))
    }

    /// "今日" / "明日" / "昨日", or nil for other days.
    static func relativeDay(_ day: Date, today: Date) -> String? {
        let calendar = Calendar.current
        let offset = calendar.dateComponents([.day], from: calendar.startOfDay(for: today), to: day).day
        return switch offset {
        case 0: "今日"
        case 1: "明日"
        case -1: "昨日"
        default: nil
        }
    }
}

extension MenuBarStatus.Phase {
    var symbolName: String {
        switch self {
        case .idle: "calendar"
        case .upcoming: "calendar.badge.clock"
        case .imminent: "bell.fill"
        case .inProgress: "record.circle"
        case .finished: "calendar.badge.checkmark"
        }
    }
}

extension MeetingLink.Provider {
    var symbolName: String {
        switch self {
        case .meet, .zoom, .webex: "video.fill"
        case .teams: "person.2.wave.2.fill"
        }
    }
}
