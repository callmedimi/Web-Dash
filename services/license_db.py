import json
import os
import threading
from datetime import datetime

_db_file = os.path.join(os.path.dirname(__file__), "license_renewals.json")
_db_lock = threading.Lock()

def _read_db():
    with _db_lock:
        if not os.path.exists(_db_file):
            return {"renewals": []}
        with open(_db_file, "r") as f:
            return json.load(f)

def _write_db(data):
    with _db_lock:
        with open(_db_file, "w") as f:
            json.dump(data, f, indent=4)

def add_renewal_report(report_id: str, report_data: list[dict], timestamp: str):
    db = _read_db()
    db["renewals"].append({
        "id": report_id,
        "timestamp": timestamp,
        "report_data": report_data
    })
    _write_db(db)

def get_all_renewal_reports():
    db = _read_db()
    return db["renewals"]

def get_renewal_report(report_id: str):
    db = _read_db()
    for report in db["renewals"]:
        if report["id"] == report_id:
            return report
    return None
