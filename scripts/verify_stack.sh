#!/usr/bin/env bash
set -euo pipefail

if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=${PYTHON:-python3}
fi

wait_for_ready() {
  local url="$1"
  local name="$2"
  local max=25
  local count=0
  echo -n "$name: "
  until curl -sf "$url" >/dev/null 2>&1; do
    count=$((count + 1))
    if [ "$count" -ge "$max" ]; then
      echo " [FAIL]"
      return 1
    fi
    sleep 1
  done
  echo " [OK]"
}

echo "=== 1. Checking Container Status ==="
docker compose ps

echo -e "\n=== 2. Checking Service Health & Readiness ==="
wait_for_ready "http://localhost:13133/" "OTel Collector Health (13133)"
wait_for_ready "http://localhost:3100/ready" "Loki Ready (3100)"
wait_for_ready "http://localhost:3200/ready" "Tempo Ready (3200)"
wait_for_ready "http://localhost:9091/-/ready" "Prometheus Ready (9091)"
wait_for_ready "http://localhost:3001/api/health" "Grafana Health (3001)"

echo -e "\n=== 3. Ingesting Sample EdgeDisco Sensor Events (Protobuf & JSON) ==="
"$PYTHON" scripts/send_test_log.py --format proto --name "Claude Code" --vendor "Anthropic" --kind "agent_runtime"
"$PYTHON" scripts/send_test_log.py --format proto --event device
"$PYTHON" scripts/send_test_log.py --format json --name "Ollama" --vendor "Ollama" --kind "application"

echo -e "\n=== 4. Waiting for Ingestion / Loki Flush (2s) ==="
sleep 2

echo -e "\n=== 5. Querying Loki for EdgeDisco Structured Metadata ==="
curl -sG http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={service_name="edgedisco"} | asset_name != ""' | \
  "$PYTHON" -c "
import sys, json
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if not results:
    raise SystemExit('No EdgeDisco asset streams found in Loki')
print(f'Retrieved {len(results)} EdgeDisco asset streams from Loki:')
for r in results[:5]:
    meta = r.get('stream', {})
    asset = meta.get('asset_name', 'unknown')
    vendor = meta.get('asset_vendor', 'unknown')
    running = meta.get('asset_running', 'unknown')
    print(f'  • {asset} ({vendor}) - running: {running}')
"

curl -sG http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={service_name="edgedisco"} | inventory_asset_count != ""' \
  --data-urlencode 'limit=100' | \
  "$PYTHON" -c "
import sys, json
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if not results:
    raise SystemExit('No EdgeDisco device-heartbeat streams found in Loki')
print(f'Retrieved {len(results)} EdgeDisco device-heartbeat streams from Loki.')
"

echo -e "\n=== Stack is verified! Grafana UI available at: http://localhost:3001 ==="
