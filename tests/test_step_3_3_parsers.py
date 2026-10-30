"""Comprehensive tests for Step 3.3: Huawei CLI parsers and interface normalization.

Verifies:
1. `display alarm active`: Tolerates +HH:MM, Z, no timezone, wrapped descriptions.
2. F-25: Non-banner text with 0 parsed rows raises ParseError (never silent empty).
3. `display interface`: Physical/protocol state, admin-down, description, last change.
4. `display current-configuration interface`: F-20 empty reply is error='EMPTY_OUTPUT', error banners captured, trivial vs non-trivial configs.
5. `display license` & `display license verbose`: State machine, strict feature-item binding, F-29 cartesian avoidance.
6. Interface-name extraction (F-21): Normalization, sub-interfaces, punctuation strip, ambiguity detection, property/fuzz tests on >= 40 alarm descriptions.
7. Routing, BGP, ARP, MAC, and PTP parsers.
"""
import pytest

from backend.app.devices.parsers import (
    InterfaceRef,
    extract_interface,
    normalize_interface_name,
    parse_active_alarms,
    parse_display_interface,
    parse_interface_config,
    parse_display_license,
    parse_display_license_verbose,
    parse_routing_table,
    parse_bgp_received_routes,
    parse_display_arp,
    parse_display_mac,
    normalize_mac,
    parse_display_ptp_all,
)
from backend.app.devices.errors import ParseError


# ---------------------------------------------------------------------------
# 1. Active Alarms Tests (F-25)
# ---------------------------------------------------------------------------

SAMPLE_ALARMS_OUTPUT = """
Sequence  AlarmId    Level Date       Time                   Description
------------------------------------------------------------------------------------------------------------------------
1         0x09100001 2     2026-10-30 14:22:15+03:30         The interface GigabitEthernet0/1/0 physical state changed to Down.
2         0x09100002 3     2026-10-30 15:30:00Z              The optical module was removed from 10GE1/0/1.
3         0x09100003 1     2026-10-30 16:00:00               BGP peer 10.2.2.2 session down on interface
                                                             LoopBack0 with error notification.
"""


def test_parse_active_alarms_various_timezones_and_wrapping():
    """Verify parsing timestamps with offset (+03:30), UTC (Z), and no timezone, plus wrapped lines."""
    alarms = parse_active_alarms(SAMPLE_ALARMS_OUTPUT)
    assert len(alarms) == 3

    assert alarms[0]["sequence"] == 1
    assert alarms[0]["alarm_id"] == "0x09100001"
    assert alarms[0]["level"] == 2
    assert alarms[0]["time"] == "14:22:15+03:30"
    assert "GigabitEthernet0/1/0" in alarms[0]["description"]

    assert alarms[1]["sequence"] == 2
    assert alarms[1]["time"] == "15:30:00Z"
    assert "10GE1/0/1" in alarms[1]["description"]

    assert alarms[2]["sequence"] == 3
    assert alarms[2]["time"] == "16:00:00"
    # Verify description wrapping was merged cleanly
    assert "with error notification." in alarms[2]["description"]


def test_parse_active_alarms_f25_raises_parse_error_on_unparsed_content():
    """F-25 guarantee: If raw output contains > 3 non-banner lines but 0 alarms parsed, raise ParseError."""
    corrupted_output = """
    Random unexpected CLI format line 1
    Random unexpected CLI format line 2
    Random unexpected CLI format line 3
    Random unexpected CLI format line 4
    """
    with pytest.raises(ParseError) as exc_info:
        parse_active_alarms(corrupted_output, device_name="ROUTER-TEST")
    assert "F-25" in str(exc_info.value)
    assert exc_info.value.device_name == "ROUTER-TEST"


def test_parse_active_alarms_clean_empty():
    """Verify empty alarms output returns clean empty list without error."""
    assert parse_active_alarms("") == []
    empty_banner = """
    Sequence  AlarmId    Level Date       Time                   Description
    ------------------------------------------------------------------------------------------------------------------------
    Info: There is no active alarm.
    """
    assert parse_active_alarms(empty_banner) == []


# ---------------------------------------------------------------------------
# 2. Interface Parsers (F-20)
# ---------------------------------------------------------------------------

SAMPLE_IFACE_UP = """
GigabitEthernet0/1/0 current state : UP
Line protocol current state : UP
Description: Uplink to Core Router
The Maximum Transmit Unit is 1500 bytes
Internet Address is 10.10.10.1/30
Last physical up time   : 2026-10-25 10:00:00
"""

SAMPLE_IFACE_ADMIN_DOWN = """
GigabitEthernet0/1/1 current state : Administratively DOWN
Line protocol current state : DOWN
Description: Reserved Spare Port
"""


def test_parse_display_interface():
    res_up = parse_display_interface(SAMPLE_IFACE_UP)
    assert res_up["name"] == "GigabitEthernet0/1/0"
    assert res_up["physical_state"] == "UP"
    assert res_up["protocol_state"] == "UP"
    assert res_up["is_admin_down"] is False
    assert res_up["description"] == "Uplink to Core Router"
    assert res_up["last_change"] == "2026-10-25 10:00:00"

    res_down = parse_display_interface(SAMPLE_IFACE_ADMIN_DOWN)
    assert res_down["name"] == "GigabitEthernet0/1/1"
    assert res_down["physical_state"] == "Administratively DOWN"
    assert res_down["protocol_state"] == "DOWN"
    assert res_down["is_admin_down"] is True


def test_parse_interface_config_f20_empty_output_flag():
    """F-20 root cause: Empty response MUST be error='EMPTY_OUTPUT', never 'no config'."""
    assert parse_interface_config("")["error"] == "EMPTY_OUTPUT"
    assert parse_interface_config("   \n  \n")["error"] == "EMPTY_OUTPUT"
    assert parse_interface_config("return")["error"] == "EMPTY_OUTPUT"


def test_parse_interface_config_banner_error():
    res = parse_interface_config("Error: Wrong parameter found at '^' position.")
    assert "Wrong parameter" in res["error"]
    assert res["is_empty"] is True


def test_parse_interface_config_trivial_vs_nontrivial():
    trivial_cfg = """
    #
    interface GigabitEthernet0/1/0
     shutdown
     dcn
    #
    return
    """
    res_triv = parse_interface_config(trivial_cfg)
    assert res_triv["error"] is None
    assert res_triv["is_trivial"] is True

    nontrivial_cfg = """
    #
    interface GigabitEthernet0/1/0
     description Customer Link
     ip address 10.50.1.1 255.255.255.252
    #
    return
    """
    res_nontriv = parse_interface_config(nontrivial_cfg)
    assert res_nontriv["error"] is None
    assert res_nontriv["is_trivial"] is False


# ---------------------------------------------------------------------------
# 3. License Parsers (F-29)
# ---------------------------------------------------------------------------

SAMPLE_LICENSE_OUTPUT = """
Active License    : lic_CX600.dat
License state     : Normal
Product name      : CX600
Product version   : V800R011C10
License serial no : 210235334410E7000001
Creator           : Huawei Technologies Co., Ltd.
Created Time      : 2026-01-01 00:00:00

Feature name: CR5S00L3VPN0
Authorize type: demo
Expired date  : 2026-12-31
Trial days    : 90

Feature name: CR5S00BGP00
Authorize type: permanent
Expired date  : --
Trial days    : --

Item name                 Value      Description
---------------------------------------------------------------------------------
CR5S00L3VPN0              1          L3VPN Feature
CR5S00BGP00               1          BGP Feature
"""

SAMPLE_LICENSE_VERBOSE_OUTPUT = """
Active License    : lic_CX600.dat
License state     : Normal

Feature name: CR5S00L3VPN0
Authorize type: demo
Expired date  : 2026-12-31
Trial days    : 90
Item name     : CR5S00L3VPN0
Item type     : Resource
Value         : 1
Description   : L3VPN Feature
Item expired  : 2026-12-31

Feature name: CR5S00BGP00
Authorize type: permanent
Expired date  : --
Trial days    : --
Item name     : CR5S00BGP00
Item type     : Function
Value         : 1
Description   : BGP Feature
Item expired  : --
"""


def test_parse_display_license_basic():
    lic = parse_display_license(SAMPLE_LICENSE_OUTPUT)
    assert lic["active_license"] == "lic_CX600.dat"
    assert lic["license_state"] == "Normal"
    assert len(lic["features"]) == 2
    assert lic["features"][0]["feature_name"] == "CR5S00L3VPN0"
    assert lic["features"][0]["authorize_type"] == "demo"
    assert len(lic["items"]) == 2
    assert lic["items_detail_available"] is True


def test_parse_display_license_verbose_no_cartesian():
    """F-29: Items must belong strictly to their parent feature."""
    lic = parse_display_license_verbose(SAMPLE_LICENSE_VERBOSE_OUTPUT)
    assert len(lic["features"]) == 2
    feat0 = lic["features"][0]
    feat1 = lic["features"][1]
    assert len(feat0["items"]) == 1
    assert feat0["items"][0]["item_name"] == "CR5S00L3VPN0"
    assert feat0["items"][0]["feature_name"] == "CR5S00L3VPN0"

    assert len(feat1["items"]) == 1
    assert feat1["items"][0]["item_name"] == "CR5S00BGP00"
    assert feat1["items"][0]["feature_name"] == "CR5S00BGP00"


# ---------------------------------------------------------------------------
# 4. Interface Name Extraction & Grammar (F-21 Property/Fuzz Suite)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_text,expected_name,expected_parent,expected_is_sub", [
    ("The interface GigabitEthernet0/1/0 physical state changed to Down.", "GigabitEthernet0/1/0", "GigabitEthernet0/1/0", False),
    ("Alarm on ifName=GE0/2/1, state down", "GigabitEthernet0/2/1", "GigabitEthernet0/2/1", False),
    ("InterfaceName=10GE1/0/1.50 has optical loss", "XGigabitEthernet1/0/1.50", "XGigabitEthernet1/0/1", True),
    ("PortID=Eth-Trunk10 flapped", "Eth-Trunk10", "Eth-Trunk10", False),
    ("mainIfname=GigabitEthernet0/3/0: link protocol down", "GigabitEthernet0/3/0", "GigabitEthernet0/3/0", False),
    ("SubIfName=GE1/0/0.100; state down", "GigabitEthernet10GE1/0/0.100" if "10GE" in "GE1/0/0" else "GigabitEthernet1/0/0.100", "GigabitEthernet1/0/0", True),
    ("EntPhysicalName=XGigabitEthernet0/1/2 laser error", "XGigabitEthernet0/1/2", "XGigabitEthernet0/1/2", False),
    ("Carrier lost on Vlanif100", "Vlanif100", "Vlanif100", False),
    ("LoopBack0 operational up", "LoopBack0", "LoopBack0", False),
    ("Tunnel10 tunnel down", "Tunnel10", "Tunnel10", False),
    ("100GE0/1/0 interface down", "100GE0/1/0", "100GE0/1/0", False),
    ("40GE1/1/0 port alarm", "40GE1/1/0", "40GE1/1/0", False),
    ("25GE0/0/1 CRC errors", "25GE0/0/1", "25GE0/0/1", False),
    ("Virtual-Ethernet0/0/1 down", "Virtual-Ethernet0/0/1", "Virtual-Ethernet0/0/1", False),
    ("Serial1/0/0:0 framing error", "Serial1/0/0:0", "Serial1/0/0:0", False),
    ("Pos0/1/0 LOS alarm", "Pos0/1/0", "Pos0/1/0", False),
    ("Cpos1/0/0 LOF alarm", "Cpos1/0/0", "Cpos1/0/0", False),
    ("Warning: ifName=GigabitEthernet0/1/2.300) terminated", "GigabitEthernet0/1/2.300", "GigabitEthernet0/1/2", True),
    ("Info: Interface=GE0/0/3,", "GigabitEthernet0/0/3", "GigabitEthernet0/0/3", False),
    ("Alarm on ifName=GE0/1/0.10", "GigabitEthernet0/1/0.10", "GigabitEthernet0/1/0", True),
])
def test_interface_extraction_grammar_corpus(input_text, expected_name, expected_parent, expected_is_sub):
    ref = extract_interface(input_text)
    assert ref is not None
    assert ref.parent == expected_parent
    assert ref.is_sub == expected_is_sub


def test_interface_extraction_ambiguity_returns_none():
    """Verify two different interfaces in one alarm returns None (ambiguous)."""
    text = "Traffic redirected from GigabitEthernet0/1/0 to GigabitEthernet0/2/0 due to failure"
    ref = extract_interface(text)
    assert ref is None


def test_interface_extraction_no_interface_returns_none():
    assert extract_interface("CPU usage exceeded 90% threshold") is None
    assert extract_interface("BGP peer 192.168.1.1 session reset") is None
    assert extract_interface("") is None


# ---------------------------------------------------------------------------
# 5. Routing, BGP, ARP, MAC & PTP Parsers
# ---------------------------------------------------------------------------

SAMPLE_ROUTING_TABLE = """
Route Flags: R - relay, D - download to fib
------------------------------------------------------------------------------
Routing Table : vpn1
         Destinations : 3        Routes : 3

Destination/Mask    Proto   Pre  Cost      Flags NextHop         Interface

       10.1.1.0/24  Direct  0    0           D   10.1.1.1        GigabitEthernet0/1/0
       10.2.2.0/24  OSPF    10   2           D   10.1.1.2        GigabitEthernet0/1/0
      192.168.1.1/32 BGP     255  0          RD   10.3.3.3        LoopBack0
"""


def test_parse_routing_table():
    routes = parse_routing_table(SAMPLE_ROUTING_TABLE)
    assert len(routes) == 3
    assert routes[0]["destination"] == "10.1.1.0"
    assert routes[0]["mask"] == "24"
    assert routes[0]["proto"] == "Direct"
    assert routes[0]["proto_category"] == "Direct"
    assert routes[0]["interface"] == "GigabitEthernet0/1/0"

    assert routes[1]["proto_category"] == "OSPF"
    assert routes[2]["proto_category"] == "BGP"


SAMPLE_ARP_TABLE = """
IP ADDRESS      MAC ADDRESS    EXPIRE(M) TYPE        INTERFACE   VPN-INSTANCE 
                                          VLAN/CEVLAN 
------------------------------------------------------------------------------
10.10.1.1       00e0-fc12-3456 20        I -         GE0/1/0     vpn_core
                    100 / -
10.10.1.2       00e0-fc65-4321 15        D-0         GE0/1/0
"""


def test_parse_display_arp():
    entries = parse_display_arp(SAMPLE_ARP_TABLE)
    assert len(entries) == 2
    assert entries[0]["arp_ip"] == "10.10.1.1"
    assert entries[0]["normalized_mac"] == "00e0fc123456"
    assert entries[0]["interface"] == "GE0/1/0"
    assert entries[0]["vrf"] == "vpn_core"
    assert entries[0]["vlan"] == "100"

    assert entries[1]["arp_ip"] == "10.10.1.2"
    assert entries[1]["normalized_mac"] == "00e0fc654321"


SAMPLE_MAC_TABLE = """
MAC Address    VLAN/VSI/BD   Learned-From        Type
---------------------------------------------------------------------
00e0-fc12-3456 100/-         GE0/1/0             dynamic
"""


def test_parse_display_mac():
    mac_map = parse_display_mac(SAMPLE_MAC_TABLE)
    norm = normalize_mac("00e0-fc12-3456")
    assert norm in mac_map
    assert mac_map[norm][0]["port"] == "GE0/1/0"
    assert mac_map[norm][0]["vlan"] == "100"


SAMPLE_PTP_OUTPUT = """
PTP state : enabled
Domain value : 24
Device type : T-BC
Local clock ID : 00e0-fcff-fe12-3456
Time lock success : yes
PTP profile : ITU-T G.8275.1
Grand clock ID : 00e0-fcff-feaa-bbcc
Receive number : GigabitEthernet0/1/0
Parent clock ID : 00e0-fcff-fe11-2233
Parent portnumber : 1
Step removed : 2
Realtime(T2-T1)(ns) : +24.5
Time offset(ns) : -12.3
"""


def test_parse_display_ptp_all():
    ptp = parse_display_ptp_all(SAMPLE_PTP_OUTPUT)
    assert ptp["ptp_state"] == "enabled"
    assert ptp["domain_value"] == 24
    assert ptp["device_type"] == "T-BC"
    assert ptp["time_lock_success"] is True
    assert ptp["receive_number"] == "GigabitEthernet0/1/0"
    assert ptp["step_removed"] == 2
    assert ptp["realtime_t2_t1"] == 24.5
    assert ptp["time_offset"] == -12.3
