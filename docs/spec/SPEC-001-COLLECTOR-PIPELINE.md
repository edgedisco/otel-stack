# SPEC-001: OpenTelemetry Collector Pipeline Invariants & Verification

**Status:** ✅ Active  
**Version:** 1.0.0  

---

## 1. Overview

This specification establishes the requirements and invariants for the `otel-stack` collector pipeline, Loki structured metadata export, and verification harnesses when ingesting telemetry from edge sensors such as `edgedisco`.

---

## 2. Requirements & Traceability Matrix

| Requirement ID | Specification Clause | Verification Test / Method | Expected Outcome | Status |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-OT-001** | Protobuf & JSON OTLP Equivalence | `tests/test_collector_pipeline.py::test_proto_and_json_schemas_equivalent` | Both formats parse to identical resource and log record attribute schemas. | **Implemented** |
| **REQ-OT-002** | OTTL Empty Body Synthesis | `tests/test_collector_pipeline.py::test_ottl_transform_empty_body_rule` | Synthesizes formatted body string if and only if body is empty and `asset.name` is present. Existing non-empty bodies are preserved unmodified. | **Implemented** |
| **REQ-OT-003** | Loki Structured Metadata Mapping | `tests/test_collector_pipeline.py::test_loki_structured_metadata_preservation` | High-cardinality attributes (`edgedisco.observation.id`, `asset.name`, `device.id`) remain in metadata, not high-cardinality stream labels. | **Implemented** |
| **REQ-OT-004** | Health & Ingestion Probe Separation | `scripts/verify_stack.sh` | Health check probe (port 13133) is distinguished from log stream queryability in Loki (port 3100). | **Implemented** |
| **REQ-OT-005** | Localhost Port Exposure Defaults | `tests/test_collector_pipeline.py::test_compose_security_and_localhost_bindings` | All published ports in `docker-compose.yml` are bound explicitly to `127.0.0.1`. | **Implemented** |

---

## 3. Invariant Definitions

### Invariant 1: Non-Destructive OTTL Synthesis
The OpenTelemetry Collector transform processor statement:
```yaml
set(body, Concat(["edgedisco.asset.observed: ", attributes["asset.name"], " (", attributes["asset.vendor"], ") [kind=", attributes["asset.kind"], "]"], ""))
where (body == nil or body == "") and attributes["asset.name"] != nil
```
MUST NOT overwrite or mutate any incoming log record where `body` is already populated with non-whitespace content.

### Invariant 2: Attribute Fidelity
All canonical attributes emitted by Schema v2 sensors (`edgedisco.schema.version`, `edgedisco.observation.id`, `device.id`, `asset.kind`, `asset.name`, `asset.vendor`, `asset.running`, `asset.present`, `asset.host_app`, `asset.relationship`, `edgedisco.simulated`) MUST survive the collector processor pipeline and reach downstream storage without field truncation or data-type coercion.

### Invariant 3: Zero-Canary Ingestion
Ingested payloads MUST NOT require credentials, API keys, or raw process prompts to be processed by the collector or indexed by Loki.
