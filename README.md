# OTel Stack 🔭

A self-hosted OpenTelemetry observability stack for **general-purpose telemetry** (logs, traces, metrics) with pre-configured visualization in Grafana.

Unlike LLM-specific trace tooling (like Langfuse), this stack is designed to catch standard OTLP data from endpoint sensors, edge discovery tools (such as [EdgeDisco](../edgedisco)), and infrastructure services.

---

## Architecture

```
                       ┌─────────────────────────┐
                       │   Endpoint Sensors /    │
                       │   EdgeDisco Discovery   │
                       └────────────┬────────────┘
                                    │ OTLP HTTP / gRPC
                                    ▼
                       ┌─────────────────────────┐
                       │  OpenTelemetry Collector│
                       │  (Receivers, Processors)│
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
| **otel-collector** | `otel/opentelemetry-collector-contrib` | OTLP gateway (HTTP/gRPC), batching, routing | `4317` (gRPC), `4318` (HTTP), `8889` (metrics), `13133` (health) |
| **loki** | `grafana/loki:3.0.0` | High-efficiency log store with native OTLP ingestion | `3100` |
| **tempo** | `grafana/tempo:2.4.1` | Distributed tracing backend | `3200` |
| **prometheus** | `prom/prometheus:v2.51.0` | Metrics engine scraping collector performance | `9091` |
| **grafana** | `grafana/grafana:10.2.2` | Visualization with pre-provisioned dashboards | `3001` |

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
1. All containers are up and healthy.
2. Collector health probe returns `OK` (`:13133`).
3. Loki, Tempo, Prometheus, and Grafana are ready.
4. Emits synthetic EdgeDisco asset detection records.
5. Confirms Loki successfully stored the log stream.

### 3. Open Grafana

Open your browser to:
[http://localhost:3001](http://localhost:3001)

Anonymous admin access is enabled by default. The **EdgeDisco AI Asset Discovery** dashboard is loaded at root.

---

## Sending EdgeDisco Telemetry

EdgeDisco's outbox projections target the standard OTLP logs endpoint:

- **Protocol:** HTTP POST
- **Endpoint:** `http://localhost:4318/v1/logs`
- **Content-Type:** `application/x-protobuf` or `application/json`

### Test with the included script

```bash
./scripts/send_test_log.py --name "Claude Code" --vendor "Anthropic" --kind "agent_runtime"
./scripts/send_test_log.py --name "Ollama" --vendor "Ollama" --kind "application"
```

### Tail incoming records in real time

The collector is configured with the `debug` exporter:

```bash
docker compose logs -f otel-collector
```

---

## Configuration Files

- `config/otel-collector-config.yaml`: Receivers (4317/4318), processors, Loki/Tempo/Prometheus exporters.
- `config/loki-config.yaml`: TSDB schema v13, filesystem storage, structured metadata enabled.
- `config/tempo-config.yaml`: Local WAL and block storage.
- `config/prometheus.yaml`: Scrapes collector pipeline telemetry on `:8889`.
- `grafana/provisioning/`: Auto-registers Loki, Tempo, and Prometheus datasources.
- `grafana/dashboards/`: Auto-loads EdgeDisco AI asset detection dashboards.
