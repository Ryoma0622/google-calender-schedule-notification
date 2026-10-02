import Foundation

public enum MenuBarStyle: String, CaseIterable, Sendable {
    /// "Weekly Standup · 15分後"
    case titleAndCountdown
    /// "14:00 · 15分後"
    case timeAndCountdown
    case iconOnly
}

/// What the menu bar item shows for a moment in the day.
public struct MenuBarStatus: Equatable, Sendable {
    public enum Phase: Sendable {
        /// No meetings today.
        case idle
        case upcoming
        /// The next meeting starts within the imminent window.
        case imminent
        case inProgress
        /// All of today's meetings are over.
        case finished
    }

    public let phase: Phase
    public let text: String

    public init(phase: Phase, text: String) {
        self.phase = phase
        self.text = text
    }

    public static func make(
        agenda: DayAgenda,
        now: Date,
        style: MenuBarStyle,
        maxTitleWidth: Int,
        imminentMinutes: Int = 5,
        calendar: Calendar = .current
    ) -> MenuBarStatus {
        let current = agenda.current(at: now)
        let next = agenda.next(after: now)
        let minutesToNext = next.map { Countdown.minutes(until: $0.start, from: now) }

        func title(_ meeting: Meeting) -> String {
            TextWidth.truncate(meeting.title, maxWidth: maxTitleWidth)
        }

        // Once the next meeting is imminent it matters more than the one that is ending.
        if let next, let minutesToNext, current == nil || minutesToNext <= imminentMinutes {
            let countdown = Countdown.untilStart(minutesToNext)
            let text = switch style {
            case .titleAndCountdown: "\(title(next)) · \(countdown)"
            case .timeAndCountdown: "\(clock(next.start, calendar)) · \(countdown)"
            case .iconOnly: ""
            }
            return MenuBarStatus(phase: minutesToNext <= imminentMinutes ? .imminent : .upcoming, text: text)
        }

        if let current {
            let remaining = Countdown.remaining(Countdown.minutes(until: current.end, from: now))
            let text = switch style {
            case .titleAndCountdown: "\(title(current)) · \(remaining)"
            case .timeAndCountdown: remaining
            case .iconOnly: ""
            }
            return MenuBarStatus(phase: .inProgress, text: text)
        }

        let hasMeetings = agenda.timed.contains { !$0.isDeclined }
        return MenuBarStatus(phase: hasMeetings ? .finished : .idle, text: "")
    }

    private static func clock(_ date: Date, _ calendar: Calendar) -> String {
        let parts = calendar.dateComponents([.hour, .minute], from: date)
        return String(format: "%d:%02d", parts.hour ?? 0, parts.minute ?? 0)
    }
}
