import CalBarCore
import SwiftUI

/// The top card on today's popover: the meeting in progress and the one after it.
struct NowCard: View {
    let model: AppModel

    var body: some View {
        let agenda = model.todayAgenda
        let now = model.now
        let current = agenda.current(at: now)
        let next = agenda.next(after: now)

        VStack(alignment: .leading, spacing: 10) {
            if let current {
                currentSection(current, now: now)
                if let next {
                    Divider()
                    nextSection(next, now: now, prominent: false)
                }
            } else if let next {
                nextSection(next, now: now, prominent: true)
            } else {
                emptySection(hasMeetings: agenda.timed.contains { !$0.isDeclined })
                if let first = model.tomorrowAgenda.timed.first(where: { !$0.isDeclined }) {
                    Divider()
                    tomorrowSection(first)
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func currentSection(_ meeting: Meeting, now: Date) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("進行中", systemImage: "record.circle")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.red)
                Spacer()
                Text(Countdown.remaining(Countdown.minutes(until: meeting.end, from: now)))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(meeting.title)
                        .font(.headline)
                        .lineLimit(2)
                    Text("\(Format.clock(meeting.start))〜\(Format.clock(meeting.end))")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if meeting.link != nil {
                    JoinButton(model: model, meeting: meeting, prominent: true)
                }
            }
            ProgressView(value: meeting.progress(at: now))
                .tint(meeting.calendarColor.color)
        }
    }

    private func nextSection(_ meeting: Meeting, now: Date, prominent: Bool) -> some View {
        let minutes = Countdown.minutes(until: meeting.start, from: now)
        return HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text("次の予定 · \(Countdown.untilStart(minutes))")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(minutes <= 5 ? AnyShapeStyle(.orange) : AnyShapeStyle(.secondary))
                Text(meeting.title)
                    .font(prominent ? .headline : .callout.weight(.medium))
                    .lineLimit(2)
                Text(detail(meeting))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            if meeting.link != nil {
                JoinButton(model: model, meeting: meeting, prominent: prominent && minutes <= 10)
            }
        }
    }

    private func emptySection(hasMeetings: Bool) -> some View {
        Label(
            hasMeetings ? "今日の予定はすべて終わりました" : "今日の予定はありません",
            systemImage: hasMeetings ? "checkmark.circle" : "sun.max"
        )
        .font(.callout)
        .foregroundStyle(.secondary)
    }

    private func tomorrowSection(_ meeting: Meeting) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("明日の最初の予定")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                Text(Format.clock(meeting.start))
                    .font(.callout.monospacedDigit())
                    .foregroundStyle(.secondary)
                Text(meeting.title)
                    .font(.callout.weight(.medium))
                    .lineLimit(1)
            }
        }
    }

    private func detail(_ meeting: Meeting) -> String {
        let time = "\(Format.clock(meeting.start))〜\(Format.clock(meeting.end))"
        guard let location = meeting.location else { return time }
        return "\(time) · \(location)"
    }
}

struct JoinButton: View {
    let model: AppModel
    let meeting: Meeting
    var prominent = false

    var body: some View {
        if let link = meeting.link {
            let button = Button {
                model.join(meeting)
            } label: {
                Label("参加", systemImage: link.provider.symbolName)
                    .labelStyle(.titleAndIcon)
            }
            .help("\(link.provider.rawValue) で参加")

            if prominent {
                button
                    .buttonStyle(.borderedProminent)
                    .controlSize(.regular)
            } else {
                button
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
    }
}

struct MeetingRow: View {
    let model: AppModel
    let meeting: Meeting
    @State private var isHovering = false

    var body: some View {
        let now = model.now
        let isCurrent = model.isShowingToday && meeting.isInProgress(at: now) && !meeting.isDeclined
        let hasEnded = meeting.hasEnded(at: now)
        let color = meeting.calendarColor.color

        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .trailing, spacing: 1) {
                Text(Format.clock(meeting.start))
                    .font(.callout.monospacedDigit())
                Text(Format.clock(meeting.end))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .frame(width: 44, alignment: .trailing)

            RoundedRectangle(cornerRadius: 2)
                .fill(meeting.attendance == .tentative || meeting.attendance == .pending ? AnyShapeStyle(color.opacity(0.4)) : AnyShapeStyle(color))
                .frame(width: 4)
                .frame(maxHeight: .infinity)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(meeting.title)
                        .font(.callout.weight(isCurrent ? .semibold : .regular))
                        .strikethrough(meeting.isDeclined)
                        .lineLimit(1)
                    if let badge = attendanceBadge {
                        Text(badge)
                            .font(.caption2)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(.quaternary, in: Capsule())
                            .foregroundStyle(.secondary)
                    }
                }
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 4)
            if meeting.link != nil, !hasEnded, !meeting.isDeclined {
                JoinButton(model: model, meeting: meeting)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .fixedSize(horizontal: false, vertical: true)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(isCurrent ? color.opacity(0.16) : isHovering ? Color.primary.opacity(0.06) : .clear)
        )
        .opacity(hasEnded || meeting.isDeclined ? 0.45 : 1)
        .contentShape(Rectangle())
        .onHover { isHovering = $0 }
        .onTapGesture(count: 2) { model.revealInCalendar(meeting) }
        .contextMenu {
            if meeting.link != nil {
                Button("会議に参加") { model.join(meeting) }
                Button("会議 URL をコピー") { model.copyLink(of: meeting) }
                Divider()
            }
            Button("カレンダーで表示") { model.revealInCalendar(meeting) }
        }
        .help("ダブルクリックでカレンダーに表示")
    }

    private var attendanceBadge: String? {
        switch meeting.attendance {
        case .tentative: "仮"
        case .pending: "未回答"
        case .declined: "辞退"
        case .accepted, .none: nil
        }
    }

    private var subtitle: String? {
        meeting.location ?? (meeting.link.map { $0.provider.rawValue })
    }
}
