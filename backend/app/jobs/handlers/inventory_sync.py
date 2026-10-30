"""Inventory & Telemetry Sync Job Handler (Step 5.1)."""
from typing import Dict, Any, Optional

from backend.app.jobs.worker import TaskContext
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext


class InventorySyncHandler:
    """Job engine handler for automated inventory import and telemetry synchronization."""

    @staticmethod
    def run_task(ctx: TaskContext, session: Optional[Any] = None) -> Dict[str, Any]:
        params = ctx.params or {}
        feature = feature_registry.get("inventory_discovery")
        if not feature:
            raise RuntimeError("InventoryDiscoveryFeature not registered")

        f_ctx = FeatureContext(
            db_session=ctx.session,
            user_id=ctx.user_id,
            params=params,
            job_id=ctx.job_id,
            task_id=ctx.task_id,
            dry_run=params.get("dry_run", False),
        )

        return feature.run(f_ctx)
