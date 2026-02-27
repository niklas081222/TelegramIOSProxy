import Foundation
import SwiftSignalKit
import TelegramCore
import Postbox
import AccountContext

/// Observes incoming messages at the data layer and pre-translates them
/// so translations are available before the user opens the chat.
///
/// Subscribes to `account.stateManager.notificationMessages` which fires
/// for all incoming messages from the server. For each batch, translates
/// message text via the batch API and stores `TranslationMessageAttribute`
/// on the message in Postbox.
public final class AIBackgroundTranslationObserver {
    private static var shared: AIBackgroundTranslationObserver?

    /// Call once when an authorized account is available.
    public static func startIfNeeded(context: AccountContext) {
        guard shared == nil else { return }
        shared = AIBackgroundTranslationObserver(context: context)
    }

    private let disposable = MetaDisposable()

    private init(context: AccountContext) {
        let accountPeerId = context.account.peerId

        disposable.set((context.account.stateManager.notificationMessages
        |> deliverOn(Queue.mainQueue())).start(next: { messageList in
            guard AITranslationSettings.enabled, AITranslationSettings.autoTranslateIncoming else { return }

            for (messages, _, _, _) in messageList {
                var toTranslate: [(MessageId, String)] = []
                for message in messages {
                    // Skip own messages, empty text, already translated
                    guard message.author?.id != accountPeerId,
                          !message.text.isEmpty,
                          !message.attributes.contains(where: { $0 is TranslationMessageAttribute })
                    else { continue }
                    toTranslate.append((message.id, message.text))
                }
                guard !toTranslate.isEmpty else { continue }

                // Build batch request keyed by index string
                var textDict: [AnyHashable: String] = [:]
                var idMap: [String: MessageId] = [:]
                for (i, (msgId, text)) in toTranslate.enumerated() {
                    let key = "\(i)"
                    textDict[key as AnyHashable] = text
                    idMap[key] = msgId
                }

                // Translate via batch API, then store TranslationMessageAttribute in Postbox
                let _ = (AITranslationService.shared.translateTexts(texts: textDict, fromLang: "de", toLang: "en")
                |> mapToSignal { results -> Signal<Void, NoError> in
                    guard let results = results else { return .complete() }
                    return context.account.postbox.transaction { transaction in
                        for (key, translatedText) in results {
                            guard let k = key as? String, let msgId = idMap[k] else { continue }
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
                    } |> map { _ in }
                }).start()
            }
        }))
    }

    deinit {
        disposable.dispose()
    }
}
