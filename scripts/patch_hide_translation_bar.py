#!/usr/bin/env python3
"""Patch ChatControllerNode.swift to hide the translation pop-up bar.

Telegram's built-in translation feature shows a "Show Original" bar at the top
of the chat when translationState.isEnabled is true. This patch prevents the bar
from being rendered while keeping translationState enabled so the data pipeline
(on-open translation via Telegram's ExperimentalInternalTranslationService) still works.

Target: the `hasTranslationPanel = true` line in the header panel layout logic.
"""
import sys


def patch_hide_translation_bar(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    if "AI Translation: hide translation bar" in content:
        print("Already patched, skipping.")
        return

    # Target the exact block that sets hasTranslationPanel = true
    # This is in the header panel layout method of ChatControllerNode
    old = """    } else {
                hasTranslationPanel = true
            }
        }"""

    if old not in content:
        print("ERROR: Could not find hasTranslationPanel = true block in ChatControllerNode.swift")
        print("Translation bar will still be visible.")
        return

    # Replace with an empty else block — the panel is never added to headerPanels
    new = """    } else {
                // AI Translation: hide translation bar (keep translationState for data pipeline)
                let _ = hasTranslationPanel
            }
        }"""

    content = content.replace(old, new, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: hidden translation bar while keeping data pipeline active")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatControllerNode.swift>")
        sys.exit(1)

    patch_hide_translation_bar(sys.argv[1])
