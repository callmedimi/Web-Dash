"""API Tokens and OpenAPI Specification Blueprint (Step 5.14)."""
from flask import Blueprint, jsonify, request, session, render_template_string

from auth import login_required
from backend.app.api.common import get_json_payload
from backend.app.services.tokens import ApiTokenService
from backend.app.api.openapi_spec import OPENAPI_SPEC

tokens_bp = Blueprint("tokens_api", __name__)


SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Web-Dash API Documentation</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css" />
  <style>
    body { margin: 0; background-color: #fafafa; }
    .topbar { display: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function() {
      SwaggerUIBundle({
        url: "/api/v1/openapi.json",
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout"
      });
    };
  </script>
</body>
</html>
"""


@tokens_bp.route("/api/v1/openapi.json", methods=["GET"])
def get_openapi_spec():
    """Serve the public OpenAPI 3.0.3 specification."""
    return jsonify(OPENAPI_SPEC), 200


@tokens_bp.route("/api/v1/docs", methods=["GET"])
@tokens_bp.route("/docs", methods=["GET"])
def get_api_docs():
    """Serve interactive Swagger UI API documentation."""
    return render_template_string(SWAGGER_UI_HTML), 200


@tokens_bp.route("/api/v1/tokens", methods=["GET"])
@login_required
def list_api_tokens():
    """List issued API tokens for automation."""
    user = session.get("user", {})
    user_id = user.get("id")
    is_admin = user.get("role") in ("admin", "god")

    tokens = ApiTokenService.list_tokens(user_id=None if is_admin else user_id)
    return jsonify({"tokens": tokens, "count": len(tokens)}), 200


@tokens_bp.route("/api/v1/tokens", methods=["POST"])
@login_required
def create_api_token():
    """Issue a new scoped API token."""
    user = session.get("user", {})
    user_id = user.get("id")
    if not user_id:
        return jsonify({"error": "Authentication required", "code": "UNAUTHORIZED"}), 401

    payload = get_json_payload()
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Token name is required", "code": "VALIDATION_ERROR"}), 400

    scopes = payload.get("scopes") or ["*"]
    expires_in_days = payload.get("expires_in_days", 30)

    try:
        token_info, raw_secret = ApiTokenService.create_token(
            user_id=user_id,
            name=name,
            scopes=scopes,
            expires_in_days=expires_in_days,
        )
    except Exception as exc:
        return jsonify({"error": str(exc), "code": "CREATION_FAILED"}), 400

    return jsonify({
        "status": "created",
        "token": token_info,
        "token_secret": raw_secret,
        "warning": "Make sure to copy your API token now as you will not be able to see it again.",
    }), 201


@tokens_bp.route("/api/v1/tokens/<int:token_id>", methods=["DELETE"])
@login_required
def revoke_api_token(token_id: int):
    """Revoke an API token."""
    user = session.get("user", {})
    user_id = user.get("id")
    is_admin = user.get("role") in ("admin", "god")

    ok = ApiTokenService.revoke_token(
        token_id=token_id,
        user_id=None if is_admin else user_id,
    )
    if not ok:
        return jsonify({"error": "Token not found or already revoked", "code": "NOT_FOUND"}), 404

    return jsonify({"status": "revoked", "token_id": token_id}), 200
