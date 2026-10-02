#if DEBUG
import AppKit
import CalBarCore
import SwiftUI

/// Renders the popover and the settings window to PNG with sample data:
/// `CalBar --render-previews <directory>` (debug builds only).
@MainActor
enum PreviewRenderer {
    static func render(to directory: URL) {
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        func at(_ hour: Int, _ minute: Int = 0) -> Date {
            calendar.date(bySettingHour: hour, minute: minute, second: 0, of: today) ?? today
        }

        let work = CalendarColor(red: 0.01, green: 0.61, blue: 0.9)
        let focus = CalendarColor(red: 0.47, green: 0.36, blue: 0.85)
        let meet = MeetingLink.find(in: ["https://meet.google.com/abc-defg-hij"])
        let zoom = MeetingLink.find(in: ["https://example.zoom.us/j/12345678901"])
        let meetings = [
            Meeting(id: "1", title: "朝会", start: at(9, 30), end: at(10), link: meet, calendarColor: work, attendance: .accepted),
            Meeting(id: "2", title: "Frontend Daily Sync", start: at(10, 45), end: at(11), link: meet, calendarColor: work, attendance: .accepted),
            Meeting(id: "3", title: "ランチ", start: at(12), end: at(13), calendarColor: focus),
            Meeting(id: "4", title: "Design Review: 新しいオンボーディング", start: at(14), end: at(15), location: "会議室 18F-A", link: zoom, calendarColor: work, attendance: .accepted),
            Meeting(id: "5", title: "全社ミーティング", start: at(15), end: at(16), link: zoom, calendarColor: work, attendance: .declined),
            Meeting(id: "6", title: "1on1", start: at(15, 0), end: at(15, 30), link: meet, calendarColor: work, attendance: .tentative),
            Meeting(id: "7", title: "スプリント計画の準備", start: at(16, 30), end: at(17, 30), calendarColor: focus),
            Meeting(id: "8", title: "体育の日", start: today, end: calendar.date(byAdding: .day, value: 1, to: today) ?? today, isAllDay: true, calendarColor: CalendarColor(red: 0.2, green: 0.71, blue: 0.47)),
        ]

        for (name, hour, minute) in [("popover-in-meeting", 14, 20), ("popover-upcoming", 13, 52), ("popover-finished", 18, 10)] {
            let model = AppModel(previewMeetings: meetings, now: at(hour, minute))
            snapshot(PopoverView(model: model), name: name, in: directory)
            if name == "popover-in-meeting" {
                snapshot(MenuBarLabel(model: model).fixedSize().padding(6), name: "menubar-in-meeting", in: directory)
                snapshot(SettingsView(model: model), name: "settings", in: directory)
            }
            if name == "popover-upcoming" {
                snapshot(MenuBarLabel(model: model).fixedSize().padding(6), name: "menubar-upcoming", in: directory)
            }
        }
    }

    private static func snapshot(_ view: some View, name: String, in directory: URL) {
        let hosting = NSHostingView(rootView: view.background(Color(nsColor: .windowBackgroundColor)))
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 10, height: 10),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.contentView = hosting
        // Let state that depends on layout (such as the timeline height) settle before capturing.
        for _ in 0..<3 {
            hosting.setFrameSize(hosting.fittingSize)
            window.setContentSize(hosting.fittingSize)
            hosting.layoutSubtreeIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        guard let bitmap = hosting.bitmapImageRepForCachingDisplay(in: hosting.bounds) else { return }
        hosting.cacheDisplay(in: hosting.bounds, to: bitmap)
        try? bitmap.representation(using: .png, properties: [:])?
            .write(to: directory.appending(path: "\(name).png"))
    }
}
#endif
