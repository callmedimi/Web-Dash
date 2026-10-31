"""PTP & Telecom Sync Troubleshooting Feature (Phase 5 Step 5.6)."""
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.ptp import PtpTroubleshootService


class PtpTroubleshootFeature(BaseFeature):
    """Automation catalog feature for hop-by-hop PTP clock tree traceback and topology visualization."""

    spec = FeatureSpec(
        name="PTP & Telecom Sync Troubleshoot",
        feature_key="ptp_troubleshoot",
        risk="low",
        needs_ssh=True,
        needs_telemetry=False,
        read_only=True,
        inputs={
            "target": {"type": "string", "required": True, "description": "Target router name, IP, or Site Code (e.g. TEH-PE01)"},
            "max_hops": {"type": "int", "default": 5, "description": "Maximum upstream clock tree hops to trace"},
        },
        outputs={
            "status": {"type": "string"},
            "hop_count": {"type": "int"},
            "overall_status": {"type": "string"},
            "text_verdict": {"type": "string"},
            "topology_graph": {"type": "object"},
            "demarcation": {"type": "object"},
            "hop_chain": {"type": "list"},
        },
        device_commands=[
            "display ptp all",
            "display clock source",
            "display ptp interface ...",
            "display interface ... transceiver verbose",
            "display alarm active | include PTP",
            "display lldp neighbor brief",
        ],
        failure_modes={
            "TARGET_NOT_FOUND": "Could not resolve target device identifier",
            "SSH_FAILED": "Failed to connect to router via SSH",
        },
        report_columns=[
            "hop",
            "name",
            "host",
            "role",
            "status",
            "clock_class",
            "offset",
            "port",
        ],
        permission_key="operator",
        description="Hop-by-hop PTP clock tree traceback, ITU-T G.8275.1 standards check, visual topology graph, and automated team demarcation.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        target = params.get("target", "").strip()
        max_hops = int(params.get("max_hops", 5))
        session_mock = params.get("_session_mock")

        if not target:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "MISSING_TARGET",
                "message": "Parameter 'target' is required.",
            }

        try:
            result = PtpTroubleshootService.run_traceback(
                db_session=session,
                target_identifier=target,
                max_hops=max_hops,
                session_mock=session_mock,
            )
            return {
                "feature": self.spec.feature_key,
                "status": "success",
                **result,
            }
        except Exception as exc:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "EXECUTION_ERROR",
                "message": str(exc),
            }


# Register feature
feature_registry.register(PtpTroubleshootFeature())
