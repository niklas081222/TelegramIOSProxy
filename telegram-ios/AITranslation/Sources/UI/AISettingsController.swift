import Foundation
import UIKit
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

        case let .connectionStatus(_, connected):
            return ItemListTextItem(
                presentationData: presentationData,
                text: .plain(connected ? "Connected" : "Not connected"),
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

// MARK: - Entries generation

private func aiSettingsEntries(state: AISettingsState) -> [AISettingsEntry] {
    var entries: [AISettingsEntry] = []

    entries.append(.connectionHeader("CONNECTION"))
    entries.append(.proxyURL("Server URL", AITranslationSettings.proxyServerURL))
    entries.append(.testConnection("Test Connection"))
    entries.append(.connectionStatus("Status", state.isConnected))

    entries.append(.translationHeader("TRANSLATION"))
    entries.append(.globalToggle("Enable AI Translation", AITranslationSettings.enabled))
    entries.append(.incomingToggle("Translate Incoming (DE > EN)", AITranslationSettings.autoTranslateIncoming))
    entries.append(.outgoingToggle("Translate Outgoing (EN > DE)", AITranslationSettings.autoTranslateOutgoing))

    entries.append(.devHeader("DEVELOPER SETTINGS"))
    entries.append(.contextMode("Translation Context", AITranslationSettings.contextMode))
    if AITranslationSettings.contextMode == 2 {
        entries.append(.contextCount("Context Messages", AITranslationSettings.contextMessageCount))
    }
    entries.append(.showRawResponses("Show Raw API Responses", AITranslationSettings.showRawAPIResponses))

    entries.append(.cacheHeader("CACHE"))
    entries.append(.clearCache("Clear Translation Cache"))

    return entries
}

// MARK: - Controller

public func aiSettingsController(context: AccountContext) -> ViewController {
    let statePromise = ValuePromise(AISettingsState(), ignoreRepeated: true)
    let stateValue = Atomic(value: AISettingsState())

    var presentControllerImpl: ((ViewController, ViewControllerPresentationArguments?) -> Void)?

    let arguments = AISettingsArguments(
        editProxyURL: {
            let currentURL = AITranslationSettings.proxyServerURL
            let alert = UIAlertController(
                title: "Proxy Server URL",
                message: "Enter your translation proxy URL (e.g. cloudflared tunnel URL)",
                preferredStyle: .alert
            )
            alert.addTextField { textField in
                textField.text = currentURL
                textField.placeholder = "https://your-tunnel.trycloudflare.com"
                textField.keyboardType = .URL
                textField.autocapitalizationType = .none
                textField.autocorrectionType = .no
            }
            alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
            alert.addAction(UIAlertAction(title: "Save", style: .default) { _ in
                if let newURL = alert.textFields?.first?.text, !newURL.isEmpty {
                    AITranslationSettings.proxyServerURL = newURL
                    AITranslationService.shared.updateProxyClient()
                }
            })
            context.sharedContext.mainWindow?.presentNative(alert)
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
            let current = AITranslationSettings.contextMessageCount
            let options = [5, 10, 20, 50, 100]
            let nextIndex = (options.firstIndex(where: { $0 > current }) ?? 0)
            AITranslationSettings.contextMessageCount = options[nextIndex]
        },
        toggleShowRaw: { value in
            AITranslationSettings.showRawAPIResponses = value
        },
        clearCache: {
            AITranslationService.shared.clearCache()
            let presentationData = context.sharedContext.currentPresentationData.with { $0 }
            let undoController = UndoOverlayController(
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
            context.sharedContext.mainWindow?.present(undoController, on: .root)
        }
    )

    let signal = combineLatest(
        context.sharedContext.presentationData,
        statePromise.get()
    )
    |> map { presentationData, state -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let entries = aiSettingsEntries(state: state)
        let controllerState = ItemListControllerState(
            presentationData: ItemListPresentationData(presentationData),
            title: .text("AI Translation"),
            leftNavigationButton: nil,
            rightNavigationButton: nil,
            backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back)
        )
        let listState = ItemListNodeState(
            presentationData: ItemListPresentationData(presentationData),
            entries: entries.map { $0 },
            style: .blocks,
            animateChanges: false
        )
        return (controllerState, (listState, arguments))
    }

    let controller = ItemListController(context: context, state: signal)

    presentControllerImpl = { [weak controller] c, a in
        controller?.present(c, in: .window(.root), with: a)
    }

    return controller
}
