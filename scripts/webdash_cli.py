#!/usr/bin/env python3
"""Web-Dash Command Line Interface (webdash-cli) — Step 5.14.

Lightweight, dependency-free CLI wrapper for the Web-Dash Public REST API.
Enables cross-team automation, CI/CD pipelines, and script integration.

Usage:
  python webdash_cli.py [global options] <subcommand> [args]

Global Options:
  --url URL        Base URL of Web-Dash server (default: env WEBDASH_URL or http://127.0.0.1:5000)
  --token TOKEN    API Bearer token (default: env WEBDASH_TOKEN)
  --json           Output raw machine-readable JSON
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Any, List, Optional, Tuple


class WebDashCliError(Exception):
    """Base exception for CLI errors."""
    pass


class WebDashCliClient:
    """HTTP client communicating with Web-Dash REST API endpoints."""

    def __init__(self, base_url: str = "http://127.0.0.1:5000", token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token or os.environ.get("WEBDASH_TOKEN", "")

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        raw_response: bool = False,
    ) -> Tuple[int, Any]:
        """Execute HTTP request using Python standard library urllib."""
        url = f"{self.base_url}{path}"
        headers = {"User-Agent": "webdash-cli/2.0.0"}

        if self.token:
            headers["Authorization"] = f"Bearer {self.token.strip()}"

        data_bytes = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url=url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                body = resp.read()
                if raw_response:
                    return status, body
                try:
                    return status, json.loads(body.decode("utf-8"))
                except Exception:
                    return status, body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed_err = json.loads(err_body)
            except Exception:
                parsed_err = {"error": err_body}
            raise WebDashCliError(f"HTTP {exc.code}: {parsed_err.get('message') or parsed_err.get('error') or err_body}")
        except urllib.error.URLError as exc:
            raise WebDashCliError(f"Connection failed to {url}: {exc.reason}")

    def list_devices(self, province: Optional[str] = None, role: Optional[str] = None) -> List[Dict[str, Any]]:
        """List inventory devices."""
        params = {}
        if province:
            params["province"] = province
        if role:
            params["role"] = role
        query_str = f"?{urllib.parse.urlencode(params)}" if params else ""
        status, data = self._request("GET", f"/api/v1/devices{query_str}")
        if isinstance(data, dict):
            return data.get("devices", [])
        return data if isinstance(data, list) else []

    def start_job(
        self,
        job_type: str,
        mode: str = "apply",
        params: Optional[Dict[str, Any]] = None,
        devices: Optional[List[str]] = None,
    ) -> str:
        """Submit a network automation job."""
        payload = {
            "job_type": job_type,
            "mode": mode,
            "params": params or {},
        }
        if devices:
            payload["devices"] = devices
        status, data = self._request("POST", "/api/v1/jobs", payload=payload)
        job_id = data.get("job_id")
        if not job_id:
            raise WebDashCliError(f"Job creation did not return job_id: {data}")
        return job_id

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Fetch details and status of a submitted job."""
        status, data = self._request("GET", f"/api/v1/jobs/{job_id}")
        return data

    def wait_for_job(self, job_id: str, timeout: int = 60, poll_interval: float = 1.0) -> Dict[str, Any]:
        """Poll job until completion or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            info = self.get_job_status(job_id)
            st = info.get("status")
            if st in ("succeeded", "failed", "cancelled", "partial"):
                return info
            time.sleep(poll_interval)
        raise TimeoutError(f"Timed out after {timeout} seconds waiting for job {job_id}")

    def get_noc_digest(self, hours: int = 24) -> Dict[str, Any]:
        """Fetch daily NOC operations digest."""
        status, data = self._request("GET", f"/api/v1/reports/digest?hours={hours}")
        return data

    def download_digest(self, out_path: str, format_type: str = "xlsx", hours: int = 24) -> str:
        """Download daily NOC digest artifact to disk."""
        status, raw_bytes = self._request(
            "GET", f"/api/v1/reports/digest/export?format={format_type}&hours={hours}", raw_response=True
        )
        with open(out_path, "wb") as f:
            f.write(raw_bytes)
        return out_path


def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Format simple ASCII table."""
    col_widths = [len(h) for h in headers]
    for r in rows:
        for idx, val in enumerate(r):
            col_widths[idx] = max(col_widths[idx], len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    hdr_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    lines = [sep, hdr_line, sep]
    for r in rows:
        lines.append("| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(r)) + " |")
    lines.append(sep)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="webdash-cli",
        description="Web-Dash Automation Platform CLI",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("WEBDASH_URL", "http://127.0.0.1:5000"),
        help="Base server URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("WEBDASH_TOKEN", ""),
        help="API Bearer Token",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of tables",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: devices
    p_dev = subparsers.add_parser("devices", help="List network devices")
    p_dev.add_argument("--province", help="Filter by province")
    p_dev.add_argument("--role", help="Filter by device role (AGG, PE, RR)")

    # Subcommand: job-start
    p_start = subparsers.add_parser("job-start", help="Submit automation job")
    p_start.add_argument("job_type", help="Job type (e.g. config_backup, license_check, alarm_clear)")
    p_start.add_argument("--mode", default="apply", choices=["apply", "dry_run"])
    p_start.add_argument("--params", default="{}", help="JSON parameters")
    p_start.add_argument("--devices", nargs="*", help="Target device names")

    # Subcommand: job-status
    p_stat = subparsers.add_parser("job-status", help="Get job status")
    p_stat.add_argument("job_id", help="Job ID")

    # Subcommand: job-wait
    p_wait = subparsers.add_parser("job-wait", help="Wait for job to complete")
    p_wait.add_argument("job_id", help="Job ID")
    p_wait.add_argument("--timeout", type=int, default=60, help="Wait timeout in seconds")

    # Subcommand: digest
    p_dig = subparsers.add_parser("digest", help="Retrieve daily NOC digest")
    p_dig.add_argument("--hours", type=int, default=24, help="Window hours")
    p_dig.add_argument("--out", help="Save file to disk")
    p_dig.add_argument("--format", default="xlsx", choices=["xlsx", "csv", "json"])

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI Entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    client = WebDashCliClient(base_url=args.url, token=args.token)

    try:
        if args.subcommand == "devices":
            devices = client.list_devices(province=args.province, role=args.role)
            if args.json:
                print(json.dumps(devices, indent=2))
            else:
                headers = ["ID", "Name", "Management IP", "Role", "Province", "Health"]
                rows = [
                    [d.get("id"), d.get("name"), d.get("mgmt_ip"), d.get("role"), d.get("province"), d.get("health_status")]
                    for d in devices
                ]
                print(format_table(headers, rows))
            return 0

        elif args.subcommand == "job-start":
            params = json.loads(args.params)
            job_id = client.start_job(
                job_type=args.job_type,
                mode=args.mode,
                params=params,
                devices=args.devices,
            )
            if args.json:
                print(json.dumps({"job_id": job_id, "status": "submitted"}))
            else:
                print(f"Job successfully submitted: {job_id}")
            return 0

        elif args.subcommand == "job-status":
            info = client.get_job_status(args.job_id)
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                print(f"Job: {info.get('id')} | Type: {info.get('type')} | Status: {info.get('status')}")
            return 0

        elif args.subcommand == "job-wait":
            info = client.wait_for_job(args.job_id, timeout=args.timeout)
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                print(f"Job finished: {info.get('id')} with status {info.get('status')}")
            return 0 if info.get("status") == "succeeded" else 1

        elif args.subcommand == "digest":
            if args.out:
                client.download_digest(args.out, format_type=args.format, hours=args.hours)
                print(f"NOC digest saved to {args.out}")
            else:
                digest = client.get_noc_digest(hours=args.hours)
                if args.json:
                    print(json.dumps(digest, indent=2))
                else:
                    print(f"Daily NOC Digest — Status: {digest.get('status')}")
                    for h in digest.get("highlights", []):
                        print(f" - {h}")
            return 0

    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
