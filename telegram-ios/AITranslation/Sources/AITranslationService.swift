import Foundation
import SwiftSignalKit
import TelegramCore
import Postbox
import AccountContext

public final class AITranslationService {
    public static let shared = AITranslationService()

    private let cache = TranslationCache()
    private var proxyClient: AIProxyClient?

    private init() {
        updateProxyClient()
    }

    /// Recreate the proxy client when the URL changes.
    public func updateProxyClient() {
        let url = AITranslationSettings.proxyServerURL
        guard !url.isEmpty else {
            proxyClient = nil
            return
        }
        proxyClient = AIProxyClient(baseURL: url)
    }

    // MARK: - Outgoing Translation (EN → DE)

    /// Translates outgoing message text before it is sent.
    /// Returns the translated text, or the original text on any failure.
    public func translateOutgoing(
        text: String,
        chatId: PeerId,
        context: AccountContext
    ) -> Signal<String, NoError> {
        guard shouldTranslateOutgoing(chatId: chatId),
              let client = proxyClient else {
            return .single(text)
        }

        let contextSignal: Signal<[AIContextMessage], NoError>
        if AITranslationSettings.contextMode == 2 {
            contextSignal = ConversationContextProvider.getContext(
                chatId: chatId,
                context: context
            )
        } else {
            contextSignal = .single([])
        }

        return contextSignal
        |> mapToSignal { contextMessages -> Signal<String, NoError> in
            return client.translate(
                text: text,
                direction: "outgoing",
                chatId: chatId.id._internalGetInt64Value(),
                context: contextMessages
            )
        }
    }

    // MARK: - Incoming Translation (DE → EN)

    /// Translates incoming message text for display.
    /// Returns the translated text, or the original text on any failure.
    /// Results are cached by MessageId.
    public func translateIncoming(
        text: String,
        messageId: MessageId,
        chatId: PeerId,
        context: AccountContext
    ) -> Signal<String, NoError> {
        // Check cache first
        if let cached = cache.get(messageId) {
            return .single(cached)
        }

        guard shouldTranslateIncoming(chatId: chatId),
              let client = proxyClient else {
            return .single(text)
        }

        let contextSignal: Signal<[AIContextMessage], NoError>
        if AITranslationSettings.contextMode == 2 {
            contextSignal = ConversationContextProvider.getContext(
                chatId: chatId,
                context: context
            )
        } else {
            contextSignal = .single([])
        }

        return contextSignal
        |> mapToSignal { [weak self] contextMessages -> Signal<String, NoError> in
            return client.translate(
                text: text,
                direction: "incoming",
                chatId: chatId.id._internalGetInt64Value(),
                context: contextMessages
            )
            |> map { translatedText -> String in
                self?.cache.set(messageId, translation: translatedText)
                return translatedText
            }
        }
    }

    // MARK: - Batch Translation for ExperimentalInternalTranslationService

    /// Translates a batch of texts for the built-in translation system.
    public func translateTexts(
        texts: [AnyHashable: String],
        fromLang: String,
        toLang: String
    ) -> Signal<[AnyHashable: String]?, NoError> {
        guard AITranslationSettings.enabled,
              let client = proxyClient else {
            return .single(nil)
        }

        let direction: String
        if toLang.hasPrefix("en") {
            direction = "incoming"
        } else {
            direction = "outgoing"
        }

        let signals: [Signal<(AnyHashable, String), NoError>] = texts.map { key, text in
            return client.translate(
                text: text,
                direction: direction,
                chatId: 0,
                context: []
            )
            |> map { translatedText in
                return (key, translatedText)
            }
        }

        return combineLatest(signals)
        |> map { results -> [AnyHashable: String]? in
            var dict: [AnyHashable: String] = [:]
            for (key, value) in results {
                dict[key] = value
            }
            return dict
        }
    }

    // MARK: - Per-Chat Toggle

    public func isEnabledForChat(_ peerId: PeerId) -> Bool {
        let chatId = peerId.id._internalGetInt64Value()
        return AITranslationSettings.enabledChatIds.contains(chatId)
    }

    public func toggleChat(_ peerId: PeerId) {
        let chatId = peerId.id._internalGetInt64Value()
        var ids = AITranslationSettings.enabledChatIds
        if let index = ids.firstIndex(of: chatId) {
            ids.remove(at: index)
        } else {
            ids.append(chatId)
        }
        AITranslationSettings.enabledChatIds = ids
    }

    // MARK: - Cache Management

    public func clearCache() {
        cache.clear()
    }

    // MARK: - System Prompt

    public func getPrompt() -> Signal<String, NoError> {
        guard let client = proxyClient else {
            return .single("")
        }
        return client.getPrompt()
    }

    public func setPrompt(_ prompt: String) -> Signal<Bool, NoError> {
        guard let client = proxyClient else {
            return .single(false)
        }
        return client.setPrompt(prompt)
    }

    // MARK: - Connection Test

    public func testConnection() -> Signal<Bool, NoError> {
        guard let client = proxyClient else {
            return .single(false)
        }
        return client.healthCheck()
    }

    // MARK: - Private

    private func shouldTranslateOutgoing(chatId: PeerId) -> Bool {
        guard AITranslationSettings.enabled && AITranslationSettings.autoTranslateOutgoing else {
            return false
        }
        // If per-chat list is empty, translate all chats (default behavior)
        // If per-chat list has entries, only translate those specific chats
        let perChatIds = AITranslationSettings.enabledChatIds
        if perChatIds.isEmpty {
            return true
        }
        return perChatIds.contains(chatId.id._internalGetInt64Value())
    }

    private func shouldTranslateIncoming(chatId: PeerId) -> Bool {
        guard AITranslationSettings.enabled && AITranslationSettings.autoTranslateIncoming else {
            return false
        }
        let perChatIds = AITranslationSettings.enabledChatIds
        if perChatIds.isEmpty {
            return true
        }
        return perChatIds.contains(chatId.id._internalGetInt64Value())
    }
}
