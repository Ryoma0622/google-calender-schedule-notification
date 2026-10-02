import AppKit
import CalBarCore
import EventKit

struct CalendarInfo: Identifiable, Hashable {
    let id: String
    let title: String
    let sourceTitle: String
    let color: CalendarColor
}

enum CalendarAccess {
    case notDetermined
    case granted
    case denied
}

/// Reads events from the macOS calendar database, which includes Google accounts
/// added under System Settings > Internet Accounts.
@MainActor
final class CalendarService {
    private let store = EKEventStore()

    var access: CalendarAccess {
        switch EKEventStore.authorizationStatus(for: .event) {
        case .fullAccess: .granted
        case .notDetermined: .notDetermined
        default: .denied
        }
    }

    func requestAccess() async -> Bool {
        await withCheckedContinuation { continuation in
            store.requestFullAccessToEvents { granted, _ in
                continuation.resume(returning: granted)
            }
        }
    }

    /// Asks the accounts to sync with their servers; changes arrive as `EKEventStoreChanged`.
    func refreshFromServers() {
        store.refreshSourcesIfNecessary()
    }

    func calendars() -> [CalendarInfo] {
        store.calendars(for: .event)
            .filter { $0.type != .birthday }
            .map {
                CalendarInfo(
                    id: $0.calendarIdentifier,
                    title: $0.title,
                    sourceTitle: $0.source?.title ?? "",
                    color: Self.rgb($0.cgColor)
                )
            }
            .sorted { ($0.sourceTitle, $0.title) < ($1.sourceTitle, $1.title) }
    }

    func meetings(from start: Date, to end: Date, excluding disabledCalendarIDs: Set<String>) -> [Meeting] {
        let calendars = store.calendars(for: .event).filter {
            $0.type != .birthday && !disabledCalendarIDs.contains($0.calendarIdentifier)
        }
        guard !calendars.isEmpty else { return [] }

        let predicate = store.predicateForEvents(withStart: start, end: end, calendars: calendars)
        return store.events(matching: predicate).map(Self.meeting)
    }

    private static func meeting(from event: EKEvent) -> Meeting {
        Meeting(
            id: "\(event.calendarItemIdentifier)-\(Int(event.startDate.timeIntervalSince1970))",
            eventIdentifier: event.eventIdentifier,
            title: event.title?.isEmpty == false ? event.title : "（タイトルなし）",
            start: event.startDate,
            end: event.endDate,
            isAllDay: event.isAllDay,
            location: event.location?.isEmpty == false ? event.location : nil,
            link: MeetingLink.find(in: [event.url?.absoluteString, event.location, event.notes]),
            calendarTitle: event.calendar?.title ?? "",
            calendarColor: rgb(event.calendar?.cgColor),
            attendance: attendance(of: event)
        )
    }

    private static func attendance(of event: EKEvent) -> Attendance {
        guard let me = event.attendees?.first(where: \.isCurrentUser) else { return .none }
        return switch me.participantStatus {
        case .accepted: .accepted
        case .tentative: .tentative
        case .declined: .declined
        case .pending: .pending
        default: .none
        }
    }

    private static func rgb(_ cgColor: CGColor?) -> CalendarColor {
        guard let cgColor, let color = NSColor(cgColor: cgColor)?.usingColorSpace(.sRGB) else {
            return .fallback
        }
        return CalendarColor(red: color.redComponent, green: color.greenComponent, blue: color.blueComponent)
    }
}
