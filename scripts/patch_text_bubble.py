#!/usr/bin/env python3
"""Patch ChatMessageTextBubbleContentNode.swift for translation display.

Three-way translateToLanguage fallback ensures translations display even when
Telegram's standard pipeline doesn't set translateToLanguage:
1. Standard translateToLanguage from ChatHistoryListNode (if it was set)
2. TranslationMessageAttribute exists on message → force ("de","en")
3. AITranslationSettings.enabled + incoming → force ("de","en") (catch-all)

Also adds `import AITranslation` for settings access.
"""
import sys
import re


def patch_text_bubble(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # 1. Add import AITranslation at the top
    if "import AITranslation" not in content:
        content = content.replace("import UIKit", "import UIKit\nimport AITranslation", 1)
        print("Added import AITranslation")

    # Target: the translation guard that restricts to incoming messages only
    # Original: } else if let translateToLanguage = item.associatedData.translateToLanguage, !item.message.text.isEmpty && incoming {
    #               isTranslating = true
    old = "} else if let translateToLanguage = item.associatedData.translateToLanguage, !item.message.text.isEmpty && incoming {\n                        isTranslating = true"

    if old not in content:
        print("ERROR: Could not find translateToLanguage && incoming guard in ChatMessageTextBubbleContentNode.swift")
        print("Translation display will NOT work correctly.")
        return

    # Three-way fallback for translateToLanguage:
    # 1. Standard from item.associatedData (Telegram's pipeline)
    # 2. TranslationMessageAttribute exists (background observer pre-translated)
    # 3. Settings enabled + incoming (catch-all for all incoming messages)
    # Note: item.associatedData.translateToLanguage is String? (target language only, e.g. "en")
    new = """} else if !item.message.text.isEmpty, let translateToLanguage = item.associatedData.translateToLanguage ?? ((item.message.attributes.contains(where: { $0 is TranslationMessageAttribute }) || (AITranslationSettings.enabled && AITranslationSettings.autoTranslateIncoming)) ? "en" : nil) {
                        // AI Translation: three-way translateToLanguage fallback (no incoming guard — own messages included)
                        if !item.message.attributes.contains(where: { $0 is TranslationMessageAttribute }) {
                            isTranslating = true
                        }"""

    content = content.replace(old, new, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: three-way translateToLanguage fallback for translation display")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatMessageTextBubbleContentNode.swift>")
        sys.exit(1)

    patch_text_bubble(sys.argv[1])
