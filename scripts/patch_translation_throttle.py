#!/usr/bin/env python3
"""Patch ChatHistoryListNode.swift to reduce the incoming translation throttle delay.

The default ChatMessageThrottledProcessingManager uses a 1.0-second delay before
dispatching the first batch of translation requests. This adds noticeable latency
to incoming message translation. Reducing it to 0.1 seconds makes translations
start almost immediately when messages appear on screen.
"""
import sys


def patch_translation_throttle(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    old = "ChatMessageThrottledProcessingManager(submitInterval: 1.0)"
    new = "ChatMessageThrottledProcessingManager(delay: 0.1, submitInterval: 1.0)"

    if old not in content:
        print("WARNING: Could not find ThrottledProcessingManager with submitInterval: 1.0")
        print("Translation throttle delay not reduced.")
        return

    content = content.replace(old, new, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: reduced translation throttle delay from 1.0s to 0.1s")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatHistoryListNode.swift>")
        sys.exit(1)

    patch_translation_throttle(sys.argv[1])
