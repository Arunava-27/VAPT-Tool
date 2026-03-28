"""
Elasticsearch index setup script for VAPT platform.

Creates all required indices with their mappings and configures
ILM policies and index templates for time-based audit log rotation.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

import requests

ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
MAPPINGS_DIR = Path(__file__).parent / "mappings"

# Index definitions: (index_name, mapping_file)
INDICES: list[tuple[str, str]] = [
    ("vapt-scan-results", "scan_results.json"),
    ("vapt-vulnerabilities", "vulnerabilities.json"),
    ("vapt-audit-logs", "audit_logs.json"),
]

ILM_POLICY_NAME = "vapt-audit-logs-policy"
INDEX_TEMPLATE_NAME = "vapt-audit-logs-template"


def _load_json(filename: str) -> Dict[str, Any]:
    """Load a JSON file from the mappings directory."""
    with open(MAPPINGS_DIR / filename, encoding="utf-8") as fh:
        return json.load(fh)


def _load_ilm_policy() -> Dict[str, Any]:
    """Load the ILM policy from the templates file."""
    templates_path = Path(__file__).parent / "index_templates.json"
    with open(templates_path, encoding="utf-8") as fh:
        return json.load(fh)


def _es_put(path: str, body: Dict[str, Any]) -> requests.Response:
    """PUT request to Elasticsearch."""
    return requests.put(
        f"{ELASTICSEARCH_URL}/{path}",
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )


def _es_get(path: str) -> requests.Response:
    """GET request to Elasticsearch."""
    return requests.get(f"{ELASTICSEARCH_URL}/{path}", timeout=30)


def create_ilm_policy() -> None:
    """Create the ILM lifecycle policy for audit logs."""
    policy = _load_ilm_policy()
    resp = _es_put(f"_ilm/policy/{ILM_POLICY_NAME}", policy)
    if resp.status_code in (200, 201):
        print(f"  ✅ ILM policy '{ILM_POLICY_NAME}' created/updated")
    else:
        print(f"  ⚠️  ILM policy warning ({resp.status_code}): {resp.text[:200]}")


def create_index_template() -> None:
    """Create an index template for time-based audit log rotation."""
    audit_mapping = _load_json("audit_logs.json")
    template_body = {
        "index_patterns": ["vapt-audit-logs-*"],
        "template": {
            "settings": {
                **audit_mapping.get("settings", {}),
                "index.lifecycle.name": ILM_POLICY_NAME,
                "index.lifecycle.rollover_alias": "vapt-audit-logs",
            },
            "mappings": audit_mapping.get("mappings", {}),
        },
        "priority": 200,
    }
    resp = _es_put(f"_index_template/{INDEX_TEMPLATE_NAME}", template_body)
    if resp.status_code in (200, 201):
        print(f"  ✅ Index template '{INDEX_TEMPLATE_NAME}' created/updated")
    else:
        print(f"  ⚠️  Index template warning ({resp.status_code}): {resp.text[:200]}")


def create_indices() -> Dict[str, str]:
    """Create all indices if they do not already exist. Returns status map."""
    results: Dict[str, str] = {}

    for index_name, mapping_file in INDICES:
        check = _es_get(index_name)
        if check.status_code == 200:
            results[index_name] = "existing"
            print(f"  ⏭️  Index '{index_name}' already exists — skipped")
            continue

        mapping = _load_json(mapping_file)
        resp = _es_put(index_name, mapping)
        if resp.status_code in (200, 201):
            results[index_name] = "created"
            print(f"  ✅ Index '{index_name}' created")
        else:
            results[index_name] = f"error:{resp.status_code}"
            print(f"  ❌ Failed to create '{index_name}' ({resp.status_code}): {resp.text[:200]}")

    return results


def main() -> None:
    """Entry point — set up all Elasticsearch indices and policies."""
    print("\n📊 Elasticsearch Index Setup")
    print("=" * 50)
    print(f"  Connecting to: {ELASTICSEARCH_URL}")

    # Verify cluster is reachable
    try:
        health = _es_get("_cluster/health")
        health.raise_for_status()
        cluster_status = health.json().get("status", "unknown")
        print(f"  Cluster health: {cluster_status}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ Cannot connect to Elasticsearch: {exc}")
        sys.exit(1)

    print("\n  ILM Policy:")
    create_ilm_policy()

    print("\n  Index Template:")
    create_index_template()

    print("\n  Indices:")
    results = create_indices()

    print("\n" + "=" * 50)
    created = sum(1 for v in results.values() if v == "created")
    existing = sum(1 for v in results.values() if v == "existing")
    errors = sum(1 for v in results.values() if v.startswith("error"))
    print(f"  Summary — created: {created}, existing: {existing}, errors: {errors}")

    if errors:
        sys.exit(1)
    print("  ✅ Elasticsearch setup complete\n")


if __name__ == "__main__":
    main()
