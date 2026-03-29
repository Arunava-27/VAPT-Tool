#!/bin/sh
# =============================================================================
# Vault Initialization & Auto-Unseal Script — VAPT Platform
# Runs on every container start:
#   First run  → initializes Vault, saves keys, unseals, seeds secrets
#   Restart    → reads stored keys, unseals if sealed, skips setup
# =============================================================================
set -e

VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
export VAULT_ADDR

INIT_DIR="/vault/init"
KEYS_FILE="$INIT_DIR/unseal_key.txt"
TOKEN_FILE="$INIT_DIR/root_token.txt"
SERVICE_TOKEN_FILE="$INIT_DIR/service_token.txt"
CONFIGURED_FLAG="$INIT_DIR/.configured"

mkdir -p "$INIT_DIR"

# ---------------------------------------------------------------------------
# 1. Wait for Vault API to respond
# ---------------------------------------------------------------------------
echo "==> Waiting for Vault API at $VAULT_ADDR ..."
RETRIES=30
until vault status > /dev/null 2>&1 || vault status 2>&1 | grep -q "Initialized"; do
  RETRIES=$((RETRIES - 1))
  if [ "$RETRIES" -le 0 ]; then
    echo "ERROR: Vault did not become available in time"
    exit 1
  fi
  sleep 2
done
echo "==> Vault API is up"

# ---------------------------------------------------------------------------
# 2. Initialize if not yet done
# ---------------------------------------------------------------------------
VAULT_INIT_STATUS=$(vault status 2>&1 | grep "^Initialized" | awk '{print $2}')
if [ "$VAULT_INIT_STATUS" = "false" ]; then
  echo "==> Vault is not initialized — initializing with 1 key share ..."
  vault operator init -key-shares=1 -key-threshold=1 > "$INIT_DIR/init-output.txt"
  grep "^Unseal Key 1:" "$INIT_DIR/init-output.txt" | awk '{print $NF}' > "$KEYS_FILE"
  grep "^Initial Root Token:" "$INIT_DIR/init-output.txt" | awk '{print $NF}' > "$TOKEN_FILE"
  echo "==> Vault initialized — keys saved to volume"
fi

# ---------------------------------------------------------------------------
# 3. Unseal if sealed
# ---------------------------------------------------------------------------
VAULT_SEALED=$(vault status 2>&1 | grep "^Sealed" | awk '{print $2}')
if [ "$VAULT_SEALED" = "true" ]; then
  echo "==> Vault is sealed — unsealing ..."
  UNSEAL_KEY=$(cat "$KEYS_FILE")
  vault operator unseal "$UNSEAL_KEY"
  echo "==> Vault unsealed"
fi

# ---------------------------------------------------------------------------
# 4. Authenticate as root
# ---------------------------------------------------------------------------
export VAULT_TOKEN=$(cat "$TOKEN_FILE")

# ---------------------------------------------------------------------------
# 5. First-time setup: KV engine, policy, service token, seed secrets
# ---------------------------------------------------------------------------
if [ ! -f "$CONFIGURED_FLAG" ]; then
  echo "==> First-time setup: enabling KV v2 secrets engine ..."
  vault secrets enable -path=secret kv-v2 2>/dev/null || true

  echo "==> Creating vapt-platform policy ..."
  vault policy write vapt-platform - <<'POLICY'
path "secret/data/vapt/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "secret/metadata/vapt/*" {
  capabilities = ["list", "read", "delete"]
}
POLICY

  echo "==> Creating long-lived service token ..."
  vault token create \
    -display-name="vapt-platform-service" \
    -policy=vapt-platform \
    -no-default-policy \
    -ttl=87600h \
    -field=token > "$SERVICE_TOKEN_FILE"

  echo "==> Seeding initial secrets from environment ..."

  vault kv put secret/vapt/database \
    host="postgres" \
    port="5432" \
    name="${POSTGRES_DB:-vapt_platform}" \
    username="${POSTGRES_USER:-vapt_user}" \
    password="${POSTGRES_PASSWORD:-changeme123}"

  vault kv put secret/vapt/auth \
    jwt_secret_key="${JWT_SECRET_KEY:-change-me-in-production}" \
    superuser_email="${SUPERUSER_EMAIL:-admin@vapt-platform.local}" \
    superuser_password="${SUPERUSER_PASSWORD:-Admin@123}"

  vault kv put secret/vapt/rabbitmq \
    username="${RABBITMQ_USER:-guest}" \
    password="${RABBITMQ_PASSWORD:-guest}"

  vault kv put secret/vapt/minio \
    root_user="${MINIO_ROOT_USER:-minioadmin}" \
    root_password="${MINIO_ROOT_PASSWORD:-minioadmin123}"

  vault kv put secret/vapt/redis \
    password="${REDIS_PASSWORD:-redis123}"

  vault kv put secret/vapt/llm \
    openai_api_key="${OPENAI_API_KEY:-}" \
    anthropic_api_key="${ANTHROPIC_API_KEY:-}"

  touch "$CONFIGURED_FLAG"
  echo "==> Vault fully configured!"
else
  echo "==> Vault already configured — skipping seed"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=============================================="
echo " HashiCorp Vault — VAPT Platform"
echo " Status : READY (unsealed)"
echo " UI     : http://localhost:8200"
echo " Token  : $(cat $TOKEN_FILE)"
if [ -f "$SERVICE_TOKEN_FILE" ]; then
  echo " SvcTok : $(cat $SERVICE_TOKEN_FILE)"
fi
echo "=============================================="