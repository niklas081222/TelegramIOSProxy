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

            // Read recent messages from the chat using scanTopMessages
            var messages: [Message] = []
            transaction.scanTopMessages(peerId: chatId, namespace: Namespaces.Message.Cloud, limit: messageCount) { message in
                messages.append(message)
                return true
            }

            // Sort chronologically (scanTopMessages returns newest first)
            messages.sort { $0.timestamp < $1.timestamp }

            // Convert to context messages
            var contextMessages: [AIContextMessage] = []
            for message in messages {
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
