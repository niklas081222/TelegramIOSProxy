#!/usr/bin/env python3
"""Patch ChatControllerLoadDisplayNode.swift to trigger catch-up translation on chat open.

When a chat is opened, this patch triggers AIBackgroundTranslationObserver.translateMessages()
to stream-translate any messages missing a TranslationMessageAttribute (newest first).

Does NOT set translationState — Telegram's built-in batch pipeline is intentionally
bypassed. All translations go through our streaming catch-up exclusively.
"""
import sys
import re


def patch_incoming_translation(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # Target line: presentationInterfaceState = presentationInterfaceState.updatedTranslationState(contentData.state.translationState)
    # We add our override right after it.

    target = "presentationInterfaceState = presentationInterfaceState.updatedTranslationState(contentData.state.translationState)"

    if target not in content:
        print("ERROR: Could not find updatedTranslationState line")
        print("Incoming auto-translation will NOT work.")
        return

    override_code = """presentationInterfaceState = presentationInterfaceState.updatedTranslationState(contentData.state.translationState)

            // AI Translation: catch-up translate on chat open (streaming, newest first)
            if AITranslationSettings.enabled && AITranslationSettings.autoTranslateIncoming {
                if case let .peer(chatPeerId) = self.chatLocation {
                    AIBackgroundTranslationObserver.translateMessages(peerId: chatPeerId, context: self.context)
                }
            }"""

    content = content.replace(target, override_code, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath} with incoming auto-translation override + catch-up")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatControllerLoadDisplayNode.swift>")
        sys.exit(1)

    patch_incoming_translation(sys.argv[1])
