"""Step 6.6 Verification Suite — Serving React SPA from Flask with Security & Cache Headers.

Tests:
1. GET / serves frontend/dist/index.html with no-cache headers.
2. Security headers are properly injected (CSP, X-Content-Type-Options, Referrer-Policy, X-Frame-Options).
3. Hashed assets under /assets/ are served with immutable long cache headers.
4. Self-hosted local fonts under /fonts/ are served with immutable cache headers.
5. SPA client routes (/login, /_ui, /change-password) fallback to index.html with 200 OK.
6. API routes (/healthz, /readyz, /api/v1/...) are not swallowed and continue functioning normally.
"""
from __future__ import annotations

import os
import pytest
from backend.app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "DATABASE_URL": "sqlite:///:memory:"})
    with app.test_client() as client:
        yield client


def test_root_serves_spa_index(client):
    """GET / serves frontend/dist/index.html with no-cache header."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "no-cache, no-store, must-revalidate"
    assert "<!doctype html>" in resp.text.lower() or "<html" in resp.text.lower()


def test_security_headers_injected(client):
    """Verify CSP, X-Content-Type-Options, Referrer-Policy, and X-Frame-Options."""
    resp = client.get("/")
    assert resp.status_code == 200

    csp = resp.headers.get("Content-Security-Policy")
    assert csp is not None, "Content-Security-Policy header must be present"
    assert "default-src 'self'" in csp
    assert "frame-src" in csp
    assert "connect-src 'self'" in csp

    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("Referrer-Policy") == "same-origin"
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_spa_client_routes_fallback(client):
    """Client routes like /login, /_ui, /change-password fallback to index.html with 200."""
    for path in ["/login", "/_ui", "/change-password"]:
        resp = client.get(path)
        assert resp.status_code == 200, f"Route {path} must serve index.html with 200"
        assert resp.headers.get("Cache-Control") == "no-cache, no-store, must-revalidate"
        assert "<!doctype html>" in resp.text.lower() or "<html" in resp.text.lower()


def test_static_assets_cache_headers(client):
    """Assets under /assets/ have immutable long cache headers."""
    dist_assets = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist", "assets")
    if os.path.isdir(dist_assets):
        files = os.listdir(dist_assets)
        if files:
            sample_asset = files[0]
            resp = client.get(f"/assets/{sample_asset}")
            assert resp.status_code == 200
            assert resp.headers.get("Cache-Control") == "public, max-age=31536000, immutable"


def test_font_assets_cache_headers(client):
    """Local WOFF2 fonts under /fonts/ are served with immutable cache headers."""
    resp = client.get("/fonts/vazirmatn.woff2")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "public, max-age=31536000, immutable"


def test_api_routes_not_swallowed(client):
    """Core API and probe routes must not be captured by SPA fallback."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

    resp = client.get("/readyz")
    assert resp.status_code in (200, 503)
    assert "read_only" in resp.json
