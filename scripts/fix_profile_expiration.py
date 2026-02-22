#!/usr/bin/env python3
"""Fix expired fake provisioning profiles by extending their ExpirationDate.

The fake-codesigning profiles in Telegram-iOS expired on 2025-10-29.
This script:
1. Decodes each .mobileprovision with `security cms -D`
2. Modifies ExpirationDate to 10 years from now
3. Re-signs with `security cms -S` using the self-signed certificate
"""

import sys
import os
import subprocess
import plistlib
import tempfile
import datetime


def main():
    if len(sys.argv) < 2:
        print("Usage: fix_profile_expiration.py <telegram-ios-build-dir>")
        sys.exit(1)

    build_dir = sys.argv[1]
    profiles_dir = os.path.join(build_dir, "build-system", "fake-codesigning", "profiles")
    certs_dir = os.path.join(build_dir, "build-system", "fake-codesigning", "certs")
    p12_path = os.path.join(certs_dir, "SelfSigned.p12")

    if not os.path.exists(p12_path):
        print(f"ERROR: Certificate not found at {p12_path}")
        sys.exit(1)

    # Create a temporary keychain for signing
    keychain_name = "fake-codesigning-temp.keychain"
    keychain_password = "temp_password_12345"

    try:
        # Delete keychain if it exists from a previous run
        subprocess.run(["security", "delete-keychain", keychain_name],
                      capture_output=True)

        # Create temporary keychain
        subprocess.check_call([
            "security", "create-keychain", "-p", keychain_password, keychain_name
        ])

        # Set as default for cms operations
        subprocess.check_call([
            "security", "set-keychain-settings", keychain_name
        ])

        # Unlock it
        subprocess.check_call([
            "security", "unlock-keychain", "-p", keychain_password, keychain_name
        ])

        # Import the self-signed certificate (empty password)
        subprocess.check_call([
            "security", "import", p12_path,
            "-k", keychain_name,
            "-P", "",
            "-T", "/usr/bin/codesign",
            "-T", "/usr/bin/security"
        ])

        # Add to search list
        result = subprocess.check_output(["security", "list-keychains", "-d", "user"])
        existing_keychains = [k.strip().strip(b'"').decode() for k in result.split(b'\n') if k.strip()]
        subprocess.check_call([
            "security", "list-keychains", "-d", "user", "-s", keychain_name
        ] + existing_keychains)

        # Allow access without prompting
        subprocess.check_call([
            "security", "set-key-partition-list",
            "-S", "apple-tool:,apple:",
            "-s", "-k", keychain_password,
            keychain_name
        ])

        # Get the signing identity name from the certificate
        identity_output = subprocess.check_output([
            "security", "find-identity", "-v", "-p", "codesigning", keychain_name
        ]).decode()

        # Extract the identity name (CN value)
        # Format: 1) HASH "CN value"
        identity_name = None
        for line in identity_output.split('\n'):
            if '"' in line:
                identity_name = line.split('"')[1]
                break

        if not identity_name:
            print("WARNING: Could not find signing identity, using default")
            identity_name = "Apple Distribution: Telegram FZ-LLC (C67CF9S4VU)"

        print(f"Using signing identity: {identity_name}")

        new_expiration = datetime.datetime.now() + datetime.timedelta(days=3650)
        new_creation = datetime.datetime.now()

        count = 0
        for fname in sorted(os.listdir(profiles_dir)):
            if not fname.endswith('.mobileprovision'):
                continue

            file_path = os.path.join(profiles_dir, fname)

            # Decode the profile to get the plist
            try:
                plist_data = subprocess.check_output([
                    "security", "cms", "-D", "-i", file_path
                ])
            except subprocess.CalledProcessError:
                print(f"  WARNING: Could not decode {fname}, skipping")
                continue

            # Parse and modify the plist
            profile_dict = plistlib.loads(plist_data)
            old_expiration = profile_dict.get('ExpirationDate', 'unknown')
            profile_dict['ExpirationDate'] = new_expiration
            profile_dict['CreationDate'] = new_creation

            # Write modified plist to a temp file
            with tempfile.NamedTemporaryFile(suffix='.plist', delete=False) as tmp:
                plistlib.dump(profile_dict, tmp)
                tmp_plist_path = tmp.name

            try:
                # Re-sign the modified plist
                with tempfile.NamedTemporaryFile(suffix='.mobileprovision', delete=False) as out:
                    out_path = out.name

                subprocess.check_call([
                    "security", "cms", "-S",
                    "-N", identity_name,
                    "-k", keychain_name,
                    "-i", tmp_plist_path,
                    "-o", out_path
                ])

                # Replace the original profile
                os.replace(out_path, file_path)
                print(f"  Fixed: {fname} (was: {old_expiration}, now: {new_expiration})")
                count += 1

            except subprocess.CalledProcessError as e:
                print(f"  WARNING: Could not re-sign {fname}: {e}")
                # Clean up temp output file
                if os.path.exists(out_path):
                    os.unlink(out_path)
            finally:
                os.unlink(tmp_plist_path)

        print(f"\nFixed {count} profiles with new expiration: {new_expiration}")

    finally:
        # Clean up temporary keychain
        subprocess.run(["security", "delete-keychain", keychain_name],
                      capture_output=True)


if __name__ == "__main__":
    main()
