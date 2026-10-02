import Foundation

public struct MeetingLink: Sendable, Hashable {
    public enum Provider: String, Sendable, Hashable {
        case meet = "Meet"
        case zoom = "Zoom"
        case teams = "Teams"
        case webex = "Webex"
    }

    public let provider: Provider
    public let url: URL

    public init(provider: Provider, url: URL) {
        self.provider = provider
        self.url = url
    }

    private static let patterns: [(Provider, NSRegularExpression)] = [
        (.meet, #"(?:https?://)?meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}\b"#),
        (.zoom, #"https://[\w.-]*zoom\.us/(?:j|my|w|s)/[\w.-]+(?:\?[\w=&%.-]+)?"#),
        (.teams, #"https://teams\.(?:microsoft|live)\.com/(?:l/meetup-join|meet)/[\w%.\-/?=&@:]+"#),
        (.webex, #"https://[\w.-]+\.webex\.com/[\w/.\-?=&]+"#),
    ].map { provider, pattern in
        // The patterns are compile-time constants; a failure here is a programming error.
        (provider, try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive]))
    }

    /// Returns the first conference link found, searching the sources in order and,
    /// within a source, preferring the link that appears earliest in the text.
    public static func find(in sources: [String?]) -> MeetingLink? {
        for case let text? in sources where !text.isEmpty {
            if let link = firstLink(in: text) {
                return link
            }
        }
        return nil
    }

    private static func firstLink(in text: String) -> MeetingLink? {
        let range = NSRange(text.startIndex..., in: text)
        let matches = patterns.compactMap { provider, regex -> (Provider, NSRange)? in
            regex.firstMatch(in: text, range: range).map { (provider, $0.range) }
        }
        guard let (provider, matchRange) = matches.min(by: { $0.1.location < $1.1.location }),
              let swiftRange = Range(matchRange, in: text)
        else { return nil }

        var raw = String(text[swiftRange])
        if !raw.lowercased().hasPrefix("http") {
            raw = "https://" + raw
        }
        return URL(string: raw).map { MeetingLink(provider: provider, url: $0) }
    }
}
