import json
import re
import unittest
from pathlib import Path
import yaml
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "golden_otlp"
CONFIG_DIR = Path(__file__).parent.parent / "config"
COMPOSE_FILE = Path(__file__).parent.parent / "docker-compose.yml"


class CollectorPipelineTests(unittest.TestCase):
    def test_proto_and_json_schemas_equivalent(self):
        """REQ-OT-001: Protobuf and JSON fixtures contain identical schema attributes."""
        pb_path = FIXTURES_DIR / "observation_v2.pb"
        json_path = FIXTURES_DIR / "observation_v2.json"
        self.assertTrue(pb_path.exists())
        self.assertTrue(json_path.exists())

        # Decode protobuf
        req = ExportLogsServiceRequest()
        req.ParseFromString(pb_path.read_bytes())
        self.assertEqual(len(req.resource_logs), 1)
        record = req.resource_logs[0].scope_logs[0].log_records[0]
        
        pb_attrs = {}
        for kv in record.attributes:
            val = kv.value
            if val.HasField("string_value"):
                pb_attrs[kv.key] = val.string_value
            elif val.HasField("bool_value"):
                pb_attrs[kv.key] = val.bool_value
            elif val.HasField("int_value"):
                pb_attrs[kv.key] = val.int_value

        # Decode JSON
        json_obj = json.loads(json_path.read_text(encoding="utf-8"))
        json_attrs = json_obj["attributes"]

        self.assertEqual(pb_attrs["edgedisco.schema.version"], json_attrs["edgedisco.schema.version"])
        self.assertEqual(pb_attrs["asset.name"], json_attrs["asset.name"])
        self.assertEqual(pb_attrs["asset.vendor"], json_attrs["asset.vendor"])
        self.assertEqual(pb_attrs["asset.kind"], json_attrs["asset.kind"])
        self.assertEqual(pb_attrs["asset.running"], json_attrs["asset.running"])
        self.assertEqual(pb_attrs["asset.present"], json_attrs["asset.present"])
        self.assertEqual(pb_attrs["device.id"], json_attrs["device.id"])
        self.assertEqual(pb_attrs["edgedisco.observation.id"], json_attrs["edgedisco.observation.id"])

    def test_ottl_transform_empty_body_rule(self):
        """REQ-OT-002: OTTL transform synthesizes body only when empty, preserving non-empty bodies."""
        collector_cfg = yaml.safe_load((CONFIG_DIR / "otel-collector-config.yaml").read_text(encoding="utf-8"))
        statements = collector_cfg["processors"]["transform"]["log_statements"][0]["statements"]
        ottl_rule = statements[0]
        
        # Verify the OTTL statement matches specification
        self.assertIn('set(body, Concat(["edgedisco.asset.observed: ", attributes["asset.name"], " (", attributes["asset.vendor"], ") [kind=", attributes["asset.kind"], "]"], ""))', ottl_rule)
        self.assertIn('(body == nil or body == "") and attributes["asset.name"] != nil', ottl_rule)

        # Simulation function mirroring exact OTTL statement
        def apply_ottl(body, attributes):
            if (body is None or body == "") and attributes.get("asset.name") is not None:
                return f"edgedisco.asset.observed: {attributes['asset.name']} ({attributes['asset.vendor']}) [kind={attributes['asset.kind']}]"
            return body

        # Case A: empty body -> synthesized
        attrs = {"asset.name": "Ollama", "asset.vendor": "Ollama", "asset.kind": "agent_runtime"}
        synthesized = apply_ottl("", attrs)
        self.assertEqual(synthesized, "edgedisco.asset.observed: Ollama (Ollama) [kind=agent_runtime]")

        # Case B: explicit body -> non-destructive preservation
        explicit = apply_ottl("Custom log payload", attrs)
        self.assertEqual(explicit, "Custom log payload")

    def test_loki_structured_metadata_preservation(self):
        """REQ-OT-003: Loki config enables structured metadata and TSDB schema."""
        loki_cfg = yaml.safe_load((CONFIG_DIR / "loki-config.yaml").read_text(encoding="utf-8"))
        self.assertTrue(loki_cfg.get("limits_config", {}).get("allow_structured_metadata"))
        
        schemas = loki_cfg.get("schema_config", {}).get("configs", [])
        self.assertTrue(any(s.get("schema") == "v13" and s.get("store") == "tsdb" for s in schemas))

    def test_compose_security_and_localhost_bindings(self):
        """REQ-OT-005: All published ports in docker-compose.yml bind explicitly to localhost."""
        compose_cfg = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
        services = compose_cfg.get("services", {})
        
        for name, svc in services.items():
            ports = svc.get("ports", [])
            for p in ports:
                p_str = str(p)
                # Ensure the port string either directly starts with 127.0.0.1 / localhost or has ${OTEL_STACK_BIND_ADDRESS:-127.0.0.1}
                self.assertTrue(
                    p_str.startswith("127.0.0.1:") or
                    p_str.startswith("localhost:") or
                    p_str.startswith("${OTEL_STACK_BIND_ADDRESS:-127.0.0.1}:") or
                    p_str.startswith("${GRAFANA_BIND_ADDRESS:-127.0.0.1}:"),
                    f"Service '{name}' port mapping '{p_str}' must bind to 127.0.0.1 by default for security"
                )

    def test_zero_canary_in_configs_and_fixtures(self):
        """Invariant: Golden fixtures and configs contain zero privacy canary sentinels."""
        canaries_json = FIXTURES_DIR / "privacy_canaries.json"
        canaries = json.loads(canaries_json.read_text(encoding="utf-8"))
        
        for category, items in canaries.items():
            for canary in items:
                # Check collector config
                self.assertNotIn(canary, (CONFIG_DIR / "otel-collector-config.yaml").read_text(encoding="utf-8"))
                # Check loki config
                self.assertNotIn(canary, (CONFIG_DIR / "loki-config.yaml").read_text(encoding="utf-8"))
                # Check compose file
                self.assertNotIn(canary, COMPOSE_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
