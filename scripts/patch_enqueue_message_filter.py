#!/usr/bin/env python3
"""Patch EnqueueMessage.swift to whitelist TranslationMessageAttribute in the outgoing filter.

The filterMessageAttributesForOutgoingMessage() function uses a whitelist to decide which
MessageAttribute subtypes are stored in the Postbox for outgoing messages. Without this patch,
TranslationMessageAttribute falls through to `default: return false` and is silently discarded,
which means the original English text is lost before it reaches local storage.

This does NOT cause the attribute to be sent to Telegram's servers — PendingMessageManager
constructs API requests by extracting specific fields, not by sending raw attributes.
"""
import sys


def patch_enqueue_message_filter(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    old = "        case _ as SuggestedPostMessageAttribute:\n            return true\n        default:\n            return false"

    if old not in content:
        print("ERROR: Could not find SuggestedPostMessageAttribute/default pattern in EnqueueMessage.swift")
        print("TranslationMessageAttribute will NOT be preserved in outgoing messages.")
        return

    new = "        case _ as SuggestedPostMessageAttribute:\n            return true\n        case _ as TranslationMessageAttribute:\n            return true\n        default:\n            return false"

    content = content.replace(old, new, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: TranslationMessageAttribute whitelisted in outgoing message filter")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_EnqueueMessage.swift>")
        sys.exit(1)

    patch_enqueue_message_filter(sys.argv[1])
