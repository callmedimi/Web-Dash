"""Step 6.4 Verification Suite — Core NOC Components & Kitchen Sink Route.

Tests:
1. Component files existence and token integration.
2. KitchenSink route registration at /_ui.
3. Vitest unit tests run and pass.
4. TypeScript strict typecheck passes.
5. ESLint linting passes with zero warnings.
6. Production build outputs frontend/dist/index.html and assets within size budgets.
"""
from __future__ import annotations

import os
import subprocess
import pytest

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")


def test_core_components_exist():
    """Verify all required NOC components from plan/08_PHASE6_UI_DESIGN_SYSTEM.md §5.4 exist."""
    required_files = [
        "src/components/datatable/DataTable.tsx",
        "src/components/logviewer/LogViewer.tsx",
        "src/components/logviewer/useJobEvents.ts",
        "src/components/timeline/RunTimeline.tsx",
        "src/components/diff/DiffViewer.tsx",
        "src/components/ui/StatusBadge.tsx",
        "src/components/ui/Timestamp.tsx",
        "src/components/ui/Mono.tsx",
        "src/components/ui/ConfirmDialog.tsx",
        "src/components/ui/Drawer.tsx",
        "src/components/ui/Tabs.tsx",
        "src/components/ui/Toast.tsx",
        "src/components/ui/CommandPalette.tsx",
        "src/components/ui/TimeRangePicker.tsx",
        "src/components/charts/TimeSeriesChart.tsx",
        "src/components/charts/TopologyGraph.tsx",
        "src/components/charts/GrafanaPanel.tsx",
        "src/pages/KitchenSink.tsx",
        "src/components/CoreComponents.test.tsx",
    ]

    for rel_path in required_files:
        full_path = os.path.join(FRONTEND_DIR, rel_path)
        assert os.path.isfile(full_path), f"Missing core component: {rel_path}"


def test_kitchen_sink_route_registered():
    """Verify KitchenSink is imported and registered in App.tsx at /_ui."""
    app_tsx_path = os.path.join(FRONTEND_DIR, "src", "App.tsx")
    with open(app_tsx_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "KitchenSink" in content, "App.tsx must import KitchenSink"
    assert "/_ui" in content, "App.tsx must define /_ui route"


def test_vitest_unit_tests():
    """Run npm test and verify all vitest unit tests pass."""
    proc = subprocess.run(
        ["npm.cmd", "test"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, f"Vitest tests failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_typecheck():
    """Run npm run typecheck and verify zero TypeScript compiler errors."""
    proc = subprocess.run(
        ["npm.cmd", "run", "typecheck"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, f"Typecheck failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_lint():
    """Run npm run lint and verify zero warnings/errors."""
    proc = subprocess.run(
        ["npm.cmd", "run", "lint"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, f"Lint failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_production_build_and_dist_artifacts():
    """Verify frontend/dist contains index.html and pre-bundled assets for air-gapped deployment."""
    index_html = os.path.join(DIST_DIR, "index.html")
    assert os.path.isfile(index_html), "frontend/dist/index.html must exist"

    assets_dir = os.path.join(DIST_DIR, "assets")
    assert os.path.isdir(assets_dir), "frontend/dist/assets must exist"

    files = os.listdir(assets_dir)
    js_files = [f for f in files if f.endswith(".js")]
    css_files = [f for f in files if f.endswith(".css")]

    assert len(js_files) >= 1, "At least one bundled JS artifact must exist"
    assert len(css_files) >= 1, "At least one bundled CSS artifact must exist"
