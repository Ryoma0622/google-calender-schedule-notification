import CalBarCore
import Foundation
import Observation

/// User settings persisted in UserDefaults.
@MainActor
@Observable
final class Preferences {
    enum TitleLength: Int, CaseIterable, Identifiable {
        case short = 16
        case standard = 24
        case long = 36

        var id: Int { rawValue }

        var label: String {
            switch self {
            case .short: "短め"
            case .standard: "標準"
            case .long: "長め"
            }
        }
    }

    private enum Key {
        static let leadMinutes = "leadMinutes"
        static let autoJoin = "autoJoin"
        static let menuBarStyle = "menuBarStyle"
        static let titleLength = "titleLength"
        static let showAllDay = "showAllDay"
        static let showDeclined = "showDeclined"
        static let showFreeTime = "showFreeTime"
        static let disabledCalendarIDs = "disabledCalendarIDs"
        static let hotKeyEnabled = "hotKeyEnabled"
        static let migratedLegacyConfig = "migratedLegacyConfig"
    }

    static let leadMinuteChoices = [0, 1, 3, 5, 10, 15]

    @ObservationIgnored private let defaults: UserDefaults

    var leadMinutes: Int { didSet { defaults.set(leadMinutes, forKey: Key.leadMinutes) } }
    var autoJoin: Bool { didSet { defaults.set(autoJoin, forKey: Key.autoJoin) } }
    var menuBarStyle: MenuBarStyle { didSet { defaults.set(menuBarStyle.rawValue, forKey: Key.menuBarStyle) } }
    var titleLength: TitleLength { didSet { defaults.set(titleLength.rawValue, forKey: Key.titleLength) } }
    var showAllDay: Bool { didSet { defaults.set(showAllDay, forKey: Key.showAllDay) } }
    var showDeclined: Bool { didSet { defaults.set(showDeclined, forKey: Key.showDeclined) } }
    var showFreeTime: Bool { didSet { defaults.set(showFreeTime, forKey: Key.showFreeTime) } }
    /// Calendars are shown unless listed here, so newly added calendars appear by default.
    var disabledCalendarIDs: Set<String> {
        didSet { defaults.set(Array(disabledCalendarIDs).sorted(), forKey: Key.disabledCalendarIDs) }
    }
    var hotKeyEnabled: Bool { didSet { defaults.set(hotKeyEnabled, forKey: Key.hotKeyEnabled) } }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        Self.migrateLegacyConfig(into: defaults)
        defaults.register(defaults: [
            Key.leadMinutes: 5,
            Key.autoJoin: false,
            Key.menuBarStyle: MenuBarStyle.titleAndCountdown.rawValue,
            // Short by default so the item is not pushed behind the notch on crowded menu bars.
            Key.titleLength: TitleLength.short.rawValue,
            Key.showAllDay: true,
            Key.showDeclined: false,
            Key.showFreeTime: true,
            Key.hotKeyEnabled: true,
        ])
        leadMinutes = defaults.integer(forKey: Key.leadMinutes)
        autoJoin = defaults.bool(forKey: Key.autoJoin)
        menuBarStyle = MenuBarStyle(rawValue: defaults.string(forKey: Key.menuBarStyle) ?? "") ?? .titleAndCountdown
        titleLength = TitleLength(rawValue: defaults.integer(forKey: Key.titleLength)) ?? .short
        showAllDay = defaults.bool(forKey: Key.showAllDay)
        showDeclined = defaults.bool(forKey: Key.showDeclined)
        showFreeTime = defaults.bool(forKey: Key.showFreeTime)
        disabledCalendarIDs = Set(defaults.stringArray(forKey: Key.disabledCalendarIDs) ?? [])
        hotKeyEnabled = defaults.bool(forKey: Key.hotKeyEnabled)
    }

    /// Carries the settings over from the Python version's `~/.calbar/config.json`, once.
    private static func migrateLegacyConfig(into defaults: UserDefaults) {
        guard !defaults.bool(forKey: Key.migratedLegacyConfig) else { return }
        defaults.set(true, forKey: Key.migratedLegacyConfig)

        let url = FileManager.default.homeDirectoryForCurrentUser.appending(path: ".calbar/config.json")
        guard let data = try? Data(contentsOf: url),
              let legacy = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }

        if let minutes = legacy["notification_minutes_before"] as? Int {
            // Snap to the nearest choice the settings screen offers.
            let nearest = leadMinuteChoices.min { abs($0 - minutes) < abs($1 - minutes) } ?? 5
            defaults.set(nearest, forKey: Key.leadMinutes)
        }
        if let autoOpen = legacy["auto_open_meeting_on_start"] as? Bool {
            defaults.set(autoOpen, forKey: Key.autoJoin)
        }
        if let showAllDay = legacy["show_all_day_events"] as? Bool {
            defaults.set(showAllDay, forKey: Key.showAllDay)
        }
    }
}
