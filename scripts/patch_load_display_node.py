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

    new_code = f"""{indent}// AI Translation: fire-and-forget translate + enqueue for each message.
{indent}// Text input clears instantly; translation runs in background.
{indent}for aiMsg in transformedMessages {{
{indent}    switch aiMsg {{
{indent}    case let .message(text, attributes, inlineStickers, mediaReference, threadId, replyToMessageId, replyToStoryId, localGroupingKey, correlationId, bubbleUpEmojiOrStickersets):
{indent}        if !text.isEmpty && AITranslationSettings.enabled && AITranslationSettings.autoTranslateOutgoing {{
{indent}            let originalText = text
{indent}            let _ = (AITranslationService.shared.translateOutgoing(text: text, chatId: peerId, context: strongSelf.context)
{indent}            |> mapToSignal {{ translatedText -> Signal<[MessageId?], NoError> in
{indent}                var newAttributes = attributes
{indent}                newAttributes.append(TranslationMessageAttribute(text: originalText, entities: [], toLang: "en"))
{indent}                return enqueueMessages(account: strongSelf.context.account, peerId: peerId, messages: [.message(text: translatedText, attributes: newAttributes, inlineStickers: inlineStickers, mediaReference: mediaReference, threadId: threadId, replyToMessageId: replyToMessageId, replyToStoryId: replyToStoryId, localGroupingKey: localGroupingKey, correlationId: correlationId, bubbleUpEmojiOrStickersets: bubbleUpEmojiOrStickersets)])
{indent}            }}).start()
{indent}        }} else {{
{indent}            let _ = enqueueMessages(account: strongSelf.context.account, peerId: peerId, messages: [aiMsg]).start()
{indent}        }}
{indent}    case .forward:
{indent}        let _ = enqueueMessages(account: strongSelf.context.account, peerId: peerId, messages: [aiMsg]).start()
{indent}    }}
{indent}}}
{indent}signal = .single([])
{indent}// AI Translation: clear text input immediately since messages are enqueued asynchronously.
{indent}// setupSendActionOnViewUpdate() defers clearing until a Postbox view update, which won't
{indent}// happen until translation completes (1-3s). Bypass it by clearing directly.
{indent}if let textInputPanelNode = strongSelf.chatDisplayNode.inputPanelNode as? ChatTextInputPanelNode {{
{indent}    textInputPanelNode.text = ""
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
