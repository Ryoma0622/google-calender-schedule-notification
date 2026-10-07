import Foundation

// Swift Testing and XCTest are not available with the Command Line Tools alone,
// so the checks run as a plain executable: `swift run CalBarCoreChecks`.

nonisolated(unsafe) var failures = 0
nonisolated(unsafe) var checks = 0

func expect(_ condition: Bool, file: StaticString = #file, line: UInt = #line) {
    checks += 1
    if !condition {
        failures += 1
        print("FAIL \(file):\(line)")
    }
}

let link = MeetingLinkTests()
link.findsMeetInNotesAndAddsScheme()
link.keepsZoomPasscode()
link.prefersEarlierSourceThenEarlierPosition()
link.findsTeams()
link.ignoresPlainText()

let countdown = CountdownTests()
countdown.roundsUpPartialMinutes()
countdown.formatsJapaneseDurations()
countdown.truncatesByDisplayWidth()

let agenda = DayAgendaTests()
agenda.separatesAllDayAndSortsTimed()
agenda.currentAndNextSkipDeclined()
agenda.joinTargetPrefersTheMeetingAboutToStart()
agenda.timelineInsertsGapsBetweenBusyBlocks()
agenda.timelineWithoutGaps()

let status = MenuBarStatusTests()
status.upcomingShowsNextMeeting()
status.inProgressShowsRemainingUntilNextIsImminent()
status.finishedAndIdle()
status.timeStylesShowStartThenEnd()
status.iconOnlyHasNoText()

print("\(checks - failures)/\(checks) checks passed")
exit(failures == 0 ? 0 : 1)
