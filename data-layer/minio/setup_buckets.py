"""
MinIO bucket setup script for VAPT platform.

Creates all required buckets with appropriate access policies
and lifecycle rules.
"""

import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List

from minio import Minio
from minio.commonconfig import Filter
from minio.error import S3Error
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

DATA_DIR = Path(__file__).parent

# Bucket definitions: (name, description)
BUCKETS: List[tuple[str, str]] = [
    ("scan-results", "Raw scan output from security tools"),
    ("reports",      "Generated security reports (HTML/PDF/JSON)"),
    ("artifacts",    "Scan artifacts and evidence files"),
    ("temp",         "Temporary files — auto-deleted after 7 days"),
]


def _load_json(filename: str) -> Dict[str, Any]:
    """Load a JSON file from the data directory."""
    with open(DATA_DIR / filename, encoding="utf-8") as fh:
        return json.load(fh)


def _get_client() -> Minio:
    """Create and return a MinIO client."""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


def create_buckets(client: Minio) -> Dict[str, str]:
    """Create all buckets if they do not already exist."""
    results: Dict[str, str] = {}

    for bucket_name, description in BUCKETS:
        try:
            if client.bucket_exists(bucket_name):
                results[bucket_name] = "existing"
                print(f"  ⏭️  Bucket '{bucket_name}' already exists — skipped")
            else:
                client.make_bucket(bucket_name)
                results[bucket_name] = "created"
                print(f"  ✅ Bucket '{bucket_name}' created  ({description})")
        except S3Error as exc:
            results[bucket_name] = f"error:{exc.code}"
            print(f"  ❌ Failed to create '{bucket_name}': {exc}")

    return results


def apply_lifecycle_rules(client: Minio) -> None:
    """Apply lifecycle rules to the temp bucket (delete after 7 days)."""
    lifecycle_config = LifecycleConfig(
        rules=[
            Rule(
                rule_filter=Filter(prefix=""),
                rule_id="delete-temp-after-7-days",
                status="Enabled",
                expiration=Expiration(days=7),
            )
        ]
    )
    try:
        client.set_bucket_lifecycle("temp", lifecycle_config)
        print("  ✅ Lifecycle rules applied to 'temp' bucket (7-day expiry)")
    except S3Error as exc:
        print(f"  ⚠️  Lifecycle rule warning for 'temp': {exc}")


def apply_bucket_policies(client: Minio) -> None:
    """Apply access policies to all buckets (all private)."""
    policies = _load_json("bucket_policies.json")

    for bucket_name, policy in policies.items():
        try:
            # Check bucket exists before applying policy
            if not client.bucket_exists(bucket_name):
                continue
            client.set_bucket_policy(bucket_name, json.dumps(policy))
            print(f"  ✅ Policy applied to '{bucket_name}'")
        except S3Error as exc:
            # MinIO may reject AWS-style deny policies — log and continue
            print(f"  ⚠️  Policy warning for '{bucket_name}': {exc}")


def main() -> None:
    """Entry point — set up all MinIO buckets."""
    print("\n🗄️  MinIO Bucket Setup")
    print("=" * 50)
    print(f"  Endpoint : {MINIO_ENDPOINT}")
    print(f"  Secure   : {MINIO_SECURE}")

    try:
        client = _get_client()
        # Quick connectivity check
        list(client.list_buckets())
        print("  Connection: OK")
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ Cannot connect to MinIO: {exc}")
        sys.exit(1)

    print("\n  Buckets:")
    results = create_buckets(client)

    print("\n  Lifecycle Rules:")
    apply_lifecycle_rules(client)

    print("\n  Bucket Policies:")
    apply_bucket_policies(client)

    print("\n" + "=" * 50)
    created = sum(1 for v in results.values() if v == "created")
    existing = sum(1 for v in results.values() if v == "existing")
    errors = sum(1 for v in results.values() if v.startswith("error"))
    print(f"  Summary — created: {created}, existing: {existing}, errors: {errors}")

    if errors:
        sys.exit(1)
    print("  ✅ MinIO setup complete\n")


if __name__ == "__main__":
    main()
