"""Unified settings module for Web-Dash (Step 1.7 - F-12).

Centralizes infrastructure configuration and device addresses.
Loads values from environment variables (first priority) or config.ini.
Fails fast with a clear RuntimeError if any required infra constant is missing.
"""
import configparser
import os
from typing import Tuple

from validators import validate_host_or_ip, validate_router_name


def _find_config_file() -> str | None:
    """Locate config.ini in environment or standard paths."""
    env_path = os.environ.get("CONFIG_FILE")
    if env_path and os.path.isfile(env_path):
        return os.path.abspath(env_path)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.getcwd(), "config.ini"),
        os.path.join(base_dir, "config.ini"),
        os.path.join(os.getcwd(), "config.example.ini"),
        os.path.join(base_dir, "config.example.ini"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


class Settings:
    """Infrastructure and application settings container."""

    def __init__(self, config_file: str | None = None):
        self.config = configparser.ConfigParser()
        self.config_path = config_file or _find_config_file()
        if self.config_path and os.path.isfile(self.config_path):
            self.config.read(self.config_path, encoding="utf-8")

        self.VRF_ROUTER_NAME: str = self._get_required(
            env_key="VRF_ROUTER_NAME",
            section="vrf",
            option="router_name",
            validator=validate_router_name,
            legacy_env="HARDCODED_ROUTER_NAME",
        )

        self.VRF_ROUTER_IP: str = self._get_required(
            env_key="VRF_ROUTER_IP",
            section="vrf",
            option="router_ip",
            validator=validate_host_or_ip,
            legacy_env="HARDCODED_ROUTER_IP",
        )

        self.VRF_RR_IP: str = self._get_required(
            env_key="VRF_RR_IP",
            section="vrf",
            option="rr_ip",
            validator=validate_host_or_ip,
            legacy_env="HARDCODED_RR_IP",
        )

        raw_prefixes = self._get_optional(
            env_key="TARGET_NE_PREFIXES",
            section="site_arp",
            option="target_ne_prefixes",
            default="IL,BR,BA,BC",
        )
        self.TARGET_NE_PREFIXES: Tuple[str, ...] = tuple(
            p.strip().upper() for p in raw_prefixes.split(",") if p.strip()
        )

        # Backwards compatibility aliases
        self.HARDCODED_ROUTER_NAME: str = self.VRF_ROUTER_NAME
        self.HARDCODED_ROUTER_IP: str = self.VRF_ROUTER_IP
        self.HARDCODED_RR_IP: str = self.VRF_RR_IP

    def _get_required(
        self,
        env_key: str,
        section: str,
        option: str,
        validator=None,
        legacy_env: str | None = None,
    ) -> str:
        val = os.environ.get(env_key)
        if not val and legacy_env:
            val = os.environ.get(legacy_env)

        if not val and self.config.has_section(section) and self.config.has_option(section, option):
            val = self.config.get(section, option).strip()

        if not val:
            raise RuntimeError(
                f"Missing required infrastructure setting: '{env_key}'. "
                f"Please set environment variable {env_key} or define [{section}] {option} in config.ini."
            )

        if validator:
            try:
                val = validator(val)
            except ValueError as e:
                raise RuntimeError(
                    f"Invalid configuration value for '{env_key}': {val}. Error: {e}"
                ) from e
        return val

    def _get_optional(
        self,
        env_key: str,
        section: str,
        option: str,
        default: str = "",
    ) -> str:
        val = os.environ.get(env_key)
        if not val and self.config.has_section(section) and self.config.has_option(section, option):
            val = self.config.get(section, option).strip()
        return val if val else default


# Global module singleton
_settings = Settings()

VRF_ROUTER_NAME = _settings.VRF_ROUTER_NAME
VRF_ROUTER_IP = _settings.VRF_ROUTER_IP
VRF_RR_IP = _settings.VRF_RR_IP
TARGET_NE_PREFIXES = _settings.TARGET_NE_PREFIXES

# Backwards compatibility aliases
HARDCODED_ROUTER_NAME = VRF_ROUTER_NAME
HARDCODED_ROUTER_IP = VRF_ROUTER_IP
HARDCODED_RR_IP = VRF_RR_IP


def is_read_only_mode() -> bool:
    """Check if system is in READ_ONLY_MODE (env var or config.ini)."""
    env_val = os.environ.get("READ_ONLY_MODE", "").strip().lower()
    if env_val in ("true", "1", "yes", "on"):
        return True
    if env_val in ("false", "0", "no", "off"):
        return False

    cfg_file = _find_config_file()
    if cfg_file and os.path.isfile(cfg_file):
        cp = configparser.ConfigParser()
        try:
            cp.read(cfg_file, encoding="utf-8")
            for sec in ("app", "security", "vrf"):
                if cp.has_section(sec) and cp.has_option(sec, "read_only_mode"):
                    return cp.get(sec, "read_only_mode").strip().lower() in ("true", "1", "yes", "on")
        except Exception:
            pass
    return False
