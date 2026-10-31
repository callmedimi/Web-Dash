"""Site ARP & MAC Address Lookup Feature (Phase 5 Step 5.7)."""
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.arp import SiteArpService


class SiteArpLookupFeature(BaseFeature):
    """Automation catalog feature for cross-referencing Site Code, IP, MAC address and associated ports."""

    spec = FeatureSpec(
        name="Site ARP & MAC Lookup",
        feature_key="site_arp_lookup",
        risk="low",
        needs_ssh=False,
        needs_telemetry=False,
        read_only=True,
        inputs={
            "query": {"type": "string", "required": True, "description": "Site code (e.g. TEH-0392) or IP address (e.g. <IP>)"},
            "ttl_seconds": {"type": "int", "default": 300, "description": "Cache Time-To-Live in seconds"},
            "force_refresh": {"type": "bool", "default": False, "description": "Bypass TTL cache and query live tables"},
        },
        outputs={
            "status": {"type": "string"},
            "query": {"type": "string"},
            "count": {"type": "int"},
            "results": {"type": "list"},
            "macs": {"type": "list"},
            "freshness": {"type": "object"},
        },
        device_commands=[],
        failure_modes={
            "MISSING_QUERY": "Query parameter (Site Code or IP) is missing",
            "NOT_FOUND": "No matching ARP or MAC entries found",
        },
        report_columns=[
            "Site_Code",
            "IP",
            "Model",
            "NE",
            "NE_IP",
            "ARP_MAC",
            "Vlan",
            "VRF",
            "ARP_Interface",
            "MAC_Port",
            "collected_at",
        ],
        permission_key="operator",
        description="Cross-references Site Code to IP and MAC table, locating VLAN, VRF, interface, and upstream switch port.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        query = params.get("query") or params.get("site_code") or params.get("ip") or ""
        query = str(query).strip()

        if not query:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "MISSING_QUERY",
                "message": "Query parameter (Site Code or IP) is required.",
                "count": 0,
                "results": [],
            }

        ttl_seconds = int(params.get("ttl_seconds", 300))
        force_refresh = bool(params.get("force_refresh", False))

        res = SiteArpService.lookup(
            db_session=session,
            query=query,
            ttl_seconds=ttl_seconds,
            force_refresh=force_refresh,
        )

        if not res.get("success"):
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "NOT_FOUND",
                "message": res.get("error", "No records found."),
                "query": query,
                "count": 0,
                "results": [],
                "freshness": res.get("freshness", {}),
            }

        results = res.get("results", [])
        csv_data = SiteArpService.export_csv(results)

        return {
            "feature": self.spec.feature_key,
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results,
            "macs": res.get("macs", []),
            "freshness": res.get("freshness", {}),
            "csv_preview": csv_data[:500] if csv_data else "",
        }


# Register feature
site_arp_feature = SiteArpLookupFeature()
feature_registry.register(site_arp_feature)
