#!/usr/bin/env python3
"""Patch ChatMessageTextBubbleContentNode.swift to show translations for outgoing messages.

Telegram's message bubble only applies TranslationMessageAttribute for incoming messages
(guarded by `&& incoming`). For our outgoing translation flow, we attach the original
English text as a TranslationMessageAttribute on the message (while the German translation
goes as message.text for server delivery). This patch allows outgoing messages to also
display the TranslationMessageAttribute text, so the user sees English locally.
"""
import sys


def patch_text_bubble(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # Target: the translation guard that restricts to incoming messages only
    old = "} else if let translateToLanguage = item.associatedData.translateToLanguage, !item.message.text.isEmpty && incoming {\n                        isTranslating = true"

    if old not in content:
        print("ERROR: Could not find translateToLanguage && incoming guard in ChatMessageTextBubbleContentNode.swift")
        print("Outgoing messages will NOT display English locally.")
        return

    # Remove `&& incoming` from the condition, but only set isTranslating for incoming
    new = "} else if let translateToLanguage = item.associatedData.translateToLanguage, !item.message.text.isEmpty {\n                        if incoming {\n                            isTranslating = true\n                        }"

    content = content.replace(old, new, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: removed incoming guard for TranslationMessageAttribute display")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatMessageTextBubbleContentNode.swift>")
        sys.exit(1)

    patch_text_bubble(sys.argv[1])
