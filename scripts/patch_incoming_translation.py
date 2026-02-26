#!/usr/bin/env python3
"""Patch ChatControllerLoadDisplayNode.swift to auto-enable incoming translation.

Telegram's built-in translation requires the user to manually tap the "Translate"
banner. This patch auto-sets translationState to enabled (fromLang: "de", toLang: "en")
when our AI translation is active, triggering Telegram's built-in pipeline which calls
our AIExperimentalTranslationService.
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

            // AI Translation: auto-enable incoming translation when our service is active
            if AITranslationSettings.enabled && AITranslationSettings.autoTranslateIncoming {
                let existingState = presentationInterfaceState.translationState
                if existingState == nil || existingState?.isEnabled != true {
                    presentationInterfaceState = presentationInterfaceState.updatedTranslationState(
                        ChatPresentationTranslationState(isEnabled: true, fromLang: "de", toLang: "en")
                    )
                }
            }"""

    content = content.replace(target, override_code, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath} with incoming auto-translation override")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatControllerLoadDisplayNode.swift>")
        sys.exit(1)

    patch_incoming_translation(sys.argv[1])
