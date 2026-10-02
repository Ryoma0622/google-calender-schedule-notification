import AppKit
import CalBarCore
import EventKit
import Observation
import OSLog
import ServiceManagement

@MainActor
@Observable
final class AppModel {
    let preferences: Preferences
    private(set) var access: CalendarAccess = .notDetermined
    private(set) var now = Date()
    /// Start of the day shown in the popover.
    private(set) var selectedDay: Date
    private(set) var todayAgenda = DayAgenda(meetings: [])
    private(set) var tomorrowAgenda = DayAgenda(meetings: [])
    private(set) var selectedAgenda = DayAgenda(meetings: [])
    private(set) var calendars: [CalendarInfo] = []

    @ObservationIgnored private let service: CalendarService?
    @ObservationIgnored private let notifications = NotificationService()
    @ObservationIgnored private let hotKey = GlobalHotKey()
    @ObservationIgnored private var timer: Timer?
    @ObservationIgnored private var autoJoinedIDs = Set<String>()

    private static let log = Logger(subsystem: "com.calbar.app", category: "calendar")
    private static let autoJoinWindow: TimeInterval = 90
    private static let freeTimeThreshold: TimeInterval = 15 * 60

    init(preferences: Preferences = Preferences()) {
        self.preferences = preferences
        service = CalendarService()
        selectedDay = Calendar.current.startOfDay(for: Date())
    }

    /// A model filled with fixed data, for rendering the UI without calendar access.
    init(previewMeetings: [Meeting], now: Date) {
        preferences = Preferences(defaults: UserDefaults(suiteName: "CalBarPreview") ?? .standard)
        service = nil
        access = .granted
        self.now = now
        selectedDay = Calendar.current.startOfDay(for: now)
        todayAgenda = DayAgenda(meetings: previewMeetings)
        selectedAgenda = todayAgenda
        tomorrowAgenda = DayAgenda(meetings: previewMeetings.map { meeting in
            Meeting(
                id: "tomorrow-\(meeting.id)",
                title: meeting.title,
                start: meeting.start.addingTimeInterval(24 * 60 * 60),
                end: meeting.end.addingTimeInterval(24 * 60 * 60),
                isAllDay: meeting.isAllDay,
                link: meeting.link,
                calendarColor: meeting.calendarColor,
                attendance: meeting.attendance
            )
        })
        calendars = [
            CalendarInfo(id: "work", title: "仕事", sourceTitle: "Google", color: CalendarColor(red: 0.01, green: 0.61, blue: 0.9)),
            CalendarInfo(id: "holiday", title: "日本の祝日", sourceTitle: "Google", color: CalendarColor(red: 0.2, green: 0.71, blue: 0.47)),
        ]
    }

    // MARK: - Derived state

    var isShowingToday: Bool { selectedDay == Calendar.current.startOfDay(for: now) }

    var menuBarStatus: MenuBarStatus {
        MenuBarStatus.make(
            agenda: todayAgenda,
            now: now,
            style: preferences.menuBarStyle,
            maxTitleWidth: preferences.titleLength.rawValue
        )
    }

    var selectedTimeline: [TimelineEntry] {
        selectedAgenda.timeline(minimumGap: preferences.showFreeTime ? Self.freeTimeThreshold : nil)
            .filter { entry in
                guard case .meeting(let meeting) = entry else { return true }
                return preferences.showDeclined || !meeting.isDeclined
            }
    }

    var selectedAllDay: [Meeting] {
        preferences.showAllDay ? selectedAgenda.allDay : []
    }

    var joinTarget: Meeting? { todayAgenda.joinTarget(at: now) }

    var launchesAtLogin: Bool {
        get { SMAppService.mainApp.status == .enabled }
        set {
            do {
                if newValue {
                    try SMAppService.mainApp.register()
                } else {
                    try SMAppService.mainApp.unregister()
                }
            } catch {
                Self.log.error("Failed to change the login item: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    // MARK: - Lifecycle

    func start() {
        guard let service else { return }
        notifications.setUp()
        access = service.access
        if access == .notDetermined {
            requestAccess()
        }
        reload()

        NotificationCenter.default.addObserver(forName: .EKEventStoreChanged, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.reload() }
        }
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didWakeNotification, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }

        let timer = Timer(timeInterval: 5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
        timer.tolerance = 1
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer

        updateHotKey()
    }

    func requestAccess() {
        guard let service else { return }
        Task {
            _ = await service.requestAccess()
            access = service.access
            reload()
        }
    }

    /// Syncs the calendar accounts with their servers, then reloads.
    func refresh() {
        service?.refreshFromServers()
        reload()
    }

    /// Re-reads events and calendars and reschedules notifications. Called whenever
    /// EventKit reports a change, a setting that affects the data changes, or the day rolls over.
    func reload() {
        guard let service else { return }
        now = Date()
        access = service.access
        guard access == .granted else {
            Self.log.notice("Calendar access is not granted: \(String(describing: self.access), privacy: .public)")
            return
        }

        let calendar = Calendar.current
        let today = calendar.startOfDay(for: now)
        let dayAfterTomorrow = calendar.date(byAdding: .day, value: 2, to: today) ?? today
        let disabled = preferences.disabledCalendarIDs
        let upcoming = service.meetings(from: today, to: dayAfterTomorrow, excluding: disabled)

        calendars = service.calendars()
        todayAgenda = DayAgenda(meetings: upcoming.filter { overlaps($0, day: today) })
        let tomorrow = calendar.date(byAdding: .day, value: 1, to: today) ?? today
        tomorrowAgenda = DayAgenda(meetings: upcoming.filter { overlaps($0, day: tomorrow) })
        selectedAgenda = DayAgenda(
            meetings: service.meetings(
                from: selectedDay,
                to: calendar.date(byAdding: .day, value: 1, to: selectedDay) ?? selectedDay,
                excluding: disabled
            )
        )
        Self.log.info(
            "Reloaded \(self.calendars.count) calendars, \(self.todayAgenda.timed.count) timed and \(self.todayAgenda.allDay.count) all-day events today"
        )
        let horizon = now.addingTimeInterval(24 * 60 * 60)
        notifications.schedule(
            upcoming.filter { $0.start < horizon },
            leadMinutes: preferences.leadMinutes,
            now: now
        )
    }

    private func overlaps(_ meeting: Meeting, day: Date) -> Bool {
        let end = Calendar.current.date(byAdding: .day, value: 1, to: day) ?? day
        return meeting.start < end && meeting.end > day
    }

    private func tick() {
        let previousDay = Calendar.current.startOfDay(for: now)
        now = Date()
        let today = Calendar.current.startOfDay(for: now)
        if today != previousDay {
            if selectedDay == previousDay {
                selectedDay = today
            }
            reload()
        }
        autoJoinIfNeeded()
    }

    private func autoJoinIfNeeded() {
        guard preferences.autoJoin else { return }
        for meeting in todayAgenda.timed
        where meeting.link != nil && !meeting.isDeclined && !autoJoinedIDs.contains(meeting.id)
            && meeting.start <= now && now < meeting.start.addingTimeInterval(Self.autoJoinWindow) {
            autoJoinedIDs.insert(meeting.id)
            join(meeting)
        }
    }

    func updateHotKey() {
        if preferences.hotKeyEnabled {
            hotKey.register { [weak self] in self?.joinNow() }
        } else {
            hotKey.unregister()
        }
    }

    // MARK: - Actions

    func join(_ meeting: Meeting) {
        guard let url = meeting.link?.url else { return }
        NSWorkspace.shared.open(url)
    }

    /// Joins the most relevant meeting right now; beeps when there is none.
    func joinNow() {
        guard let target = joinTarget else {
            NSSound.beep()
            return
        }
        join(target)
    }

    func copyLink(of meeting: Meeting) {
        guard let url = meeting.link?.url else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(url.absoluteString, forType: .string)
    }

    func revealInCalendar(_ meeting: Meeting) {
        if let identifier = meeting.eventIdentifier,
           let url = URL(string: "ical://ekevent/\(identifier)?method=show&options=more") {
            NSWorkspace.shared.open(url)
        } else {
            openCalendarApp()
        }
    }

    func openCalendarApp() {
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.iCal") else { return }
        NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration())
    }

    func openPrivacySettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Calendars") else { return }
        NSWorkspace.shared.open(url)
    }

    func showDay(offset: Int) {
        selectedDay = Calendar.current.date(byAdding: .day, value: offset, to: selectedDay) ?? selectedDay
        reload()
    }

    func showToday() {
        selectedDay = Calendar.current.startOfDay(for: Date())
        reload()
    }

    func setCalendar(_ id: String, enabled: Bool) {
        if enabled {
            preferences.disabledCalendarIDs.remove(id)
        } else {
            preferences.disabledCalendarIDs.insert(id)
        }
        reload()
    }

    func sendTestNotification() {
        let start = now.addingTimeInterval(Double(preferences.leadMinutes) * 60)
        let sample = todayAgenda.next(after: now) ?? Meeting(
            id: "test",
            title: "CalBar テスト通知",
            start: start,
            end: start.addingTimeInterval(30 * 60),
            link: MeetingLink.find(in: ["https://meet.google.com/abc-defg-hij"])
        )
        notifications.sendTest(sample)
    }
}
