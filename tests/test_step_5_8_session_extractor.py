"""Comprehensive tests for Phase 5 Step 5.8: SecureCRT Session Extractor."""
import io
import zipfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.models.user import User
from backend.app.models.device import Device
from backend.app.services.session_extractor import (
    sanitize_filename,
    derive_role_from_name,
    make_zip_entry_path,
    build_securecrt_ini,
    SessionExtractorService,
)
from backend.app.features.registry import feature_registry
from backend.app.features.base import FeatureContext
from backend.app import create_app
import backend.app.features  # noqa: F401


SAMPLE_SESSION_CSV = """
NE Name,NE IP Address,Subnet Path
TEH-AGG01,10.10.1.1,ROOT/IPBH/Tehran
TEH-PE01,10.10.1.2,ROOT/IPBH/Tehran
ISF-CORE01,10.20.1.1,ROOT/IPBH/Isfahan
SHZ-ACC01,10.30.1.1,ROOT/Access/Shiraz
"""

MALFORMED_CSV = """
Router_Hostname,Management_IP
TEH-AGG01,10.10.1.1
"""


@pytest.fixture
def test_db_session(tmp_path):
    """Provide a fresh SQLite test session."""
    db_file = tmp_path / "test_sessions.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Provide a Flask test client with test configuration and logged-in user."""
    db_file = tmp_path / "test_app_sessions.db"
    monkeypatch.setenv("WEBDASH_DB_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("WEBDASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBDASH_VAULT_KEY", "u1BvX_L7xQw_P7bY1fRk9Y1x_Z8wQ2tL9k_A1sD5fG0=")

    app = create_app({"TESTING": True})
    with app.app_context():
        from backend.app.db.session import get_db_session
        with get_db_session() as s:
            Base.metadata.create_all(bind=s.bind)
            admin = User(username="admin_sess", role="admin", password_hash="dummy_hash")
            s.add(admin)

            dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", enabled=True)
            dev2 = Device(name="ISF-PE01", mgmt_ip="10.20.1.1", role="PE", province="ISF", enabled=True)
            s.add_all([dev1, dev2])
            s.commit()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = {
                "username": "admin_sess",
                "role": "admin",
                "id": 1,
            }
        yield client


def test_sanitize_filename_and_path_generation():
    """Verify sanitization of illegal path characters and zip entry generation."""
    assert sanitize_filename('Router/01:test*name?"<bar>|') == 'Router_01_test_name___bar__'
    assert sanitize_filename("") == "unnamed"

    p1 = make_zip_entry_path("ROOT/IPBH/Tehran", "TEH-AGG01")
    assert p1 == "IPBH/Tehran/TEH-AGG01.ini"

    p2 = make_zip_entry_path("ROOT", "ISF-CORE01")
    assert p2 == "ISF-CORE01.ini"

    p3 = make_zip_entry_path("", "SHZ-PE01")
    assert p3 == "SHZ-PE01.ini"


def test_derive_role_from_name():
    """Verify network role derivation from router hostnames."""
    assert derive_role_from_name("TEH-AGG01") == "AGG"
    assert derive_role_from_name("TEH_AGG_02") == "AGG"
    assert derive_role_from_name("MHD-PE01") == "PE"
    assert derive_role_from_name("ISF-CORE-01") == "CORE"
    assert derive_role_from_name("TBZ-RR01") == "RR"
    assert derive_role_from_name("KRD-CE01") == "CE"
    assert derive_role_from_name("UNKNOWN-DEVICE") == "OTHER"


def test_securecrt_ini_content_and_security_audit():
    """Strict security audit: verify SSH2 parameters and confirm ZERO embedded passwords."""
    ini = build_securecrt_ini(ip_address="10.10.1.1", username="noc_admin", port=22)

    # 1. Essential SecureCRT settings
    assert 'S:"Hostname"=10.10.1.1' in ini
    assert 'S:"Protocol Name"=SSH2' in ini
    assert 'D:"[SSH2] Port"=00000016' in ini
    assert 'S:"Username"=noc_admin' in ini
    assert "\r\n" in ini  # CRLF compliance for Windows SecureCRT

    # 2. Strict Security Mandate: No embedded passwords, prompt on connect
    assert 'D:"Session Password Saved"=00000000' in ini
    assert 'S:"Password"' not in ini
    assert 'Password=' not in ini


def test_csv_parser_valid_and_malformed():
    """Verify CSV parsing, column alias handling, and error on missing mandatory columns."""
    # 1. Valid CSV
    routers, subnets, err = SessionExtractorService.parse_csv(SAMPLE_SESSION_CSV.encode("utf-8-sig"))
    assert err is None
    assert len(routers) == 4
    assert len(subnets) == 3

    assert routers[0]["name"] == "TEH-AGG01"
    assert routers[0]["ip"] == "10.10.1.1"
    assert routers[0]["subnet_path"] == "ROOT/IPBH/Tehran"
    assert routers[0]["province"] == "TEH"
    assert routers[0]["role"] == "AGG"

    # Subnets summary counts
    sub_dict = {s["path"]: s["count"] for s in subnets}
    assert sub_dict["ROOT/IPBH/Tehran"] == 2
    assert sub_dict["ROOT/IPBH/Isfahan"] == 1

    # 2. Malformed CSV (missing required headers)
    r_bad, s_bad, err_bad = SessionExtractorService.parse_csv(MALFORMED_CSV.encode("utf-8"))
    assert err_bad is not None
    assert "missing required columns" in err_bad
    assert len(r_bad) == 0


def test_hierarchy_presets():
    """Verify zip directory hierarchies generated across all 5 organizational presets."""
    routers = [
        {"name": "TEH-AGG01", "ip": "10.10.1.1", "subnet_path": "ROOT/IPBH/Tehran", "province": "TEH", "role": "AGG"},
        {"name": "ISF-PE01", "ip": "10.20.1.1", "subnet_path": "ROOT/IPBH/Isfahan", "province": "ISF", "role": "PE"},
    ]

    # 1. Preset: subnet_path
    zip_sub = SessionExtractorService.generate_zip(routers, preset="subnet_path")
    with zipfile.ZipFile(zip_sub) as zf:
        names = zf.namelist()
        assert "IPBH/Tehran/TEH-AGG01.ini" in names
        assert "IPBH/Isfahan/ISF-PE01.ini" in names

    # 2. Preset: province_role
    zip_pr = SessionExtractorService.generate_zip(routers, preset="province_role")
    with zipfile.ZipFile(zip_pr) as zf:
        names = zf.namelist()
        assert "TEH/AGG/TEH-AGG01.ini" in names
        assert "ISF/PE/ISF-PE01.ini" in names

    # 3. Preset: province
    zip_p = SessionExtractorService.generate_zip(routers, preset="province")
    with zipfile.ZipFile(zip_p) as zf:
        names = zf.namelist()
        assert "TEH/TEH-AGG01.ini" in names
        assert "ISF/ISF-PE01.ini" in names

    # 4. Preset: role
    zip_r = SessionExtractorService.generate_zip(routers, preset="role")
    with zipfile.ZipFile(zip_r) as zf:
        names = zf.namelist()
        assert "AGG/TEH-AGG01.ini" in names
        assert "PE/ISF-PE01.ini" in names

    # 5. Preset: flat
    zip_f = SessionExtractorService.generate_zip(routers, preset="flat")
    with zipfile.ZipFile(zip_f) as zf:
        names = zf.namelist()
        assert "TEH-AGG01.ini" in names
        assert "ISF-PE01.ini" in names


def test_extract_from_inventory(test_db_session):
    """Verify direct extraction from Device inventory table with province/role filters."""
    dev1 = Device(name="TEH-AGG01", mgmt_ip="10.10.1.1", role="AGG", province="TEH", enabled=True)
    dev2 = Device(name="TEH-PE01", mgmt_ip="10.10.1.2", role="PE", province="TEH", enabled=True)
    dev3 = Device(name="SHZ-CORE01", mgmt_ip="10.30.1.1", role="CORE", province="SHZ", enabled=True)
    test_db_session.add_all([dev1, dev2, dev3])
    test_db_session.commit()

    # 1. Extract all inventory devices
    all_routers, zip_buf = SessionExtractorService.extract_from_inventory(
        db_session=test_db_session,
        preset="province_role",
    )
    assert len(all_routers) == 3
    with zipfile.ZipFile(zip_buf) as zf:
        names = zf.namelist()
        assert "TEH/AGG/TEH-AGG01.ini" in names
        assert "TEH/PE/TEH-PE01.ini" in names
        assert "SHZ/CORE/SHZ-CORE01.ini" in names

    # 2. Extract with province filter
    teh_routers, zip_teh = SessionExtractorService.extract_from_inventory(
        db_session=test_db_session,
        filter_province="TEH",
        preset="role",
    )
    assert len(teh_routers) == 2
    with zipfile.ZipFile(zip_teh) as zf:
        names = zf.namelist()
        assert "AGG/TEH-AGG01.ini" in names
        assert "PE/TEH-PE01.ini" in names


def test_session_extractor_feature_run(test_db_session):
    """Verify SessionExtractorFeature execution via catalog registry."""
    dev = Device(name="KRD-PE01", mgmt_ip="10.40.1.1", role="PE", province="KRD", enabled=True)
    test_db_session.add(dev)
    test_db_session.commit()

    feature = feature_registry.get("session_extractor")
    assert feature is not None

    ctx = FeatureContext(
        db_session=test_db_session,
        params={
            "preset": "province_role",
            "province": "KRD",
            "username": "noc_operator",
        },
    )

    res = feature.run(ctx)
    assert res["status"] == "success"
    assert res["total_sessions"] == 1
    assert res["preset_used"] == "province_role"
    assert "PASS" in res["security_verdict"]
    assert res["zip_size_bytes"] > 0
    assert len(res["sample_entries"]) == 1
    assert res["sample_entries"][0]["entry_path"] == "KRD/PE/KRD-PE01.ini"


def test_sessions_rest_api_lifecycle(app_client):
    """Verify REST API endpoints: presets, parse, and generate ZIP."""
    # 1. Presets API
    presets_res = app_client.get("/api/v1/sessions/presets")
    assert presets_res.status_code == 200
    presets_data = presets_res.get_json()
    assert "presets" in presets_data
    assert len(presets_data["presets"]) == 5

    # 2. Parse CSV API
    parse_res = app_client.post(
        "/api/v1/sessions/parse",
        data={
            "file": (io.BytesIO(SAMPLE_SESSION_CSV.encode("utf-8")), "routers_export.csv")
        },
    )
    assert parse_res.status_code == 200
    parse_data = parse_res.get_json()
    assert parse_data["status"] == "success"
    assert parse_data["total_routers"] == 4
    sid = parse_data["sid"]

    # 3. Generate ZIP from parsed job ID
    gen_res = app_client.post(
        "/api/v1/sessions/generate",
        json={
            "sid": sid,
            "preset": "province_role",
            "username": "admin",
        },
    )
    assert gen_res.status_code == 200
    assert gen_res.content_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(gen_res.data)) as zf:
        names = zf.namelist()
        assert "TEH/AGG/TEH-AGG01.ini" in names
        assert "ISF/CORE/ISF-CORE01.ini" in names

    # 4. Generate ZIP directly from inventory
    inv_res = app_client.post(
        "/api/v1/sessions/generate",
        json={
            "from_inventory": True,
            "preset": "flat",
            "username": "noc",
        },
    )
    assert inv_res.status_code == 200
    assert inv_res.content_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(inv_res.data)) as zf:
        names = zf.namelist()
        assert "TEH-AGG01.ini" in names
        assert "ISF-PE01.ini" in names
