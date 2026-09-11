#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
cd /app
if python /tests/test_cache.py; then
  echo 1 > /logs/verifier/reward.txt
  exit 0
fi
echo 0 > /logs/verifier/reward.txt
exit 0
