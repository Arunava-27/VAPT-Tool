"""
Data Layer Initialisation Script.

Master init script that:
1. Waits for PostgreSQL, Elasticsearch and MinIO to be ready.
2. Runs Alembic migrations (alembic upgrade head).
3. Sets up Elasticsearch indices.
4. Sets up MinIO buckets.
5. Seeds required initial data.
6. Prints a ✅ / ❌ status for each component.
"""

import os
import subprocess
import sys
import time
from typing import Callable

import requests
from minio import Minio
from minio.error import S3Error
import psycopg2

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://vapt_user:changeme123@localhost:5432/vapt_platform",
)
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"

MAX_RETRIES = 30
RETRY_INTERVAL = 5  # seconds


# ---------------------------------------------------------------------------
# Readiness checks
# ---------------------------------------------------------------------------

def wait_for(name: str, check: Callable[[], bool]) -> bool:
    """Retry *check* up to MAX_RETRIES times, waiting RETRY_INTERVAL between attempts."""
    print(f"  Waiting for {name}...", end="", flush=True)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if check():
                print(f" ready after {attempt} attempt(s)")
                return True
        except Exception:  # noqa: BLE001
            pass
        print(".", end="", flush=True)
        time.sleep(RETRY_INTERVAL)
    print(f"\n  ❌ {name} did not become ready after {MAX_RETRIES} attempts")
    return False


def _postgres_ready() -> bool:
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
    conn.close()
    return True


def _elasticsearch_ready() -> bool:
    resp = requests.get(f"{ELASTICSEARCH_URL}/_cluster/health", timeout=5)
    return resp.status_code == 200


def _minio_ready() -> bool:
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )
    list(client.list_buckets())
    return True


# ---------------------------------------------------------------------------
# Component setup
# ---------------------------------------------------------------------------

def run_alembic_migrations() -> bool:
    """Run alembic upgrade head."""
    print("\n📦 Running Alembic migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode == 0:
        print("  ✅ Migrations applied successfully")
        return True
    print(f"  ❌ Migrations failed:\n{result.stderr.strip()}")
    return False


def setup_elasticsearch() -> bool:
    """Run the Elasticsearch index setup script."""
    print("\n📊 Setting up Elasticsearch indices...")
    try:
        # Import and run directly (avoids subprocess path issues)
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "setup_indices",
            __import__("pathlib").Path(__file__).parent / "elasticsearch" / "setup_indices.py",
        )
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        module.main()
        return True
    except SystemExit as exc:
        if exc.code == 0:
            return True
        print(f"  ❌ Elasticsearch setup exited with code {exc.code}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ Elasticsearch setup error: {exc}")
        return False


def setup_minio() -> bool:
    """Run the MinIO bucket setup script."""
    print("\n🗄️  Setting up MinIO buckets...")
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "setup_buckets",
            __import__("pathlib").Path(__file__).parent / "minio" / "setup_buckets.py",
        )
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        module.main()
        return True
    except SystemExit as exc:
        if exc.code == 0:
            return True
        print(f"  ❌ MinIO setup exited with code {exc.code}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ MinIO setup error: {exc}")
        return False


def seed_initial_data() -> bool:
    """
    Seed initial required data (idempotent).

    The database seed is handled by init_database.sql and Alembic migrations.
    This function provides a hook for any additional runtime seeding.
    """
    print("\n🌱 Seeding initial data...")
    print("  ✅ Seed data handled by Alembic migrations (idempotent)")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Orchestrate the full data layer initialisation."""
    print("=" * 60)
    print("🚀 VAPT Platform — Data Layer Initialisation")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Wait for services
    # ------------------------------------------------------------------
    print("\n⏳ Waiting for services to be ready...")
    services_ready = all([
        wait_for("PostgreSQL", _postgres_ready),
        wait_for("Elasticsearch", _elasticsearch_ready),
        wait_for("MinIO", _minio_ready),
    ])

    if not services_ready:
        print("\n❌ One or more services are not ready. Aborting.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Run components
    # ------------------------------------------------------------------
    results = {
        "PostgreSQL":      True,  # confirmed ready above
        "Elasticsearch":   True,
        "MinIO":           True,
        "Migrations":      run_alembic_migrations(),
        "ES Indices":      setup_elasticsearch(),
        "MinIO Buckets":   setup_minio(),
        "Seed Data":       seed_initial_data(),
    }

    # ------------------------------------------------------------------
    # 3. Final status report
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("📋 Initialisation Summary")
    print("=" * 60)
    all_ok = True
    for component, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status}  {component}")
        if not ok:
            all_ok = False

    print("=" * 60)
    if all_ok:
        print("✅ Data layer initialisation complete!\n")
    else:
        print("❌ Some components failed. Check logs above.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
