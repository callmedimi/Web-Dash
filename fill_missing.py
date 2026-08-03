#!/usr/bin/env python3
"""Fill empty columns in missing.csv by looking up code_sites through
a route/emad mapping CSV and searching the Zabbix router DB.

missing.csv columns:
    province, place, input_code_site, host_name, host_codesite,
    matched_interface_name, matched_interface_desc,
    eth_trunk_name, eth_trunk_desc, eth_trunk_codesite

Mapping CSV columns: input_code_site, emad
    - input_code_site is the common key between both files
    - emad contains the search keyword for Zabbix DB

Logic:
    1. Match input_code_site from missing.csv against the input_code_site
       column in the mapping CSV.
    2. From the matched row, get the paired emad value.
    3. Search zabbix_router_db.json using the emad value as keyword.
    4. Fill empty host/interface/eth-trunk columns with search results.
"""

import csv
import json
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
MISSING_CSV = os.path.join(HERE, "missing.csv")
MAPPING_CSV = os.path.join(HERE, "mapping.csv")
DB_PATH = os.path.join(HERE, "zabbix_router_db.json")
OUTPUT_CSV = os.path.join(HERE, "filled_missing.csv")


def load_mapping(path: str) -> dict[str, str]:
    """Read mapping CSV (input_code_site, emad). Returns input_code_site -> emad lookup."""
    mapping: dict[str, str] = {}
    if not os.path.isfile(path):
        print(f"Warning: mapping file not found: {path}", file=sys.stderr)
        return mapping
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return mapping
        code_col = next((c for c in reader.fieldnames if c.strip().lower().replace(" ", "_") == "input_code_site"), None)
        emad_col = next((c for c in reader.fieldnames if c.strip().lower() == "emad"), None)
        if not code_col or not emad_col:
            print(f"Error: mapping CSV must have columns 'input_code_site' and 'emad'. Got: {reader.fieldnames}",
                  file=sys.stderr)
            sys.exit(1)
        for row in reader:
            code_val = (row.get(code_col) or "").strip()
            emad_val = (row.get(emad_col) or "").strip()
            if code_val and emad_val:
                mapping[code_val.lower()] = emad_val
    return mapping


def load_db(path: str) -> dict:
    if not os.path.isfile(path):
        print(f"Error: DB not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_codesite(text: str) -> str:
    m = re.search(r"_([A-Za-z]{2}\d{4})$", text)
    if m:
        return m.group(1)
    m = re.search(r"(\w{2}\d{4})", text)
    if m:
        return m.group(1)
    return ""


def find_eth_trunk0(router: dict) -> dict | None:
    for iface in router.get("interface_items", []):
        name = iface.get("interface_name", "")
        if re.search(r"(?i)\bEth-Trunk0\b", name):
            return iface
    return None


def search_db(db: dict, keyword: str) -> list[dict]:
    term = keyword.lower()
    results = []
    for router in db.get("routers", []):
        matched = []
        for iface in router.get("interface_items", []):
            haystack = f"{iface.get('interface_name', '')} {iface.get('description', '')}"
            if term in haystack.lower():
                matched.append(iface)
        if not matched:
            continue
        hostname = router.get("host", "")
        host_codesite = extract_codesite(hostname)
        eth0 = find_eth_trunk0(router)
        for iface in matched:
            results.append({
                "host_name": hostname,
                "host_codesite": host_codesite,
                "matched_interface_name": iface.get("interface_name", ""),
                "matched_interface_desc": iface.get("description", ""),
                "eth_trunk_name": eth0.get("interface_name", "") if eth0 else "",
                "eth_trunk_desc": eth0.get("description", "") if eth0 else "",
                "eth_trunk_codesite": extract_codesite(eth0.get("description", "")) if eth0 else "",
            })
    return results


def main():
    if not os.path.isfile(MISSING_CSV):
        print(f"Error: {MISSING_CSV} not found", file=sys.stderr)
        sys.exit(1)

    mapping = load_mapping(MAPPING_CSV)
    db = load_db(DB_PATH)

    rows_out = []
    stats_found = 0
    stats_mapped = 0

    with open(MISSING_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("Error: empty missing.csv", file=sys.stderr)
            sys.exit(1)

        fn_lower = [c.strip().lower().replace(" ", "_") for c in reader.fieldnames]
        expected = {"province", "place", "input_code_site"}
        if not expected.issubset(fn_lower):
            print(f"Error: missing.csv must have province, place, input_code_site. Got: {reader.fieldnames}",
                  file=sys.stderr)
            sys.exit(1)

        province_key = reader.fieldnames[fn_lower.index("province")]
        place_key = reader.fieldnames[fn_lower.index("place")]
        code_key = reader.fieldnames[fn_lower.index("input_code_site")]

        for row in reader:
            province = (row.get(province_key) or "").strip()
            place = (row.get(place_key) or "").strip()
            code_site = (row.get(code_key) or "").strip()
            if not code_site:
                continue

            emad_val = mapping.get(code_site.lower())
            if emad_val:
                stats_mapped += 1
                matches = search_db(db, emad_val)
            else:
                matches = []

            if matches:
                for m in matches:
                    stats_found += 1
                    rows_out.append({
                        "province": province,
                        "place": place,
                        "input_code_site": code_site,
                        **m,
                    })
            else:
                rows_out.append({
                    "province": province,
                    "place": place,
                    "input_code_site": code_site,
                    "host_name": "",
                    "host_codesite": "",
                    "matched_interface_name": "",
                    "matched_interface_desc": "",
                    "eth_trunk_name": "",
                    "eth_trunk_desc": "",
                    "eth_trunk_codesite": "",
                })

    if not rows_out:
        print("No rows processed", file=sys.stderr)
        return

    fieldnames = [
        "province", "place", "input_code_site",
        "host_name", "host_codesite",
        "matched_interface_name", "matched_interface_desc",
        "eth_trunk_name", "eth_trunk_desc", "eth_trunk_codesite",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Wrote {len(rows_out)} row(s) to {OUTPUT_CSV}")
    print(f"  Mapped via mapping.csv: {stats_mapped}")
    print(f"  Found in DB: {stats_found}")
    print(f"  Empty results: {len(rows_out) - stats_found}")


if __name__ == "__main__":
    main()
