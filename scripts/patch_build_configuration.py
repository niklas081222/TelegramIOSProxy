#!/usr/bin/env python3
"""Patch Telegram-iOS build system for fake-codesigning builds.

1. Replace copy_profiles_from_directory with a simple direct-copy version
   (avoids fragile openssl smime parsing).
2. Create any missing provisioning profiles that Telegram/BUILD references
   but don't exist in fake-codesigning/profiles/ (e.g. BroadcastUpload at release-11.13).
"""

import sys
import os
import shutil
import re


def patch_copy_profiles(build_dir):
    """Replace copy_profiles_from_directory with direct copy."""
    config_path = os.path.join(build_dir, "build-system", "Make", "BuildConfiguration.py")

    with open(config_path, "r") as f:
        content = f.read()

    func_start = "def copy_profiles_from_directory(source_path, destination_path, team_id, bundle_id):"
    func_end = "\ndef resolve_aps_environment_from_directory("

    if func_start not in content or func_end not in content:
        print(f"WARNING: Could not find function boundaries in {config_path}")
        return False

    before = content[:content.index(func_start)]
    after = content[content.index(func_end):]

    new_func_lines = [
        "def copy_profiles_from_directory(source_path, destination_path, team_id, bundle_id):",
        "    import glob",
        "    for file_path in glob.glob(os.path.join(source_path, '*.mobileprovision')):",
        "        file_name = os.path.basename(file_path)",
        "        dest_file = os.path.join(destination_path, file_name)",
        "        shutil.copyfile(file_path, dest_file)",
        "        print('Copied profile: {} -> {}'.format(file_name, dest_file))",
        "",
    ]
    new_func = "\n".join(new_func_lines) + "\n"

    content = before + new_func + after

    with open(config_path, "w") as f:
        f.write(content)

    print(f"[1] Patched copy_profiles_from_directory in {config_path}")
    return True


def create_missing_profiles(build_dir):
    """Create missing .mobileprovision files by copying from an existing one.

    Telegram/BUILD references profiles that may not exist in fake-codesigning/profiles/.
    At release-11.13, BroadcastUpload.mobileprovision is missing.
    """
    profiles_dir = os.path.join(build_dir, "build-system", "fake-codesigning", "profiles")
    telegram_build = os.path.join(build_dir, "Telegram", "BUILD")

    # Find all profile names referenced in Telegram/BUILD
    with open(telegram_build, "r") as f:
        build_content = f.read()

    # Match patterns like: @build_configuration//provisioning:NAME.mobileprovision
    referenced = set(re.findall(r'@build_configuration//provisioning:(\w+)\.mobileprovision', build_content))

    # Find existing profiles
    existing = set()
    for fname in os.listdir(profiles_dir):
        if fname.endswith('.mobileprovision'):
            existing.add(fname.replace('.mobileprovision', ''))

    missing = referenced - existing
    if not missing:
        print(f"[2] All {len(referenced)} referenced profiles exist")
        return

    # Use the Share profile as a template (it's small and simple)
    template = os.path.join(profiles_dir, "Share.mobileprovision")
    if not os.path.exists(template):
        template = os.path.join(profiles_dir, next(iter(existing)) + ".mobileprovision")

    for name in missing:
        dest = os.path.join(profiles_dir, f"{name}.mobileprovision")
        shutil.copyfile(template, dest)
        print(f"[2] Created missing profile: {name}.mobileprovision (from template)")

    print(f"[2] Profiles dir now contains: {sorted(os.listdir(profiles_dir))}")


def main():
    if len(sys.argv) < 2:
        print("Usage: patch_build_configuration.py <telegram-ios-build-dir>")
        sys.exit(1)

    build_dir = sys.argv[1]

    if not os.path.isdir(build_dir):
        print(f"ERROR: {build_dir} is not a directory")
        sys.exit(1)

    patch_copy_profiles(build_dir)
    create_missing_profiles(build_dir)

    print("\nAll patches applied successfully.")


if __name__ == "__main__":
    main()
