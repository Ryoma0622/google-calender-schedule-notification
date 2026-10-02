import CalBarCore
import SwiftUI

struct SettingsView: View {
    static let windowID = "settings"

    @Bindable private var preferences: Preferences
    private let model: AppModel
    @State private var launchesAtLogin = false

    init(model: AppModel) {
        self.model = model
        preferences = model.preferences
    }

    var body: some View {
        Form {
            Section("通知") {
                Picker("通知のタイミング", selection: $preferences.leadMinutes) {
                    ForEach(Preferences.leadMinuteChoices, id: \.self) { minutes in
                        Text(minutes == 0 ? "開始時刻" : "\(minutes)分前").tag(minutes)
                    }
                }
                Toggle("開始時刻に会議 URL を自動で開く", isOn: $preferences.autoJoin)
                LabeledContent("通知の確認") {
                    Button("テスト通知を送る") { model.sendTestNotification() }
                }
            }

            Section("メニューバー") {
                Picker("表示内容", selection: $preferences.menuBarStyle) {
                    Text("タイトルと残り時間").tag(MenuBarStyle.titleAndCountdown)
                    Text("開始時刻と残り時間").tag(MenuBarStyle.timeAndCountdown)
                    Text("アイコンのみ").tag(MenuBarStyle.iconOnly)
                }
                Picker("タイトルの長さ", selection: $preferences.titleLength) {
                    ForEach(Preferences.TitleLength.allCases) { length in
                        Text(length.label).tag(length)
                    }
                }
                .disabled(preferences.menuBarStyle != .titleAndCountdown)
            }

            Section("予定リスト") {
                Toggle("終日の予定を表示", isOn: $preferences.showAllDay)
                Toggle("辞退した予定を表示", isOn: $preferences.showDeclined)
                Toggle("15分以上の空き時間を表示", isOn: $preferences.showFreeTime)
            }

            Section {
                if model.calendars.isEmpty {
                    Text("カレンダーが見つかりません。カレンダー.app に Google アカウントを追加してください。")
                        .foregroundStyle(.secondary)
                }
                ForEach(model.calendars) { calendar in
                    Toggle(isOn: Binding(
                        get: { !preferences.disabledCalendarIDs.contains(calendar.id) },
                        set: { model.setCalendar(calendar.id, enabled: $0) }
                    )) {
                        HStack(spacing: 8) {
                            Circle()
                                .fill(calendar.color.color)
                                .frame(width: 10, height: 10)
                            Text(calendar.title)
                            Text(calendar.sourceTitle)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            } header: {
                Text("表示するカレンダー")
            } footer: {
                Text("オフにしたカレンダーの予定は、一覧・メニューバー・通知のすべてから除外されます。")
                    .foregroundStyle(.secondary)
            }

            Section("一般") {
                Toggle("ログイン時に CalBar を起動", isOn: $launchesAtLogin)
                    .onChange(of: launchesAtLogin) { _, newValue in
                        model.launchesAtLogin = newValue
                        launchesAtLogin = model.launchesAtLogin
                    }
                Toggle("\(GlobalHotKey.displayName) で次の会議に参加", isOn: $preferences.hotKeyEnabled)
                    .onChange(of: preferences.hotKeyEnabled) { model.updateHotKey() }
            }
        }
        .formStyle(.grouped)
        .frame(width: 480)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear { launchesAtLogin = model.launchesAtLogin }
        .onChange(of: preferences.leadMinutes) { model.reload() }
    }
}
