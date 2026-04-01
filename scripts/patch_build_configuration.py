#!/usr/bin/env python3
"""Patch Telegram-iOS build system files for CI builds.

1. Replace copy_profiles_from_directory with a simple glob-based copy.
2. Fix Swift compiler opts quoting issue in Make.py for Bazel 8.x.
3. Add DEVELOPER_DIR action_env to .bazelrc so ibtool can find the iOS platform.
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

    # Also replace resolve_aps_environment_from_directory
    func_end2 = "\ndef copy_certificates_from_directory("
    if func_end2 not in content:
        print(f"WARNING: Could not find copy_certificates_from_directory boundary")
        return False

    after = content[content.index(func_end2):]

    new_func_lines = [
        "def copy_profiles_from_directory(source_path, destination_path, team_id, bundle_id):",
        "    import glob",
        "    for file_path in glob.glob(os.path.join(source_path, '*.mobileprovision')):",
        "        file_name = os.path.basename(file_path)",
        "        dest_file = os.path.join(destination_path, file_name)",
        "        shutil.copyfile(file_path, dest_file)",
        "        print('Copied profile: {} -> {}'.format(file_name, dest_file))",
        "",
        "",
        "def resolve_aps_environment_from_directory(source_path, team_id, bundle_id):",
        '    return ""',
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


def patch_bazelrc_action_env(build_dir):
    """Add action_env entries to .bazelrc for ibtool platform discovery.

    On macOS 15+, ibtool (invoked by Bazel's xctoolrunner) fails to find
    the iOS platform because xctoolrunner runs tools with `env -` (clearing
    all environment variables). Apple's platform resolution framework needs
    DEVELOPER_DIR, HOME, and TMPDIR to locate registered platforms.

    The --action_env flag makes Bazel pass these through to build actions.
    """
    import subprocess

    # Get the current DEVELOPER_DIR from xcode-select
    try:
        developer_dir = subprocess.check_output(
            ["xcode-select", "-p"], text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        developer_dir = "/Applications/Xcode_16.2.app/Contents/Developer"

    bazelrc_path = os.path.join(build_dir, ".bazelrc")

    with open(bazelrc_path, "r") as f:
        content = f.read()

    # Pass through env vars needed by Apple dev tools (ibtool, actool, etc.)
    env_vars = {
        "DEVELOPER_DIR": developer_dir,
        "HOME": None,      # pass through from host
        "TMPDIR": None,     # pass through from host
        "GOOGLE_APPLICATION_CREDENTIALS": None,  # pass through for GCS remote cache
    }

    lines_to_add = []
    for var, value in env_vars.items():
        key = f"action_env={var}"
        if key in content:
            print(f"[3] {var} already set in {bazelrc_path}")
            continue
        if value:
            lines_to_add.append(f"build --action_env={var}={value}")
        else:
            lines_to_add.append(f"build --action_env={var}")

    if not lines_to_add:
        return True

    content = content + "\n" + "\n".join(lines_to_add) + "\n"

    with open(bazelrc_path, "w") as f:
        f.write(content)

    for line in lines_to_add:
        print(f"[3] Added: {line}")
    return True


def patch_remote_downloader(build_dir):
    """Remove --experimental_remote_downloader from Make.py.

    Make.py adds --experimental_remote_downloader alongside --remote_cache,
    but this flag only works with gRPC caching, not HTTP/GCS. When using
    --cacheHost with an HTTPS URL, the downloader flag causes Bazel to error:
    'The remote downloader can only be used in combination with gRPC caching'
    """
    make_path = os.path.join(build_dir, "build-system", "Make", "Make.py")

    with open(make_path, "r") as f:
        content = f.read()

    original = content
    # Remove lines that add --experimental_remote_downloader
    content = re.sub(
        r"\s*'--experimental_remote_downloader=\{}'.format\(self\.remote_cache\),?\n",
        "\n",
        content
    )

    if content != original:
        with open(make_path, "w") as f:
            f.write(content)
        print(f"[4] Removed --experimental_remote_downloader from {make_path}")
    else:
        print(f"[4] No --experimental_remote_downloader found in {make_path}")

    return True



def patch_entitlements_app_groups(build_dir):
    """Remove com.apple.security.application-groups from Telegram.entitlements.

    Real Apple provisioning profiles created via the API don't include app group
    containers (Apple requires portal UI for that). Bazel's plisttool validates
    that every entitlement key in the app's .entitlements file is also present
    in the profile with a non-empty value. Since the profile has an empty array,
    plisttool rejects it.

    Fix: remove the key from the entitlements plist so plisttool skips the check.
    The app still works — app groups are only needed for shared containers between
    app and extensions, which we don't use.
    """
    import glob
    import plistlib

    # Find all .entitlements files
    pattern = os.path.join(build_dir, "**", "*.entitlements")
    entitlement_files = glob.glob(pattern, recursive=True)

    # Also check Telegram/BUILD for entitlements references
    build_path = os.path.join(build_dir, "Telegram", "BUILD")
    if os.path.exists(build_path):
        with open(build_path, "r") as f:
            build_content = f.read()

        # Remove application-groups from any inline entitlements dict in BUILD
        if "com.apple.security.application-groups" in build_content:
            build_content = re.sub(
                r'\s*"com\.apple\.security\.application-groups":\s*\[.*?\],?\n',
                "\n",
                build_content,
                flags=re.DOTALL,
            )
            with open(build_path, "w") as f:
                f.write(build_content)
            print(f"[5] Removed application-groups from {build_path}")

    count = 0
    for ent_file in entitlement_files:
        try:
            with open(ent_file, "rb") as f:
                plist = plistlib.load(f)
        except Exception:
            continue

        if "com.apple.security.application-groups" in plist:
            del plist["com.apple.security.application-groups"]
            with open(ent_file, "wb") as f:
                plistlib.dump(plist, f)
            count += 1
            print(f"[5] Removed application-groups from {ent_file}")

    if count == 0 and "com.apple.security.application-groups" not in (build_content if os.path.exists(build_path) else ""):
        print(f"[5] No application-groups entitlements found to remove")


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
    patch_bazelrc_action_env(build_dir)
    patch_remote_downloader(build_dir)
    patch_entitlements_app_groups(build_dir)


if __name__ == "__main__":
    main()
