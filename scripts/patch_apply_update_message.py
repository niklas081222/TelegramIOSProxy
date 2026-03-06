#!/usr/bin/env python3
"""Patch ApplyUpdateMessage.swift to preserve TranslationMessageAttribute during server sync.

When the server confirms or updates a message, Telegram replaces all message attributes
with the server's version. Since TranslationMessageAttribute is local-only (not sent to
server), it gets stripped. This patch preserves the attribute through ALL server update paths.

Strategy: find EVERY occurrence of `attributes = updatedMessage.attributes` in the file
and inject preservation code after each one. This catches all update paths, not just the
two originally targeted (single message + group message).

Also ensures `var` mutability where needed.
"""
import sys
import re


def patch_apply_update_message(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    if "Preserve local TranslationMessageAttribute" in content:
        print("Already patched, skipping.")
        return

    preserve_snippet = (
        '\n'
        '                // Preserve local TranslationMessageAttribute through server sync\n'
        '                if let translation = currentMessage.attributes.first(where: { $0 is TranslationMessageAttribute }) as? TranslationMessageAttribute {\n'
        '                    if !attributes.contains(where: { $0 is TranslationMessageAttribute }) {\n'
        '                        attributes.append(translation)\n'
        '                    }\n'
        '                }'
    )

    # Change ALL `let attributes: [MessageAttribute]` to `var` for mutability
    let_count = content.count("let attributes: [MessageAttribute]")
    if let_count > 0:
        content = content.replace("let attributes: [MessageAttribute]", "var attributes: [MessageAttribute]")
        print(f"Changed {let_count} 'let attributes' to 'var attributes'")

    # Find ALL occurrences of `attributes = updatedMessage.attributes` and inject preservation
    target = "attributes = updatedMessage.attributes"
    count = content.count(target)

    if count == 0:
        print("ERROR: Could not find any 'attributes = updatedMessage.attributes' in ApplyUpdateMessage.swift")
        print("TranslationMessageAttribute will be lost after server sync.")
        return

    # Replace each occurrence: add preservation code right after the assignment
    content = content.replace(target, target + preserve_snippet)
    print(f"Patched {count} attribute assignment(s) with TranslationMessageAttribute preservation")

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: TranslationMessageAttribute preserved through ALL server sync paths")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ApplyUpdateMessage.swift>")
        sys.exit(1)

    patch_apply_update_message(sys.argv[1])
