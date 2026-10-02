import Foundation

/// The user's response to an invitation, as reported by the calendar.
public enum Attendance: String, Sendable, Hashable {
    case accepted
    case tentative
    case declined
    case pending
    /// The event has no attendees, or the user is not one of them.
    case none
}

public struct CalendarColor: Sendable, Hashable {
    public let red: Double
    public let green: Double
    public let blue: Double

    public init(red: Double, green: Double, blue: Double) {
        self.red = red
        self.green = green
        self.blue = blue
    }

    /// Used when a calendar reports no color.
    public static let fallback = CalendarColor(red: 0.26, green: 0.52, blue: 0.96)
}

public struct Meeting: Identifiable, Sendable, Hashable {
    /// Unique per occurrence: recurring events share an event identifier, so the start time is part of the key.
    public let id: String
    /// Identifier understood by EventKit, used to reveal the event in Calendar.app.
    public let eventIdentifier: String?
    public let title: String
    public let start: Date
    public let end: Date
    public let isAllDay: Bool
    public let location: String?
    public let link: MeetingLink?
    public let calendarTitle: String
    public let calendarColor: CalendarColor
    public let attendance: Attendance

    public init(
        id: String,
        eventIdentifier: String? = nil,
        title: String,
        start: Date,
        end: Date,
        isAllDay: Bool = false,
        location: String? = nil,
        link: MeetingLink? = nil,
        calendarTitle: String = "",
        calendarColor: CalendarColor = .fallback,
        attendance: Attendance = .none
    ) {
        self.id = id
        self.eventIdentifier = eventIdentifier
        self.title = title
        self.start = start
        self.end = end
        self.isAllDay = isAllDay
        self.location = location
        self.link = link
        self.calendarTitle = calendarTitle
        self.calendarColor = calendarColor
        self.attendance = attendance
    }

    public var isDeclined: Bool { attendance == .declined }

    public func isInProgress(at now: Date) -> Bool {
        start <= now && now < end
    }

    public func hasEnded(at now: Date) -> Bool {
        end <= now
    }

    /// Fraction of the meeting that has elapsed, clamped to 0...1.
    public func progress(at now: Date) -> Double {
        let total = end.timeIntervalSince(start)
        guard total > 0 else { return 1 }
        return min(max(now.timeIntervalSince(start) / total, 0), 1)
    }
}
