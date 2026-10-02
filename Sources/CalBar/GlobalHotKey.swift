import Carbon.HIToolbox

/// A system-wide ⌃⌥J shortcut. Carbon hot keys need no Accessibility permission.
@MainActor
final class GlobalHotKey {
    static let displayName = "⌃⌥J"

    private static var action: (() -> Void)?
    private var hotKeyRef: EventHotKeyRef?
    private var handlerRef: EventHandlerRef?

    func register(action: @escaping () -> Void) {
        guard hotKeyRef == nil else { return }
        Self.action = action

        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(
            GetApplicationEventTarget(),
            { _, _, _ in
                // Carbon delivers application events on the main thread.
                MainActor.assumeIsolated { GlobalHotKey.action?() }
                return noErr
            },
            1,
            &eventType,
            nil,
            &handlerRef
        )

        let id = EventHotKeyID(signature: OSType(0x434C_4252), id: 1) // "CLBR"
        RegisterEventHotKey(
            UInt32(kVK_ANSI_J),
            UInt32(controlKey | optionKey),
            id,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )
    }

    func unregister() {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
        }
        if let handlerRef {
            RemoveEventHandler(handlerRef)
        }
        hotKeyRef = nil
        handlerRef = nil
        Self.action = nil
    }
}
