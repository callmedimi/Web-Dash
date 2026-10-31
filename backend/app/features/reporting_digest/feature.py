"""Reporting, Unified Exports & Daily NOC Digest Catalog Feature (Step 5.13)."""
from typing import Dict, Any, Optional

from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry
from backend.app.services.noc_digest import NocDigestService
from backend.app.services.export_service import UnifiedExportService


class ReportingDigestFeature(BaseFeature):
    """Catalog feature for generating scheduled daily NOC digests and streaming multi-format exports."""

    spec = FeatureSpec(
        name="Reporting & Daily NOC Digest",
        feature_key="reporting_digest",
        risk="low",
        needs_ssh=False,
        needs_telemetry=False,
        read_only=True,
        description="Aggregate daily NOC operations health across alarms, down links, licenses, jobs, and compliance with streaming multi-format exports.",
        permission_key="operator",
        inputs={
            "action": "generate_digest | export_digest | export_data",
            "hours": "Trailing window in hours (default: 24)",
            "format": "Export format: xlsx | csv | json (default: xlsx)",
            "data": "List of tabular records for generic export",
            "fieldnames": "Optional column names list for export",
            "filename": "Optional target filename for export",
        },
        outputs={
            "digest": "Structured NOC digest object",
            "export_size_bytes": "Size of generated export artifact",
            "filename": "Filename generated for download",
        },
    )

    def run(self, ctx: FeatureContext) -> Dict[str, Any]:
        """Execute NOC digest generation or data export."""
        params = ctx.params or {}
        action = params.get("action", "generate_digest")

        if action == "generate_digest":
            hours = int(params.get("hours", 24))
            digest = NocDigestService.generate_digest(
                db_session=ctx.db_session,
                hours=hours,
            )
            return {
                "status": "success",
                "action": "generate_digest",
                "digest": digest,
            }

        elif action == "export_digest":
            hours = int(params.get("hours", 24))
            fmt = str(params.get("format", "xlsx"))
            digest = NocDigestService.generate_digest(
                db_session=ctx.db_session,
                hours=hours,
            )
            raw_bytes, mimetype, filename = NocDigestService.export_digest(digest, format_type=fmt)
            return {
                "status": "success",
                "action": "export_digest",
                "format": fmt,
                "filename": filename,
                "mimetype": mimetype,
                "export_size_bytes": len(raw_bytes),
                "digest": digest,
            }

        elif action == "export_data":
            data = params.get("data") or []
            fieldnames = params.get("fieldnames")
            fmt = str(params.get("format", "csv")).lower()

            if fmt == "csv":
                raw_bytes = UnifiedExportService.export_csv(data, fieldnames=fieldnames)
                mimetype = "text/csv; charset=utf-8-sig"
                filename = params.get("filename", "export.csv")
            elif fmt == "xlsx":
                raw_bytes = UnifiedExportService.export_xlsx(data, default_title=params.get("filename", "Export"))
                mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                filename = params.get("filename", "export.xlsx")
            elif fmt == "json":
                raw_bytes = UnifiedExportService.export_json(data)
                mimetype = "application/json"
                filename = params.get("filename", "export.json")
            else:
                return {
                    "status": "error",
                    "error": "UNSUPPORTED_FORMAT",
                    "message": f"Unsupported export format '{fmt}'",
                }

            return {
                "status": "success",
                "action": "export_data",
                "format": fmt,
                "filename": filename,
                "mimetype": mimetype,
                "export_size_bytes": len(raw_bytes),
            }

        else:
            return {
                "status": "error",
                "error": "INVALID_ACTION",
                "message": f"Unknown action '{action}'",
            }


# Register feature with catalog registry
reporting_digest_feature = ReportingDigestFeature()
feature_registry.register(reporting_digest_feature)

