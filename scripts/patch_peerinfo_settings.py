#!/usr/bin/env python3
"""
Patches PeerInfoScreen.swift to add a "Translation Proxy" settings entry
between "My Profile" and "Saved Messages" in Telegram's Settings screen.

This connects to the AISettingsController in the AITranslation module.
"""
import sys
import re


def patch_peerinfo_screen(filepath: str) -> None:
    with open(filepath, "r") as f:
        content = f.read()

    # 1. Add 'import AITranslation' after 'import UIKit'
    if "import AITranslation" not in content:
        content = content.replace(
            "import UIKit\n",
            "import UIKit\nimport AITranslation\n",
            1
        )
        print("  Added 'import AITranslation'")
    else:
        print("  'import AITranslation' already present")

    # 2. Add 'case translationProxy' to PeerInfoSettingsSection enum
    if "case translationProxy" not in content:
        content = content.replace(
            "case proxy\n",
            "case proxy\n    case translationProxy\n",
            1
        )
        print("  Added 'case translationProxy' to PeerInfoSettingsSection")
    else:
        print("  'case translationProxy' already present in PeerInfoSettingsSection")

    # 3. Add 'case translationProxy' to SettingsSection enum (between myProfile and proxy)
    # The SettingsSection enum controls section ordering in the settings list
    if content.count("case translationProxy") < 2:
        # Find the SettingsSection enum and add between myProfile and proxy
        settings_section_pattern = r'(private enum SettingsSection: Int, CaseIterable \{[^}]*?case myProfile\n)'
        match = re.search(settings_section_pattern, content, re.DOTALL)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + "    case translationProxy\n" + content[insert_pos:]
            print("  Added 'case translationProxy' to SettingsSection")
        else:
            print("  WARNING: Could not find SettingsSection enum")
    else:
        print("  'case translationProxy' already present in SettingsSection")

    # 4. Add the Translation Proxy menu item entry after the myProfile item
    # The item should appear in the translationProxy section
    if "items[.translationProxy]" not in content:
        # Find the myProfile item and add our entry right after it
        my_profile_pattern = (
            r'(items\[\.myProfile\]!\.append\(PeerInfoScreenDisclosureItem\('
            r'id: 0, text: presentationData\.strings\.Settings_MyProfile, '
            r'icon: PresentationResourcesSettings\.myProfile, action: \{\n'
            r'\s*interaction\.openSettings\(\.profile\)\n'
            r'\s*\}\)\))'
        )
        match = re.search(my_profile_pattern, content)
        if match:
            insert_pos = match.end()
            translation_entry = '''

        items[.translationProxy]!.append(PeerInfoScreenDisclosureItem(id: 0, text: "Translation Proxy", icon: PresentationResourcesSettings.language, action: {
            interaction.openSettings(.translationProxy)
        }))'''
            content = content[:insert_pos] + translation_entry + content[insert_pos:]
            print("  Added Translation Proxy menu item")
        else:
            print("  WARNING: Could not find myProfile item to insert after")
            # Try a simpler pattern
            simple_pattern = r'(interaction\.openSettings\(\.profile\)\n\s*\}\)\))'
            match = re.search(simple_pattern, content)
            if match:
                insert_pos = match.end()
                translation_entry = '''

        items[.translationProxy]!.append(PeerInfoScreenDisclosureItem(id: 0, text: "Translation Proxy", icon: PresentationResourcesSettings.language, action: {
            interaction.openSettings(.translationProxy)
        }))'''
                content = content[:insert_pos] + translation_entry + content[insert_pos:]
                print("  Added Translation Proxy menu item (via simpler pattern)")
            else:
                print("  ERROR: Could not find insertion point for Translation Proxy entry")
                return
    else:
        print("  Translation Proxy menu item already present")

    # 5. Add the case handler in openSettings for .translationProxy
    if "case .translationProxy:" not in content:
        # Find 'case .profile:' in the openSettings method and add our case before it
        profile_case_pattern = r'(        case \.profile:\n)'
        match = re.search(profile_case_pattern, content)
        if match:
            insert_pos = match.start()
            handler_code = '''        case .translationProxy:
            push(aiSettingsController(context: self.context))
'''
            content = content[:insert_pos] + handler_code + content[insert_pos:]
            print("  Added .translationProxy case handler in openSettings")
        else:
            print("  WARNING: Could not find case .profile: to insert before")
            # Try alternate approach - find case .proxy: and insert after
            proxy_case = "case .proxy:\n            self.controller?.push(proxySettingsController(context: self.context))"
            if proxy_case in content:
                insert_pos = content.index(proxy_case) + len(proxy_case)
                handler_code = '''
        case .translationProxy:
            push(aiSettingsController(context: self.context))'''
                content = content[:insert_pos] + handler_code + content[insert_pos:]
                print("  Added .translationProxy case handler after .proxy case")
            else:
                print("  ERROR: Could not find insertion point for openSettings handler")
                return
    else:
        print("  .translationProxy case handler already present")

    with open(filepath, "w") as f:
        f.write(content)

    print("  PeerInfoScreen.swift patched successfully")


def patch_peerinfo_build(filepath: str) -> None:
    """Add AITranslation dependency to PeerInfoScreen BUILD file."""
    with open(filepath, "r") as f:
        content = f.read()

    if "AITranslation" in content:
        print("  AITranslation already in PeerInfoScreen BUILD deps")
        return

    # Add after the first dep entry
    content = content.replace(
        '    deps = [\n',
        '    deps = [\n        "//submodules/AITranslation:AITranslation",\n',
        1
    )

    with open(filepath, "w") as f:
        f.write(content)

    print("  Added AITranslation to PeerInfoScreen BUILD deps")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <telegram-ios-build-dir>")
        sys.exit(1)

    build_dir = sys.argv[1]

    peerinfo_swift = f"{build_dir}/submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoScreen.swift"
    peerinfo_build = f"{build_dir}/submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/BUILD"

    print("Patching PeerInfoScreen BUILD...")
    patch_peerinfo_build(peerinfo_build)

    print("Patching PeerInfoScreen.swift...")
    patch_peerinfo_screen(peerinfo_swift)
