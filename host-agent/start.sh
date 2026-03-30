#!/bin/bash
cd "$(dirname "$0")"

echo "============================================"
echo " VAPT Platform - Host Discovery Agent"
echo "============================================"

if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv .venv
    echo "[*] Installing dependencies..."
    .venv/bin/pip install -r requirements.txt --quiet
fi

echo "[+] Starting host agent on http://localhost:9999"
echo "[+] Keep this terminal open while using VAPT Platform"
echo ""
.venv/bin/python agent.py
