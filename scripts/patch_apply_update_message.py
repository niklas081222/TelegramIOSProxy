#!/usr/bin/env python3
"""Patch ApplyUpdateMessage.swift to preserve TranslationMessageAttribute during server sync.

When the server confirms a sent message, Telegram replaces all message attributes with
the server's version. Since TranslationMessageAttribute is local-only (not sent to server),
it gets stripped. This patch preserves the attribute through the server confirmation cycle.

Two locations are patched:
1. Single message send confirmation (line ~150)
2. Group message send confirmation (line ~505)
"""
import sys


def patch_apply_update_message(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    preserve_code = """
                // Preserve local TranslationMessageAttribute through server sync
                if let translation = currentMessage.attributes.first(where: { $0 is TranslationMessageAttribute }) as? TranslationMessageAttribute {
                    if !attributes.contains(where: { $0 is TranslationMessageAttribute }) {
                        attributes.append(translation)
                    }
                }"""

    # Patch 1: Single message path (line ~150)
    target1 = "                attributes = updatedMessage.attributes\n                text = updatedMessage.text\n                forwardInfo = updatedMessage.forwardInfo"

    if target1 not in content:
        print("ERROR: Could not find single message attributes assignment in ApplyUpdateMessage.swift")
        print("Outgoing TranslationMessageAttribute will be lost after server sync.")
        return

    replacement1 = "                attributes = updatedMessage.attributes" + preserve_code + "\n                text = updatedMessage.text\n                forwardInfo = updatedMessage.forwardInfo"

    content = content.replace(target1, replacement1, 1)
    print("Patched single message path")

    # Patch 2: Group message path (line ~505)
    # The group path declares `let attributes` (immutable), so we need to change it to `var`
    let_target = "                let attributes: [MessageAttribute]"
    var_replacement = "                var attributes: [MessageAttribute]"
    if let_target not in content:
        print("WARNING: Could not find 'let attributes' in group message path (may already be patched)")
    else:
        content = content.replace(let_target, var_replacement, 1)
        print("Changed 'let attributes' to 'var attributes' in group message path")

    target2 = "                attributes = updatedMessage.attributes\n                text = updatedMessage.text"

    if target2 not in content:
        print("WARNING: Could not find group message attributes assignment (may already be patched or different format)")
    else:
        replacement2 = "                attributes = updatedMessage.attributes" + preserve_code + "\n                text = updatedMessage.text"
        content = content.replace(target2, replacement2, 1)
        print("Patched group message path")

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: TranslationMessageAttribute preserved through server sync")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ApplyUpdateMessage.swift>")
        sys.exit(1)

    patch_apply_update_message(sys.argv[1])
