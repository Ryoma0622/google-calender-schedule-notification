import SwiftUI

struct MenuBarLabel: View {
    let model: AppModel

    var body: some View {
        if model.access != .granted {
            Image(systemName: "calendar.badge.exclamationmark")
        } else {
            let status = model.menuBarStatus
            HStack(spacing: 4) {
                Image(systemName: status.phase.symbolName)
                if !status.text.isEmpty {
                    Text(status.text)
                        .monospacedDigit()
                }
            }
        }
    }
}
