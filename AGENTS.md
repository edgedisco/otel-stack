# AGENTS.md

This file provides guidance to coding agents (Claude Code, Hermes Agent, Antigravity, and any tool that reads `AGENTS.md`) when working with code in this repository. `CLAUDE.md` is a symlink to this file, so both stay in sync.

## What this repo is

A production-grade, self-hosted OpenTelemetry observability stack running via `docker-compose.yml`. It provides an OpenTelemetry Collector, unified log/trace/metric storage (Loki, Tempo, Prometheus), and Grafana visualization.

Unlike LLM-specific trace trackers (e.g. Langfuse), this stack is built for **general-purpose telemetry** — specifically designed to catch OTLP logs, traces, and metrics from endpoint sensors and discovery agents such as `edgedisco` (`../edgedisco`).

## Architecture

Five services wired together on an internal Docker network with published host ports for sensor ingestion and dashboard access.

| Service | Image | Purpose | Host Port |
|---|---|---|---|
| `otel-collector` | `otel/opentelemetry-collector-contrib` | OTLP pipeline: receives gRPC/HTTP, batches, exports | `4317` (gRPC), `4318` (HTTP), `8889` (metrics), `13133` (health) |
| `loki` | `grafana/loki:3.0.0` | Log store with native OTLP ingestion & structured metadata | `3100` |
| `tempo` | `grafana/tempo:2.4.1` | Distributed trace backend | `3200` |
| `prometheus` | `prom/prometheus:v2.51.0` | Metrics store, scrapes collector pipeline stats | `9091` (avoids 9090 MinIO conflict) |
| `grafana` | `grafana/grafana:10.2.2` | Visualization UI with pre-provisioned datasources & dashboards | `3001` (avoids 3000 Langfuse conflict) |

### Request Flow for EdgeDisco Sensors

1. **Sensor / Outbox:** `edgedisco` projects AI asset discoveries (`POST /v1/logs` with `Content-Type: application/x-protobuf` or `application/json`).
2. **Collector:** `otel-collector` receives on port `4318`, parses OTLP LogRecords, applies memory limiter & batching processors, and outputs detailed debug logs to stdout.
3. **Storage:**
   - Logs flow to Loki via `http://loki:3100/otlp` with full structured attributes (`asset.name`, `asset.vendor`, `device.id`, `asset.running`).
   - Traces flow to Tempo via `tempo:4317`.
   - Collector internal metrics are scraped by Prometheus from `:8889`.
4. **Visualization:** Grafana automatically provisions Loki, Tempo, and Prometheus, opening with the **EdgeDisco AI Asset Discovery** dashboard on `http://localhost:3001`.

## Host Port Reservations & Conflicts

To prevent collisions with existing mac-mini services:
- **Port 3001** is used for Grafana (since Langfuse uses `3000`).
- **Port 9091** is used for Prometheus (since MinIO uses `9090`).
- **Port 4317 & 4318** are dedicated to the OTel Collector.
- **Port 3100** is dedicated to Loki.
- **Port 3200** is dedicated to Tempo.
- **Port 13133** is dedicated to Collector health probes.

## Commands

All commands assume CWD is the repo root. `.env` is picked up automatically by Docker Compose.

```bash
# Start stack detached
docker compose up -d

# Check service health
docker compose ps

# Tail collector logs to observe sensor ingestion in real time
docker compose logs -f otel-collector

# Run full pipeline verification (health checks + sample test events + Loki query)
./scripts/verify_stack.sh

# Emit a test EdgeDisco asset observation event
./scripts/send_test_log.py --name "Claude Code" --vendor "Anthropic" --kind "agent_runtime"

# Stop stack, keeping data volumes
docker compose down

# Stop stack and nuke data volumes
docker compose down -v
```

## EdgeDisco Integration Contract

EdgeDisco emits OTLP Logs to `/v1/logs`.
- Resource: `service.name: edgedisco`
- Scope: `ai_asset_inventory.otlp_encoder`
- Attributes preserved in Loki:
  - `edgedisco.schema.version` (int)
  - `edgedisco.observation.id` (sha256 hex string)
  - `device.id` (32-char hex string)
  - `asset.kind` (`application` | `process` | `agent_runtime`)
  - `asset.name` (string)
  - `asset.vendor` (string)
  - `asset.running` (bool)
  - `edgedisco.simulated` (bool)
  - `asset.host_app` (optional, e.g. `Cursor`, `Direct/local`)
  - `asset.relationship` (optional, e.g. `spawned_by`, `local_process`)
