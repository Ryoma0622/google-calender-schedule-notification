import Foundation

public enum Countdown {
    /// Whole minutes from `now` until `date`, rounded up so that "14:00" seen at 13:45:30 reads as 15.
    public static func minutes(until date: Date, from now: Date) -> Int {
        max(Int((date.timeIntervalSince(now) / 60).rounded(.up)), 0)
    }

    /// "まもなく" / "15分後" / "1時間後" / "1時間20分後"
    public static func untilStart(_ minutes: Int) -> String {
        minutes <= 0 ? "まもなく" : duration(minutes) + "後"
    }

    /// "残り12分" / "残り1時間5分"
    public static func remaining(_ minutes: Int) -> String {
        "残り" + duration(max(minutes, 1))
    }

    /// "45分" / "1時間" / "1時間30分"
    public static func duration(_ minutes: Int) -> String {
        let hours = minutes / 60
        let rest = minutes % 60
        switch (hours, rest) {
        case (0, _): return "\(rest)分"
        case (_, 0): return "\(hours)時間"
        default: return "\(hours)時間\(rest)分"
        }
    }
}

public enum TextWidth {
    /// Approximate rendered width: East Asian wide characters count as 2, others as 1.
    public static func of(_ text: String) -> Int {
        text.unicodeScalars.reduce(0) { $0 + (isWide($1) ? 2 : 1) }
    }

    /// Truncates to at most `maxWidth`, ending with "…" when something was cut.
    public static func truncate(_ text: String, maxWidth: Int) -> String {
        guard of(text) > maxWidth else { return text }
        var result = ""
        var width = 0
        for character in text {
            let charWidth = of(String(character))
            if width + charWidth > maxWidth - 1 { break }
            result.append(character)
            width += charWidth
        }
        return result.trimmingCharacters(in: .whitespaces) + "…"
    }

    private static func isWide(_ scalar: Unicode.Scalar) -> Bool {
        switch scalar.value {
        case 0x1100...0x115F, 0x2E80...0x303E, 0x3041...0x33FF, 0x3400...0x4DBF,
             0x4E00...0x9FFF, 0xA000...0xA4CF, 0xAC00...0xD7A3, 0xF900...0xFAFF,
             0xFE30...0xFE4F, 0xFF00...0xFF60, 0xFFE0...0xFFE6, 0x1F300...0x1FAFF,
             0x20000...0x3FFFD:
            true
        default:
            false
        }
    }
}
