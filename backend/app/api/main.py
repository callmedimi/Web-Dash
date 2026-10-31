"""Main blueprint serving React SPA frontend from frontend/dist with cache headers and SPA fallback."""
import os
from flask import Blueprint, send_from_directory, render_template, request

main_bp = Blueprint("main", __name__)

DIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist")
)
FONTS_DIR = os.path.join(DIST_DIR, "fonts")
if not os.path.isdir(FONTS_DIR):
    FONTS_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "public", "fonts")
    )


@main_bp.route("/")
def index():
    """Serve the root SPA frontend index.html with no-cache headers."""
    index_file = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(index_file):
        resp = send_from_directory(DIST_DIR, "index.html")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp
    # Fallback to legacy template if frontend has not been compiled
    return render_template("index.html")


@main_bp.route("/assets/<path:filename>")
def serve_assets(filename: str):
    """Serve hashed frontend JS/CSS assets with long immutable cache headers."""
    assets_dir = os.path.join(DIST_DIR, "assets")
    resp = send_from_directory(assets_dir, filename)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@main_bp.route("/fonts/<path:filename>")
def serve_fonts(filename: str):
    """Serve local self-hosted WOFF2 fonts with immutable cache headers."""
    resp = send_from_directory(FONTS_DIR, filename)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@main_bp.route("/<path:path>")
def spa_fallback(path: str):
    """SPA fallback for client-side routes (e.g. /login, /change-password, /_ui)."""
    # 1. Direct file in dist (e.g. favicon.ico, manifest.json)
    target_file = os.path.join(DIST_DIR, path)
    if os.path.isfile(target_file):
        resp = send_from_directory(DIST_DIR, path)
        if path.startswith("assets/") or path.startswith("fonts/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

    # 2. Check for legacy template route if explicitly requested
    if path == "legacy":
        return render_template("index.html")

    # 3. For client routes, serve index.html if dist exists
    index_file = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(index_file):
        resp = send_from_directory(DIST_DIR, "index.html")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    return {"error": "Not Found", "code": "NOT_FOUND"}, 404
