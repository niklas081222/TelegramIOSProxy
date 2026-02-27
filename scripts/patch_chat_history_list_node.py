#!/usr/bin/env python3
"""Patch ChatHistoryListNode.swift to force incoming translation when AI translation is active.

Telegram's built-in translation pipeline in ChatHistoryListNode only sets
`translateToLanguage` when `(isPremium || autoTranslate) && translationState.isEnabled`.
For non-premium users without a persisted ChatTranslationState, this is always nil,
meaning zero messages are ever queued for translation.

This patch adds a fallback that forces `translateToLanguage` to ("de", "en") when
our AI translation service is active, bypassing both the premium guard and the
missing persisted state.

Uses regex for robust matching (tolerant of whitespace variations).
"""
import sys
import re


def patch_chat_history_list_node(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # Add import AITranslation at the top
    if "import AITranslation" not in content:
        content = content.replace("import UIKit", "import UIKit\nimport AITranslation", 1)
        print("Added import AITranslation")

    # Target: the end of the translateToLanguage extraction block.
    # Use regex for flexible whitespace matching to avoid silent failures.
    # Pattern: translateToLanguage = (normalizeTranslationLanguage(...), normalizeTranslationLanguage(languageCode))
    #          }
    pattern = re.compile(
        r'(translateToLanguage\s*=\s*\(normalizeTranslationLanguage\(translationState\.fromLang\),\s*normalizeTranslationLanguage\(languageCode\)\))'
        r'(\s*\})',
        re.DOTALL
    )

    match = pattern.search(content)
    if not match:
        # Fallback: try exact string match (original approach)
        target = "translateToLanguage = (normalizeTranslationLanguage(translationState.fromLang), normalizeTranslationLanguage(languageCode))\n                }"
        if target not in content:
            print("ERROR: Could not find translateToLanguage extraction block in ChatHistoryListNode.swift")
            print("Incoming translation override will NOT work.")
            return
        # Use the exact match
        override_code = target + """

                // AI Translation: force-enable incoming translation when our service is active
                if translateToLanguage == nil && AITranslationSettings.enabled && AITranslationSettings.autoTranslateIncoming {
                    translateToLanguage = ("de", "en")
                }"""
        content = content.replace(target, override_code, 1)
    else:
        # Use regex match — preserve original whitespace
        replacement = match.group(0) + """

                // AI Translation: force-enable incoming translation when our service is active
                if translateToLanguage == nil && AITranslationSettings.enabled && AITranslationSettings.autoTranslateIncoming {
                    translateToLanguage = ("de", "en")
                }"""
        content = content[:match.start()] + replacement + content[match.end():]

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath} with AI translation translateToLanguage override")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatHistoryListNode.swift>")
        sys.exit(1)

    patch_chat_history_list_node(sys.argv[1])
