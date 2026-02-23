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
echo "  [1/4] Adding AITranslation to TelegramUI/BUILD deps..."
BUILD_FILE="${TARGET_DIR}/submodules/TelegramUI/BUILD"
if grep -q "AITranslation" "$BUILD_FILE" 2>/dev/null; then
    echo "    Already present, skipping."
else
    insert_after "$BUILD_FILE" "deps = [" '        "//submodules/AITranslation:AITranslation",'
    echo "    Done."
fi

# 2. Add import + registration to AppDelegate.swift
echo "  [2/4] Patching AppDelegate.swift..."
APPDELEGATE="${TARGET_DIR}/submodules/TelegramUI/Sources/AppDelegate.swift"
if grep -q "import AITranslation" "$APPDELEGATE" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    insert_after "$APPDELEGATE" "import UIKit" "import AITranslation"
    insert_after "$APPDELEGATE" "testIsLaunched = true" "        registerAITranslationService()"
    echo "    Done."
fi

# 3. Patch ChatController.swift for outgoing message interception
echo "  [3/4] Patching ChatController.swift..."
CHAT_CTRL="${TARGET_DIR}/submodules/TelegramUI/Sources/ChatController.swift"
if grep -q "import AITranslation" "$CHAT_CTRL" 2>/dev/null; then
    echo "    Already patched, skipping."
else
    insert_after "$CHAT_CTRL" "import UIKit" "import AITranslation"

    # Use Python for the more complex sendMessages modification
    python3 "${SCRIPT_DIR}/patch_chat_controller.py" "$CHAT_CTRL"
    echo "    Done."
fi

# 4. Apply any additional .patch files
echo "  [4/4] Applying additional patch files..."
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
