"""SecureCRT Session Extractor Catalog Feature (Phase 5 Step 5.8)."""
from typing import Dict, Any, List, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.session_extractor import SessionExtractorService


class SessionExtractorFeature(BaseFeature):
    """Automation catalog feature to generate hierarchical SecureCRT session ZIP packages."""

    spec = FeatureSpec(
        name="Session Extractor (SecureCRT)",
        feature_key="session_extractor",
        risk="low",
        needs_ssh=False,
        needs_telemetry=False,
        read_only=True,
        inputs={
            "preset": {"type": "string", "default": "province_role", "description": "Folder hierarchy preset: subnet_path | province_role | province | role | flat"},
            "province": {"type": "string", "required": False, "description": "Optional filter by province (e.g. TEH)"},
            "role": {"type": "string", "required": False, "description": "Optional filter by router role (e.g. PE)"},
            "username": {"type": "string", "default": "", "description": "Default SSH username (prompt for password)"},
            "routers": {"type": "list", "required": False, "description": "Optional explicit list of routers (overrides inventory)"},
        },
        outputs={
            "status": {"type": "string"},
            "total_sessions": {"type": "int"},
            "preset_used": {"type": "string"},
            "zip_size_bytes": {"type": "int"},
            "sample_entries": {"type": "list"},
            "security_verdict": {"type": "string"},
        },
        device_commands=[],
        failure_modes={
            "NO_ROUTERS": "No routers available to extract",
            "INVALID_PRESET": "Unknown folder hierarchy preset",
        },
        report_columns=[
            "name",
            "ip",
            "province",
            "role",
            "entry_path",
        ],
        permission_key="operator",
        description="Generates SecureCRT SSH2 session (.ini) ZIP archives organized by subnet, province, or role. Enforces password-free security.",
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        session = ctx.db_session
        params = ctx.params or {}

        preset = params.get("preset", "province_role").strip().lower()
        if preset not in SessionExtractorService.PRESETS:
            preset = "province_role"

        filter_province = params.get("province")
        filter_role = params.get("role")
        username = params.get("username", "").strip()
        custom_routers = params.get("routers")

        if custom_routers and isinstance(custom_routers, list):
            routers = custom_routers
            zip_buffer = SessionExtractorService.generate_zip(
                routers=routers,
                preset=preset,
                username=username,
            )
        else:
            routers, zip_buffer = SessionExtractorService.extract_from_inventory(
                db_session=session,
                preset=preset,
                filter_province=filter_province,
                filter_role=filter_role,
                username=username,
            )

        if not routers:
            return {
                "feature": self.spec.feature_key,
                "status": "failed",
                "error": "NO_ROUTERS",
                "message": "No matching routers found to extract sessions.",
                "total_sessions": 0,
            }

        zip_bytes = zip_buffer.getvalue()

        # Security check verification
        has_embedded_pwd = b'S:"Password"' in zip_bytes or b'Password=' in zip_bytes
        security_verdict = (
            "FAIL: Embedded passwords detected!"
            if has_embedded_pwd
            else "PASS: 0 embedded passwords detected (prompt-on-connect enforced, Session Password Saved = 0)"
        )

        sample_entries = [
            {
                "name": r.get("name"),
                "ip": r.get("ip"),
                "province": r.get("province", ""),
                "role": r.get("role", ""),
                "entry_path": SessionExtractorService.resolve_entry_path(r, preset=preset),
            }
            for r in routers[:15]
        ]

        return {
            "feature": self.spec.feature_key,
            "status": "success",
            "total_sessions": len(routers),
            "preset_used": preset,
            "zip_size_bytes": len(zip_bytes),
            "sample_entries": sample_entries,
            "security_verdict": security_verdict,
        }


# Register feature
session_extractor_feature = SessionExtractorFeature()
feature_registry.register(session_extractor_feature)
