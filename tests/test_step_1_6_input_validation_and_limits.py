"""Unit and fuzz tests for Step 1.6: Input validation, limits, and CLI injection prevention (F-09, F-10, F-90)."""
import json
import pytest
from app import app
from validators import (
    validate_router_name,
    validate_host_or_ip,
    validate_target_ip,
    validate_interface_name,
    validate_vrf_name,
    validate_province,
    validate_age,
    validate_routers_list,
    sanitize_cli_arg,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("INITIAL_ADMIN_USER", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "InitialAdminPassword123!")
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1MB for fast 413 testing

    import auth
    auth.clear_all_rate_limits()
    auth._load_users()

    # Create or update admin
    u = auth.get_user("admin")
    if not u:
        auth.create_user("admin", "InitialAdminPassword123!", role="god")
    auth.update_user("admin", {"password": "InitialAdminPassword123!", "must_change_password": False, "is_active": True})

    with app.test_client() as c:
        yield c


def login_admin(client):
    import auth
    auth.clear_all_rate_limits()
    res = client.post("/login", json={"username": "admin", "password": "InitialAdminPassword123!"})
    assert res.status_code == 200
    me = client.get("/me").get_json()
    return me.get("csrf_token")


# ---------------------------------------------------------------------------
# Direct Validator Unit & Injection Tests
# ---------------------------------------------------------------------------
def test_sanitize_cli_arg_rejections():
    """Dangerous CLI delimiters and control characters must be rejected immediately."""
    dangerous = [
        "GE0/0/1\nundo shutdown",
        "GE0/0/1\r",
        "GE0/0/1; dis cur",
        "GE0/0/1 | display this",
        "GE0/0/1 & ping 1.1.1.1",
        "GE0/0/1$VAR",
        "GE0/0/1`id`",
        "GE0/0/1<redirect>",
        "GE0/0/1\\backslash",
        "GE0/0/1!bang",
        "GE0/0/1\"quote",
        "GE0/0/1'single",
        "GE0/0/1 with space",
        "",
        "   ",
    ]
    for d in dangerous:
        with pytest.raises(ValueError):
            sanitize_cli_arg(d)


def test_validate_interface_name():
    """Huawei interfaces must match valid pattern and be <= 64 chars."""
    valid = [
        "GE0/0/1",
        "GigabitEthernet0/0/1",
        "XGigabitEthernet0/0/1",
        "100GE1/0/1",
        "Eth-Trunk1",
        "Eth-Trunk1.100",
        "LoopBack0",
        "Vlanif100",
        "NULL0",
        "Serial1/0/0:0",
    ]
    for v in valid:
        assert validate_interface_name(v) == v

    invalid = [
        "GE0/0/1\nundo shutdown",
        "GE0/0/1; dis cur",
        "A" * 70,  # too long
        "GE 0/0/1",  # whitespace
        "interface/with/strange#chars",
    ]
    for inv in invalid:
        with pytest.raises(ValueError):
            validate_interface_name(inv)


def test_validate_router_name():
    """Router name must be <= 64 alphanumeric/dots/hyphens/underscores."""
    assert validate_router_name("TBZ_HW_NE40E-X8") == "TBZ_HW_NE40E-X8"
    assert validate_router_name("router.core-01") == "router.core-01"

    with pytest.raises(ValueError):
        validate_router_name("router; reboot")
    with pytest.raises(ValueError):
        validate_router_name("A" * 70)


def test_validate_host_or_ip():
    """Host or IP must be valid IPv4/IPv6 or RFC 1123 hostname."""
    assert validate_host_or_ip("10.10.10.1") == "10.10.10.1"
    assert validate_host_or_ip("2001:db8::1") == "2001:db8::1"
    assert validate_host_or_ip("router01.teh.net") == "router01.teh.net"

    invalid = [
        "999.999.999.999",
        "10.10.10.1\n",
        "10.10.10.1; whoami",
        "invalid..hostname",
        "A" * 70,
    ]
    for inv in invalid:
        with pytest.raises(ValueError):
            validate_host_or_ip(inv)


def test_validate_target_ip():
    """Target IP must be valid IP or CIDR."""
    assert validate_target_ip("192.168.1.1") == "192.168.1.1"
    assert validate_target_ip("192.168.1.0/24") == "192.168.1.0/24"

    invalid = [
        "192.168.1.1\nreboot",
        "192.168.1.1/35",  # invalid mask
        "not-an-ip",
    ]
    for inv in invalid:
        with pytest.raises(ValueError):
            validate_target_ip(inv)


def test_validate_vrf_name():
    """VRF name <= 31 chars alphanumeric and safe symbols."""
    assert validate_vrf_name("VPN_INTERNET") == "VPN_INTERNET"
    with pytest.raises(ValueError):
        validate_vrf_name("VPN; drop table")
    with pytest.raises(ValueError):
        validate_vrf_name("A" * 35)


def test_validate_province():
    """Province must be 2-6 uppercase ASCII letters."""
    assert validate_province("teh") == "TEH"
    assert validate_province("ISF") == "ISF"
    assert validate_province("TBZ") == "TBZ"

    with pytest.raises(ValueError):
        validate_province("T")  # too short
    with pytest.raises(ValueError):
        validate_province("TOOLONGPROV")  # too long
    with pytest.raises(ValueError):
        validate_province("TE1")  # numbers not allowed
    with pytest.raises(ValueError):
        validate_province("TE\n")


def test_validate_age():
    """Age value 1..3650 and unit hours/days."""
    assert validate_age(2, "days") == (2, "days")
    assert validate_age("12", "hours") == (12, "hours")

    with pytest.raises(ValueError):
        validate_age("abc", "days")
    with pytest.raises(ValueError):
        validate_age(0, "days")
    with pytest.raises(ValueError):
        validate_age(5000, "days")
    with pytest.raises(ValueError):
        validate_age(10, "weeks")


def test_validate_routers_list():
    """Routers list must have 1..2000 entries and valid hosts."""
    valid_list = [{"name": "R1", "host": "10.0.0.1"}, {"name": "R2", "ip": "10.0.0.2"}]
    clean = validate_routers_list(valid_list, max_items=2000)
    assert len(clean) == 2

    # Empty
    with pytest.raises(ValueError):
        validate_routers_list([])

    # Not a list
    with pytest.raises(ValueError):
        validate_routers_list("not a list")

    # Exceeds max items
    too_many = [{"name": f"R{i}", "host": "10.0.0.1"} for i in range(10)]
    with pytest.raises(ValueError):
        validate_routers_list(too_many, max_items=5)

    # Missing host/ip
    with pytest.raises(ValueError):
        validate_routers_list([{"name": "R1"}])

    # Host injection
    with pytest.raises(ValueError):
        validate_routers_list([{"name": "R1", "host": "10.0.0.1\nreboot"}])


# ---------------------------------------------------------------------------
# API Route Integration & Fuzzing Tests
# ---------------------------------------------------------------------------
def test_run_report_invalid_age_fuzz(client):
    """Payload with invalid age_value ('abc') returns 400 VALIDATION_ERROR."""
    csrf = login_admin(client)
    res = client.post(
        "/run-report",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "netuser",
            "password": "netpassword",
            "province": "TEH",
            "age_value": "abc",  # invalid
            "age_unit": "days",
            "routers": [{"name": "R1", "host": "10.1.1.1"}],
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "VALIDATION_ERROR"
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_run_report_invalid_province(client):
    """Payload with invalid province code returns 400."""
    csrf = login_admin(client)
    res = client.post(
        "/run-report",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "netuser",
            "password": "netpassword",
            "province": "INVALID123",
            "age_value": 2,
            "routers": [{"name": "R1", "host": "10.1.1.1"}],
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "VALIDATION_ERROR"


def test_run_manual_routers_list_exceeds_limit(client):
    """Payload with > 2000 routers returns 400."""
    csrf = login_admin(client)
    large_list = [{"name": f"R_{i}", "host": "10.0.0.1"} for i in range(2001)]
    res = client.post(
        "/run-manual",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "netuser",
            "password": "netpassword",
            "routers": large_list,
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "Too many routers" in data["message"]


def test_check_bgp_route_injection_rejected(client):
    """CLI injection in target_ip returns 400 VALIDATION_ERROR."""
    csrf = login_admin(client)
    res = client.post(
        "/check-bgp-route",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "netuser",
            "password": "netpassword",
            "target_ip": "10.0.0.1\nundo ip route-static",
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "VALIDATION_ERROR"


def test_show_originator_interfaces_vrf_injection_rejected(client):
    """CLI injection in VRF name returns 400 VALIDATION_ERROR."""
    csrf = login_admin(client)
    res = client.post(
        "/show-originator-interfaces",
        headers={"X-CSRF-Token": csrf},
        json={
            "username": "netuser",
            "password": "netpassword",
            "originator_ip": "10.10.10.1",
            "target_ip": "192.168.1.1",
            "vrf": "VPN_TEST; reboot",
        },
    )
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "VALIDATION_ERROR"


def test_payload_too_large_413(client):
    """Payload exceeding MAX_CONTENT_LENGTH returns 413 PAYLOAD_TOO_LARGE."""
    csrf = login_admin(client)
    # MAX_CONTENT_LENGTH was set to 1MB in fixture, so a 1.5MB body triggers 413
    huge_data = "x" * (1024 * 1024 + 100 * 1024)
    res = client.post(
        "/run-manual",
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
        data=json.dumps({"username": "user", "password": "pwd", "routers": [{"name": huge_data, "host": "10.0.0.1"}]}),
    )
    assert res.status_code == 413
    data = res.get_json()
    assert data["code"] == "PAYLOAD_TOO_LARGE"
    assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"
