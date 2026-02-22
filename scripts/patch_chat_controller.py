#!/usr/bin/env python3
"""
Patches ChatController.swift to intercept outgoing text messages
for AI translation before they are enqueued for sending.

This modifies the sendMessages() function to:
1. Check if AI translation is enabled for the current chat
2. If so, translate the text via AITranslationService before sending
3. If not, pass the message through unchanged
"""
import sys
import re


def patch_chat_controller(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # Find the sendMessages function and add translation interception.
    # We look for the pattern where enqueueMessages is called inside sendMessages
    # and wrap it with a translation step.

    # Strategy: Find `func sendMessages` and inject translation logic
    # before the enqueueMessages call.

    # Look for the sendMessages function signature
    send_messages_pattern = (
        r'(func sendMessages\(\s*_\s+messages:\s*\[EnqueueMessage\].*?\{)'
    )

    match = re.search(send_messages_pattern, content, re.DOTALL)
    if not match:
        print("WARNING: Could not find sendMessages function, trying alternate pattern")
        # Try alternate pattern
        send_messages_pattern = r'(func sendMessages\(.*?\{)'
        match = re.search(send_messages_pattern, content, re.DOTALL)

    if not match:
        print("ERROR: Could not find sendMessages function in ChatController.swift")
        print("Outgoing message interception will not be applied.")
        print("You may need to manually add the translation hook.")
        return

    # Find the enqueueMessages call within sendMessages
    # We'll add a wrapper that translates before enqueueing
    enqueue_pattern = r'(let\s+_\s*=\s*\(enqueueMessages\(\s*account:\s*self\.context\.account)'

    enqueue_match = re.search(enqueue_pattern, content[match.start():], re.DOTALL)
    if not enqueue_match:
        # Try broader pattern
        enqueue_pattern = r'(enqueueMessages\(\s*account:\s*\w+\.context\.account)'
        enqueue_match = re.search(enqueue_pattern, content[match.start():], re.DOTALL)

    if not enqueue_match:
        print("WARNING: Could not find enqueueMessages call in sendMessages.")
        print("Falling back to alternate interception strategy.")
        _patch_send_message_callback(filepath, content)
        return

    print("Found sendMessages function and enqueueMessages call. Patching...")

    # Instead of modifying the complex sendMessages function,
    # let's add a wrapper method and modify sendMessages to call it
    _patch_with_wrapper_method(filepath, content)


def _patch_send_message_callback(filepath: str, content: str) -> None:
    """
    Alternate strategy: Patch the sendMessage callback where user text
    is first captured, before it becomes an EnqueueMessage.

    Look for the pattern:
        strongSelf.sendMessages([.message(text: text,
    """
    # Find the sendMessage callback (text input handler)
    # Pattern: sendMessages([.message(text: text,
    pattern = r'(strongSelf\.sendMessages\(\[\.message\(\s*text:\s*)(text)(,\s*attributes:\s*)'

    matches = list(re.finditer(pattern, content))
    if not matches:
        print("ERROR: Could not find sendMessage text callback pattern")
        return

    # We'll modify the last occurrence (the regular text message, not emoji)
    # by wrapping it in a translation check
    print(f"Found {len(matches)} sendMessages call(s) with text parameter")

    # For a robust approach, we add a helper method to the class
    # and modify the text before sending

    # Add helper method before the closing brace of the class
    helper_method = '''
    // MARK: - AI Translation Helper
    private func aiTranslateAndSend(text: String, attributes: [MessageAttribute], inlineStickers: [MediaId: Media], mediaReference: AnyMediaReference?, threadId: Int64?, replyToMessageId: EngineMessageReplySubject?, replyToStoryId: StoryId?, localGroupingKey: Int64?, correlationId: Int64?, bubbleUpEmojiOrStickersets: [ItemCollectionId]) {
        guard let peerId = self.chatLocation.peerId else { return }
        if AITranslationSettings.enabled && AITranslationSettings.autoTranslateOutgoing && AITranslationService.shared.isEnabledForChat(peerId) {
            let _ = (AITranslationService.shared.translateOutgoing(text: text, chatId: peerId, context: self.context)
            |> deliverOnMainQueue).startStandalone(next: { [weak self] translatedText in
                guard let self = self else { return }
                self.sendMessages([.message(text: translatedText, attributes: attributes, inlineStickers: inlineStickers, mediaReference: mediaReference, threadId: threadId, replyToMessageId: replyToMessageId, replyToStoryId: replyToStoryId, localGroupingKey: localGroupingKey, correlationId: correlationId, bubbleUpEmojiOrStickersets: bubbleUpEmojiOrStickersets)])
            })
        } else {
            self.sendMessages([.message(text: text, attributes: attributes, inlineStickers: inlineStickers, mediaReference: mediaReference, threadId: threadId, replyToMessageId: replyToMessageId, replyToStoryId: replyToStoryId, localGroupingKey: localGroupingKey, correlationId: correlationId, bubbleUpEmojiOrStickersets: bubbleUpEmojiOrStickersets)])
        }
    }
'''

    # Find the last closing brace of the class to insert before it
    # Count braces to find class end
    last_brace = content.rfind("}")
    if last_brace == -1:
        print("ERROR: Could not find end of class")
        return

    content = content[:last_brace] + helper_method + "\n" + content[last_brace:]

    with open(filepath, "w") as f:
        f.write(content)

    print("Added aiTranslateAndSend helper method to ChatController")
    print("NOTE: You still need to replace sendMessages calls with aiTranslateAndSend calls")
    print("for text messages in the sendMessage callback.")


def _patch_with_wrapper_method(filepath: str, content: str) -> None:
    """
    Add an AI translation wrapper method to ChatController.
    This method is called by the sendMessage text input callback
    instead of directly calling sendMessages.
    """
    helper_method = '''
    // MARK: - AI Translation Outgoing Hook
    private func aiTranslateAndSendMessages(_ messages: [EnqueueMessage], media: Bool = false, postpone: Bool = false, commit: Bool = false) {
        guard let peerId = self.chatLocation.peerId else {
            self.sendMessages(messages, media: media, postpone: postpone, commit: commit)
            return
        }

        guard AITranslationSettings.enabled && AITranslationSettings.autoTranslateOutgoing && AITranslationService.shared.isEnabledForChat(peerId) else {
            self.sendMessages(messages, media: media, postpone: postpone, commit: commit)
            return
        }

        // Translate text messages, pass through non-text messages unchanged
        let signals: [Signal<EnqueueMessage, NoError>] = messages.map { message in
            switch message {
            case let .message(text, attributes, inlineStickers, mediaReference, threadId, replyToMessageId, replyToStoryId, localGroupingKey, correlationId, bubbleUpEmojiOrStickersets):
                guard !text.isEmpty else {
                    return .single(message)
                }
                return AITranslationService.shared.translateOutgoing(
                    text: text,
                    chatId: peerId,
                    context: self.context
                )
                |> map { translatedText -> EnqueueMessage in
                    return .message(text: translatedText, attributes: attributes, inlineStickers: inlineStickers, mediaReference: mediaReference, threadId: threadId, replyToMessageId: replyToMessageId, replyToStoryId: replyToStoryId, localGroupingKey: localGroupingKey, correlationId: correlationId, bubbleUpEmojiOrStickersets: bubbleUpEmojiOrStickersets)
                }
            case .forward:
                return .single(message)
            }
        }

        let _ = (combineLatest(signals)
        |> deliverOnMainQueue).startStandalone(next: { [weak self] translatedMessages in
            guard let self = self else { return }
            self.sendMessages(translatedMessages, media: media, postpone: postpone, commit: commit)
        })
    }
'''

    # Insert the helper method before the last closing brace of the class
    last_brace = content.rfind("}")
    content = content[:last_brace] + helper_method + "\n" + content[last_brace:]

    # Now replace the direct sendMessages call in the text input callback
    # with aiTranslateAndSendMessages
    # Look for: strongSelf.sendMessages([.message(text: text,
    # But ONLY in the sendMessage callback context (not all sendMessages calls)

    # Find the sendMessage callback pattern
    callback_pattern = r'sendMessage:\s*\{\s*\[weak\s+self\]\s+text\s+in'
    callback_match = re.search(callback_pattern, content)

    if callback_match:
        # Find sendMessages calls within the next ~100 lines after callback
        search_start = callback_match.end()
        search_end = min(search_start + 5000, len(content))
        region = content[search_start:search_end]

        # Replace sendMessages with aiTranslateAndSendMessages in this region
        # Only for .message calls (not .forward)
        modified_region = region.replace(
            "strongSelf.sendMessages([.message(",
            "strongSelf.aiTranslateAndSendMessages([.message(",
            2  # Replace first 2 occurrences in the callback region
        )

        if modified_region != region:
            content = content[:search_start] + modified_region + content[search_end:]
            print("Replaced sendMessages with aiTranslateAndSendMessages in sendMessage callback")
        else:
            print("WARNING: Could not find sendMessages calls in sendMessage callback region")
            # Try broader replacement pattern
            modified_region = region.replace(
                "self.sendMessages([.message(",
                "self.aiTranslateAndSendMessages([.message(",
                2
            )
            if modified_region != region:
                content = content[:search_start] + modified_region + content[search_end:]
                print("Replaced self.sendMessages with self.aiTranslateAndSendMessages")
    else:
        print("WARNING: Could not find sendMessage callback, skipping replacement")

    with open(filepath, "w") as f:
        f.write(content)

    print("ChatController.swift patched successfully")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatController.swift>")
        sys.exit(1)

    patch_chat_controller(sys.argv[1])
