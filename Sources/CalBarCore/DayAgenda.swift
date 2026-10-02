import Foundation

public enum TimelineEntry: Identifiable, Sendable, Hashable {
    case meeting(Meeting)
    case gap(start: Date, end: Date)

    public var id: String {
        switch self {
        case .meeting(let meeting): meeting.id
        case .gap(let start, _): "gap-\(start.timeIntervalSince1970)"
        }
    }
}

/// One day's meetings, with the queries the menu bar and the popover need.
public struct DayAgenda: Sendable {
    public let allDay: [Meeting]
    /// Timed meetings sorted by start, then by end.
    public let timed: [Meeting]

    public init(meetings: [Meeting]) {
        allDay = meetings.filter(\.isAllDay).sorted { $0.title < $1.title }
        timed = meetings.filter { !$0.isAllDay }.sorted {
            ($0.start, $0.end) < ($1.start, $1.end)
        }
    }

    /// Meetings that occupy the user's time; declined ones do not.
    private var attending: [Meeting] {
        timed.filter { !$0.isDeclined }
    }

    /// The in-progress meeting that started most recently.
    public func current(at now: Date) -> Meeting? {
        attending.last { $0.isInProgress(at: now) }
    }

    public func next(after now: Date) -> Meeting? {
        attending.first { $0.start > now }
    }

    /// The meeting a "join" shortcut should open: the latest-starting meeting with a link
    /// that is in progress or starts within `lookahead`. Near the end of one meeting this
    /// prefers the meeting that is about to start.
    public func joinTarget(at now: Date, lookahead: TimeInterval = 5 * 60) -> Meeting? {
        attending
            .filter { $0.link != nil && $0.start <= now.addingTimeInterval(lookahead) && now < $0.end }
            .last
    }

    /// Timed meetings interleaved with free slots of at least `minimumGap`
    /// between the first start and the last end of the day.
    public func timeline(minimumGap: TimeInterval?) -> [TimelineEntry] {
        guard let minimumGap else { return timed.map(TimelineEntry.meeting) }

        var entries: [TimelineEntry] = []
        var busyUntil: Date?
        for meeting in timed {
            if !meeting.isDeclined {
                if let busyUntil, meeting.start.timeIntervalSince(busyUntil) >= minimumGap {
                    entries.append(.gap(start: busyUntil, end: meeting.start))
                }
                busyUntil = max(busyUntil ?? meeting.end, meeting.end)
            }
            entries.append(.meeting(meeting))
        }
        return entries
    }
}
