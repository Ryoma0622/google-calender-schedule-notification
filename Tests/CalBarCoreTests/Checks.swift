import Foundation
import CalBarCore

private let calendar: Calendar = {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "Asia/Tokyo")!
    return calendar
}()

private func at(_ hour: Int, _ minute: Int = 0, _ second: Int = 0) -> Date {
    calendar.date(from: DateComponents(year: 2026, month: 10, day: 2, hour: hour, minute: minute, second: second))!
}

private func meeting(
    _ title: String,
    _ start: Date,
    _ end: Date,
    link: Bool = false,
    attendance: Attendance = .accepted
) -> Meeting {
    Meeting(
        id: title,
        title: title,
        start: start,
        end: end,
        link: link ? MeetingLink(provider: .meet, url: URL(string: "https://meet.google.com/abc-defg-hij")!) : nil,
        attendance: attendance
    )
}

struct MeetingLinkTests {
    func findsMeetInNotesAndAddsScheme() {
        let link = MeetingLink.find(in: [nil, "", "Google Meet に参加: meet.google.com/xyz-abcd-efg\n電話で参加"])
        expect(link == MeetingLink(provider: .meet, url: URL(string: "https://meet.google.com/xyz-abcd-efg")!))
    }

    func keepsZoomPasscode() {
        let link = MeetingLink.find(in: ["https://example.zoom.us/j/12345678901?pwd=Abc123Xyz (Passcode)"])
        expect(link?.provider == .zoom)
        expect(link?.url.absoluteString == "https://example.zoom.us/j/12345678901?pwd=Abc123Xyz")
    }

    func prefersEarlierSourceThenEarlierPosition() {
        let link = MeetingLink.find(in: [
            "会議室 A",
            "Zoom: https://example.zoom.us/j/123 / Meet: https://meet.google.com/abc-defg-hij",
        ])
        expect(link?.provider == .zoom)
    }

    func findsTeams() {
        let link = MeetingLink.find(in: ["Join: https://teams.microsoft.com/l/meetup-join/19%3ameeting_x%40thread.v2/0?context=y"])
        expect(link?.provider == .teams)
    }

    func ignoresPlainText() {
        expect(MeetingLink.find(in: ["赤坂オフィス 18F", "https://example.com/doc"]) == nil)
    }
}

struct CountdownTests {
    func roundsUpPartialMinutes() {
        expect(Countdown.minutes(until: at(14), from: at(13, 45, 30)) == 15)
        expect(Countdown.minutes(until: at(14), from: at(14, 0, 10)) == 0)
    }

    func formatsJapaneseDurations() {
        expect(Countdown.untilStart(0) == "まもなく")
        expect(Countdown.untilStart(15) == "15分後")
        expect(Countdown.untilStart(60) == "1時間後")
        expect(Countdown.untilStart(80) == "1時間20分後")
        expect(Countdown.remaining(0) == "残り1分")
        expect(Countdown.remaining(65) == "残り1時間5分")
    }

    func truncatesByDisplayWidth() {
        expect(TextWidth.of("Sync 定例") == 9)
        expect(TextWidth.truncate("Weekly Standup", maxWidth: 20) == "Weekly Standup")
        expect(TextWidth.truncate("Product 開発定例（基本30分開催）", maxWidth: 16) == "Product 開発定…")
    }
}

struct DayAgendaTests {
    let agenda = DayAgenda(meetings: [
        meeting("Daily", at(10, 45), at(11), link: true),
        meeting("Lunch", at(12), at(13)),
        meeting("Declined", at(13), at(14), link: true, attendance: .declined),
        meeting("Kick-off", at(14, 30), at(15, 30), link: true),
        meeting("Review", at(15), at(16), link: true),
        Meeting(id: "holiday", title: "祝日", start: at(0), end: at(24), isAllDay: true),
    ])

    func separatesAllDayAndSortsTimed() {
        expect(agenda.allDay.map(\.title) == ["祝日"])
        expect(agenda.timed.map(\.title) == ["Daily", "Lunch", "Declined", "Kick-off", "Review"])
    }

    func currentAndNextSkipDeclined() {
        expect(agenda.current(at: at(13, 30)) == nil)
        expect(agenda.next(after: at(13, 30))?.title == "Kick-off")
        expect(agenda.current(at: at(15, 10))?.title == "Review")
    }

    func joinTargetPrefersTheMeetingAboutToStart() {
        expect(agenda.joinTarget(at: at(14, 40))?.title == "Kick-off")
        expect(agenda.joinTarget(at: at(14, 56))?.title == "Review")
        expect(agenda.joinTarget(at: at(12, 30)) == nil)
    }

    func timelineInsertsGapsBetweenBusyBlocks() {
        let gaps = agenda.timeline(minimumGap: 15 * 60).compactMap { entry -> String? in
            guard case .gap(let start, let end) = entry else { return nil }
            return "\(calendar.component(.hour, from: start)):\(calendar.component(.minute, from: start))-\(calendar.component(.hour, from: end)):\(calendar.component(.minute, from: end))"
        }
        // 11:00-12:00 between Daily and Lunch, 13:00-14:30 because the declined meeting does not count.
        expect(gaps == ["11:0-12:0", "13:0-14:30"])
    }

    func timelineWithoutGaps() {
        expect(agenda.timeline(minimumGap: nil).count == 5)
    }
}

struct MenuBarStatusTests {
    let agenda = DayAgenda(meetings: [
        meeting("Weekly Standup", at(14), at(15)),
        meeting("1on1", at(15), at(15, 30)),
    ])

    private func status(_ now: Date, _ style: MenuBarStyle = .titleAndCountdown) -> MenuBarStatus {
        MenuBarStatus.make(agenda: agenda, now: now, style: style, maxTitleWidth: 20, calendar: calendar)
    }

    func upcomingShowsNextMeeting() {
        expect(status(at(13, 45)) == MenuBarStatus(phase: .upcoming, text: "Weekly Standup · 15分後"))
        expect(status(at(13, 45), .timeAndCountdown).text == "14:00 · 15分後")
        expect(status(at(13, 57)).phase == .imminent)
    }

    func inProgressShowsRemainingUntilNextIsImminent() {
        expect(status(at(14, 20)) == MenuBarStatus(phase: .inProgress, text: "Weekly Standup · 残り40分"))
        expect(status(at(14, 20), .timeAndCountdown).text == "残り40分")
        expect(status(at(14, 56)) == MenuBarStatus(phase: .imminent, text: "1on1 · 4分後"))
    }

    func finishedAndIdle() {
        expect(status(at(16)) == MenuBarStatus(phase: .finished, text: ""))
        let empty = MenuBarStatus.make(agenda: DayAgenda(meetings: []), now: at(9), style: .titleAndCountdown, maxTitleWidth: 20)
        expect(empty.phase == .idle)
    }

    func timeStylesShowStartThenEnd() {
        expect(status(at(13, 45), .timeAndTitle).text == "14:00 Weekly Standup")
        expect(status(at(13, 45), .timeOnly).text == "14:00")
        expect(status(at(14, 20), .timeAndTitle) == MenuBarStatus(phase: .inProgress, text: "〜15:00 Weekly Standup"))
        expect(status(at(14, 20), .timeOnly).text == "〜15:00")
        expect(status(at(14, 56), .timeOnly) == MenuBarStatus(phase: .imminent, text: "15:00"))
    }

    func iconOnlyHasNoText() {
        expect(status(at(13, 45), .iconOnly).text.isEmpty)
    }
}
