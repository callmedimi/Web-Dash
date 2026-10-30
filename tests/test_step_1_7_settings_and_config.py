"""Unit tests for Step 1.7: Move hardcoded infra constants to config (F-12)."""
import os
import re
import pytest
from settings import Settings


def test_settings_load_from_config(tmp_path):
    """Verify Settings loads from a valid config.ini."""
    ini_file = tmp_path / "custom_config.ini"
    ini_file.write_text(
        "[vrf]\n"
        "router_name = CORE_ROUTER_01\n"
        "router_ip = 10.50.0.1\n"
        "rr_ip = 10.50.0.2\n"
        "[site_arp]\n"
        "target_ne_prefixes = TEH,TBZ,ISF\n",
        encoding="utf-8",
    )
    s = Settings(config_file=str(ini_file))
    assert s.VRF_ROUTER_NAME == "CORE_ROUTER_01"
    assert s.VRF_ROUTER_IP == "10.50.0.1"
    assert s.VRF_RR_IP == "10.50.0.2"
    assert s.TARGET_NE_PREFIXES == ("TEH", "TBZ", "ISF")
    assert s.HARDCODED_ROUTER_NAME == "CORE_ROUTER_01"
    assert s.HARDCODED_ROUTER_IP == "10.50.0.1"
    assert s.HARDCODED_RR_IP == "10.50.0.2"


def test_settings_env_var_override(tmp_path, monkeypatch):
    """Verify environment variables take precedence over config.ini."""
    ini_file = tmp_path / "config.ini"
    ini_file.write_text(
        "[vrf]\n"
        "router_name = INI_ROUTER\n"
        "router_ip = 10.1.1.1\n"
        "rr_ip = 10.1.1.2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VRF_ROUTER_NAME", "ENV_ROUTER")
    monkeypatch.setenv("VRF_ROUTER_IP", "192.168.100.1")
    monkeypatch.setenv("VRF_RR_IP", "192.168.100.2")

    s = Settings(config_file=str(ini_file))
    assert s.VRF_ROUTER_NAME == "ENV_ROUTER"
    assert s.VRF_ROUTER_IP == "192.168.100.1"
    assert s.VRF_RR_IP == "192.168.100.2"


def test_settings_missing_required_fails_fast(tmp_path, monkeypatch):
    """Verify startup raises clear RuntimeError when required infra setting is missing."""
    empty_ini = tmp_path / "empty.ini"
    empty_ini.write_text("[vrf]\n", encoding="utf-8")
    monkeypatch.delenv("VRF_ROUTER_NAME", raising=False)
    monkeypatch.delenv("HARDCODED_ROUTER_NAME", raising=False)
    monkeypatch.delenv("VRF_ROUTER_IP", raising=False)
    monkeypatch.delenv("HARDCODED_ROUTER_IP", raising=False)
    monkeypatch.delenv("VRF_RR_IP", raising=False)
    monkeypatch.delenv("HARDCODED_RR_IP", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        Settings(config_file=str(empty_ini))
    assert "Missing required infrastructure setting" in str(exc_info.value)


def test_settings_invalid_ip_fails_fast(tmp_path, monkeypatch):
    """Verify startup raises RuntimeError when configured IP address is invalid."""
    bad_ini = tmp_path / "bad.ini"
    bad_ini.write_text(
        "[vrf]\n"
        "router_name = R1\n"
        "router_ip = 999.999.999.999\n"
        "rr_ip = 10.1.1.1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("VRF_ROUTER_IP", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        Settings(config_file=str(bad_ini))
    assert "Invalid configuration value for 'VRF_ROUTER_IP'" in str(exc_info.value)


def test_no_hardcoded_dotted_ips_in_non_test_python_code():
    """Verify zero hardcoded dotted IPs exist in any non-test .py file in the repository."""
    ip_regex = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
    )
    violations = []
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    for root, dirs, files in os.walk(root_dir):
        if any(p in root for p in (".git", "tests", "__pycache__", "node_modules", "venv", ".venv")):
            continue
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, root_dir)
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        ips = [ip for ip in ip_regex.findall(line) if ip not in ("0.0.0.0", "127.0.0.1")]
                        if ips:
                            violations.append(f"{rel_path}:{line_num} -> {ips}: {line.strip()}")

    assert not violations, f"Found hardcoded dotted IPs in production code:\n" + "\n".join(violations)
