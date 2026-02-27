#!/usr/bin/env python3
"""Patch ApplicationContext.swift to start the background translation observer.

Adds a call to AIBackgroundTranslationObserver.startIfNeeded(context:) in
AuthorizedApplicationContext.init() so incoming messages are pre-translated
at the data layer, even when the chat is not open.
"""
import sys


def patch_application_context(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # 1. Add import AITranslation
    if "import AITranslation" not in content:
        content = content.replace("import UIKit", "import UIKit\nimport AITranslation", 1)
        print("Added import AITranslation")

    # 2. Insert observer startup before the notificationMessagesDisposable setup.
    # Target: the unique line where notificationMessagesDisposable subscribes to notificationMessages.
    target = "self.notificationMessagesDisposable.set((context.account.stateManager.notificationMessages"

    if target not in content:
        print("ERROR: Could not find notificationMessagesDisposable.set target in ApplicationContext.swift")
        print("Background incoming translation will NOT work.")
        return

    observer_code = """// AI Translation: start background translation observer for incoming messages
            AIBackgroundTranslationObserver.startIfNeeded(context: context)

            """

    # Check if already patched
    if "AIBackgroundTranslationObserver.startIfNeeded" in content:
        print("Already patched, skipping.")
        return

    content = content.replace(target, observer_code + target, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath} with AIBackgroundTranslationObserver startup")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ApplicationContext.swift>")
        sys.exit(1)

    patch_application_context(sys.argv[1])
