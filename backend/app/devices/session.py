"""DeviceSession context manager and SSH lifecycle abstraction (Target Architecture §3 & Step 3.1).

Guarantees:
1. Connect retry discipline: max 2 retries (total 3 attempts) with backoff, ONLY on connect/auth timeouts.
2. Safety latch: NEVER retry after a configuration command was sent.
3. Socket leak prevention: disconnect() is ALWAYS called in finally, including between retries (F-28).
4. Auto-detect OS family (VRP5 vs VRP8) and select proper driver.
5. Error banner detection: rejects commands producing Huawei error banners.
6. Transcript sanitization: masks passwords/secrets before writing to disk (disabled by default).
"""
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from backend.app.devices.errors import (
    DeviceError,
    ConnectTimeout,
    AuthFailed,
    CommandTimeout,
    ConfigRejected,
    map_netmiko_exception,
)
from backend.app.devices.registry import default_registry, CommandRegistry
from backend.app.devices.drivers import get_driver, BaseVRPDriver
import settings

# Regex patterns for sanitizing sensitive credentials in transcripts
SECRET_REDACT_PATTERNS = [
    (re.compile(r'(password\s+(?:cipher|simple|irreversible-cipher)?\s+)(\S+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(secret\s+)(\S+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(key\s+cipher\s+)(\S+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(community\s+read\s+cipher\s+)(\S+)', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(community\s+write\s+cipher\s+)(\S+)', re.IGNORECASE), r'\1[REDACTED]'),
]


def redact_sensitive_cli(text: str) -> str:
    """Mask passwords and cryptographic keys in CLI output/commands."""
    if not text:
        return text
    result = text
    for pat, repl in SECRET_REDACT_PATTERNS:
        result = pat.sub(repl, result)
    return result


def parse_vrp_version(version_output: str) -> str:
    """Parse 'display version' output to determine VRP OS family (vrp5 vs vrp8)."""
    if not version_output:
        return "vrp8"
    upper = version_output.upper()
    if "VERSION 8." in upper or "VRP (R) SOFTWARE, VERSION 8" in upper or "VRP8" in upper:
        return "vrp8"
    if "VERSION 5." in upper or "VRP (R) SOFTWARE, VERSION 5" in upper or "VRP5" in upper:
        return "vrp5"
    return "vrp8"


class DeviceSession:
    """Robust context manager wrapping Netmiko connection with Huawei VRP drivers."""

    def __init__(
        self,
        device_name: str = "router",
        host: Optional[str] = None,
        username: str = "",
        password: str = "",
        ip: Optional[str] = None,
        os_family: str = "vrp8",
        port: int = 22,
        ssh_key: Optional[str] = None,
        jump_host: Optional[Dict[str, Any]] = None,
        conn_timeout: int = 15,
        auth_timeout: int = 15,
        banner_timeout: int = 15,
        read_timeout: int = 30,
        global_delay_factor: float = 1.0,
        retries: int = 2,
        retry_backoff: Optional[List[float]] = None,
        debug_transcript: bool = False,
        transcript_dir: Optional[str] = None,
        registry: Optional[CommandRegistry] = None,
        connect_factory: Optional[Callable[..., Any]] = None,
    ):
        self.device_name = device_name
        self.host = host or ip or "127.0.0.1"
        self.username = username
        self.password = password
        self.os_family = os_family.lower()
        self.port = port
        self.ssh_key = ssh_key
        self.jump_host = jump_host
        self.conn_timeout = conn_timeout
        self.auth_timeout = auth_timeout
        self.banner_timeout = banner_timeout
        self.read_timeout = read_timeout
        self.global_delay_factor = global_delay_factor
        self.retries = retries
        self.retry_backoff = retry_backoff if retry_backoff is not None else [3.0, 9.0]
        self.debug_transcript = debug_transcript
        data_dir = settings.get_data_dir() if hasattr(settings, "get_data_dir") else getattr(settings, "DATA_DIR", "./data")
        self.transcript_dir = transcript_dir or os.path.join(data_dir, "transcripts")
        self.registry = registry or default_registry
        self.connect_factory = connect_factory

        self.driver: BaseVRPDriver = get_driver(self.os_family)
        self.conn: Any = None
        self._connected: bool = False
        self._config_executed: bool = False
        self._disconnect_count: int = 0
        self._transcript: List[str] = []

    def __enter__(self) -> "DeviceSession":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    def _safe_disconnect(self) -> None:
        """Helper to disconnect active connection cleanly without throwing."""
        self._disconnect_count += 1
        if self.conn is not None:
            try:
                if hasattr(self.conn, "disconnect"):
                    self.conn.disconnect()
            except Exception:
                pass
            finally:
                self.conn = None
                self._connected = False

    def connect(self) -> "DeviceSession":
        """Connect to device with strict retry discipline and socket safety."""
        attempt = 0
        max_attempts = 1 + self.retries

        device_params = {
            "device_type": self.driver.netmiko_device_type,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "conn_timeout": self.conn_timeout,
            "auth_timeout": self.auth_timeout,
            "banner_timeout": self.banner_timeout,
            "global_delay_factor": self.global_delay_factor,
        }

        if self.ssh_key:
            device_params["use_keys"] = True
            device_params["key_file"] = self.ssh_key

        if self.jump_host and isinstance(self.jump_host, dict):
            if "ssh_config_file" in self.jump_host:
                device_params["ssh_config_file"] = self.jump_host["ssh_config_file"]

        while attempt < max_attempts:
            try:
                if self.connect_factory is not None:
                    self.conn = self.connect_factory(**device_params)
                else:
                    import netmiko
                    self.conn = netmiko.ConnectHandler(**device_params)

                self._connected = True
                self.driver.disable_paging(self.conn)
                return self

            except Exception as raw_exc:
                self._safe_disconnect()
                err = map_netmiko_exception(raw_exc, device_name=self.device_name)
                attempt += 1

                # Never retry if a config command was sent or if error is not retryable
                if self._config_executed or not isinstance(err, (ConnectTimeout, AuthFailed)):
                    raise err

                if attempt >= max_attempts:
                    raise err

                backoff_idx = min(attempt - 1, len(self.retry_backoff) - 1)
                delay = self.retry_backoff[backoff_idx] if self.retry_backoff else 0.0
                if delay > 0:
                    time.sleep(delay)

        return self

    def disconnect(self) -> None:
        """Disconnect session and flush redacted transcripts if enabled."""
        try:
            self._safe_disconnect()
        finally:
            if self.debug_transcript and self._transcript:
                self._flush_transcript()

    def _flush_transcript(self) -> None:
        """Write sanitized transcript to disk."""
        try:
            os.makedirs(self.transcript_dir, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.device_name}_{ts}.log"
            filepath = os.path.join(self.transcript_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Session Transcript for {self.device_name} ({self.host})\n")
                f.write(f"# Timestamp: {ts} UTC\n\n")
                f.write("\n".join(self._transcript))
        except Exception:
            pass

    def run(self, cmd_or_name: str, **vars: Any) -> str:
        """Execute a read command from registry or raw string."""
        if not self._connected or self.conn is None:
            raise DeviceError("Device session is not connected", device_name=self.device_name)

        if self.registry.has(cmd_or_name):
            cmd_obj = self.registry.get(cmd_or_name)
            cmd_str = cmd_obj.format(self.os_family, **vars)
            timeout = vars.get("read_timeout", cmd_obj.timeout)
        else:
            cmd_str = cmd_or_name.format(**vars) if vars else cmd_or_name
            timeout = vars.get("read_timeout", self.read_timeout)

        try:
            output = self.conn.send_command(cmd_str, read_timeout=timeout)
        except Exception as e:
            raise map_netmiko_exception(e, device_name=self.device_name)

        if self.debug_transcript:
            self._transcript.append(f"> {redact_sensitive_cli(cmd_str)}")
            self._transcript.append(redact_sensitive_cli(output))

        return output

    def config_block(self, lines: List[str], *, dry_run: bool = False) -> Dict[str, Any]:
        """Execute a configuration block in system-view with commit and error checking."""
        if not self._connected or self.conn is None:
            raise DeviceError("Device session is not connected", device_name=self.device_name)

        # Set safety latch: once config execution begins, NO reconnection/retry is allowed!
        self._config_executed = True

        if dry_run:
            return {
                "dry_run": True,
                "applied": False,
                "lines": lines,
                "results": [],
            }

        # 1. Enter system view
        try:
            self.driver.enter_system_view(self.conn)
        except Exception as e:
            raise map_netmiko_exception(e, device_name=self.device_name)

        results = []
        try:
            # 2. Execute each command line
            for line in lines:
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"):
                    continue

                out = self.conn.send_command(clean_line)
                err = self.driver.check_error(out)

                if self.debug_transcript:
                    self._transcript.append(f"[SYS]> {redact_sensitive_cli(clean_line)}")
                    self._transcript.append(redact_sensitive_cli(out))

                results.append({"command": clean_line, "output": out, "error": err})

                if err:
                    raise ConfigRejected(
                        f"Configuration command rejected by device: '{clean_line}' -> {err}",
                        command=clean_line,
                        error_banner=err,
                        device_name=self.device_name,
                    )

            # 3. Commit if required (VRP8)
            commit_out = ""
            if self.driver.commit_required:
                commit_out = self.driver.commit(self.conn)
                if self.debug_transcript:
                    self._transcript.append("[SYS]> commit")
                    self._transcript.append(redact_sensitive_cli(commit_out))

        finally:
            # 4. Exit back to user view
            try:
                self.driver.exit_system_view(self.conn)
            except Exception:
                pass

        return {
            "dry_run": False,
            "applied": True,
            "lines": lines,
            "results": results,
            "commit_output": commit_out if self.driver.commit_required else None,
        }

    def detect_os_family(self) -> str:
        """Probe device via 'display version' and dynamically update driver."""
        ver_output = self.run("display_version")
        family = parse_vrp_version(ver_output)
        if family != self.os_family:
            self.os_family = family
            self.driver = get_driver(family)
        return family
