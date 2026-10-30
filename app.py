"""Web-Dash Application Entrypoint.

Thin loader shim initializing the application via backend.app.create_app().
Maintains full backwards compatibility with WSGI runners, test suites, and legacy scripts.
"""
import os
import sys

# Ensure project root is in python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
    app.run(host=host, port=port, debug=debug, threaded=True)
