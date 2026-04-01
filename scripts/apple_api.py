#!/usr/bin/env python3
"""Apple Developer API helper — register devices, create certificates, profiles."""
import json
import time
import subprocess
import sys
import base64
import tempfile
import os

import jwt
import requests

KEY_ID = "5TM3C5Y28T"
ISSUER_ID = "8d0fd173-4305-4206-a309-d4fe2725164d"
KEY_PATH = os.path.expanduser("~/Downloads/AuthKey_5TM3C5Y28T.p8")
TEAM_ID = "5RPK5SFG6M"
BUNDLE_ID = "com.niklas.translategram2"
BASE_URL = "https://api.appstoreconnect.apple.com/v1"

DEVICES = [
    ("80dccdbc6d929e5c1dabf7208465a6532728614b", "Tims iPhone"),
    ("00008030-00165014346B402E", "iPhone 11"),
    ("cb3e3ebfa10b4aebbdb900c6a65bdd4209687f92", "iPhone 8"),
    ("00008110-001E48DE1E84401E", "New Device 1"),
    ("00008020001C2D1234567890ABCDEF12", "New Device 2"),
]

PROFILE_SUFFIX_MAP = {
    'Telegram': '',
    'Share': '.Share',
    'Widget': '.Widget',
    'NotificationContent': '.NotificationContent',
    'NotificationService': '.NotificationService',
    'Intents': '.SiriIntents',
    'BroadcastUpload': '.BroadcastUpload',
    'WatchApp': '.watchkitapp',
    'WatchExtension': '.watchkitapp.watchkitextension',
}


def generate_token():
    with open(KEY_PATH, "r") as f:
        private_key = f.read()
    now = int(time.time())
    payload = {
        "iss": ISSUER_ID,
        "iat": now,
        "exp": now + 1200,
        "aud": "appstoreconnect-v1",
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": KEY_ID})


def api_get(path, token, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers={"Authorization": f"Bearer {token}"}, params=params)
    if r.status_code >= 400:
        print(f"  GET {path} -> {r.status_code}: {r.text[:300]}")
    return r


def api_post(path, token, data):
    r = requests.post(f"{BASE_URL}{path}", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, json=data)
    if r.status_code >= 400:
        print(f"  POST {path} -> {r.status_code}: {r.text[:300]}")
    return r


def register_devices(token):
    print("\n=== REGISTERING DEVICES ===")
    # Get existing devices
    r = api_get("/devices", token, {"limit": 200})
    existing = {}
    if r.status_code == 200:
        for d in r.json().get("data", []):
            existing[d["attributes"]["udid"].lower()] = d

    for udid, name in DEVICES:
        udid_lower = udid.lower()
        if udid_lower in existing:
            d = existing[udid_lower]
            print(f"  OK: {name} ({udid}) — already registered as '{d['attributes']['name']}'")
        else:
            print(f"  REGISTERING: {name} ({udid})...")
            r = api_post("/devices", token, {
                "data": {
                    "type": "devices",
                    "attributes": {
                        "name": name,
                        "udid": udid,
                        "platform": "IOS",
                    }
                }
            })
            if r.status_code in (200, 201):
                print(f"  OK: Registered {name}")
            else:
                print(f"  FAILED: {r.status_code} {r.text[:200]}")


def register_bundle_ids(token):
    print("\n=== REGISTERING BUNDLE IDS ===")
    # Check existing
    r = api_get("/bundleIds", token, {"limit": 200})
    existing = {}
    if r.status_code == 200:
        for b in r.json().get("data", []):
            existing[b["attributes"]["identifier"]] = b

    bundle_ids_needed = []
    for name, suffix in PROFILE_SUFFIX_MAP.items():
        full_id = f"{BUNDLE_ID}{suffix}"
        bundle_ids_needed.append((name, full_id))

    registered = {}
    for name, full_id in bundle_ids_needed:
        if full_id in existing:
            print(f"  OK: {full_id} — already registered")
            registered[name] = existing[full_id]["id"]
        else:
            print(f"  REGISTERING: {full_id}...")
            r = api_post("/bundleIds", token, {
                "data": {
                    "type": "bundleIds",
                    "attributes": {
                        "identifier": full_id,
                        "name": f"TranslateGram2 {name}",
                        "platform": "IOS",
                    }
                }
            })
            if r.status_code in (200, 201):
                registered[name] = r.json()["data"]["id"]
                print(f"  OK: Registered {full_id}")
            else:
                print(f"  FAILED: {r.status_code} {r.text[:200]}")

    return registered


def create_certificate(token):
    print("\n=== CREATING DISTRIBUTION CERTIFICATE ===")
    # Check existing certificates
    r = api_get("/certificates", token, {"filter[certificateType]": "DEVELOPMENT"})
    if r.status_code == 200:
        certs = r.json().get("data", [])
        for c in certs:
            print(f"  Existing: {c['attributes']['name']} (type={c['attributes']['certificateType']}, expires={c['attributes'].get('expirationDate','')})")

    # Generate CSR
    print("  Generating CSR...")
    key_path = tempfile.mktemp(suffix=".key")
    csr_path = tempfile.mktemp(suffix=".csr")

    subprocess.check_call([
        "openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
        "-keyout", key_path, "-out", csr_path,
        "-subj", "/CN=TranslateGram2 Dev/O=Personal/C=DE"
    ], stderr=subprocess.DEVNULL)

    with open(csr_path, "r") as f:
        csr_content = f.read()

    # Create certificate via API
    print("  Requesting certificate from Apple...")
    r = api_post("/certificates", token, {
        "data": {
            "type": "certificates",
            "attributes": {
                "certificateType": "DEVELOPMENT",
                "csrContent": csr_content,
            }
        }
    })

    if r.status_code in (200, 201):
        cert_data = r.json()["data"]
        cert_id = cert_data["id"]
        cert_content = cert_data["attributes"]["certificateContent"]
        print(f"  OK: Certificate created (id={cert_id})")

        # Save certificate as .cer
        cer_path = tempfile.mktemp(suffix=".cer")
        with open(cer_path, "wb") as f:
            f.write(base64.b64decode(cert_content))

        # Create .p12 from cert + key
        p12_path = "/tmp/translategram2-dev.p12"
        pem_cert_path = tempfile.mktemp(suffix=".pem")
        subprocess.check_call([
            "openssl", "x509", "-inform", "DER", "-in", cer_path, "-out", pem_cert_path
        ], stderr=subprocess.DEVNULL)
        subprocess.check_call([
            "openssl", "pkcs12", "-export",
            "-inkey", key_path, "-in", pem_cert_path,
            "-out", p12_path, "-passout", "pass:"
        ], stderr=subprocess.DEVNULL)
        print(f"  OK: P12 saved to {p12_path}")

        # Cleanup temp files
        for f in [key_path, csr_path, cer_path, pem_cert_path]:
            os.unlink(f)

        return cert_id, p12_path
    else:
        print(f"  FAILED: {r.status_code} {r.text[:300]}")
        # Cleanup
        for f in [key_path, csr_path]:
            if os.path.exists(f):
                os.unlink(f)
        return None, None


def create_profiles(token, cert_id, bundle_id_map):
    print("\n=== CREATING PROVISIONING PROFILES ===")
    # Get all device IDs
    r = api_get("/devices", token, {"limit": 200})
    device_ids = []
    if r.status_code == 200:
        for d in r.json().get("data", []):
            if d["attributes"]["platform"] == "IOS" and d["attributes"]["status"] == "ENABLED":
                device_ids.append(d["id"])
    print(f"  Found {len(device_ids)} enabled iOS devices")

    # Delete existing profiles for this bundle ID (they have old cert/devices)
    r = api_get("/profiles", token, {"limit": 200})
    if r.status_code == 200:
        for p in r.json().get("data", []):
            pname = p["attributes"]["name"]
            if "TranslateGram2" in pname or "translategram2" in pname.lower():
                print(f"  Deleting old profile: {pname}")
                requests.delete(f"{BASE_URL}/profiles/{p['id']}",
                                headers={"Authorization": f"Bearer {token}"})

    profiles = {}
    for name, suffix in PROFILE_SUFFIX_MAP.items():
        full_id = f"{BUNDLE_ID}{suffix}"
        bid = bundle_id_map.get(name)
        if not bid:
            print(f"  SKIP: No bundle ID registered for {name}")
            continue

        profile_name = f"TranslateGram2 Dev {name}"
        print(f"  Creating profile: {profile_name} ({full_id})...")

        r = api_post("/profiles", token, {
            "data": {
                "type": "profiles",
                "attributes": {
                    "name": profile_name,
                    "profileType": "IOS_APP_DEVELOPMENT",
                },
                "relationships": {
                    "bundleId": {
                        "data": {"type": "bundleIds", "id": bid}
                    },
                    "certificates": {
                        "data": [{"type": "certificates", "id": cert_id}]
                    },
                    "devices": {
                        "data": [{"type": "devices", "id": did} for did in device_ids]
                    },
                }
            }
        })

        if r.status_code in (200, 201):
            profile_data = r.json()["data"]
            profile_content = profile_data["attributes"]["profileContent"]
            profiles[name] = base64.b64decode(profile_content)
            print(f"  OK: {profile_name}")
        else:
            print(f"  FAILED: {r.status_code} {r.text[:200]}")

    return profiles


def save_profiles_and_cert(profiles, p12_path):
    print("\n=== SAVING TO GITHUB SECRETS ===")
    # Encode profiles as base64 for GitHub secrets
    repo = "niklas03122/TelegramIOSProxy"
    gh_token = os.environ.get("GH_TOKEN", "")

    # Upload certificate
    with open(p12_path, "rb") as f:
        p12_b64 = base64.b64encode(f.read()).decode()

    secrets_to_set = {
        "SIGNING_CERTIFICATE_P12": p12_b64,
        "SIGNING_CERTIFICATE_PASSWORD": "",
    }

    profile_secret_map = {
        "Telegram": "PROFILE_TELEGRAM",
        "Share": "PROFILE_SHARE",
        "Widget": "PROFILE_WIDGET",
        "NotificationContent": "PROFILE_NOTIFICATIONCONTENT",
        "NotificationService": "PROFILE_NOTIFICATIONSERVICE",
        "Intents": "PROFILE_INTENTS",
        "BroadcastUpload": "PROFILE_BROADCASTUPLOAD",
        "WatchApp": "PROFILE_WATCHAPP",
        "WatchExtension": "PROFILE_WATCHEXTENSION",
    }

    for name, content in profiles.items():
        secret_name = profile_secret_map.get(name)
        if secret_name:
            secrets_to_set[secret_name] = base64.b64encode(content).decode()

    for secret_name, value in secrets_to_set.items():
        print(f"  Setting {secret_name}...")
        result = subprocess.run(
            ["gh", "secret", "set", secret_name, "--repo", repo, "--body", value],
            env={**os.environ, "GH_TOKEN": gh_token},
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  OK: {secret_name}")
        else:
            print(f"  FAILED: {result.stderr[:200]}")


def main():
    print("=" * 60)
    print("TranslateGram2 — Apple Developer Setup")
    print("=" * 60)
    print(f"Bundle ID: {BUNDLE_ID}")
    print(f"Team ID:   {TEAM_ID}")
    print(f"Key ID:    {KEY_ID}")

    token = generate_token()
    print("JWT token generated OK")

    # Step 1: Register devices
    register_devices(token)

    # Step 2: Register bundle IDs
    bundle_id_map = register_bundle_ids(token)

    # Step 3: Create certificate
    cert_id, p12_path = create_certificate(token)
    if not cert_id:
        print("\nFATAL: Certificate creation failed. Cannot continue.")
        sys.exit(1)

    # Step 4: Create provisioning profiles
    profiles = create_profiles(token, cert_id, bundle_id_map)
    if not profiles:
        print("\nFATAL: No profiles created. Cannot continue.")
        sys.exit(1)

    # Step 5: Save to GitHub Secrets
    save_profiles_and_cert(profiles, p12_path)

    print("\n" + "=" * 60)
    print(f"DONE: {len(profiles)} profiles + certificate uploaded to GitHub Secrets")
    print("Ready to trigger build.")
    print("=" * 60)


if __name__ == "__main__":
    main()
