# AGENTS.md

This file provides guidance to coding agents (Claude Code, Hermes Agent, Antigravity, and any tool that reads `AGENTS.md`) when working with code in this repository. `CLAUDE.md` is a symlink to this file, so both stay in sync.

## What this repo is

A self-hosted OpenTelemetry observability stack for local development and evaluation running via `docker-compose.yml`. It provides an OpenTelemetry Collector, unified log/trace/metric storage (Loki, Tempo, Prometheus), and Grafana visualization.

Unlike LLM-specific trace trackers (e.g. Langfuse), this stack is built for **general-purpose telemetry** — specifically designed to catch OTLP logs, traces, and metrics from endpoint sensors and discovery agents such as `edgedisco` (`../edgedisco`).

## Architecture

Five services wired together on an internal Docker network with published host ports for sensor ingestion and dashboard access.

| Service | Image | Purpose | Host Port |
|---|---|---|---|
| `otel-collector` | `otel/opentelemetry-collector-contrib` | OTLP pipeline: receives gRPC/HTTP, OTTL transform, batches, exports | `4317` (gRPC), `4318` (HTTP), `8889` (metrics), `13133` (health) |
| `loki` | `grafana/loki:3.0.0` | Log store with native OTLP ingestion & structured metadata | `3100` |
| `tempo` | `grafana/tempo:2.4.1` | Distributed trace backend | `3200` |
| `prometheus` | `prom/prometheus:v2.51.0` | Metrics store, scrapes collector pipeline stats | `9091` (avoids 9090 MinIO conflict) |
| `grafana` | `grafana/grafana:10.2.2` | Visualization UI with pre-provisioned datasources & dashboards | `3001` (avoids 3000 Langfuse conflict) |

### Request Flow for EdgeDisco Sensors

1. **Sensor / Outbox:** `edgedisco` projects AI asset discoveries (`POST /v1/logs` with `Content-Type: application/x-protobuf` or `application/json`).
2. **Collector:** `otel-collector` receives on port `4318`, parses OTLP LogRecords, applies memory limiter, runs OTTL transform to populate body from attributes if empty, batches records, and outputs detailed debug logs to stdout.
3. **Storage:**
   - Logs flow to Loki via `http://loki:3100/otlp` with full structured metadata (`asset_name`, `asset_vendor`, `device_id`, `asset_running`, etc.).
   - Traces flow to Tempo via `tempo:4317`.
   - Collector internal metrics are scraped by Prometheus from `:8889`.
4. **Visualization:** Grafana automatically provisions Loki, Tempo, and Prometheus, opening with the **EdgeDisco AI Asset Discovery** dashboard on `http://localhost:3001`.

## Host Port Reservations & Conflicts

Published services bind to localhost by default. Set `OTEL_STACK_BIND_ADDRESS` explicitly only when a protected remote bind is required. To prevent collisions with existing mac-mini services:
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

# Run full pipeline verification (health checks + protobuf/json sample events + Loki query)
./scripts/verify_stack.sh

# Emit test EdgeDisco asset observation events
./scripts/send_test_log.py --format proto --name "Claude Code" --vendor "Anthropic" --kind "agent_runtime"
./scripts/send_test_log.py --format json --name "Ollama" --vendor "Ollama" --kind "application"

# Stop stack, keeping data volumes
docker compose down

# Stop stack and nuke data volumes
docker compose down -v
```

The OTLP `event_name` header is not emitted as a Loki stream label by this configuration.
Use the type-specific attribute filters above when querying asset records and device heartbeats.

## EdgeDisco Integration Contract

EdgeDisco emits OTLP Logs to `/v1/logs`.
- Method: `POST`
- Path: `/v1/logs`
- Content-Type: `application/x-protobuf` (`ExportLogsServiceRequest`) or `application/json`
- Resource: `service.name: "edgedisco"`, `service.version: "0.5.0"`
- Scope: `ai_asset_inventory.otlp_encoder (v0.5.0)`
- Record:
  - `event_name = "edgedisco.asset.observed"` for asset state changes, or `"edgedisco.device.inventory"` for device inventory heartbeats
  - `severity_number = 9` (INFO)
  - `time_unix_nano` = nanoseconds timestamp
  - `body` = a fixed `edgedisco.device.inventory` string for heartbeat events; asset bodies are synthesized by the collector OTTL transform into `edgedisco.asset.observed: <name> (<vendor>) [kind=<kind>]`
- Attributes preserved in Loki structured metadata:
  - `edgedisco.schema.version` (int `2` for current payloads)
  - `edgedisco.observation.id` (`sha256:<64 hex chars>`)
  - `device.id` (`<32 hex chars>`)
  - `asset.kind` (`"application"` | `"process"` | `"agent_runtime"`)
  - `asset.name` (string)
  - `asset.vendor` (string)
  - `asset.running` (bool)
  - `asset.present` (bool; distinct from running state)
  - `inventory.asset_count` and `inventory.simulated_asset_count` for device heartbeat events
  - `edgedisco.simulated` (bool)
  - `asset.host_app` (optional, e.g. `"Cursor"`, `"Direct/local"`)
  - `asset.relationship` (optional, e.g. `"spawned_by"`, `"local_process"`)

### LogQL Query Syntax

```logql
# Asset state changes only
{service_name="edgedisco"} | asset_name != ""

# Structured metadata pipeline filters (Loki 3.0)
{service_name="edgedisco"} | inventory_asset_count != ""

# Structured metadata pipeline filters (Loki 3.0)
{service_name="edgedisco"} | asset_name = "Claude Code"
{service_name="edgedisco"} | asset_vendor = "Anthropic" | asset_present = "true" | asset_running = "true"
```
