#!/usr/bin/env python3
"""Patch Translate.swift to always use our ExperimentalInternalTranslationService.

Telegram's built-in translation pipeline in _internal_translateMessagesByPeerId()
has a guard: `if enableLocalIfPossible, let engineExperimentalInternalTranslationService, let fromLang`

The `enableLocalIfPossible` parameter is passed by the caller and may be false,
preventing our service from being used even when registered. This patch removes
that guard so our service is always used when registered and fromLang is available.
"""
import sys


def patch_translate_engine(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    old = "if enableLocalIfPossible, let engineExperimentalInternalTranslationService, let fromLang {"
    new = "if let engineExperimentalInternalTranslationService, let fromLang {"

    if old not in content:
        print("ERROR: Could not find enableLocalIfPossible guard in Translate.swift")
        print("Incoming translation via our service may not work.")
        return

    content = content.replace(old, new, 1)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Patched {filepath}: removed enableLocalIfPossible guard")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_Translate.swift>")
        sys.exit(1)

    patch_translate_engine(sys.argv[1])
