"""Grafana integration client (Target Architecture §3 & Step 3.4).

Provides:
- Mode A: Deep links and embed URLs (d-solo iframes) with theme, kiosk, and time range.
- Health checks: GET /api/health for system readiness probes.
- Annotations: Optional write-back of job events (off by default via GRAFANA_ANNOTATE=false).
- Token security: Grafana token is NEVER passed or proxied to the user browser.
"""
import urllib.parse
from typing import Dict, Any, Optional, List
import requests
import settings


class GrafanaClient:
    """Client for Grafana links, embeds, and optional annotations."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 5.0,
        annotate_enabled: bool = False,
    ):
        self.base_url = (base_url or getattr(settings, "grafana_url", "http://localhost:3000")).rstrip("/")
        self.token = token
        self.timeout = timeout
        self.annotate_enabled = annotate_enabled

    def check_health(self) -> Dict[str, Any]:
        """Check Grafana server readiness via /api/health."""
        try:
            url = f"{self.base_url}/api/health"
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}

    def build_dashboard_url(
        self,
        dashboard_uid: str,
        t_from: str = "now-6h",
        t_to: str = "now",
        variables: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build a direct browser URL to open a Grafana dashboard."""
        query_params = {
            "from": t_from,
            "to": t_to,
        }
        if variables:
            for k, v in variables.items():
                var_key = k if k.startswith("var-") else f"var-{k}"
                query_params[var_key] = v

        qs = urllib.parse.urlencode(query_params)
        return f"{self.base_url}/d/{dashboard_uid}?{qs}"

    def build_embed_url(
        self,
        dashboard_uid: str,
        panel_id: int,
        t_from: str = "now-6h",
        t_to: str = "now",
        theme: str = "dark",
        kiosk: bool = True,
        variables: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Build an iframe embed URL (d-solo) for a single panel.
        Requires Grafana setting 'allow_embedding = true'.
        """
        query_params: Dict[str, Any] = {
            "panelId": panel_id,
            "from": t_from,
            "to": t_to,
            "theme": theme,
        }
        if kiosk:
            query_params["kiosk"] = "true"

        if variables:
            for k, v in variables.items():
                var_key = k if k.startswith("var-") else f"var-{k}"
                query_params[var_key] = v

        qs = urllib.parse.urlencode(query_params)
        return f"{self.base_url}/d-solo/{dashboard_uid}?{qs}"

    def create_annotation(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        time_ms: Optional[int] = None,
    ) -> bool:
        """Post a job event annotation to Grafana (requires editor token and annotate_enabled)."""
        if not self.annotate_enabled or not self.token:
            return False

        try:
            url = f"{self.base_url}/api/annotations"
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "tags": tags or ["webdash"],
            }
            if time_ms:
                payload["time"] = time_ms

            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return True
        except Exception:
            return False
