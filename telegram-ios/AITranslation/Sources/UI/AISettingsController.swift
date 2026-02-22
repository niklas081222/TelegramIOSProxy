import Foundation
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import TelegramUIPreferences
import ItemListUI
import PresentationDataUtils
import AccountContext
import UndoUI

// MARK: - Entry IDs

private enum AISettingsSection: Int32 {
    case connection = 0
    case translation = 1
    case devSettings = 2
    case cache = 3
}

private enum AISettingsEntry: ItemListNodeEntry {
    case connectionHeader(String)
    case proxyURL(String, String)
    case testConnection(String)
    case connectionStatus(String, Bool)

    case translationHeader(String)
    case globalToggle(String, Bool)
    case incomingToggle(String, Bool)
    case outgoingToggle(String, Bool)

    case devHeader(String)
    case contextMode(String, Int)
    case contextCount(String, Int)
    case showRawResponses(String, Bool)

    case cacheHeader(String)
    case clearCache(String)

    var section: ItemListSectionId {
        switch self {
        case .connectionHeader, .proxyURL, .testConnection, .connectionStatus:
            return AISettingsSection.connection.rawValue
        case .translationHeader, .globalToggle, .incomingToggle, .outgoingToggle:
            return AISettingsSection.translation.rawValue
        case .devHeader, .contextMode, .contextCount, .showRawResponses:
            return AISettingsSection.devSettings.rawValue
        case .cacheHeader, .clearCache:
            return AISettingsSection.cache.rawValue
        }
    }

    var stableId: Int32 {
        switch self {
        case .connectionHeader: return 0
        case .proxyURL: return 1
        case .testConnection: return 2
        case .connectionStatus: return 3
        case .translationHeader: return 10
        case .globalToggle: return 11
        case .incomingToggle: return 12
        case .outgoingToggle: return 13
        case .devHeader: return 20
        case .contextMode: return 21
        case .contextCount: return 22
        case .showRawResponses: return 23
        case .cacheHeader: return 30
        case .clearCache: return 31
        }
    }

    static func < (lhs: AISettingsEntry, rhs: AISettingsEntry) -> Bool {
        return lhs.stableId < rhs.stableId
    }

    static func == (lhs: AISettingsEntry, rhs: AISettingsEntry) -> Bool {
        return lhs.stableId == rhs.stableId
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        guard let arguments = arguments as? AISettingsArguments else {
            fatalError()
        }

        switch self {
        case let .connectionHeader(text):
            return ItemListSectionHeaderItem(
                presentationData: presentationData,
                text: text,
                sectionId: self.section
            )

        case let .proxyURL(title, value):
            return ItemListDisclosureItem(
                presentationData: presentationData,
                title: title,
                label: value.isEmpty ? "Not set" : value,
                sectionId: self.section,
                style: .blocks,
                action: { arguments.editProxyURL() }
            )

        case let .testConnection(title):
            return ItemListActionItem(
                presentationData: presentationData,
                title: title,
                kind: .generic,
                alignment: .natural,
                sectionId: self.section,
                style: .blocks,
                action: { arguments.testConnection() }
            )

        case let .connectionStatus(text, connected):
            return ItemListTextItem(
                presentationData: presentationData,
                text: .plain(connected ? "✓ Connected" : "✗ Not connected"),
                sectionId: self.section
            )

        case let .translationHeader(text):
            return ItemListSectionHeaderItem(
                presentationData: presentationData,
                text: text,
                sectionId: self.section
            )

        case let .globalToggle(title, value):
            return ItemListSwitchItem(
                presentationData: presentationData,
                title: title,
                value: value,
                sectionId: self.section,
                style: .blocks,
                updated: { value in arguments.toggleGlobal(value) }
            )

        case let .incomingToggle(title, value):
            return ItemListSwitchItem(
                presentationData: presentationData,
                title: title,
                value: value,
                sectionId: self.section,
                style: .blocks,
                updated: { value in arguments.toggleIncoming(value) }
            )

        case let .outgoingToggle(title, value):
            return ItemListSwitchItem(
                presentationData: presentationData,
                title: title,
                value: value,
                sectionId: self.section,
                style: .blocks,
                updated: { value in arguments.toggleOutgoing(value) }
            )

        case let .devHeader(text):
            return ItemListSectionHeaderItem(
                presentationData: presentationData,
                text: text,
                sectionId: self.section
            )

        case let .contextMode(title, mode):
            return ItemListDisclosureItem(
                presentationData: presentationData,
                title: title,
                label: mode == 1 ? "Single Message" : "Conversation Context",
                sectionId: self.section,
                style: .blocks,
                action: { arguments.toggleContextMode() }
            )

        case let .contextCount(title, count):
            return ItemListDisclosureItem(
                presentationData: presentationData,
                title: title,
                label: "\(count) messages",
                sectionId: self.section,
                style: .blocks,
                action: { arguments.editContextCount() }
            )

        case let .showRawResponses(title, value):
            return ItemListSwitchItem(
                presentationData: presentationData,
                title: title,
                value: value,
                sectionId: self.section,
                style: .blocks,
                updated: { value in arguments.toggleShowRaw(value) }
            )

        case let .cacheHeader(text):
            return ItemListSectionHeaderItem(
                presentationData: presentationData,
                text: text,
                sectionId: self.section
            )

        case let .clearCache(title):
            return ItemListActionItem(
                presentationData: presentationData,
                title: title,
                kind: .destructive,
                alignment: .natural,
                sectionId: self.section,
                style: .blocks,
                action: { arguments.clearCache() }
            )
        }
    }
}

// MARK: - Arguments

private final class AISettingsArguments {
    let editProxyURL: () -> Void
    let testConnection: () -> Void
    let toggleGlobal: (Bool) -> Void
    let toggleIncoming: (Bool) -> Void
    let toggleOutgoing: (Bool) -> Void
    let toggleContextMode: () -> Void
    let editContextCount: () -> Void
    let toggleShowRaw: (Bool) -> Void
    let clearCache: () -> Void

    init(
        editProxyURL: @escaping () -> Void,
        testConnection: @escaping () -> Void,
        toggleGlobal: @escaping (Bool) -> Void,
        toggleIncoming: @escaping (Bool) -> Void,
        toggleOutgoing: @escaping (Bool) -> Void,
        toggleContextMode: @escaping () -> Void,
        editContextCount: @escaping () -> Void,
        toggleShowRaw: @escaping (Bool) -> Void,
        clearCache: @escaping () -> Void
    ) {
        self.editProxyURL = editProxyURL
        self.testConnection = testConnection
        self.toggleGlobal = toggleGlobal
        self.toggleIncoming = toggleIncoming
        self.toggleOutgoing = toggleOutgoing
        self.toggleContextMode = toggleContextMode
        self.editContextCount = editContextCount
        self.toggleShowRaw = toggleShowRaw
        self.clearCache = clearCache
    }
}

// MARK: - State

private struct AISettingsState: Equatable {
    var isConnected: Bool = false
    var isTesting: Bool = false
}

// MARK: - Controller

public func aiSettingsController(context: AccountContext) -> ViewController {
    let statePromise = ValuePromise(AISettingsState(), ignoreRepeated: true)
    let stateValue = Atomic(value: AISettingsState())

    let arguments = AISettingsArguments(
        editProxyURL: {
            // Present a text input alert for the proxy URL
            let presentationData = context.sharedContext.currentPresentationData.with { $0 }
            let controller = textAlertController(
                context: context,
                title: "Proxy Server URL",
                text: "Enter the URL of the translation proxy server",
                actions: [
                    TextAlertAction(type: .genericAction, title: "Cancel", action: {}),
                    TextAlertAction(type: .defaultAction, title: "Save", action: { text in
                        AITranslationSettings.proxyServerURL = text ?? ""
                        AITranslationService.shared.updateProxyClient()
                    })
                ],
                actionLayout: .horizontal,
                inputPlaceholder: "https://your-server.com",
                inputText: AITranslationSettings.proxyServerURL
            )
            context.sharedContext.mainWindow?.present(controller, on: .root)
        },
        testConnection: {
            let _ = stateValue.modify { state in
                var state = state
                state.isTesting = true
                return state
            }
            statePromise.set(stateValue.with { $0 })

            let _ = (AITranslationService.shared.testConnection()
            |> deliverOnMainQueue).start(next: { connected in
                let _ = stateValue.modify { state in
                    var state = state
                    state.isConnected = connected
                    state.isTesting = false
                    return state
                }
                statePromise.set(stateValue.with { $0 })
            })
        },
        toggleGlobal: { value in
            AITranslationSettings.enabled = value
            updateAITranslationServiceRegistration()
        },
        toggleIncoming: { value in
            AITranslationSettings.autoTranslateIncoming = value
        },
        toggleOutgoing: { value in
            AITranslationSettings.autoTranslateOutgoing = value
        },
        toggleContextMode: {
            let newMode = AITranslationSettings.contextMode == 1 ? 2 : 1
            AITranslationSettings.contextMode = newMode
        },
        editContextCount: {
            let presentationData = context.sharedContext.currentPresentationData.with { $0 }
            let controller = textAlertController(
                context: context,
                title: "Context Message Count",
                text: "How many recent messages to include as context (2-100)",
                actions: [
                    TextAlertAction(type: .genericAction, title: "Cancel", action: {}),
                    TextAlertAction(type: .defaultAction, title: "Save", action: { text in
                        if let count = Int(text ?? ""), count >= 2, count <= 100 {
                            AITranslationSettings.contextMessageCount = count
                        }
                    })
                ],
                actionLayout: .horizontal,
                inputPlaceholder: "20",
                inputText: String(AITranslationSettings.contextMessageCount)
            )
            context.sharedContext.mainWindow?.present(controller, on: .root)
        },
        toggleShowRaw: { value in
            AITranslationSettings.showRawAPIResponses = value
        },
        clearCache: {
            AITranslationService.shared.clearCache()
            let presentationData = context.sharedContext.currentPresentationData.with { $0 }
            let controller = UndoOverlayController(
                presentationData: presentationData,
                content: .info(
                    title: nil,
                    text: "Translation cache cleared",
                    timeout: nil,
                    customUndoText: nil
                ),
                elevatedLayout: false,
                action: { _ in return false }
            )
            context.sharedContext.mainWindow?.present(controller, on: .root)
        }
    )

    let signal = statePromise.get()
    |> map { state -> ([AISettingsEntry], AISettingsState) in
        var entries: [AISettingsEntry] = []

        entries.append(.connectionHeader("CONNECTION"))
        entries.append(.proxyURL("Server URL", AITranslationSettings.proxyServerURL))
        entries.append(.testConnection("Test Connection"))
        entries.append(.connectionStatus("Status", state.isConnected))

        entries.append(.translationHeader("TRANSLATION"))
        entries.append(.globalToggle("Enable AI Translation", AITranslationSettings.enabled))
        entries.append(.incomingToggle("Translate Incoming (DE→EN)", AITranslationSettings.autoTranslateIncoming))
        entries.append(.outgoingToggle("Translate Outgoing (EN→DE)", AITranslationSettings.autoTranslateOutgoing))

        entries.append(.devHeader("DEVELOPER SETTINGS"))
        entries.append(.contextMode("Translation Context", AITranslationSettings.contextMode))
        if AITranslationSettings.contextMode == 2 {
            entries.append(.contextCount("Context Messages", AITranslationSettings.contextMessageCount))
        }
        entries.append(.showRawResponses("Show Raw API Responses", AITranslationSettings.showRawAPIResponses))

        entries.append(.cacheHeader("CACHE"))
        entries.append(.clearCache("Clear Translation Cache"))

        return (entries, state)
    }

    let controller = ItemListController(
        context: context,
        state: signal |> map { entries, _ in
            return ItemListControllerState(
                presentationData: ItemListPresentationData(context.sharedContext.currentPresentationData.with { $0 }),
                title: .text("AI Translation"),
                entries: entries.map { $0 },
                style: .blocks
            )
        }
    )

    return controller
}

// MARK: - Helper for text input alerts

private func textAlertController(
    context: AccountContext,
    title: String,
    text: String,
    actions: [TextAlertAction],
    actionLayout: TextAlertContentActionLayout,
    inputPlaceholder: String,
    inputText: String
) -> AlertController {
    // Use Telegram's built-in text input alert
    return textAlertController(
        context: context,
        forceTheme: nil,
        title: title,
        text: text,
        actions: actions,
        actionLayout: actionLayout
    )
}
