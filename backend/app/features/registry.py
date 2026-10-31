"""Automation Catalog Features Registry (Target Architecture §2 & Phase 5)."""
from typing import Dict, Any, List, Optional
import logging

from backend.app.features.base import BaseFeature, FeatureSpec

logger = logging.getLogger(__name__)


class FeatureRegistry:
    """Registry maintaining active automation features."""

    def __init__(self):
        self._features: Dict[str, BaseFeature] = {}

    def register(self, feature: BaseFeature) -> None:
        """Register a feature instance."""
        key = feature.spec.feature_key
        if key in self._features:
            logger.warning("Overwriting existing feature registration for '%s'", key)
        self._features[key] = feature
        logger.info("Registered automation feature: %s (%s)", feature.spec.name, key)

    def get(self, feature_key: str) -> Optional[BaseFeature]:
        """Retrieve a registered feature by key."""
        return self._features.get(feature_key)

    def list_features(self) -> List[Dict[str, Any]]:
        """Return list of serialized feature specifications."""
        return [f.spec.to_dict() for f in self._features.values()]


feature_registry = FeatureRegistry()
