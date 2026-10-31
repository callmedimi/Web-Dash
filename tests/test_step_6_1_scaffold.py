"""Unit tests for Step 6.1: Frontend Scaffold (Vite + TS + Tailwind + Design Tokens)."""
import os
import json
import gzip
import pytest

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))


def test_package_json_scripts_and_dependencies():
    """Verify package.json defines required scripts and dependencies."""
    pkg_path = os.path.join(FRONTEND_DIR, "package.json")
    assert os.path.isfile(pkg_path), "frontend/package.json must exist"

    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)

    scripts = pkg.get("scripts", {})
    for required in ("dev", "build", "typecheck", "lint", "test"):
        assert required in scripts, f"Script '{required}' missing in package.json"

    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "react" in deps
    assert "react-dom" in deps
    assert "typescript" in deps
    assert "vite" in deps
    assert "tailwindcss" in deps


def test_tsconfig_strict_and_path_alias():
    """Verify tsconfig.json has strict type checking and @/ alias."""
    ts_path = os.path.join(FRONTEND_DIR, "tsconfig.json")
    assert os.path.isfile(ts_path), "frontend/tsconfig.json must exist"

    with open(ts_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    compiler_opts = config.get("compilerOptions", {})
    assert compiler_opts.get("strict") is True, "strict must be true in tsconfig.json"
    assert "@/*" in compiler_opts.get("paths", {}), "path alias @/* must be configured"


def test_vite_config_proxy_and_alias():
    """Verify vite.config.ts proxies /api to port 5000 and maps @ alias."""
    vite_path = os.path.join(FRONTEND_DIR, "vite.config.ts")
    assert os.path.isfile(vite_path), "frontend/vite.config.ts must exist"

    with open(vite_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "/api" in content
    assert "http://localhost:5000" in content
    assert '"@"' in content or "'@'" in content


def test_design_tokens_css_contract():
    """Verify tokens.css contains all required semantic tokens from Phase 6 spec §3."""
    tokens_path = os.path.join(FRONTEND_DIR, "src", "styles", "tokens.css")
    assert os.path.isfile(tokens_path), "frontend/src/styles/tokens.css must exist"

    with open(tokens_path, "r", encoding="utf-8") as f:
        content = f.read()

    required_tokens = [
        "--bg",
        "--surface",
        "--surface-2",
        "--ink",
        "--ink-2",
        "--line",
        "--signal",
        "--ok",
        "--warn",
        "--fault",
        "--info-muted",
    ]
    for token in required_tokens:
        assert token in content, f"Token '{token}' missing from tokens.css"


def test_build_bundle_size_under_budget():
    """Verify build output exists and total initial JS is under 250 KB gzip."""
    dist_dir = os.path.join(FRONTEND_DIR, "dist")
    assert os.path.isdir(dist_dir), "frontend/dist must exist (run npm run build)"

    index_html = os.path.join(dist_dir, "index.html")
    assert os.path.isfile(index_html), "frontend/dist/index.html must exist"

    assets_dir = os.path.join(dist_dir, "assets")
    assert os.path.isdir(assets_dir), "frontend/dist/assets must exist"

    js_files = [f for f in os.listdir(assets_dir) if f.endswith(".js")]
    assert len(js_files) > 0, "No JS files found in dist/assets"

    # Initial JS entry point (index-*.js) budget: < 250 KB gzip
    initial_js = [f for f in js_files if f.startswith("index-")]
    assert len(initial_js) > 0, "No initial index-*.js found in dist/assets"

    initial_js_path = os.path.join(assets_dir, initial_js[0])
    with open(initial_js_path, "rb") as f:
        initial_gzip_size = len(gzip.compress(f.read()))

    max_budget_bytes = 250 * 1024
    assert initial_gzip_size < max_budget_bytes, (
        f"Initial JS bundle size {initial_gzip_size / 1024:.1f} KB exceeds 250 KB budget"
    )

    # Chunks budget: each lazy chunk < 150 KB gzip
    max_chunk_budget_bytes = 150 * 1024
    for js_file in js_files:
        if js_file == initial_js[0]:
            continue
        js_path = os.path.join(assets_dir, js_file)
        with open(js_path, "rb") as f:
            chunk_gzip = len(gzip.compress(f.read()))
        assert chunk_gzip < max_chunk_budget_bytes, (
            f"Chunk {js_file} size {chunk_gzip / 1024:.1f} KB exceeds 150 KB budget"
        )

