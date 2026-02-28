import Foundation
import SwiftSignalKit
import TelegramCore
import Postbox
import AccountContext

/// Observes incoming messages at the data layer and pre-translates them
/// so translations are available before the user opens the chat.
///
/// Three mechanisms:
/// 1. Primary: `aiNewIncomingMessagesCallback` from AccountStateManager — fires for ALL new incoming messages
///    (bypasses notification filtering that excludes muted chats).
/// 2. Secondary: `notificationMessages` subscription — catches notification-worthy messages.
/// 3. Catch-up: `translateMessages(peerId:context:)` scans recent messages when a chat opens.
public final class AIBackgroundTranslationObserver {
    private static var shared: AIBackgroundTranslationObserver?
    private static var storedContext: AccountContext?
    private static let appStartTimestamp = Int32(Date().timeIntervalSince1970)

    /// Retry delays in seconds for failed translations
    private static let retryDelays: [Double] = [2.0, 5.0, 10.0]

    /// Call once when an authorized account is available.
    public static func startIfNeeded(context: AccountContext) {
        guard shared == nil else { return }
        storedContext = context
        shared = AIBackgroundTranslationObserver(context: context)

        // Register the callback from AccountStateManager for ALL incoming messages.
        // This bypasses notificationMessages filtering (muted chats, etc.).
        aiNewIncomingMessagesCallback = { messageIds in
            Self.translateMessageIds(messageIds)
        }
    }

    // MARK: - Primary: Translate by Message IDs (from AccountStateManager callback)

    /// Called by `aiNewIncomingMessagesCallback` for every new real-time incoming message.
    /// Reads messages from Postbox, filters, batch translates, and stores results.
    private static func translateMessageIds(_ ids: [MessageId]) {
        guard AITranslationSettings.enabled, AITranslationSettings.autoTranslateIncoming else { return }
        guard let context = storedContext else { return }
        guard !ids.isEmpty else { return }

        let accountPeerId = context.account.peerId
        let startTs = appStartTimestamp

        let _ = (context.account.postbox.transaction { transaction -> [(MessageId, String, PeerId)] in
            var toTranslate: [(MessageId, String, PeerId)] = []
            for id in ids {
                guard let message = transaction.getMessage(id) else { continue }
                // Only translate: incoming, recent (within 5 min of app start), non-empty, not already translated
                if message.author?.id != accountPeerId,
                   message.timestamp >= startTs - 300,
                   !message.text.isEmpty,
                   !message.attributes.contains(where: { $0 is TranslationMessageAttribute }) {
                    toTranslate.append((message.id, message.text, message.id.peerId))
                }
            }
            return toTranslate
        }
        |> deliverOnMainQueue
        |> mapToSignal { toTranslate -> Signal<Void, NoError> in
            guard !toTranslate.isEmpty else { return .complete() }

            if AITranslationSettings.incomingContextMode == 2 {
                return Self.translateWithContext(messages: toTranslate, context: context)
            } else {
                return Self.translateBatchMessages(messages: toTranslate, context: context)
            }
        }).start()
    }

    // MARK: - Batch Translation (no context)

    private static func translateBatchMessages(messages: [(MessageId, String, PeerId)], context: AccountContext) -> Signal<Void, NoError> {
        var textDict: [AnyHashable: String] = [:]
        var idMap: [String: MessageId] = [:]
        for (i, (msgId, text, _)) in messages.enumerated() {
            let key = "\(i)"
            textDict[key as AnyHashable] = text
            idMap[key] = msgId
        }

        return AITranslationService.shared.translateTexts(texts: textDict, fromLang: "de", toLang: "en")
        |> mapToSignal { results -> Signal<Void, NoError> in
            guard let results = results else {
                // All failed, schedule retry
                print("[AITranslation] Batch translation returned nil, scheduling retry for \(messages.count) messages")
                Self.scheduleRetry(ids: messages.map { $0.0 }, attempt: 0, context: context)
                return .complete()
            }
            return context.account.postbox.transaction { transaction in
                var failedIds: [MessageId] = []
                for (key, msgId) in idMap {
                    if let translatedText = results[key as AnyHashable] {
                        // Safety: skip if translated text is identical to original
                        let originalText = textDict[key as AnyHashable]
                        if let orig = originalText, translatedText == orig {
                            print("[AITranslation] Skipping storage for \(msgId): translation identical to original")
                            failedIds.append(msgId)
                            continue
                        }
                        Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                    } else {
                        failedIds.append(msgId)
                    }
                }
                if !failedIds.isEmpty {
                    print("[AITranslation] \(failedIds.count) translations failed, scheduling retry")
                    DispatchQueue.main.async {
                        Self.scheduleRetry(ids: failedIds, attempt: 0, context: context)
                    }
                }
            } |> map { _ in }
        }
    }

    // MARK: - Context-Aware Translation (individual requests with conversation context)

    private static func translateWithContext(messages: [(MessageId, String, PeerId)], context: AccountContext) -> Signal<Void, NoError> {
        // Group by peerId (chat)
        var chatGroups: [PeerId: [(MessageId, String)]] = [:]
        for (msgId, text, peerId) in messages {
            chatGroups[peerId, default: []].append((msgId, text))
        }

        var signals: [Signal<Void, NoError>] = []

        for (peerId, chatMessages) in chatGroups {
            let chatSignal = ConversationContextProvider.getContext(
                chatId: peerId,
                context: context,
                direction: "incoming"
            )
            |> mapToSignal { contextMessages -> Signal<Void, NoError> in
                // Translate each message individually with context
                let translateSignals: [Signal<(MessageId, String, String)?, NoError>] = chatMessages.map { (msgId, text) in
                    return AITranslationService.shared.translateIncomingWithContext(
                        text: text,
                        chatId: peerId,
                        context: contextMessages
                    )
                    |> map { translatedText -> (MessageId, String, String)? in
                        if translatedText == text {
                            return nil  // Translation failed
                        }
                        return (msgId, text, translatedText)
                    }
                }

                return combineLatest(translateSignals)
                |> mapToSignal { results -> Signal<Void, NoError> in
                    let succeeded = results.compactMap { $0 }
                    let failedIds = chatMessages.compactMap { (msgId, _) -> MessageId? in
                        if succeeded.contains(where: { $0.0 == msgId }) { return nil }
                        return msgId
                    }

                    let storeSignal: Signal<Void, NoError> = succeeded.isEmpty ? .complete() :
                        context.account.postbox.transaction { transaction in
                            for (msgId, _, translatedText) in succeeded {
                                Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                            }
                        } |> map { _ in }

                    if !failedIds.isEmpty {
                        print("[AITranslation] \(failedIds.count) context translations failed, scheduling retry")
                        DispatchQueue.main.async {
                            Self.scheduleRetry(ids: failedIds, attempt: 0, context: context)
                        }
                    }

                    return storeSignal
                }
            }
            signals.append(chatSignal)
        }

        return combineLatest(signals) |> map { _ in }
    }

    // MARK: - Retry Mechanism

    private static func scheduleRetry(ids: [MessageId], attempt: Int, context: AccountContext) {
        guard attempt < retryDelays.count else {
            print("[AITranslation] All \(retryDelays.count) retries exhausted for \(ids.count) messages")
            return
        }
        let delay = retryDelays[attempt]
        print("[AITranslation] Scheduling retry \(attempt + 1)/\(retryDelays.count) for \(ids.count) messages in \(delay)s")

        DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
            let _ = (context.account.postbox.transaction { transaction -> [(MessageId, String, PeerId)] in
                var toRetry: [(MessageId, String, PeerId)] = []
                for id in ids {
                    guard let message = transaction.getMessage(id) else { continue }
                    if !message.text.isEmpty,
                       !message.attributes.contains(where: { $0 is TranslationMessageAttribute }) {
                        toRetry.append((id, message.text, id.peerId))
                    }
                }
                return toRetry
            }
            |> deliverOnMainQueue
            |> mapToSignal { toRetry -> Signal<Void, NoError> in
                guard !toRetry.isEmpty else {
                    print("[AITranslation] Retry \(attempt + 1): all messages already translated")
                    return .complete()
                }
                print("[AITranslation] Retry \(attempt + 1): retrying \(toRetry.count) messages")

                if AITranslationSettings.incomingContextMode == 2 {
                    return Self.translateWithContextRetry(messages: toRetry, attempt: attempt, context: context)
                } else {
                    return Self.translateBatchRetry(messages: toRetry, attempt: attempt, context: context)
                }
            }).start()
        }
    }

    private static func translateBatchRetry(messages: [(MessageId, String, PeerId)], attempt: Int, context: AccountContext) -> Signal<Void, NoError> {
        var textDict: [AnyHashable: String] = [:]
        var idMap: [String: MessageId] = [:]
        for (i, (msgId, text, _)) in messages.enumerated() {
            let key = "\(i)"
            textDict[key as AnyHashable] = text
            idMap[key] = msgId
        }

        return AITranslationService.shared.translateTexts(texts: textDict, fromLang: "de", toLang: "en")
        |> mapToSignal { results -> Signal<Void, NoError> in
            guard let results = results else {
                Self.scheduleRetry(ids: messages.map { $0.0 }, attempt: attempt + 1, context: context)
                return .complete()
            }
            return context.account.postbox.transaction { transaction in
                var stillFailed: [MessageId] = []
                for (key, msgId) in idMap {
                    if let translatedText = results[key as AnyHashable] {
                        let originalText = textDict[key as AnyHashable]
                        if let orig = originalText, translatedText == orig {
                            stillFailed.append(msgId)
                            continue
                        }
                        Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                    } else {
                        stillFailed.append(msgId)
                    }
                }
                if !stillFailed.isEmpty {
                    DispatchQueue.main.async {
                        Self.scheduleRetry(ids: stillFailed, attempt: attempt + 1, context: context)
                    }
                }
            } |> map { _ in }
        }
    }

    private static func translateWithContextRetry(messages: [(MessageId, String, PeerId)], attempt: Int, context: AccountContext) -> Signal<Void, NoError> {
        var chatGroups: [PeerId: [(MessageId, String)]] = [:]
        for (msgId, text, peerId) in messages {
            chatGroups[peerId, default: []].append((msgId, text))
        }

        var signals: [Signal<Void, NoError>] = []

        for (peerId, chatMessages) in chatGroups {
            let chatSignal = ConversationContextProvider.getContext(
                chatId: peerId,
                context: context,
                direction: "incoming"
            )
            |> mapToSignal { contextMessages -> Signal<Void, NoError> in
                let translateSignals: [Signal<(MessageId, String, String)?, NoError>] = chatMessages.map { (msgId, text) in
                    return AITranslationService.shared.translateIncomingWithContext(
                        text: text,
                        chatId: peerId,
                        context: contextMessages
                    )
                    |> map { translatedText -> (MessageId, String, String)? in
                        if translatedText == text { return nil }
                        return (msgId, text, translatedText)
                    }
                }

                return combineLatest(translateSignals)
                |> mapToSignal { results -> Signal<Void, NoError> in
                    let succeeded = results.compactMap { $0 }
                    let failedIds = chatMessages.compactMap { (msgId, _) -> MessageId? in
                        if succeeded.contains(where: { $0.0 == msgId }) { return nil }
                        return msgId
                    }

                    let storeSignal: Signal<Void, NoError> = succeeded.isEmpty ? .complete() :
                        context.account.postbox.transaction { transaction in
                            for (msgId, _, translatedText) in succeeded {
                                Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                            }
                        } |> map { _ in }

                    if !failedIds.isEmpty {
                        DispatchQueue.main.async {
                            Self.scheduleRetry(ids: failedIds, attempt: attempt + 1, context: context)
                        }
                    }

                    return storeSignal
                }
            }
            signals.append(chatSignal)
        }

        return combineLatest(signals) |> map { _ in }
    }

    // MARK: - Catch-Up Translation

    /// Scan recent messages in a chat and translate any incoming messages
    /// that don't have a TranslationMessageAttribute yet.
    /// Call this when a chat opens to catch up on untranslated messages.
    public static func translateMessages(peerId: PeerId, context: AccountContext) {
        guard AITranslationSettings.enabled, AITranslationSettings.autoTranslateIncoming else { return }

        let accountPeerId = context.account.peerId
        let useContext = AITranslationSettings.incomingContextMode == 2

        let _ = (context.account.postbox.transaction { transaction -> [(MessageId, String)] in
            var toTranslate: [(MessageId, String)] = []
            transaction.scanTopMessages(peerId: peerId, namespace: Namespaces.Message.Cloud, limit: 100) { message in
                if message.author?.id != accountPeerId,
                   !message.text.isEmpty,
                   !message.attributes.contains(where: { $0 is TranslationMessageAttribute }) {
                    toTranslate.append((message.id, message.text))
                }
                return true
            }
            return toTranslate
        }
        |> deliverOnMainQueue
        |> mapToSignal { toTranslate -> Signal<Void, NoError> in
            guard !toTranslate.isEmpty else { return .complete() }

            if useContext {
                let messages = toTranslate.map { ($0.0, $0.1, peerId) }
                return Self.translateWithContext(messages: messages, context: context)
            } else {
                var textDict: [AnyHashable: String] = [:]
                var idMap: [String: MessageId] = [:]
                for (i, (msgId, text)) in toTranslate.enumerated() {
                    let key = "\(i)"
                    textDict[key as AnyHashable] = text
                    idMap[key] = msgId
                }

                return AITranslationService.shared.translateTexts(texts: textDict, fromLang: "de", toLang: "en")
                |> mapToSignal { results -> Signal<Void, NoError> in
                    guard let results = results else { return .complete() }
                    return context.account.postbox.transaction { transaction in
                        for (key, translatedText) in results {
                            guard let k = key as? String, let msgId = idMap[k] else { continue }
                            let originalText = textDict[k as AnyHashable]
                            if let orig = originalText, translatedText == orig {
                                continue
                            }
                            Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                        }
                    } |> map { _ in }
                }
            }
        }).start()
    }

    // MARK: - Secondary: notificationMessages Observer

    private let disposable = MetaDisposable()

    private init(context: AccountContext) {
        let accountPeerId = context.account.peerId

        disposable.set((context.account.stateManager.notificationMessages
        |> deliverOn(Queue.mainQueue())).start(next: { messageList in
            guard AITranslationSettings.enabled, AITranslationSettings.autoTranslateIncoming else { return }

            for (messages, _, _, _) in messageList {
                var toTranslate: [(MessageId, String, PeerId)] = []
                for message in messages {
                    guard message.author?.id != accountPeerId,
                          !message.text.isEmpty,
                          !message.attributes.contains(where: { $0 is TranslationMessageAttribute })
                    else { continue }
                    toTranslate.append((message.id, message.text, message.id.peerId))
                }
                guard !toTranslate.isEmpty else { continue }

                if AITranslationSettings.incomingContextMode == 2 {
                    let _ = Self.translateWithContext(messages: toTranslate, context: context).start()
                } else {
                    let _ = Self.translateBatchMessages(messages: toTranslate, context: context).start()
                }
            }
        }))
    }

    deinit {
        disposable.dispose()
    }

    // MARK: - Shared Storage Logic

    private static func storeTranslation(transaction: Transaction, msgId: MessageId, translatedText: String) {
        transaction.updateMessage(msgId, update: { currentMessage in
            var attributes = currentMessage.attributes
            guard !attributes.contains(where: { $0 is TranslationMessageAttribute }) else {
                return .skip
            }
            attributes.append(TranslationMessageAttribute(text: translatedText, entities: [], toLang: "en"))

            var storeForwardInfo: StoreMessageForwardInfo?
            if let info = currentMessage.forwardInfo {
                storeForwardInfo = StoreMessageForwardInfo(
                    authorId: info.author?.id,
                    sourceId: info.source?.id,
                    sourceMessageId: info.sourceMessageId,
                    date: info.date,
                    authorSignature: info.authorSignature,
                    psaType: info.psaType,
                    flags: info.flags
                )
            }

            return .update(StoreMessage(
                id: currentMessage.id,
                globallyUniqueId: currentMessage.globallyUniqueId,
                groupingKey: currentMessage.groupingKey,
                threadId: currentMessage.threadId,
                timestamp: currentMessage.timestamp,
                flags: StoreMessageFlags(currentMessage.flags),
                tags: currentMessage.tags,
                globalTags: currentMessage.globalTags,
                localTags: currentMessage.localTags,
                forwardInfo: storeForwardInfo,
                authorId: currentMessage.author?.id,
                text: currentMessage.text,
                attributes: attributes,
                media: currentMessage.media
            ))
        })
    }
}
