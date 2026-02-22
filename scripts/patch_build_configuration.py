#!/usr/bin/env python3
"""Patch Telegram-iOS build system files for CI builds.

1. Replace copy_profiles_from_directory with a simple glob-based copy.
2. Fix Swift compiler opts quoting issue in Make.py for Bazel 8.x.
"""

import sys
import os
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


def patch_swift_copts(build_dir):
    """Fix Swift compiler opts quoting in Make.py for Bazel 8.x.

    In Make.py, common_debug_args contains:
        '--@build_bazel_rules_swift//swift:copt="-j2"'
        '--@build_bazel_rules_swift//swift:copt="-whole-module-optimization"'

    The literal double quotes around the values cause Bazel 8.x to pass them
    as-is to swiftc, which interprets them as filenames instead of flags.
    Remove the extraneous quotes.
    """
    make_path = os.path.join(build_dir, "build-system", "Make", "Make.py")

    with open(make_path, "r") as f:
        content = f.read()

    # Remove the embedded double quotes from copt values
    # Pattern: copt="-something" -> copt=-something
    original = content
    content = re.sub(
        r'''(--@build_bazel_rules_swift//swift:copt=)["']([^"']+)["']''',
        r'\1\2',
        content
    )

    if content != original:
        with open(make_path, "w") as f:
            f.write(content)
        print(f"[2] Fixed Swift copt quoting in {make_path}")
    else:
        print(f"[2] No Swift copt quoting issues found in {make_path}")

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
    patch_swift_copts(build_dir)


if __name__ == "__main__":
    main()
