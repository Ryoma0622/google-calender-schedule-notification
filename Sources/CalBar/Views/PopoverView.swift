import CalBarCore
import SwiftUI

struct PopoverView: View {
    let model: AppModel
    @Environment(\.openWindow) private var openWindow
    @State private var timelineHeight: CGFloat = 0

    private static let width: CGFloat = 380
    private static let maxTimelineHeight: CGFloat = 400

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if model.access == .granted {
                content
            } else {
                AccessView(model: model)
            }
            Divider()
            footer
        }
        .frame(width: Self.width)
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(Format.monthDay(model.selectedDay))
                    .font(.title2.weight(.semibold))
                HStack(spacing: 6) {
                    Text(Format.weekday(model.selectedDay))
                    if let relative = Format.relativeDay(model.selectedDay, today: model.now) {
                        Text(relative)
                            .foregroundStyle(.tint)
                    }
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }
            Spacer()
            HStack(spacing: 2) {
                IconButton("chevron.left", help: "前の日") { model.showDay(offset: -1) }
                Button("今日") { model.showToday() }
                    .buttonStyle(.borderless)
                    .font(.callout.weight(.medium))
                    .padding(.horizontal, 4)
                    .disabled(model.isShowingToday)
                IconButton("chevron.right", help: "次の日") { model.showDay(offset: 1) }
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 14)
        .padding(.bottom, 10)
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        VStack(alignment: .leading, spacing: 12) {
            if model.isShowingToday {
                NowCard(model: model)
            }
            if !model.selectedAllDay.isEmpty {
                AllDayStrip(meetings: model.selectedAllDay)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 12)

        let timeline = model.selectedTimeline
        if timeline.isEmpty {
            if !model.isShowingToday {
                Text("予定はありません")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, 20)
            }
        } else {
            ScrollViewReader { proxy in
                ScrollView {
                    timelineList(timeline)
                        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { timelineHeight = $0 }
                }
                .frame(height: min(max(timelineHeight, 1), Self.maxTimelineHeight))
                .onAppear { scrollToNow(proxy, timeline) }
            }
        }
    }

    private func timelineList(_ timeline: [TimelineEntry]) -> some View {
        let nowMarkerID = nowMarkerTarget(in: timeline)
        return LazyVStack(alignment: .leading, spacing: 2) {
            ForEach(timeline) { entry in
                if entry.id == nowMarkerID {
                    NowMarker(now: model.now)
                }
                switch entry {
                case .meeting(let meeting):
                    MeetingRow(model: model, meeting: meeting)
                        .id(entry.id)
                case .gap(let start, let end):
                    GapRow(start: start, end: end, now: model.now)
                        .id(entry.id)
                }
            }
        }
        .padding(.horizontal, 8)
        .padding(.bottom, 10)
    }

    /// On today, the "now" line goes before the first upcoming entry, unless a meeting is in progress
    /// (its highlighted row already shows where we are).
    private func nowMarkerTarget(in timeline: [TimelineEntry]) -> String? {
        guard model.isShowingToday, model.todayAgenda.current(at: model.now) == nil else { return nil }
        return timeline.first { entry in
            switch entry {
            case .meeting(let meeting): meeting.start > model.now
            case .gap(let start, _): start > model.now
            }
        }?.id
    }

    private func scrollToNow(_ proxy: ScrollViewProxy, _ timeline: [TimelineEntry]) {
        guard model.isShowingToday else { return }
        let firstRelevant = timeline.first { entry in
            guard case .meeting(let meeting) = entry else { return false }
            return !meeting.hasEnded(at: model.now)
        }
        if let firstRelevant {
            proxy.scrollTo(firstRelevant.id, anchor: .top)
        }
    }

    // MARK: - Footer

    private var footer: some View {
        HStack(spacing: 4) {
            if model.preferences.hotKeyEnabled {
                Text("\(GlobalHotKey.displayName) で次の会議に参加")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            Spacer()
            IconButton("arrow.clockwise", help: "カレンダーを同期") { model.refresh() }
            IconButton("calendar", help: "カレンダー.app を開く") { model.openCalendarApp() }
            IconButton("gearshape", help: "設定") {
                openWindow(id: SettingsView.windowID)
                NSApp.activate()
            }
            IconButton("power", help: "CalBar を終了") { NSApp.terminate(nil) }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }
}

// MARK: - Pieces

struct IconButton: View {
    let systemName: String
    let help: String
    let action: () -> Void

    init(_ systemName: String, help: String, action: @escaping () -> Void) {
        self.systemName = systemName
        self.help = help
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .frame(width: 24, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .help(help)
        .accessibilityLabel(help)
    }
}

private struct AllDayStrip: View {
    let meetings: [Meeting]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("終日")
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
            ForEach(meetings) { meeting in
                HStack(spacing: 6) {
                    Circle()
                        .fill(meeting.calendarColor.color)
                        .frame(width: 7, height: 7)
                    Text(meeting.title)
                        .font(.callout)
                        .lineLimit(1)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(meeting.calendarColor.color.opacity(0.14), in: Capsule())
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct NowMarker: View {
    let now: Date

    var body: some View {
        HStack(spacing: 6) {
            Text(Format.clock(now))
                .font(.caption2.weight(.semibold).monospacedDigit())
                .foregroundStyle(.red)
                .frame(width: 44, alignment: .trailing)
            Circle().fill(.red).frame(width: 6, height: 6)
            Rectangle().fill(.red.opacity(0.7)).frame(height: 1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 2)
        .accessibilityLabel("現在時刻 \(Format.clock(now))")
    }
}

private struct GapRow: View {
    let start: Date
    let end: Date
    let now: Date

    var body: some View {
        let minutes = Int(end.timeIntervalSince(start) / 60)
        HStack(spacing: 10) {
            Color.clear.frame(width: 44)
            Image(systemName: "cup.and.saucer")
                .font(.caption)
            Text("空き \(Countdown.duration(minutes))")
                .font(.caption)
            Text("\(Format.clock(start))〜\(Format.clock(end))")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.tertiary)
        }
        .foregroundStyle(.secondary)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .opacity(end <= now ? 0.5 : 1)
    }
}

private struct AccessView: View {
    let model: AppModel

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "calendar.badge.exclamationmark")
                .font(.system(size: 34))
                .foregroundStyle(.secondary)
            Text("カレンダーへのアクセスが必要です")
                .font(.headline)
            Text("macOS のカレンダーに追加した Google アカウントの予定を表示します。")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            if model.access == .notDetermined {
                Button("アクセスを許可") { model.requestAccess() }
                    .buttonStyle(.borderedProminent)
            } else {
                Button("システム設定を開く") { model.openPrivacySettings() }
                    .buttonStyle(.borderedProminent)
                Text("「プライバシーとセキュリティ > カレンダー」で CalBar にフルアクセスを許可してください。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity)
    }
}
