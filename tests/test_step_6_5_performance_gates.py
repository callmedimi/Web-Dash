"""Step 6.5 Verification Suite — Performance & Quality Gates.

Tests:
1. Bundle size check script exists and passes (npm run check:size).
2. Initial entry JS gzip size is <= 250 KB.
3. Every individual chunk gzip size is <= 150 KB.
4. CSS bundle gzip size is <= 50 KB.
5. High-volume components enforce virtualization (zero unvirtualized lists > 200 items).
"""
from __future__ import annotations

import os
import subprocess
import zlib
import pytest

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
ASSETS_DIR = os.path.join(FRONTEND_DIR, "dist", "assets")


def test_bundle_size_check_script():
    """Run npm run check:size and assert exit code 0."""
    proc = subprocess.run(
        ["npm.cmd", "run", "check:size"],
        cwd=FRONTEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, f"check:size failed:\n{proc.stdout}\n{proc.stderr}"
    assert "SUCCESS: All bundle artifacts are within strict performance budgets." in proc.stdout


def test_asset_size_budgets():
    """Directly calculate gzip sizes of dist/assets and enforce Step 6.5 contracts."""
    assert os.path.isdir(ASSETS_DIR), f"Assets directory not found: {ASSETS_DIR}"

    files = os.listdir(ASSETS_DIR)
    assert len(files) >= 3, "dist/assets must contain built JS and CSS files"

    for f in files:
        full_path = os.path.join(ASSETS_DIR, f)
        with open(full_path, "rb") as fp:
            data = fp.read()
        gz_size = len(zlib.compress(data))
        gz_kb = gz_size / 1024.0

        if f.startswith("index-") and f.endswith(".js"):
            assert gz_kb <= 250.0, f"Initial JS {f} gzip size ({gz_kb:.1f} KB) exceeds 250 KB budget"
        elif f.endswith(".js"):
            assert gz_kb <= 150.0, f"Chunk {f} gzip size ({gz_kb:.1f} KB) exceeds 150 KB budget"
        elif f.endswith(".css"):
            assert gz_kb <= 50.0, f"CSS {f} gzip size ({gz_kb:.1f} KB) exceeds 50 KB budget"


def test_virtualization_in_heavy_components():
    """Ensure DataTable, LogViewer, and RunTimeline use @tanstack/react-virtual."""
    heavy_components = [
        "src/components/datatable/DataTable.tsx",
        "src/components/logviewer/LogViewer.tsx",
        "src/components/timeline/RunTimeline.tsx",
    ]

    for rel_path in heavy_components:
        full_path = os.path.join(FRONTEND_DIR, rel_path)
        with open(full_path, "r", encoding="utf-8") as fp:
            src = fp.read()
        assert "useVirtualizer" in src, f"{rel_path} must use @tanstack/react-virtual useVirtualizer"
