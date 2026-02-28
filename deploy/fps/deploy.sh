#!/bin/bash
# =============================================================
# Hydraulic Filter Expert — Deployment Script
# =============================================================
# Run this on the server after pushing code changes.
#
# Usage:
#   ssh deploy@<server-ip>
#   cd /opt/sprayoracle
#   bash deploy.sh
# =============================================================

set -euo pipefail

echo "=== Deploying sprayoracle.com ==="
echo "$(date)"
echo ""

cd /opt/sprayoracle

# Pull latest code
echo "[1/4] Pulling latest code..."
git pull origin main

# Rebuild the Docker image (includes frontend build + Python deps)
echo ""
echo "[2/4] Building Docker image..."
docker compose build

# Restart containers (Caddy waits for app health check before accepting traffic)
echo ""
echo "[3/4] Restarting containers..."
docker compose up -d

# Wait for the app to be healthy
echo ""
echo "[4/4] Waiting for health check..."
sleep 10

if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "Health check: PASSED"
else
    echo "Health check: FAILED — checking logs..."
    docker compose logs --tail=50 app
    exit 1
fi

echo ""
docker compose ps
echo ""
echo "=== Deploy complete ==="
echo "$(date)"
