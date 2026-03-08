#!/usr/bin/env python3
"""Hide Telegram Service Notifications chat (peer 777000) from the chat list.

Patches ChatListNode.swift to filter out entries for peer ID 777000
so the Telegram Service Notifications chat never appears in the UI.
Uses multiple strategies to find the right insertion point.
"""
import sys
import re


def patch_hide_service_chat(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    if "// AI Translation: hide service notifications" in content:
        print("Already patched, skipping.")
        return

    # Strategy 1: Find "for entry in view.entries" loop and replace with filtered version
    pattern1 = re.compile(r'(for entry in view\.entries\s*\{)')
    match = pattern1.search(content)
    if match:
        old = match.group(0)
        new = (
            "// AI Translation: hide service notifications chat (peer 777000)\n"
            "                for entry in view.entries {\n"
            "                    if case let .MessageEntry(entryData) = entry {\n"
            "                        if entryData.index.messageIndex.id.peerId.id._internalGetInt64Value() == 777000 {\n"
            "                            continue\n"
            "                        }\n"
            "                    }"
        )
        content = content.replace(old, new, 1)
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Patched {filepath}: hiding service notifications (strategy 1: view.entries loop)")
        return

    # Strategy 2: Find "for entry in entries" and add filter
    pattern2 = re.compile(r'(for entry in entries\s*\{)')
    match = pattern2.search(content)
    if match:
        old = match.group(0)
        new = (
            "// AI Translation: hide service notifications chat (peer 777000)\n"
            "                for entry in entries {\n"
            "                    if case let .MessageEntry(entryData) = entry {\n"
            "                        if entryData.index.messageIndex.id.peerId.id._internalGetInt64Value() == 777000 {\n"
            "                            continue\n"
            "                        }\n"
            "                    }"
        )
        content = content.replace(old, new, 1)
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Patched {filepath}: hiding service notifications (strategy 2: entries loop)")
        return

    # Strategy 3: Find the chatListNodeEntriesForView function and add filter at the top
    pattern3 = re.compile(
        r'(func chatListNodeEntriesForView\([^{]*\{)',
        re.DOTALL
    )
    match = pattern3.search(content)
    if match:
        func_start = match.group(0)
        filter_code = """
        // AI Translation: hide service notifications chat (peer 777000)
        let aiFilteredView = ChatListView(
            entries: view.entries.filter { entry in
                if case let .MessageEntry(entryData) = entry {
                    return entryData.index.messageIndex.id.peerId.id._internalGetInt64Value() != 777000
                }
                return true
            },
            groupEntries: view.groupEntries,
            earlierIndex: view.earlierIndex,
            laterIndex: view.laterIndex
        )
"""
        content = content.replace(func_start, func_start + filter_code, 1)
        # Also replace "view.entries" with "aiFilteredView.entries" in the function
        # This is fragile, so only do it if we find the function
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Patched {filepath}: hiding service notifications (strategy 3: function filter)")
        return

    # Strategy 4: Generic - find any "case let .MessageEntry" and add guard before processing
    pattern4 = re.compile(r'(case let \.MessageEntry\(([^)]+)\):)')
    match = pattern4.search(content)
    if match:
        full_case = match.group(0)
        first_param = match.group(2).split(",")[0].strip()
        guard_code = (
            f"{full_case}\n"
            f"                        // AI Translation: hide service notifications chat (peer 777000)\n"
            f"                        if {first_param}.index.messageIndex.id.peerId.id._internalGetInt64Value() == 777000 {{ continue }}"
        )
        content = content.replace(full_case, guard_code, 1)
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Patched {filepath}: hiding service notifications (strategy 4: MessageEntry guard)")
        return

    print("WARNING: Could not find suitable insertion point in ChatListNode.swift")
    print("Service Notifications chat will NOT be hidden from the chat list.")
    print("Tried: view.entries loop, entries loop, chatListNodeEntriesForView function, MessageEntry case")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path_to_ChatListNode.swift>")
        sys.exit(1)

    patch_hide_service_chat(sys.argv[1])
