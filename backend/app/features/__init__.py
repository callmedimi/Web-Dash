"""Automation Catalog Features Package."""
from backend.app.features.base import BaseFeature, FeatureSpec, FeatureContext
from backend.app.features.registry import feature_registry, FeatureRegistry

# Import features to trigger registration
from backend.app.features.inventory.feature import InventoryDiscoveryFeature, inventory_feature
from backend.app.features.alarm_center.feature import AlarmCenterFeature, alarm_center_feature
from backend.app.features.down_links.feature import DownLinksFeature, down_links_feature

__all__ = [
    "BaseFeature",
    "FeatureSpec",
    "FeatureContext",
    "feature_registry",
    "FeatureRegistry",
    "InventoryDiscoveryFeature",
    "inventory_feature",
    "AlarmCenterFeature",
    "alarm_center_feature",
    "DownLinksFeature",
    "down_links_feature",
]


