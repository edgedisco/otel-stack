#!/usr/bin/env python3
"""Send a synthetic EdgeDisco OTLP asset observation event to the OTel Collector.

Target: POST http://localhost:4318/v1/logs
Content-Type: application/json
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def make_test_payload(asset_name: str, vendor: str, kind: str, running: bool, simulated: bool) -> dict:
    nanos = str(time.time_ns())
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "edgedisco"}},
                        {"key": "service.version", "value": {"stringValue": "0.5.0"}}
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {
                            "name": "ai_asset_inventory.otlp_encoder",
                            "version": "0.5.0"
                        },
                        "logRecords": [
                            {
                                "timeUnixNano": nanos,
                                "observedTimeUnixNano": nanos,
                                "severityNumber": 9,
                                "severityText": "INFO",
                                "body": {
                                    "stringValue": f"edgedisco.asset.observed: {asset_name} ({vendor})"
                                },
                                "attributes": [
                                    {"key": "edgedisco.schema.version", "value": {"intValue": 1}},
                                    {
                                        "key": "edgedisco.observation.id",
                                        "value": {
                                            "stringValue": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                                        }
                                    },
                                    {
                                        "key": "device.id",
                                        "value": {"stringValue": "0123456789abcdef0123456789abcdef"}
                                    },
                                    {"key": "asset.kind", "value": {"stringValue": kind}},
                                    {"key": "asset.name", "value": {"stringValue": asset_name}},
                                    {"key": "asset.vendor", "value": {"stringValue": vendor}},
                                    {"key": "asset.running", "value": {"boolValue": running}},
                                    {"key": "edgedisco.simulated", "value": {"boolValue": simulated}},
                                    {"key": "asset.host_app", "value": {"stringValue": "Direct/local"}},
                                    {"key": "asset.relationship", "value": {"stringValue": "local_process"}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }


def main():
    parser = argparse.ArgumentParser(description="Send test EdgeDisco OTLP log to OTel Collector")
    parser.add_argument("--endpoint", default="http://localhost:4318/v1/logs", help="Collector OTLP logs endpoint")
    parser.add_argument("--name", default="Claude Code", help="Asset name")
    parser.add_argument("--vendor", default="Anthropic", help="Asset vendor")
    parser.add_argument("--kind", default="agent_runtime", help="Asset kind")
    parser.add_argument("--running", action="store_true", default=True, help="Asset running flag")
    parser.add_argument("--simulated", action="store_true", default=False, help="Asset simulated flag")
    args = parser.parse_args()

    payload = make_test_payload(args.name, args.vendor, args.kind, args.running, args.simulated)
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        args.endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    print(f"Sending OTLP log event ({args.name} / {args.vendor}) to {args.endpoint}...")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            print(f"Success! Status: {resp.status} {resp.reason}")
            if body:
                print(f"Response: {body}")
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
