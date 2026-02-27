#!/bin/bash
set -euo pipefail

TARGET_DIR="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PATCHES_DIR="${PROJECT_DIR}/telegram-ios/patches"

# Insert a line after the first occurrence of a pattern in a file.
# Uses Python for reliable cross-platform behavior (BSD sed's `a\` is buggy).
insert_after() {
    local file="$1"
    local pattern="$2"
    local new_line="$3"
    python3 -c "
import sys
with open(sys.argv[1], 'r') as f:
    lines = f.readlines()
found = False
result = []
for line in lines:
    result.append(line)
    if not found and sys.argv[2] in line.rstrip():
        result.append(sys.argv[3] + '\n')
        found = True
with open(sys.argv[1], 'w') as f:
    f.writelines(result)
if not found:
    print(f'WARNING: pattern \"{sys.argv[2]}\" not found in {sys.argv[1]}')
" "$file" "$pattern" "$new_line"
}

echo "Applying modifications to ${TARGET_DIR}..."

# 1. Add AITranslation dependency to TelegramUI/BUILD
echo "  [1/14] Adding AITranslation to TelegramUI/BUILD deps..."
BUILD_FILE="${TARGET_DIR}/submodules/TelegramUI/BUILD"
if grep -q "AITranslation" "$BUILD_FILE" 2>/dev/null; then
    echo "    Already present, skipping."
else
    insert_after "$BUILD_FILE" "deps = [" '        "//submodules/AITranslation:AITranslation",'
    echo "    Done."
fi

# 2. Add import + registration to AppDelegate.swift
echo "  [2/14] Patching AppDelegate.swift..."
APPDELEGATE="${TARGET_DIR}/submodules/TelegramUI/Sources/AppDelegate.swift"
if grep -q "import AITranslation" "$APPDELEGATE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    insert_after "$APPDELEGATE" "import UIKit" "import AITranslation"
    insert_after "$APPDELEGATE" "testIsLaunched = true" "        registerAITranslationService()"
    echo "    Done."
fi

# 3. Patch EnqueueMessage.swift to whitelist TranslationMessageAttribute
echo "  [3/14] Patching EnqueueMessage.swift message attribute filter..."
ENQUEUE_MSG="${TARGET_DIR}/submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
if grep -q "case _ as TranslationMessageAttribute" "$ENQUEUE_MSG" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_enqueue_message_filter.py" "$ENQUEUE_MSG"
    echo "    Done."
fi

# 4. Auto-enable incoming translation state in ChatControllerLoadDisplayNode
echo "  [4/14] Enabling auto-incoming translation state..."
LOAD_DISPLAY_NODE="${TARGET_DIR}/submodules/TelegramUI/Sources/Chat/ChatControllerLoadDisplayNode.swift"
if grep -q "AI Translation: auto-enable incoming translation" "$LOAD_DISPLAY_NODE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    # Add import first (needed for both this and step 5)
    if ! grep -q "import AITranslation" "$LOAD_DISPLAY_NODE" 2>/dev/null; then
        insert_after "$LOAD_DISPLAY_NODE" "import UIKit" "import AITranslation"
    fi
    python3 "${SCRIPT_DIR}/patch_incoming_translation.py" "$LOAD_DISPLAY_NODE"
    echo "    Done."
fi

# 5. Patch ChatControllerLoadDisplayNode.swift for main text input translation (fire-and-forget)
echo "  [5/14] Patching ChatControllerLoadDisplayNode.swift for outgoing translation..."
if grep -q "AI Translation: fire-and-forget" "$LOAD_DISPLAY_NODE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    # import AITranslation should already be added by step 4, but ensure it
    if ! grep -q "import AITranslation" "$LOAD_DISPLAY_NODE" 2>/dev/null; then
        insert_after "$LOAD_DISPLAY_NODE" "import UIKit" "import AITranslation"
    fi
    python3 "${SCRIPT_DIR}/patch_load_display_node.py" "$LOAD_DISPLAY_NODE"
    echo "    Done."
fi

# 6. Patch ChatHistoryListNode.swift for incoming translation
echo "  [6/14] Patching ChatHistoryListNode.swift for incoming translation..."
HISTORY_LIST_NODE="${TARGET_DIR}/submodules/TelegramUI/Sources/ChatHistoryListNode.swift"
if grep -q "AI Translation: force-enable incoming" "$HISTORY_LIST_NODE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_chat_history_list_node.py" "$HISTORY_LIST_NODE"
    echo "    Done."
fi

# 7. Reduce incoming translation throttle delay
echo "  [7/14] Reducing translation throttle delay..."
if grep -q "delay: 0.1" "$HISTORY_LIST_NODE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_translation_throttle.py" "$HISTORY_LIST_NODE"
    echo "    Done."
fi

# 8. Patch PeerInfoScreen to add Translation Proxy settings entry
echo "  [8/14] Patching PeerInfoScreen for Translation Proxy settings..."
PEERINFO="${TARGET_DIR}/submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreen.swift"
if grep -q "import AITranslation" "$PEERINFO" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_peerinfo_settings.py" "$TARGET_DIR"
    echo "    Done."
fi

# 9. Patch Translate.swift to always use our translation service
echo "  [9/14] Patching Translate.swift for AI translation service..."
TRANSLATE_SWIFT="${TARGET_DIR}/submodules/TelegramCore/Sources/TelegramEngine/Messages/Translate.swift"
if ! grep -q "enableLocalIfPossible" "$TRANSLATE_SWIFT" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_translate_engine.py" "$TRANSLATE_SWIFT"
    echo "    Done."
fi

# 10. Patch ApplyUpdateMessage.swift to preserve TranslationMessageAttribute during server sync
echo "  [10/14] Patching ApplyUpdateMessage.swift..."
APPLY_UPDATE="${TARGET_DIR}/submodules/TelegramCore/Sources/State/ApplyUpdateMessage.swift"
if grep -q "Preserve local TranslationMessageAttribute" "$APPLY_UPDATE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_apply_update_message.py" "$APPLY_UPDATE"
    echo "    Done."
fi

# 11. Patch ChatMessageTextBubbleContentNode.swift for outgoing translation display
echo "  [11/14] Patching ChatMessageTextBubbleContentNode.swift..."
TEXT_BUBBLE="${TARGET_DIR}/submodules/TelegramUI/Components/Chat/ChatMessageTextBubbleContentNode/Sources/ChatMessageTextBubbleContentNode.swift"
if grep -q "AI Translation: removed incoming guard" "$TEXT_BUBBLE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_text_bubble.py" "$TEXT_BUBBLE"
    echo "    Done."
fi

# 12. Patch ChatListItemStrings.swift for translated chat list preview
echo "  [12/14] Patching ChatListItemStrings.swift..."
CHAT_LIST_STRINGS="${TARGET_DIR}/submodules/ChatListUI/Sources/Node/ChatListItemStrings.swift"
if grep -q "TranslationMessageAttribute" "$CHAT_LIST_STRINGS" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_chat_list_strings.py" "$CHAT_LIST_STRINGS"
    echo "    Done."
fi

# 13. Patch ApplicationContext.swift for background incoming translation
echo "  [13/14] Patching ApplicationContext.swift for background translation..."
APP_CONTEXT="${TARGET_DIR}/submodules/TelegramUI/Sources/ApplicationContext.swift"
if grep -q "AIBackgroundTranslationObserver" "$APP_CONTEXT" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    python3 "${SCRIPT_DIR}/patch_application_context.py" "$APP_CONTEXT"
    echo "    Done."
fi

# 14. Apply any additional .patch files
echo "  [14/14] Applying additional patch files..."
PATCH_COUNT=0
for patch_file in "${PATCHES_DIR}"/*.patch; do
    [ -f "$patch_file" ] || continue
    patch_name="$(basename "$patch_file")"
    echo "    Applying: ${patch_name}"
    if (cd "$TARGET_DIR" && git apply --check "$patch_file" 2>/dev/null); then
        (cd "$TARGET_DIR" && git apply "$patch_file")
        PATCH_COUNT=$((PATCH_COUNT + 1))
        echo "      OK"
    else
        echo "      WARNING: Patch ${patch_name} could not apply cleanly, skipping."
    fi
done
echo "    Additional patches applied: ${PATCH_COUNT}"

echo ""
echo "All modifications applied successfully."
