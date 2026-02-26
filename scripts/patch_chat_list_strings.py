#!/usr/bin/env python3
"""Patch ChatListItemStrings.swift to show translated text in chat list preview.

The chat list overview shows the last message preview using raw message.text.
When incoming messages are translated (TranslationMessageAttribute stored on the message),
the chat list preview still shows the original German text. This patch checks for
TranslationMessageAttribute and uses the translated text for the preview.
"""
import sys


def patch_chat_list_strings(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # Target: the loop that extracts messageText from messages
    old = """        for message in messages {
            if !message.text.isEmpty {
                messageText = message.text
                break
            }
        }"""

    if old not in content:
        print("ERROR: Could not find messageText extraction loop in ChatListItemStrings.swift")
        print("Chat list preview will NOT show translated text.")
        return

    new = """        for message in messages {
            if !message.text.isEmpty {
                messageText = message.text
                if let translation = message.attributes.first(where: { $0 is TranslationMessageAttribute }) as? TranslationMessageAttribute, !translation.text.isEmpty {
                    messageText = translation.text
                }
                break
            }
        }"""

    content = content.replace(old, new, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: chat list preview now shows translated text")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatListItemStrings.swift>")
        sys.exit(1)

    patch_chat_list_strings(sys.argv[1])
