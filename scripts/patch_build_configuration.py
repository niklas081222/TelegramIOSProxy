#!/usr/bin/env python3
"""Patch BuildConfiguration.py to directly copy fake provisioning profiles.

Replaces copy_profiles_from_directory with a simple glob-based copy
that avoids the fragile openssl smime plist-matching logic.
"""

import sys
import os


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

    print(f"Patched copy_profiles_from_directory in {config_path}")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: patch_build_configuration.py <telegram-ios-build-dir>")
        sys.exit(1)

    build_dir = sys.argv[1]

    if not os.path.isdir(build_dir):
        print(f"ERROR: {build_dir} is not a directory")
        sys.exit(1)

    patch_copy_profiles(build_dir)


if __name__ == "__main__":
    main()
