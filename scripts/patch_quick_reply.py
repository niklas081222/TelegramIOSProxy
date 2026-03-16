#!/usr/bin/env python3
"""Patch ChatControllerLoadDisplayNode.swift to translate Quick Reply shortcuts.

Telegram Premium's Quick Reply feature calls sendMessageShortcut() which sends
messages via the server API directly (messages.sendQuickReplyMessages), completely
bypassing all local translation patches. English templates arrive untranslated.

This patch intercepts the sendShortcut closure to:
1. Fetch the shortcut's messages from local storage
2. Route them through sendMessages() which our existing patches translate
3. Fall back to the original server-side path if translation is disabled
"""
import sys


def patch_quick_reply(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    if "AI Translation: intercept quick reply" in content:
        print("Already patched, skipping.")
        return

    old_code = "self.context.engine.accountData.sendMessageShortcut(peerId: peerId, id: shortcutId)"

    if old_code not in content:
        print("FATAL: Could not find sendMessageShortcut call in ChatControllerLoadDisplayNode.swift")
        print("Quick reply translation will NOT work.")
        sys.exit(1)

    new_code = """// AI Translation: intercept quick reply to translate before sending
            let _ = (self.context.account.viewTracker.quickReplyMessagesViewForLocation(quickReplyId: shortcutId)
            |> take(1)
            |> deliverOnMainQueue).start(next: { [weak self] view, _, _ in
                guard let self = self else { return }

                if !AITranslationSettings.enabled || !AITranslationSettings.autoTranslateOutgoing || AIBackgroundTranslationObserver.botChatIds.contains(peerId.id._internalGetInt64Value()) {
                    self.context.engine.accountData.sendMessageShortcut(peerId: peerId, id: shortcutId)
                    return
                }

                var messagesToSend: [EnqueueMessage] = []
                for entry in view.entries {
                    let msg = entry.message
                    let text = msg.text
                    let mediaRef = msg.media.first.flatMap { AnyMediaReference.standalone(media: $0) }
                    messagesToSend.append(.message(
                        text: text,
                        attributes: [],
                        inlineStickers: [:],
                        mediaReference: mediaRef,
                        threadId: self.chatLocation.threadId,
                        replyToMessageId: nil,
                        replyToStoryId: nil,
                        localGroupingKey: nil,
                        correlationId: nil,
                        bubbleUpEmojiOrStickersets: []
                    ))
                }

                if messagesToSend.isEmpty {
                    self.context.engine.accountData.sendMessageShortcut(peerId: peerId, id: shortcutId)
                    return
                }

                self.sendMessages(messagesToSend)
            })"""

    content = content.replace(old_code, new_code, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: quick reply shortcut translation")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatControllerLoadDisplayNode.swift>")
        sys.exit(1)

    patch_quick_reply(sys.argv[1])
