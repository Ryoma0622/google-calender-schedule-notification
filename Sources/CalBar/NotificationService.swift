import AppKit
import CalBarCore
import UserNotifications

/// Schedules "meeting starts soon" notifications with Join and Snooze actions.
@MainActor
final class NotificationService: NSObject, UNUserNotificationCenterDelegate {
    private enum Category {
        static let withLink = "MEETING_WITH_LINK"
        static let withoutLink = "MEETING"
    }

    private enum Action {
        static let join = "JOIN"
        static let snooze = "SNOOZE"
    }

    private enum UserInfo {
        static let url = "url"
        static let start = "start"
    }

    /// Resolved on use: `current()` throws outside an app bundle, such as in the preview renderer.
    private var center: UNUserNotificationCenter { .current() }
    /// Requests this service has scheduled or delivered, so a reload never repeats a notification.
    private var handledIDs = Set<String>()

    func setUp() {
        center.delegate = self
        let join = UNNotificationAction(identifier: Action.join, title: "参加する")
        let snooze = UNNotificationAction(identifier: Action.snooze, title: "開始1分前に再通知")
        center.setNotificationCategories([
            UNNotificationCategory(identifier: Category.withLink, actions: [join, snooze], intentIdentifiers: []),
            UNNotificationCategory(identifier: Category.withoutLink, actions: [snooze], intentIdentifiers: []),
        ])
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// Replaces the pending notifications with ones for `meetings`.
    /// A meeting whose notification time has already passed but has not started yet
    /// (for example right after launch or wake) is notified immediately, once.
    func schedule(_ meetings: [Meeting], leadMinutes: Int, now: Date) {
        center.removePendingNotificationRequests(withIdentifiers: Array(handledIDs))

        for meeting in meetings where !meeting.isAllDay && !meeting.isDeclined && meeting.start > now {
            let id = "meeting.\(meeting.id).\(leadMinutes)"
            let fireDate = meeting.start.addingTimeInterval(-Double(leadMinutes) * 60)
            let trigger: UNNotificationTrigger?
            if fireDate > now {
                let components = Calendar.current.dateComponents(
                    [.year, .month, .day, .hour, .minute, .second], from: fireDate
                )
                trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
            } else if !handledIDs.contains(id) {
                trigger = nil
            } else {
                continue
            }
            handledIDs.insert(id)
            let content = Self.content(for: meeting, now: now)
            center.add(UNNotificationRequest(identifier: id, content: content, trigger: trigger))
        }
    }

    func sendTest(_ meeting: Meeting) {
        let content = Self.content(for: meeting, now: Date())
        center.add(UNNotificationRequest(identifier: "test.\(UUID())", content: content, trigger: nil))
    }

    private static func content(for meeting: Meeting, now: Date) -> UNMutableNotificationContent {
        let content = UNMutableNotificationContent()
        content.title = meeting.title
        let minutes = Countdown.minutes(until: meeting.start, from: now)
        let when = minutes <= 0 ? "まもなく開始" : "\(minutes)分後に開始"
        content.subtitle = "\(meeting.start.formatted(date: .omitted, time: .shortened)) · \(when)"
        content.body = [meeting.link.map { "\($0.provider.rawValue) で参加できます" }, meeting.location]
            .compactMap { $0 }
            .joined(separator: "\n")
        content.sound = .default
        content.categoryIdentifier = meeting.link == nil ? Category.withoutLink : Category.withLink
        content.threadIdentifier = "meetings"
        var userInfo: [String: Any] = [UserInfo.start: meeting.start.timeIntervalSince1970]
        if let url = meeting.link?.url {
            userInfo[UserInfo.url] = url.absoluteString
        }
        content.userInfo = userInfo
        return content
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        let content = response.notification.request.content
        switch response.actionIdentifier {
        case Action.join, UNNotificationDefaultActionIdentifier:
            guard let raw = content.userInfo[UserInfo.url] as? String, let url = URL(string: raw) else { return }
            await MainActor.run { _ = NSWorkspace.shared.open(url) }
        case Action.snooze:
            guard let start = content.userInfo[UserInfo.start] as? Double,
                  let snoozed = content.mutableCopy() as? UNMutableNotificationContent
            else { return }
            let delay = Date(timeIntervalSince1970: start - 60).timeIntervalSinceNow
            guard delay > 0 else { return }
            snoozed.subtitle = "まもなく開始"
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: delay, repeats: false)
            try? await center.add(UNNotificationRequest(identifier: "snooze.\(UUID())", content: snoozed, trigger: trigger))
        default:
            break
        }
    }
}
