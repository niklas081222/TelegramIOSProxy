#!/usr/bin/env python3
"""Patch ChatControllerLoadDisplayNode.swift for outgoing message translation.

The main user text input path goes through:
  ChatControllerNode.sendCurrentMessage()
    -> chatDisplayNode.sendMessages closure (in ChatControllerLoadDisplayNode.swift)
    -> enqueueMessages()

This bypasses ChatController.sendMessages() entirely, so our existing hook
in patch_chat_controller.py doesn't catch regular typed messages.

This patch intercepts the enqueueMessages() call in the closure to translate
text messages before they are enqueued.
"""
import sys
import re


def patch_load_display_node(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # Add import AITranslation at the top
    if "import AITranslation" not in content:
        content = content.replace("import UIKit", "import UIKit\nimport AITranslation", 1)
        print("Added import AITranslation")

    # Find the target: the single enqueueMessages call for regular (non-forward) messages
    # in the chatDisplayNode.sendMessages closure.
    #
    # Original:
    #   signal = enqueueMessages(account: strongSelf.context.account, peerId: peerId, messages: transformedMessages)
    #
    # We wrap it with translation:
    #   signal = AITranslationService.shared.translateOutgoingMessages(...)
    #            |> mapToSignal { translated in enqueueMessages(..., messages: translated) }

    old_line = "                        signal = enqueueMessages(account: strongSelf.context.account, peerId: peerId, messages: transformedMessages)"

    if old_line not in content:
        # Try without leading spaces
        old_line_pattern = r"(\s+)signal = enqueueMessages\(account: strongSelf\.context\.account, peerId: peerId, messages: transformedMessages\)"
        match = re.search(old_line_pattern, content)
        if not match:
            print("ERROR: Could not find enqueueMessages call for transformedMessages")
            print("The outgoing translation hook for typed messages will NOT work.")
            return
        old_line = match.group(0)
        indent = match.group(1)
    else:
        indent = "                        "

    new_code = f"""{indent}// AI Translation: translate text messages before enqueuing
{indent}var aiOriginalTexts: [Int: String] = [:]
{indent}let aiTranslateSignals: [Signal<EnqueueMessage, NoError>] = transformedMessages.enumerated().map {{ indexAndMsg in
{indent}    let index = indexAndMsg.offset
{indent}    let message = indexAndMsg.element
{indent}    switch message {{
{indent}    case let .message(text, attributes, inlineStickers, mediaReference, threadId, replyToMessageId, replyToStoryId, localGroupingKey, correlationId, bubbleUpEmojiOrStickersets):
{indent}        guard !text.isEmpty, AITranslationSettings.enabled, AITranslationSettings.autoTranslateOutgoing else {{
{indent}            return .single(message)
{indent}        }}
{indent}        aiOriginalTexts[index] = text
{indent}        return AITranslationService.shared.translateOutgoing(text: text, chatId: peerId, context: strongSelf.context)
{indent}        |> map {{ translatedText -> EnqueueMessage in
{indent}            return .message(text: translatedText, attributes: attributes, inlineStickers: inlineStickers, mediaReference: mediaReference, threadId: threadId, replyToMessageId: replyToMessageId, replyToStoryId: replyToStoryId, localGroupingKey: localGroupingKey, correlationId: correlationId, bubbleUpEmojiOrStickersets: bubbleUpEmojiOrStickersets)
{indent}        }}
{indent}    case .forward:
{indent}        return .single(message)
{indent}    }}
{indent}}}
{indent}let aiPostbox = strongSelf.context.account.postbox
{indent}signal = combineLatest(aiTranslateSignals)
{indent}|> mapToSignal {{ translatedMessages -> Signal<[MessageId?], NoError> in
{indent}    return enqueueMessages(account: strongSelf.context.account, peerId: peerId, messages: translatedMessages)
{indent}}}
{indent}|> map {{ messageIds -> [MessageId?] in
{indent}    if !aiOriginalTexts.isEmpty {{
{indent}        let capturedOriginals = aiOriginalTexts
{indent}        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {{
{indent}            let _ = (aiPostbox.transaction {{ transaction -> Void in
{indent}                for (index, maybeId) in messageIds.enumerated() {{
{indent}                    guard let msgId = maybeId, let original = capturedOriginals[index] else {{ continue }}
{indent}                    transaction.updateMessage(msgId, update: {{ currentMessage in
{indent}                        var storeForwardInfo: StoreMessageForwardInfo?
{indent}                        if let info = currentMessage.forwardInfo {{
{indent}                            storeForwardInfo = StoreMessageForwardInfo(authorId: info.author?.id, sourceId: info.source?.id, sourceMessageId: info.sourceMessageId, date: info.date, authorSignature: info.authorSignature, psaType: info.psaType, flags: info.flags)
{indent}                        }}
{indent}                        return .update(StoreMessage(peerId: currentMessage.id.peerId, namespace: currentMessage.id.namespace, globallyUniqueId: currentMessage.globallyUniqueId, groupingKey: currentMessage.groupingKey, threadId: currentMessage.threadId, timestamp: currentMessage.timestamp, flags: StoreMessageFlags(rawValue: currentMessage.flags.rawValue), tags: currentMessage.tags, globalTags: currentMessage.globalTags, localTags: currentMessage.localTags, forwardInfo: storeForwardInfo, authorId: currentMessage.author?.id, text: original, attributes: currentMessage.attributes, media: currentMessage.media))
{indent}                    }})
{indent}                }}
{indent}            }}).start()
{indent}        }}
{indent}    }}
{indent}    return messageIds
{indent}}}"""

    content = content.replace(old_line, new_code, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched enqueueMessages in {filepath} with AI translation hook")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatControllerLoadDisplayNode.swift>")
        sys.exit(1)

    patch_load_display_node(sys.argv[1])
