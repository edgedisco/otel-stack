#!/usr/bin/env python3
"""Send a synthetic EdgeDisco OTLP asset observation event to the OTel Collector.

Supports both binary protobuf (matching EdgeDisco's otlp_encoder.py exactly)
and standard OTLP JSON.

Target: POST http://localhost:4318/v1/logs
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

try:
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
    HAS_PROTO = True
except ImportError:
    ExportLogsServiceRequest = None
    AnyValue = None
    KeyValue = None
    HAS_PROTO = False


EVENT_NAME = "edgedisco.asset.observed"
SCHEMA_VERSION = 1
SERVICE_NAME = "edgedisco"
SERVICE_VERSION = "0.5.0"
SCOPE_NAME = "ai_asset_inventory.otlp_encoder"
SCOPE_VERSION = "0.5.0"


def make_proto_payload(asset_name: str, vendor: str, kind: str, running: bool, simulated: bool,
                       host_app: str = "Direct/local", relationship: str = "local_process") -> bytes:
    if not HAS_PROTO or ExportLogsServiceRequest is None or KeyValue is None or AnyValue is None:
        raise RuntimeError("opentelemetry.proto is required for protobuf encoding")

    nanos = time.time_ns()
    device_id = hashlib.md5(b"edgedisco-test-device").hexdigest()
    obs_id = "sha256:" + hashlib.sha256(uuid.uuid4().bytes).hexdigest()

    def kv(key: str, val):
        if isinstance(val, bool):
            return KeyValue(key=key, value=AnyValue(bool_value=val))
        elif isinstance(val, int):
            return KeyValue(key=key, value=AnyValue(int_value=val))
        return KeyValue(key=key, value=AnyValue(string_value=str(val)))

    req = ExportLogsServiceRequest()
    resource_logs = req.resource_logs.add()
    resource_logs.resource.attributes.extend([
        kv("service.name", SERVICE_NAME),
        kv("service.version", SERVICE_VERSION),
    ])

    scope_logs = resource_logs.scope_logs.add()
    scope_logs.scope.name = SCOPE_NAME
    scope_logs.scope.version = SCOPE_VERSION

    record = scope_logs.log_records.add()
    record.time_unix_nano = nanos
    record.observed_time_unix_nano = nanos
    record.severity_number = 9  # INFO
    record.severity_text = "INFO"
    record.event_name = EVENT_NAME
    # EdgeDisco's encoder leaves record.body empty and sets all fields in attributes
    record.attributes.extend([
        kv("asset.host_app", host_app),
        kv("asset.kind", kind),
        kv("asset.name", asset_name),
        kv("asset.relationship", relationship),
        kv("asset.running", running),
        kv("asset.vendor", vendor),
        kv("device.id", device_id),
        kv("edgedisco.observation.id", obs_id),
        kv("edgedisco.schema.version", SCHEMA_VERSION),
        kv("edgedisco.simulated", simulated),
    ])

    return req.SerializeToString()


def make_json_payload(asset_name: str, vendor: str, kind: str, running: bool, simulated: bool,
                      host_app: str = "Direct/local", relationship: str = "local_process") -> bytes:
    nanos = str(time.time_ns())
    device_id = hashlib.md5(b"edgedisco-test-device").hexdigest()
    obs_id = "sha256:" + hashlib.sha256(uuid.uuid4().bytes).hexdigest()

    payload = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": SERVICE_NAME}},
                        {"key": "service.version", "value": {"stringValue": SERVICE_VERSION}}
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {
                            "name": SCOPE_NAME,
                            "version": SCOPE_VERSION
                        },
                        "logRecords": [
                            {
                                "timeUnixNano": nanos,
                                "observedTimeUnixNano": nanos,
                                "severityNumber": 9,
                                "severityText": "INFO",
                                "attributes": [
                                    {"key": "edgedisco.schema.version", "value": {"intValue": SCHEMA_VERSION}},
                                    {"key": "edgedisco.observation.id", "value": {"stringValue": obs_id}},
                                    {"key": "device.id", "value": {"stringValue": device_id}},
                                    {"key": "asset.kind", "value": {"stringValue": kind}},
                                    {"key": "asset.name", "value": {"stringValue": asset_name}},
                                    {"key": "asset.vendor", "value": {"stringValue": vendor}},
                                    {"key": "asset.running", "value": {"boolValue": running}},
                                    {"key": "edgedisco.simulated", "value": {"boolValue": simulated}},
                                    {"key": "asset.host_app", "value": {"stringValue": host_app}},
                                    {"key": "asset.relationship", "value": {"stringValue": relationship}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    return json.dumps(payload).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Send test EdgeDisco OTLP log to OTel Collector")
    parser.add_argument("--endpoint", default="http://localhost:4318/v1/logs", help="Collector OTLP logs endpoint")
    parser.add_argument("--name", default="Claude Code", help="Asset name")
    parser.add_argument("--vendor", default="Anthropic", help="Asset vendor")
    parser.add_argument("--kind", default="agent_runtime", help="Asset kind")
    parser.add_argument("--running", action="store_true", default=True, help="Asset running flag")
    parser.add_argument("--simulated", action="store_true", default=False, help="Asset simulated flag")
    parser.add_argument("--format", choices=["auto", "proto", "json"], default="auto", help="Payload wire format")
    args = parser.parse_args()

    fmt = args.format
    if fmt == "auto":
        fmt = "proto" if HAS_PROTO else "json"

    if fmt == "proto":
        data = make_proto_payload(args.name, args.vendor, args.kind, args.running, args.simulated)
        content_type = "application/x-protobuf"
    else:
        data = make_json_payload(args.name, args.vendor, args.kind, args.running, args.simulated)
        content_type = "application/json"

    req = urllib.request.Request(
        args.endpoint,
        data=data,
        headers={"Content-Type": content_type},
        method="POST"
    )

    print(f"Sending OTLP {fmt.upper()} log ({args.name} / {args.vendor}) to {args.endpoint}...")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"Success! Status: {resp.status} {resp.reason}")
            if body.strip():
                print(f"Response: {body.strip()}")
            return 0
    except urllib.error.HTTPError as exc:
        print(f"HTTP Error {exc.code}: {exc.read().decode('utf-8')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Connection failed: {exc.reason}", file=sys.stderr)
        print("Ensure otel-collector is running: docker compose up -d", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
