"""VRF & Routing Check Automation Catalog Feature (Step 5.5)."""
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.routing import VrfRoutingService


class VrfRoutingCheckFeature(BaseFeature):
    """Automation catalog feature for tracing VRF routes hop-by-hop and constructing path graph."""

    spec = FeatureSpec(
        name="VRF & Routing Check",
        feature_key="vrf_routing_check",
        risk="low",
        needs_ssh=True,
        needs_telemetry=False,
        read_only=True,
        inputs={
            "vrf": {"type": "string", "required": True, "description": "VRF / VPN-Instance name (e.g. MCCI_Internet)"},
            "target_ip": {"type": "string", "required": True, "description": "Target IPv4 address or CIDR prefix (e.g. <IP>)"},
            "ingress_device_id": {"type": "int", "required": False, "description": "Optional Ingress / Route Reflector device ID"},
        },
        outputs={
            "status": {"type": "string"},
            "hops": {"type": "list"},
            "path_graph": {"type": "object"},
            "summary": {"type": "object"},
        },
        device_commands=[
            "display bgp vpnv4 all routing-table peer ... received-routes ...",
            "display ip routing-table vpn-instance ...",
            "display current-configuration interface ...",
        ],
        failure_modes={
            "INVALID_VRF": "Invalid VRF name format",
            "INVALID_TARGET_IP": "Invalid target IP address",
            "ROUTE_NOT_FOUND": "No BGP or FIB route found for target",
            "DEVICE_UNREACHABLE": "Could not connect to router via SSH",
        },
        report_columns=[
            "hop_index",
            "role",
            "device_name",
            "device_ip",
            "protocol",
            "prefix",
            "nexthop",
            "interface",
            "status",
        ],
        permission_key="operator",
        description="Hop-by-hop VRF route tracing, originator PE translation, and topology path graph visualization.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        vrf = params.get("vrf", "")
        target_ip = params.get("target_ip", "")
        ingress_device_id = params.get("ingress_device_id")
        session_mock = params.get("_session_mock")

        if not vrf or not target_ip:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "MISSING_PARAMETERS",
                "message": "Both 'vrf' and 'target_ip' parameters are required.",
            }

        try:
            result = VrfRoutingService.trace_vrf_route(
                db_session=session,
                vrf=vrf,
                target_ip_or_prefix=target_ip,
                ingress_device_id=ingress_device_id,
                session_mock=session_mock,
            )
            return {
                "feature": self.spec.feature_key,
                **result,
            }
        except ValueError as exc:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "VALIDATION_FAILED",
                "message": str(exc),
            }
        except Exception as exc:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "EXECUTION_ERROR",
                "message": str(exc),
            }


# Register feature
feature_registry.register(VrfRoutingCheckFeature())
