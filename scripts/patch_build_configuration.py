#!/usr/bin/env python3
"""Patch BuildConfiguration.py to directly copy fake provisioning profiles.

The original copy_profiles_from_directory function uses openssl smime to parse
each .mobileprovision file and match the embedded application-identifier against
the configured team_id + bundle_id. This is fragile and can silently skip profiles.

Since the fake-codesigning profiles are already named correctly (Telegram.mobileprovision,
Share.mobileprovision, etc.), we replace the function with a simple direct copy.
"""

import sys
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: patch_build_configuration.py <telegram-ios-build-dir>")
        sys.exit(1)

    build_dir = sys.argv[1]
    config_path = os.path.join(build_dir, "build-system", "Make", "BuildConfiguration.py")

    with open(config_path, "r") as f:
        content = f.read()

    # Locate the function boundaries
    func_start = "def copy_profiles_from_directory(source_path, destination_path, team_id, bundle_id):"
    func_end = "\ndef resolve_aps_environment_from_directory("

    if func_start not in content:
        print(f"ERROR: Could not find '{func_start}' in {config_path}")
        sys.exit(1)

    if func_end not in content:
        print(f"ERROR: Could not find boundary marker in {config_path}")
        sys.exit(1)

    before = content[:content.index(func_start)]
    after = content[content.index(func_end):]

    # Build replacement function
    lines = [
        "def copy_profiles_from_directory(source_path, destination_path, team_id, bundle_id):",
        "    import glob",
        "    for file_path in glob.glob(os.path.join(source_path, '*.mobileprovision')):",
        "        file_name = os.path.basename(file_path)",
        "        dest_file = os.path.join(destination_path, file_name)",
        "        shutil.copyfile(file_path, dest_file)",
        "        print('Copied profile: {} -> {}'.format(file_name, dest_file))",
        "",
    ]
    new_func = "\n".join(lines) + "\n"

    content = before + new_func + after

    with open(config_path, "w") as f:
        f.write(content)

    print(f"SUCCESS: Patched copy_profiles_from_directory in {config_path}")

    # Verify by printing the new function
    print("\n--- New function ---")
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
