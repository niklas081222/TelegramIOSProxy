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

        let _ = (context.account.postbox.transaction { transaction -> [(MessageId, String)] in
            var toTranslate: [(MessageId, String)] = []
            for id in ids {
                guard let message = transaction.getMessage(id) else { continue }
                // Only translate: incoming, recent (after app start), non-empty, not already translated
                if message.author?.id != accountPeerId,
                   message.timestamp >= startTs - 10,
                   !message.text.isEmpty,
                   !message.attributes.contains(where: { $0 is TranslationMessageAttribute }) {
                    toTranslate.append((message.id, message.text))
                }
            }
            return toTranslate
        }
        |> deliverOnMainQueue
        |> mapToSignal { toTranslate -> Signal<Void, NoError> in
            guard !toTranslate.isEmpty else { return .complete() }

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
                        Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                    }
                } |> map { _ in }
            }
        }).start()
    }

    // MARK: - Catch-Up Translation

    /// Scan recent messages in a chat and translate any incoming messages
    /// that don't have a TranslationMessageAttribute yet.
    /// Call this when a chat opens to catch up on untranslated messages.
    public static func translateMessages(peerId: PeerId, context: AccountContext) {
        guard AITranslationSettings.enabled, AITranslationSettings.autoTranslateIncoming else { return }

        let accountPeerId = context.account.peerId

        let _ = (context.account.postbox.transaction { transaction -> [(MessageId, String)] in
            var toTranslate: [(MessageId, String)] = []
            transaction.scanTopMessages(peerId: peerId, namespace: Namespaces.Message.Cloud, limit: 50) { message in
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
                        Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                    }
                } |> map { _ in }
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
                var toTranslate: [(MessageId, String)] = []
                for message in messages {
                    guard message.author?.id != accountPeerId,
                          !message.text.isEmpty,
                          !message.attributes.contains(where: { $0 is TranslationMessageAttribute })
                    else { continue }
                    toTranslate.append((message.id, message.text))
                }
                guard !toTranslate.isEmpty else { continue }

                var textDict: [AnyHashable: String] = [:]
                var idMap: [String: MessageId] = [:]
                for (i, (msgId, text)) in toTranslate.enumerated() {
                    let key = "\(i)"
                    textDict[key as AnyHashable] = text
                    idMap[key] = msgId
                }

                let _ = (AITranslationService.shared.translateTexts(texts: textDict, fromLang: "de", toLang: "en")
                |> mapToSignal { results -> Signal<Void, NoError> in
                    guard let results = results else { return .complete() }
                    return context.account.postbox.transaction { transaction in
                        for (key, translatedText) in results {
                            guard let k = key as? String, let msgId = idMap[k] else { continue }
                            Self.storeTranslation(transaction: transaction, msgId: msgId, translatedText: translatedText)
                        }
                    } |> map { _ in }
                }).start()
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
