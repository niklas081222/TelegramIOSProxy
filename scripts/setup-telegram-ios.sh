#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TARGET_DIR="${PROJECT_DIR}/telegram-ios-build"

# Telegram-iOS repo (official)
TELEGRAM_REPO="https://github.com/TelegramMessenger/Telegram-iOS.git"

echo "=== TranslateGram iOS Build Setup ==="
echo "Project directory: ${PROJECT_DIR}"
echo "Build directory: ${TARGET_DIR}"

# Step 1: Clone Telegram-iOS if not already present
if [ -d "$TARGET_DIR" ]; then
    echo "Build directory already exists. Skipping clone."
else
    echo "Cloning Telegram-iOS repository..."
    git clone --recursive --depth 1 "$TELEGRAM_REPO" "$TARGET_DIR"
fi

# Step 2: Copy AITranslation module into the build directory
echo "Copying AITranslation module..."
AITRANSLATION_SRC="${PROJECT_DIR}/telegram-ios/AITranslation"
AITRANSLATION_DST="${TARGET_DIR}/submodules/AITranslation"

if [ -d "$AITRANSLATION_DST" ]; then
    rm -rf "$AITRANSLATION_DST"
fi

cp -r "$AITRANSLATION_SRC" "$AITRANSLATION_DST"
echo "AITranslation module copied to ${AITRANSLATION_DST}"

# Step 3: Apply patches
echo "Applying patches..."
bash "${SCRIPT_DIR}/apply-patches.sh" "$TARGET_DIR"

echo ""
echo "=== Setup complete ==="
echo "Build directory: ${TARGET_DIR}"
echo "To build: cd ${TARGET_DIR} && python3 build-system/Make/Make.py build ..."
