import os
import json
import zipfile
import xml.etree.ElementTree as ET
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from netmiko import ConnectHandler
import paramiko
import re
import tempfile
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Callable

class LicenseRenewalProcessor:
    def __init__(self, routers_data: List[Dict], license_files_paths: List[str], network_creds: Dict, log_callback: Callable):
        self.routers_data = routers_data
        self.license_files_paths = license_files_paths
        self.network_creds = network_creds
        self.log = log_callback
        self.matched_routers = []
        self.unmatched_licenses = []
        self.report_rows = []
        self.lock = threading.Lock()
        self.settings = {
            'num_threads': 4,
            'conn_timeout': 20,
            'command_timeout': 60
        }

    def _clean_xml_content(self, text: str) -> str:
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\uFFFD]', '', text)
        text = re.sub(r'&(?!([a-zA-Z]+|#[0-9]+|#x[0-9a-fA-F]+);)', '&amp;', text)
        last_end = text.rfind('</LicFile>')
        if last_end != -1:
            text = text[:last_end + len('</LicFile>')]
        return text

    def parse_xml_file(self, file_path: str) -> Optional[str]:
        try:
            filename = os.path.basename(file_path)
            raw_bytes = None
            if '#' in file_path:
                zip_path, xml_path = file_path.split('#', 1)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    with zip_ref.open(xml_path) as xml_file:
                        raw_bytes = xml_file.read()
            else:
                with open(file_path, 'rb') as f:
                    raw_bytes = f.read()

            text = self._clean_xml_content(text=raw_bytes.decode('utf-8', errors='replace'))
            root = ET.fromstring(text)
            node_info = root.find('.//NodeInfo')
            if node_info is not None:
                esn_elem = node_info.find('ESN')
                if esn_elem is not None and esn_elem.text:
                    esn_clean = esn_elem.text.strip()
                    if esn_clean:
                        return esn_clean
            return None
        except Exception as e:
            self.log(f"Unexpected error parsing {os.path.basename(file_path)}: {e}", "error")
            return None

    def extract_zip_files(self, zip_path: str) -> List[str]:
        xml_files = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.filename.lower().endswith('.xml'):
                        xml_files.append(zip_path + '#' + file_info.filename)
        except Exception as e:
            self.log(f"Error extracting ZIP {zip_path}: {e}", "error")
        return xml_files

    def expand_license_files(self, file_paths: List[str]) -> List[str]:
        expanded = []
        for path in file_paths:
            if path.lower().endswith('.xml'):
                expanded.append(path)
            elif path.lower().endswith('.zip'):
                expanded.extend(self.extract_zip_files(path))
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for f in files:
                        full = os.path.join(root, f)
                        if f.lower().endswith('.xml'):
                            expanded.append(full)
                        elif f.lower().endswith('.zip'):
                            expanded.extend(self.extract_zip_files(full))
        return expanded

    def find_matching_router(self, esn: str) -> Optional[Dict]:
        if not esn:
            return None
        target = esn.strip().upper()
        # 1. Exact match
        for router in self.routers_data:
            r_esn = (router.get('esn') or '').strip().upper()
            r_lsr = (router.get('lsr_id') or '').strip().upper()
            r_name = (router.get('name') or '').strip().upper()
            r_ip = (router.get('ip') or '').strip().upper()
            if target in (r_esn, r_lsr, r_name, r_ip):
                return router

        # 2. Substring match
        for router in self.routers_data:
            r_esn = (router.get('esn') or '').strip().upper()
            r_lsr = (router.get('lsr_id') or '').strip().upper()
            r_name = (router.get('name') or '').strip().upper()
            if len(target) >= 6:
                if (r_esn and target in r_esn) or (r_name and target in r_name) or (r_lsr and target in r_lsr):
                    return router
                if (r_name and r_name in target) or (r_esn and r_esn in target):
                    return router
        return None

    def run_matching(self):
        self.log("Starting license to router matching process...")
        expanded_paths = self.expand_license_files(self.license_files_paths)
        for lic_path in expanded_paths:
            esn = self.parse_xml_file(lic_path)
            if esn:
                router = self.find_matching_router(esn)
                if router:
                    if not any(r['esn'] == esn for r in self.matched_routers):
                        self.matched_routers.append({
                            'router_name': router['name'],
                            'ip': router['ip'],
                            'esn': esn,
                            'license_file_path': lic_path
                        })
                        self.log(f"✅ Matched ESN {esn} to router {router['name']} ({router['ip']})")
                else:
                    self.unmatched_licenses.append(esn)
                    self.log(f"⚠️ ESN {esn} from license file not found in the provided router list.", "warn")
        self.log(f"Matching complete. Found {len(self.matched_routers)} matches.")
        return self.matched_routers, self.unmatched_licenses

    def _product_names_match(self, current_name: str, new_name: str) -> bool:
        if not current_name or not new_name: return False
        if current_name == 'Unknown' or new_name == 'Unknown': return False
        def normalize(name: str) -> str:
            return re.sub(r'[^a-z0-9]', '', name.lower().replace("huawei", "").replace("netengine", "ne")).strip()
        cur_norm = normalize(current_name)
        new_norm = normalize(new_name)
        if cur_norm == new_norm: return True
        if cur_norm in new_norm or new_norm in cur_norm:
            if len(cur_norm) >= 3 and len(new_norm) >= 3: return True
        return False

    def _product_versions_match(self, current_ver: str, new_ver: str) -> bool:
        if not current_ver or not new_ver: return False
        if current_ver == 'Unknown' or new_ver == 'Unknown': return False
        def normalize_ver(ver: str) -> str:
            return re.sub(r'[^a-z0-9]', '', ver.lower())
        cur_v = normalize_ver(current_ver)
        new_v = normalize_ver(new_ver)
        if cur_v == new_v: return True
        if cur_v in new_v or new_v in cur_v:
            if len(cur_v) >= 5 and len(new_v) >= 5: return True
        return False

    def get_license_status(self, conn) -> Optional[str]:
        try:
            return conn.send_command('display license')
        except Exception as e:
            self.log(f"Failed to run 'display license': {e}", "error")
            return None

    def _check_file_exists_on_router(self, conn, filename: str) -> bool:
        try:
            for base_path in ["cfcard:/", "/cfcard/", ""]:
                full_path = f"{base_path}{filename}"
                output = conn.send_command(f"dir {full_path}", read_timeout=10)
                if filename in output and ('bytes' in output or 'Directory of' in output):
                    return True
            return False
        except Exception as e:
            self.log(f"Warning checking file existence on router: {e}", "warn")
            return False

    def verify_license_file(self, conn, filename: str) -> Optional[str]:
        try:
            return conn.send_command(f'license verify {filename}')
        except Exception as e:
            self.log(f"Failed to run license verification command: {e}", "error")
            return None

    def activate_license(self, conn, filename: str) -> Tuple[bool, str]:
        full_output = ""
        try:
            self.log(f"🔄 Activating license: license active {filename}")
            conn.clear_buffer()
            cmd = f"license active {filename}"
            full_output = conn.send_command(
                cmd,
                expect_string=r'\[Y/N\]|\[y/n\]|>[ ]*$',
                read_timeout=30
            )

            if any(p in full_output for p in ["[Y/N]", "[y/n]", "Continue"]):
                self.log("⚠️ Interactive prompt detected. Responding 'Y'...")
                response = conn.send_command(
                    "Y",
                    expect_string=r'>[ ]*$',
                    read_timeout=60
                )
                full_output += "\n" + response

            lower_out = full_output.lower()
            success_conditions = (
                "succeeded in activating" in lower_out or
                "now activing the license.......done" in lower_out or
                ("done." in lower_out and "error" not in lower_out and "fail" not in lower_out)
            )
            return success_conditions, full_output
        except Exception as e:
            return False, full_output + f"\nEXCEPTION during activation: {e}"

    def parse_xml_license(self, license_content: str) -> Tuple[Dict[str, int], Dict[str, str], Dict[str, str]]:
        cleaned = self._clean_xml_content(license_content)
        features_norm = {}
        features_display = {}
        metadata = {
            'created_time': 'Unknown',
            'expired_date': 'Unknown',
            'product_name': 'Unknown',
            'product_version': 'Unknown'
        }
        try:
            root = ET.fromstring(cleaned)
            valid_dates = []
            key_info = root.find('.//KeyInfo')
            if key_info is not None:
                for key in key_info.findall('.//CapacityKey') + key_info.findall('.//FeatureKey'):
                    name = key.get('name')
                    val_elem = key.find('Value')
                    if name and val_elem is not None:
                        val_text = val_elem.text.strip()
                        valid_date = val_elem.attrib.get('validDate')
                        if valid_date:
                            valid_dates.append(valid_date)
                        features_display[name] = val_text
                        if val_text.isdigit():
                            features_norm[name] = int(val_text)
                        elif val_text.upper() == 'YES':
                            features_norm[name] = 1
                        elif val_text.upper() == 'NO':
                            features_norm[name] = 0
                        else:
                            features_norm[name] = 0

            sale_info = root.find('.//SaleInfo')
            if sale_info is not None:
                offering = sale_info.find('.//OfferingProduct')
                if offering is not None:
                    metadata['product_name'] = offering.get('name', 'Unknown')
                    metadata['product_version'] = offering.get('version', 'Unknown')
                for sale_item in sale_info.findall('.//SaleItem'):
                    val_elem = sale_item.find('Value')
                    if val_elem is not None and 'validDate' in val_elem.attrib:
                        valid_dates.append(val_elem.attrib['validDate'])

            if valid_dates:
                unique_dates = sorted(set(valid_dates))
                metadata['expired_date'] = unique_dates[-1]
            return features_norm, metadata, features_display
        except Exception as e:
            self.log(f"Error parsing XML license: {e}", "warn")
            return features_norm, metadata, features_display

    def parse_active_license_features(self, license_output: str) -> Tuple[Dict[str, int], Dict[str, str], Dict, Dict[str, str]]:
        normalized_features = {}
        display_values = {}
        license_info = {
            'created_time': 'Unknown',
            'expired_date': 'Unknown',
            'product_name': 'Unknown',
            'product_version': 'Unknown'
        }
        bundles = {}
        current_bundle = None
        in_data_section = False

        for line in license_output.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            lower_stripped = stripped.lower()
            if lower_stripped.startswith('created time'):
                parts = stripped.split(':', 1)
                if len(parts) == 2 and license_info['created_time'] == 'Unknown':
                    license_info['created_time'] = parts[1].strip()
            elif lower_stripped.startswith('expired date'):
                parts = stripped.split(':', 1)
                if len(parts) == 2 and license_info['expired_date'] == 'Unknown':
                    license_info['expired_date'] = parts[1].strip()
            elif lower_stripped.startswith('product name'):
                parts = stripped.split(':', 1)
                if len(parts) == 2 and license_info['product_name'] == 'Unknown':
                    license_info['product_name'] = parts[1].strip()
            elif lower_stripped.startswith('product version'):
                parts = stripped.split(':', 1)
                if len(parts) == 2 and license_info['product_version'] == 'Unknown':
                    license_info['product_version'] = parts[1].strip()

            if not in_data_section and 'Item name' in stripped and 'Value' in stripped:
                in_data_section = True
                continue
            if in_data_section and '(View)Resource License Command-line' in stripped:
                break
            if not in_data_section:
                continue
            if all(c in '-_' for c in stripped.replace(' ', '')):
                continue
            parts = [p.strip() for p in re.split(r'\s{2,}', line) if p.strip()]
            if len(parts) < 3:
                continue
            item_name = parts[0]
            item_type = parts[1]
            value_str = parts[2]
            clean_name = item_name.replace('-', '').replace('_', '')
            if len(item_name) < 8 or not clean_name.isalnum():
                continue
            leading_spaces = len(line) - len(line.lstrip(' '))
            if leading_spaces <= 3:
                current_bundle = item_name
                display_values[item_name] = value_str
                norm_val = int(value_str) if value_str.isdigit() else (1 if value_str.upper() == 'YES' else 0)
                normalized_features[item_name] = norm_val
                bundles[item_name] = {'bundle_value': norm_val, 'bundle_display': value_str, 'features': {}}
            elif leading_spaces >= 4:
                if current_bundle:
                    display_values[item_name] = value_str
                    norm_val = int(value_str) if value_str.isdigit() else (1 if value_str.upper() == 'YES' else 0)
                    normalized_features[item_name] = norm_val
                    bundles[current_bundle]['features'][item_name] = {'value': norm_val, 'display': value_str}

        return normalized_features, license_info, bundles, display_values

    def compare_license_features(self, new_features, active_features, new_license_info=None, current_license_info=None, current_bundles=None, current_display=None, new_display=None):
        if current_display is None: current_display = {}
        if new_display is None: new_display = {}
        if current_license_info is None: current_license_info = {}
        if new_license_info is None: new_license_info = {}

        all_ok = True
        cur_exp = current_license_info.get('expired_date', 'Unknown')
        new_exp = new_license_info.get('expired_date', 'Unknown')

        if new_exp.upper() == 'PERMANENT':
            self.log("✅ Expiry check: New license is PERMANENT.")
        elif cur_exp.upper() == 'PERMANENT':
            self.log("⚠️ Expiry check: Current license is already PERMANENT.", "warn")
        elif new_exp != 'Unknown' and cur_exp != 'Unknown' and new_exp > cur_exp:
            self.log(f"✅ Expiry check: New expiry ({new_exp}) > current ({cur_exp}).")
        else:
            self.log(f"⚠️ Expiry check: New expiry ({new_exp}) <= current ({cur_exp}).", "warn")

        cur_pn = current_license_info.get('product_name', 'Unknown')
        new_pn = new_license_info.get('product_name', 'Unknown')
        cur_pv = current_license_info.get('product_version', 'Unknown')
        new_pv = new_license_info.get('product_version', 'Unknown')

        if not self._product_names_match(cur_pn, new_pn) or not self._product_versions_match(cur_pv, new_pv):
            self.log(f"⚠️ Product info mismatch: Current='{cur_pn} {cur_pv}', New='{new_pn} {new_pv}'", "warn")
        else:
            self.log("✅ Product info matches.")

        for leaf, new_norm in new_features.items():
            cur_norm = active_features.get(leaf, 0)
            if new_norm < cur_norm:
                self.log(f"❌ Feature decrease for {leaf}: current={cur_norm}, new={new_norm}", "error")
                all_ok = False

        return all_ok, "Comparison completed."

    def _generate_renamed_license_path(self, router_name: str, esn: str, expiry_date: str) -> str:
        safe_router = re.sub(r'[^\w\-]', '_', router_name)
        safe_esn = re.sub(r'[^\w]', '', esn) if esn else 'UNKNOWN'
        safe_expiry = re.sub(r'[^\d\-]', '', expiry_date) if expiry_date else 'UNKNOWN'
        return f"{safe_router}_{safe_esn}_{safe_expiry}.xml"

    def _upload_via_sftp(self, router_ip: str, file_path: str, filename: str) -> bool:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=router_ip,
                username=self.network_creds['username'],
                password=self.network_creds['password'],
                timeout=self.settings['conn_timeout']
            )
            with ssh.open_sftp() as sftp:
                for remote in [f'cfcard:/{filename}', f'/cfcard/{filename}', filename]:
                    try:
                        sftp.put(file_path, remote)
                        ssh.close()
                        return True
                    except Exception:
                        continue
            ssh.close()
            return False
        except Exception as e:
            self.log(f"SFTP Upload Exception for {router_ip}: {e}", "error")
            return False

    def process_single_router(self, router_info: Dict):
        router_name = router_info['router_name']
        ip = router_info['ip']
        esn = router_info['esn']
        license_file_path = router_info['license_file_path']

        self.log(f"🔌 Starting renewal for {router_name} ({ip}) [ESN: {esn}]...")

        # 1. Read XML content
        try:
            if '#' in license_file_path:
                zip_path, xml_path = license_file_path.split('#', 1)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    with z.open(xml_path) as f:
                        xml_content = f.read().decode('utf-8', errors='replace')
            else:
                with open(license_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    xml_content = f.read()
        except Exception as e:
            self.log(f"❌ Read file failed for {router_name}: {e}", "error")
            return {'router_name': router_name, 'ip': ip, 'status': 'Failed', 'details': f'File read error: {e}'}

        new_features, new_license_info, new_display = self.parse_xml_license(xml_content)
        new_expiry = new_license_info.get('expired_date', 'Unknown')

        device = {
            'device_type': 'huawei',
            'host': ip,
            'username': self.network_creds['username'],
            'password': self.network_creds['password'],
            'timeout': self.settings['conn_timeout']
        }

        try:
            with ConnectHandler(**device) as conn:
                self.log(f"🔌 Connected via Netmiko to {router_name} ({ip}).")

                # Fetch current license status
                current_output = self.get_license_status(conn)
                if current_output:
                    current_features, current_info, current_bundles, current_display = self.parse_active_license_features(current_output)
                    current_expiry = current_info.get('expired_date', 'Unknown')
                else:
                    current_features, current_info, current_bundles, current_display = {}, {}, {}, {}
                    current_expiry = 'Unknown'

                # Compare
                self.compare_license_features(
                    new_features, current_features,
                    new_license_info, current_info,
                    current_bundles, current_display, new_display
                )

                # Remote filename
                new_filename = self._generate_renamed_license_path(router_name, esn, new_expiry)

                # File Upload
                temp_renamed_path = os.path.join(tempfile.gettempdir(), new_filename)
                try:
                    if '#' in license_file_path:
                        zip_path, xml_path = license_file_path.split('#', 1)
                        with zipfile.ZipFile(zip_path, 'r') as z:
                            with z.open(xml_path) as src, open(temp_renamed_path, 'wb') as dst:
                                dst.write(src.read())
                    else:
                        with open(license_file_path, 'rb') as src, open(temp_renamed_path, 'wb') as dst:
                            dst.write(src.read())

                    if self._upload_via_sftp(ip, temp_renamed_path, new_filename):
                        self.log(f"⬆️ Uploaded {new_filename} to {router_name}.")
                    else:
                        raise Exception("SFTP upload failed")
                finally:
                    if os.path.exists(temp_renamed_path):
                        try: os.unlink(temp_renamed_path)
                        except Exception: pass

                # Verify
                verify_out = self.verify_license_file(conn, new_filename)
                lower_verify = verify_out.lower() if verify_out else ""
                if not verify_out or not any(msg in lower_verify for msg in ["succeeded", "success", "verify ok"]):
                    self.log(f"⚠️ License verification notice on {router_name}: {verify_out}", "warn")
                else:
                    self.log(f"✅ License verified on {router_name}.")

                # Activate
                activation_success, activation_output = self.activate_license(conn, new_filename)
                if activation_success:
                    self.log(f"🎉 License activated successfully on {router_name}!", "success")
                    return {'router_name': router_name, 'ip': ip, 'status': 'Completed', 'details': 'Activated'}
                else:
                    self.log(f"❌ License activation FAILED on {router_name}: {activation_output}", "error")
                    return {'router_name': router_name, 'ip': ip, 'status': 'Failed', 'details': activation_output}

        except Exception as conn_err:
            self.log(f"❌ Processing failed for {router_name} ({ip}): {conn_err}", "error")
            return {'router_name': router_name, 'ip': ip, 'status': 'Failed', 'details': str(conn_err)}

    def run_renewal(self, selected_routers: List[Dict]):
        self.log(f"Starting license renewal process for {len(selected_routers)} router(s)...")
        with ThreadPoolExecutor(max_workers=self.settings['num_threads']) as executor:
            future_to_router = {executor.submit(self.process_single_router, r): r for r in selected_routers}
            for future in as_completed(future_to_router):
                router = future_to_router[future]
                try:
                    result = future.result()
                    with self.lock:
                        self.report_rows.append(result)
                except Exception as exc:
                    self.log(f"Exception processing {router['router_name']}: {exc}", "error")
                    with self.lock:
                        self.report_rows.append({"router_name": router['router_name'], "status": "Exception", "details": str(exc)})
        self.log("License renewal process finished.")
        return self.report_rows
