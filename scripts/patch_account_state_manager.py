#!/usr/bin/env python3
"""Patch AccountStateManager.swift to add a callback for ALL new incoming messages.

The existing `notificationMessages` signal filters out muted chats via
`messagesForNotification(alwaysReturnMessage: false)`. This callback bypasses
that filtering and fires for ALL new real-time incoming messages, enabling
background translation regardless of notification settings.

Pattern follows `engineExperimentalInternalTranslationService` in Translate.swift:
public global callback in TelegramCore, set from AITranslation module.
"""
import sys


def patch_account_state_manager(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # 1. Add the public global callback at file scope (before first enum/class)
    global_target = "private enum AccountStateManagerOperationContent"

    if global_target not in content:
        print("ERROR: Could not find AccountStateManagerOperationContent in AccountStateManager.swift")
        print("Background translation callback will NOT be installed.")
        return

    if "aiNewIncomingMessagesCallback" in content:
        print("Already patched, skipping.")
        return

    global_callback = """// AI Translation: callback for new incoming messages (set by AITranslation module)
public var aiNewIncomingMessagesCallback: (([MessageId]) -> Void)?

private enum AccountStateManagerOperationContent"""

    content = content.replace(global_target, global_callback, 1)
    print("Added aiNewIncomingMessagesCallback global")

    # 2. Insert callback invocation after notificationMessages processing.
    # Target: the line right after the notificationMessages pipe block,
    # identifiable by the timestamp line that follows it.
    call_target = "                let timestamp = Int32(Date().timeIntervalSince1970)\n                let minReactionTimestamp = timestamp - 20"

    if call_target not in content:
        print("ERROR: Could not find timestamp/minReactionTimestamp block after notificationMessages processing")
        print("Background translation callback will NOT fire.")
        return

    callback_call = """                // AI Translation: notify background observer of ALL new incoming messages
                if !events.addedIncomingMessageIds.isEmpty {
                    let ids = Array(events.addedIncomingMessageIds)
                    DispatchQueue.main.async {
                        aiNewIncomingMessagesCallback?(ids)
                    }
                }

                let timestamp = Int32(Date().timeIntervalSince1970)
                let minReactionTimestamp = timestamp - 20"""

    content = content.replace(call_target, callback_call, 1)
    print("Added callback invocation after notificationMessages processing")

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath} with aiNewIncomingMessagesCallback for background translation")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_AccountStateManager.swift>")
        sys.exit(1)

    patch_account_state_manager(sys.argv[1])
