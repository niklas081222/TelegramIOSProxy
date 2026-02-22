import Foundation
import SwiftSignalKit
import TelegramCore
import Postbox
import AccountContext

public final class ConversationContextProvider {
    /// Fetches the last N messages from a chat for conversation context.
    /// Returns messages in chronological order with role labels.
    public static func getContext(
        chatId: PeerId,
        context: AccountContext,
        limit: Int? = nil
    ) -> Signal<[AIContextMessage], NoError> {
        let messageCount = limit ?? AITranslationSettings.contextMessageCount

        // If context mode is single message, return empty context
        if AITranslationSettings.contextMode == 1 {
            return .single([])
        }

        return context.account.postbox.transaction { transaction -> [AIContextMessage] in
            let accountPeerId = context.account.peerId

            // Read recent messages from the chat
            var messages: [Message] = []
            let historyView = transaction.getMessagesInRange(
                peerId: chatId,
                namespace: Namespaces.Message.Cloud,
                from: MessageIndex.upperBound(peerId: chatId, namespace: Namespaces.Message.Cloud),
                to: MessageIndex.lowerBound(peerId: chatId, namespace: Namespaces.Message.Cloud),
                limit: messageCount
            )
            messages = historyView

            // Also check local namespace for unsent messages
            let localMessages = transaction.getMessagesInRange(
                peerId: chatId,
                namespace: Namespaces.Message.Local,
                from: MessageIndex.upperBound(peerId: chatId, namespace: Namespaces.Message.Local),
                to: MessageIndex.lowerBound(peerId: chatId, namespace: Namespaces.Message.Local),
                limit: messageCount
            )
            messages.append(contentsOf: localMessages)

            // Sort chronologically
            messages.sort { $0.timestamp < $1.timestamp }

            // Take only the last N messages
            let recentMessages = messages.suffix(messageCount)

            // Convert to context messages
            var contextMessages: [AIContextMessage] = []
            for message in recentMessages {
                let text = message.text
                guard !text.isEmpty else { continue }

                let role: String
                if message.author?.id == accountPeerId {
                    role = "me"
                } else {
                    role = "them"
                }

                contextMessages.append(AIContextMessage(role: role, text: text))
            }

            return contextMessages
        }
    }
}
