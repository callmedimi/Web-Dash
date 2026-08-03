#!/usr/bin/env python3
"""Weekly Zabbix router DB refresh script.
Run via Windows Task Scheduler or cron:

    python refresh_zabbix_db.py [--group "Huawei BH Routers"] [--config zabbix_config.ini]

Output: zabbix_router_db.json in the same directory.
"""
import argparse
import json
import logging
import os
import sys
from services.zabbix_service import create_zabbix_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description="Refresh local Zabbix router database")
    parser.add_argument("--groups", nargs="+", default=None, help="Zabbix host group names (space-separated)")
    parser.add_argument("--config", default=os.path.join(HERE, "zabbix_config.ini"),
                        help="Zabbix INI config path")
    parser.add_argument("--output", default=os.path.join(HERE, "zabbix_router_db.json"),
                        help="Base output JSON file path (used as template, each group gets its own file)")
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Number of routers per batch (default: 10)")
    args = parser.parse_args()

    ini_path = args.config if os.path.isfile(args.config) else None
    svc = create_zabbix_service(ini_path=ini_path)

    # Default groups list if none provided
    default_groups = [
        "Huawei BH Routers",
        "Huawei CGNAT Eudemon",
        "Huawei CL Routers",
        "Huawei IG Routers",
        "Huawei IL Switches",
        "Huawei Internet Switches",
        "Huawei IP Routers",
        "IX F5 CGNAT",
        "Juniper Firewall"
    ]
    groups = args.groups if args.groups else default_groups

    for group_name in groups:
        logging.info("Refreshing router DB for group '%s' ...", group_name)
        summary = svc.refresh_router_db(group_name=group_name, db_path=args.output, batch_size=args.batch_size)
        logging.info(
            "Done: %d routers, %d interfaces, %d items -> %s",
            summary["total_routers"],
            summary["total_logical_interfaces"],
            summary["total_items"],
            args.output,
        )


if __name__ == "__main__":
    main()
