"""Multi-Channel Enterprise Notifications Service (Automation Catalog Step 5.12).

Provides local and air-gap safe notifications:
- Webhook channel (Telegram / Slack / Eitaa / Bale intranet gateways via HTTP POST).
- Email channel (RFC 822 SMTP relay).
- Syslog channel (RFC 3164 / RFC 5424 syslog log delivery).
- Event triggers:
  * job_failed
  * change_awaiting_approval
  * license_expiring
  * device_flapping
  * compliance_regression
- In-memory event audit log and test dispatcher capture.
"""
from __future__ import annotations
import os
import json
import time
import socket
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

SUPPORTED_TRIGGERS = [
    "job_failed",
    "change_awaiting_approval",
    "license_expiring",
    "device_flapping",
    "compliance_regression",
]


class NotificationChannel:
    """Base interface for notification dispatch channels."""

    def send(self, notification: Dict[str, Any]) -> bool:
        raise NotImplementedError


class WebhookChannel(NotificationChannel):
    """Sends JSON webhook notifications to Slack, Telegram, Eitaa, or custom intranet gateway."""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.environ.get("NOTIFICATION_WEBHOOK_URL", "")

    def send(self, notification: Dict[str, Any]) -> bool:
        if not self.webhook_url:
            logger.debug("Webhook notification skipped: no URL configured")
            return False

        payload = {
            "title": notification["title"],
            "message": notification["message"],
            "severity": notification["severity"],
            "event_type": notification["event_type"],
            "timestamp": notification["timestamp"],
            "data": notification.get("data", {}),
            # Common gateway compatibility fields
            "text": f"[{notification['severity'].upper()}] {notification['title']}\n{notification['message']}",
        }

        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status in (200, 201, 202, 204)
        except Exception as exc:
            logger.warning("Failed to send webhook notification: %s", exc)
            return False


class EmailChannel(NotificationChannel):
    """Sends notification emails via local or intranet SMTP relay."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        from_addr: Optional[str] = None,
        to_addrs: Optional[List[str]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.smtp_host = smtp_host or os.environ.get("SMTP_HOST", "")
        self.smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", 25))
        self.from_addr = from_addr or os.environ.get("SMTP_FROM", "webdash@noc.corp.internal")
        recips = os.environ.get("SMTP_TO", "noc-alerts@corp.internal")
        self.to_addrs = to_addrs or [a.strip() for a in recips.split(",") if a.strip()]
        self.username = username or os.environ.get("SMTP_USER")
        self.password = password or os.environ.get("SMTP_PASSWORD")

    def send(self, notification: Dict[str, Any]) -> bool:
        if not self.smtp_host:
            logger.debug("Email notification skipped: SMTP_HOST not configured")
            return False

        subject = f"[Web-Dash {notification['severity'].upper()}] {notification['title']}"
        body = (
            f"Event Type: {notification['event_type']}\n"
            f"Severity: {notification['severity']}\n"
            f"Timestamp: {notification['timestamp']}\n\n"
            f"{notification['message']}\n\n"
            f"Details:\n{json.dumps(notification.get('data', {}), indent=2)}"
        )

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5) as server:
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            return True
        except Exception as exc:
            logger.warning("Failed to send email notification: %s", exc)
            return False


class SyslogChannel(NotificationChannel):
    """Emits notification messages to local/remote syslog facility via UDP or logger."""

    def __init__(self, syslog_host: Optional[str] = None, syslog_port: Optional[int] = None):
        self.syslog_host = syslog_host or os.environ.get("SYSLOG_HOST")
        self.syslog_port = syslog_port or int(os.environ.get("SYSLOG_PORT", 514))

    def send(self, notification: Dict[str, Any]) -> bool:
        msg = f"WEBDASH_EVENT type={notification['event_type']} severity={notification['severity']} title=\"{notification['title']}\" msg=\"{notification['message']}\""
        if self.syslog_host:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(msg.encode("utf-8"), (self.syslog_host, self.syslog_port))
                sock.close()
                return True
            except Exception as exc:
                logger.warning("Failed to send syslog message: %s", exc)
                return False
        else:
            # Fall back to logging
            logger.info("[SYSLOG EMISSION] %s", msg)
            return True


class NotificationService:
    """Central notification dispatcher coordinating multi-channel alerts and event triggers."""

    _history: List[Dict[str, Any]] = []
    _mock_dispatch_capture: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def enable_test_capture(cls) -> List[Dict[str, Any]]:
        """Enable in-memory capture of dispatched notifications for unit testing."""
        cls._mock_dispatch_capture = []
        return cls._mock_dispatch_capture

    @classmethod
    def disable_test_capture(cls) -> None:
        """Disable in-memory test capture."""
        cls._mock_dispatch_capture = None

    @classmethod
    def dispatch_notification(
        cls,
        event_type: str,
        title: str,
        message: str,
        severity: str = "info",
        data: Optional[Dict[str, Any]] = None,
        channels: Optional[List[str]] = None,
        custom_webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch notification across requested or default channels.
        Returns dispatch status and metadata.
        """
        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        notification = {
            "id": f"notif_{int(time.time() * 1000)}",
            "event_type": event_type,
            "title": title,
            "message": message,
            "severity": severity.lower(),
            "timestamp": now_iso,
            "data": data or {},
        }

        # Keep history buffer capped at 100 entries
        cls._history.append(notification)
        if len(cls._history) > 100:
            cls._history.pop(0)

        # Test capture mode
        if cls._mock_dispatch_capture is not None:
            cls._mock_dispatch_capture.append(notification)
            return {
                "status": "dispatched",
                "notification_id": notification["id"],
                "dispatched_channels": channels or ["webhook", "syslog"],
                "test_captured": True,
            }

        target_channels = channels or ["webhook", "email", "syslog"]
        dispatched: List[str] = []

        if "webhook" in target_channels:
            wh_url = custom_webhook_url or os.environ.get("NOTIFICATION_WEBHOOK_URL")
            if wh_url:
                wh = WebhookChannel(webhook_url=wh_url)
                if wh.send(notification):
                    dispatched.append("webhook")

        if "email" in target_channels:
            if os.environ.get("SMTP_HOST"):
                em = EmailChannel()
                if em.send(notification):
                    dispatched.append("email")

        if "syslog" in target_channels:
            sysl = SyslogChannel()
            if sysl.send(notification):
                dispatched.append("syslog")

        return {
            "status": "dispatched" if dispatched else "logged_only",
            "notification_id": notification["id"],
            "dispatched_channels": dispatched,
            "event_type": event_type,
        }

    # Helper Trigger Methods
    @classmethod
    def notify_job_failed(
        cls, job_id: str, job_type: str, error: str, user: str = "system"
    ) -> Dict[str, Any]:
        """Trigger alert when a background job fails."""
        return cls.dispatch_notification(
            event_type="job_failed",
            title=f"Job #{job_id} ({job_type}) FAILED",
            message=f"Job {job_id} submitted by {user} encountered a fatal error: {error}",
            severity="critical",
            data={"job_id": job_id, "job_type": job_type, "error": error, "user": user},
        )

    @classmethod
    def notify_change_awaiting_approval(
        cls, change_id: str, device_name: str, risk_level: str, approver_role: str = "admin"
    ) -> Dict[str, Any]:
        """Trigger alert when a change request is awaiting approval."""
        return cls.dispatch_notification(
            event_type="change_awaiting_approval",
            title=f"Change Request #{change_id} on {device_name} Awaiting Approval",
            message=f"A change request with risk level '{risk_level}' on {device_name} requires {approver_role} sign-off.",
            severity="warning",
            data={"change_id": change_id, "device_name": device_name, "risk_level": risk_level},
        )

    @classmethod
    def notify_license_expiring(
        cls, device_name: str, product: str, days_remaining: int
    ) -> Dict[str, Any]:
        """Trigger alert when a device license is nearing expiration."""
        sev = "critical" if days_remaining <= 7 else ("warning" if days_remaining <= 30 else "info")
        return cls.dispatch_notification(
            event_type="license_expiring",
            title=f"License Expiring on {device_name} ({days_remaining} days left)",
            message=f"Product {product} license on router {device_name} expires in {days_remaining} days. Renewal action required.",
            severity=sev,
            data={"device_name": device_name, "product": product, "days_remaining": days_remaining},
        )

    @classmethod
    def notify_device_flapping(
        cls, device_name: str, interface: str, flap_count: int
    ) -> Dict[str, Any]:
        """Trigger alert on flapping network interface."""
        return cls.dispatch_notification(
            event_type="device_flapping",
            title=f"Interface Flapping Detected on {device_name}",
            message=f"Interface {interface} flapped {flap_count} times in the last 15 minutes.",
            severity="warning",
            data={"device_name": device_name, "interface": interface, "flap_count": flap_count},
        )

    @classmethod
    def notify_compliance_regression(
        cls, device_name: str, failed_rules: List[str], province: str
    ) -> Dict[str, Any]:
        """Trigger alert on compliance check failure."""
        return cls.dispatch_notification(
            event_type="compliance_regression",
            title=f"Compliance Regression on {device_name} ({province})",
            message=f"Device {device_name} failed compliance rules: {', '.join(failed_rules)}.",
            severity="warning",
            data={"device_name": device_name, "failed_rules": failed_rules, "province": province},
        )

    @classmethod
    def get_recent_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent dispatched notifications."""
        return list(reversed(cls._history[-limit:]))
