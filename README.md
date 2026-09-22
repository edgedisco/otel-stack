# OTel Stack 🔭

A self-hosted OpenTelemetry observability stack for **local development and evaluation** of general-purpose telemetry (logs, traces, metrics) with pre-configured visualization in Grafana.

Unlike LLM-specific trace tooling (like Langfuse), this stack is designed to catch standard OTLP data from endpoint sensors, edge discovery tools (such as [EdgeDisco](../edgedisco)), and infrastructure services.

---

## Architecture

```
                       ┌─────────────────────────┐
                       │   Endpoint Sensors /    │
                       │   EdgeDisco Discovery   │
                       └────────────┬────────────┘
                                    │ OTLP Logs (Protobuf / JSON)
                                    ▼
                       ┌─────────────────────────┐
                       │  OpenTelemetry Collector│
                       │  (Receivers, Processors)│
                       │  • Memory Limiter       │
                       │  • Transform (OTTL)     │
                       │  • Batch                │
                       └─────┬──────┬──────┬─────┘
                             │      │      │
          OTLP Logs (/otlp)  │      │      │ Prometheus Scrape (:8889)
         ┌───────────────────┘      │      └──────────────────┐
         ▼                          ▼                         ▼
   ┌───────────┐             ┌─────────────┐            ┌────────────┐
   │Grafana    │             │Grafana      │            │Prometheus  │
   │Loki (3.0+)│             │Tempo (2.4+) │            │(v2.51+)    │
   └─────┬─────┘             └──────┬──────┘            └─────┬──────┘
         │                          │                         │
         └───────────────────┐      │      ┌──────────────────┘
                             ▼      ▼      ▼
                       ┌─────────────────────────┐
                       │         Grafana         │
                       │  (Port 3001 Dashboard)  │
                       └─────────────────────────┘
```

| Service | Image | Role | Port |
|---|---|---|---|
| **otel-collector** | `otel/opentelemetry-collector-contrib` | OTLP gateway (HTTP/gRPC), OTTL transform, batching, routing | `4317` (gRPC), `4318` (HTTP), `8889` (metrics), `13133` (health) |
| **loki** | `grafana/loki:3.0.0` | High-efficiency log store with native OTLP ingestion & structured metadata | `3100` |
| **tempo** | `grafana/tempo:2.4.1` | Distributed tracing backend | `3200` |
| **prometheus** | `prom/prometheus:v2.51.0` | Metrics engine scraping collector pipeline performance | `9091` |
| **grafana** | `grafana/grafana:10.2.2` | Visualization with pre-provisioned datasources and dashboards | `3001` |

> **Port Conflict Safety:** Grafana is mapped to `3001` to avoid colliding with Langfuse (`3000`), and Prometheus is mapped to `9091` to avoid colliding with MinIO (`9090`).

---

## Quick Start

### 1. Start the stack

```bash
docker compose up -d
```

### 2. Verify all services

Run the included verification script:

```bash
./scripts/verify_stack.sh
```

This script verifies:
1. All 5 containers are up and healthy.
2. Collector health probe returns `OK` (`:13133`).
3. Loki, Tempo, Prometheus, and Grafana readiness probes return `OK`.
4. Emits synthetic EdgeDisco asset detection records in both binary Protobuf and JSON.
5. Queries Loki to confirm structured metadata ingestion.

### 3. Open Grafana

Open your browser to:
[http://localhost:3001](http://localhost:3001)

Anonymous admin access is enabled by default. The **EdgeDisco AI Asset Discovery** dashboard is loaded at root.

Published ports bind to `127.0.0.1` by default. Set `OTEL_STACK_BIND_ADDRESS` explicitly if
you are placing authenticated TLS ingress in front of the stack for remote access.

---

## EdgeDisco Integration Contract

EdgeDisco's outbox projects asset discoveries using the OTLP Logs specification:

- **Transport:** HTTP POST
- **Endpoint:** `http://localhost:4318/v1/logs`
- **Content-Type:** `application/x-protobuf` (`ExportLogsServiceRequest`) or `application/json`
- **Resource Attributes:**
  - `service.name: "edgedisco"`
  - `service.version: "0.5.0"`
- **Scope:**
  - `ai_asset_inventory.otlp_encoder (v0.5.0)`
- **Record Header:**
  - `event_name = "edgedisco.asset.observed"` for asset state changes, or `"edgedisco.device.inventory"` for device inventory heartbeats
  - `severity_number = 9` (INFO)
  - `time_unix_nano` = observation timestamp
- **Record Attributes:**
  - `edgedisco.schema.version` (int `2` for current payloads)
  - `edgedisco.observation.id` (`sha256:<64 hex chars>`)
  - `device.id` (`<32 hex chars>`)
  - `asset.kind` (`"application"` | `"process"` | `"agent_runtime"`)
  - `asset.name` (e.g. `"Claude Code"`, `"Hermes Agent"`, `"Ollama"`, `"CrewAI"`)
  - `asset.vendor` (e.g. `"Anthropic"`, `"Nous Research"`, `"Ollama"`)
  - `asset.running` (boolean `true` | `false`)
  - `asset.present` (boolean; presence is independent from running state)
  - `inventory.asset_count` and `inventory.simulated_asset_count` for device heartbeat records
  - `edgedisco.simulated` (boolean `true` | `false`)
  - `asset.host_app` (optional, e.g. `"Direct/local"`, `"Cursor"`)
  - `asset.relationship` (optional, e.g. `"local_process"`, `"spawned_by"`)

### Protobuf Empty-Body Transform

EdgeDisco asset records leave `record.body` empty, packaging detection data into attributes. Device heartbeat records carry the fixed body `edgedisco.device.inventory`. The collector's OTTL `transform` processor synthesizes a readable body only for asset records:

```yaml
set(body, Concat(["edgedisco.asset.observed: ", attributes["asset.name"], " (", attributes["asset.vendor"], ") [kind=", attributes["asset.kind"], "]"], ""))
where (body == nil or body == "") and attributes["asset.name"] != nil
```

All original attributes are preserved and stored in Loki 3.0 as **structured metadata**.

---

## LogQL Query Examples

In Loki 3.0, resource attributes (like `service.name`) become stream labels (`service_name`), while log record attributes become structured metadata:

```logql
# Asset state changes
{service_name="edgedisco"} | asset_name != ""

# Device inventory heartbeats
{service_name="edgedisco"} | inventory_asset_count != ""

# Filter by asset name
{service_name="edgedisco"} | asset_name = "Claude Code"

# Filter by vendor, presence, and running status
{service_name="edgedisco"} | asset_vendor = "Anthropic" | asset_present = "true" | asset_running = "true"

# Aggregate observation rate per asset
sum by (asset_name) (rate({service_name="edgedisco"} | asset_name != "" [5m]))
```

The OTLP `event_name` header remains part of the log record but is not emitted as a Loki stream
label by this collector/Loki configuration. The type-specific attribute filters above are the
portable way to distinguish asset records from device heartbeats.

---

## Testing & Verification Scripts

### Send test events

The `scripts/send_test_log.py` utility can emit both native binary protobuf and JSON:

```bash
# Binary protobuf asset state change (matches EdgeDisco wire format)
./scripts/send_test_log.py --format proto --name "Claude Code" --vendor "Anthropic" --kind "agent_runtime"

# Binary protobuf device inventory heartbeat
./scripts/send_test_log.py --format proto --event device

# Standard OTLP JSON
./scripts/send_test_log.py --format json --name "Ollama" --vendor "Ollama" --kind "application"
```

### Tail incoming records in real time

The collector is configured with the `debug` exporter:

```bash
docker compose logs -f otel-collector
```

---

## Configuration Files

- `config/otel-collector-config.yaml`: Receivers (4317/4318), memory limiter, OTTL transform processor, Loki/Tempo/Prometheus exporters.
- `config/loki-config.yaml`: TSDB schema v13, filesystem storage, structured metadata enabled.
- `config/tempo-config.yaml`: Local WAL and block storage.
- `config/prometheus.yaml`: Scrapes collector pipeline telemetry on `:8889`.
- `grafana/provisioning/`: Auto-registers Loki, Tempo, and Prometheus datasources.
- `grafana/dashboards/`: Auto-loads EdgeDisco AI asset detection dashboards.
