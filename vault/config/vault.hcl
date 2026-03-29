# =============================================================================
# HashiCorp Vault Configuration — VAPT Platform
# Private network deployment (TLS disabled — add certs for production)
# =============================================================================

ui           = true
api_addr     = "http://0.0.0.0:8200"
cluster_addr = "http://0.0.0.0:8201"
log_level    = "info"

# File storage backend — data persists in a named Docker volume
storage "file" {
  path = "/vault/file"
}

# TCP listener — no TLS for private network dev deployments
# To enable TLS: set tls_cert_file and tls_key_file and remove tls_disable
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = "true"
}
