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
    def __init__(self, routers_data: List[Dict], license_files_paths: List[str], network_creds: Dict, log_callback: Callable, confirm_callback: Optional[Callable] = None):
        self.routers_data = routers_data
        self.license_files_paths = license_files_paths
        self.network_creds = network_creds
        self.log = log_callback
        self.confirm_callback = confirm_callback
        self.matched_routers = []
        self.unmatched_licenses = []
        self.report_rows = []
        self.lock = threading.Lock()
        self.settings = {
            'num_threads': 4,
            'conn_timeout': 20,
            'command_timeout': 60,
            'report_dir': 'reports',
            'license_archive_dir': 'license_archive'
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

    def get_license_status(self, conn) -> Optional[Tuple[str, str]]:
        try:
            try:
                conn.send_command("screen-length 0 temporary", read_timeout=10)
            except Exception:
                pass
            disp_lic = conn.send_command('display license', read_timeout=self.settings['command_timeout'])
            disp_verb = conn.send_command('display license verbose | no-more', read_timeout=self.settings['command_timeout'])
            return disp_lic, disp_verb
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

    def parse_xml_license(self, license_content: str) -> Tuple[Dict[str, int], Dict[str, str], Dict[str, str], Dict[str, dict]]:
        cleaned = self._clean_xml_content(license_content)
        features_norm = {}
        features_display = {}
        features_detail = {}
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
                    val_elems = key.findall('Value')
                    if name and val_elems:
                        perm_v, trial_v = 0, 0
                        has_p, has_t = False, False
                        last_vdate = ''
                        last_tdays = ''
                        for val_elem in val_elems:
                            v_text = val_elem.text.strip() if val_elem.text else '0'
                            v_num = int(v_text) if v_text.isdigit() else (1 if v_text.upper() == 'YES' else 0)
                            v_date = val_elem.attrib.get('validDate', '')
                            t_days = val_elem.attrib.get('trialDays', '') or key.get('trialDays', '')
                            a_type = key.get('authorizeType', '') or key.get('type', '')

                            if v_date: 
                                valid_dates.append(v_date)
                                last_vdate = v_date
                            if t_days: last_tdays = t_days

                            is_p = v_date.upper() == 'PERMANENT' or 'PERMANENT' in a_type.upper()
                            is_t = bool(t_days and t_days != '0') or 'TRIAL' in a_type.upper() or 'DEMO' in a_type.upper() or (bool(v_date) and v_date.upper() != 'PERMANENT')

                            if is_p and not is_t:
                                perm_v += v_num
                                has_p = True
                            else:
                                trial_v += v_num
                                has_t = True

                        tot_v = perm_v + trial_v
                        features_display[name] = str(tot_v)
                        features_norm[name] = tot_v
                        features_detail[name] = {
                            'value': tot_v,
                            'perm_value': perm_v,
                            'trial_value': trial_v,
                            'display': str(tot_v),
                            'valid_date': last_vdate,
                            'trial_days': last_tdays,
                            'is_permanent': has_p,
                            'is_trial': has_t
                        }

            sale_info = root.find('.//SaleInfo')
            if sale_info is not None:
                offering = sale_info.find('.//OfferingProduct')
                if offering is not None:
                    metadata['product_name'] = offering.get('name', 'Unknown')
                    metadata['product_version'] = offering.get('version', 'Unknown')
                for sale_item in sale_info.findall('.//SaleItem'):
                    item_name = sale_item.get('name')
                    val_elems = sale_item.findall('Value')
                    if item_name and val_elems:
                        perm_v, trial_v = 0, 0
                        has_p, has_t = False, False
                        last_vdate = ''
                        last_tdays = ''
                        for val_elem in val_elems:
                            v_text = val_elem.text.strip() if val_elem.text else '1'
                            v_num = int(v_text) if v_text.isdigit() else (1 if v_text.upper() == 'YES' else 0)
                            v_date = val_elem.attrib.get('validDate', '')
                            t_days = val_elem.attrib.get('trialDays', '') or sale_item.get('trialDays', '')
                            a_type = sale_item.get('authorizeType', '') or sale_item.get('type', '')

                            if v_date: 
                                valid_dates.append(v_date)
                                last_vdate = v_date
                            if t_days: last_tdays = t_days

                            is_p = v_date.upper() == 'PERMANENT' or 'PERMANENT' in a_type.upper()
                            is_t = bool(t_days and t_days != '0') or 'TRIAL' in a_type.upper() or 'DEMO' in a_type.upper() or (bool(v_date) and v_date.upper() != 'PERMANENT')

                            if is_p and not is_t:
                                perm_v += v_num
                                has_p = True
                            else:
                                trial_v += v_num
                                has_t = True

                        tot_v = perm_v + trial_v
                        features_display[item_name] = str(tot_v)
                        features_norm[item_name] = tot_v
                        features_detail[item_name] = {
                            'value': tot_v,
                            'perm_value': perm_v,
                            'trial_value': trial_v,
                            'display': str(tot_v),
                            'valid_date': last_vdate,
                            'trial_days': last_tdays,
                            'is_permanent': has_p,
                            'is_trial': has_t
                        }

            if valid_dates:
                unique_dates = sorted(set(valid_dates))
                metadata['expired_date'] = unique_dates[-1]
            return features_norm, metadata, features_display, features_detail
        except Exception as e:
            self.log(f"Error parsing XML license: {e}", "warn")
            return features_norm, metadata, features_display, features_detail

    def parse_active_license_features(self, license_output: str, verbose_output: str = "") -> Tuple[Dict[str, int], Dict[str, str], Dict, Dict[str, str], Dict[str, dict]]:
        normalized_features = {}
        display_values = {}
        features_detail = {}
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
            norm_val = int(value_str) if value_str.isdigit() else (1 if value_str.upper() == 'YES' else 0)
            if leading_spaces <= 3:
                current_bundle = item_name
                display_values[item_name] = value_str
                normalized_features[item_name] = norm_val
                bundles[item_name] = {'bundle_value': norm_val, 'bundle_display': value_str, 'features': {}}
            elif leading_spaces >= 4:
                if current_bundle:
                    display_values[item_name] = value_str
                    normalized_features[item_name] = norm_val
                    bundles[current_bundle]['features'][item_name] = {'value': norm_val, 'display': value_str}

            features_detail[item_name] = {
                'value': norm_val,
                'display': value_str,
                'type': item_type,
                'is_trial': False,
                'is_permanent': license_info.get('expired_date', '').upper() == 'PERMANENT'
            }

        # If verbose output is available, parse detailed trial item information
        if verbose_output:
            current_feat_name = None
            current_feat_auth = ''
            current_feat_exp = ''
            current_feat_trial = ''
            current_item_dict = None

            for vline in verbose_output.split('\n'):
                vstr = vline.strip()
                if not vstr:
                    continue
                if vstr.startswith('Feature name'):
                    current_feat_name = vstr.split(':', 1)[1].strip() if ':' in vstr else ''
                    current_feat_auth = ''
                    current_feat_exp = ''
                    current_feat_trial = ''
                elif vstr.startswith('Authorize type'):
                    current_feat_auth = vstr.split(':', 1)[1].strip()
                elif vstr.startswith('Expired date') and not vstr.startswith('Item expired'):
                    current_feat_exp = vstr.split(':', 1)[1].strip()
                elif vstr.startswith('Trial days'):
                    current_feat_trial = vstr.split(':', 1)[1].strip()
                elif vstr.startswith('Sale name'):
                    current_item_dict = {
                        'sale_name': vstr.split(':', 1)[1].strip(),
                        'feature_name': current_feat_name,
                        'feature_auth': current_feat_auth,
                        'feature_exp': current_feat_exp,
                        'feature_trial': current_feat_trial
                    }
                elif vstr.startswith('Item name') and current_item_dict is not None:
                    iname = vstr.split(':', 1)[1].strip()
                    current_item_dict['item_name'] = iname
                elif vstr.startswith('Control value') and current_item_dict is not None:
                    cval = vstr.split(':', 1)[1].strip()
                    current_item_dict['control_value'] = cval
                elif vstr.startswith('Item expired date') and current_item_dict is not None:
                    exp_d = vstr.split(':', 1)[1].strip()
                    current_item_dict['item_expired_date'] = exp_d
                elif vstr.startswith('Item trial days') and current_item_dict is not None:
                    tdays = vstr.split(':', 1)[1].strip()
                    current_item_dict['item_trial_days'] = tdays
                    iname = current_item_dict.get('item_name')
                    if iname:
                        feat_name_upper = (current_feat_name or '').upper()
                        feat_exp = (current_feat_exp or '').upper()
                        feat_auth = (current_feat_auth or '').upper()
                        item_exp = (current_item_dict.get('item_expired_date', '')).upper()
                        
                        is_trial = (
                            'TRIAL' in feat_name_upper or 'DEMO' in feat_name_upper or
                            'TRIAL' in feat_auth or 'DEMO' in feat_auth or
                            (feat_exp != '' and feat_exp != 'PERMANENT') or
                            (item_exp != '' and item_exp != 'PERMANENT')
                        )
                        is_perm = (item_exp == 'PERMANENT' or feat_exp == 'PERMANENT' or 'PERMANENT' in feat_auth)

                        ctrl_val_str = current_item_dict.get('control_value', '0')
                        ctrl_num = int(ctrl_val_str) if ctrl_val_str.isdigit() else 1
                        
                        if iname in features_detail:
                            existing_p = features_detail[iname].get('perm_value', 0)
                            existing_t = features_detail[iname].get('trial_value', 0)
                            
                            features_detail[iname].update({
                                'item_trial_days': tdays,
                                'item_expired_date': current_item_dict.get('item_expired_date', ''),
                                'is_trial': is_trial or features_detail[iname].get('is_trial', False),
                                'is_permanent': is_perm or features_detail[iname].get('is_permanent', False),
                                'perm_value': existing_p + (ctrl_num if (is_perm and not is_trial) else 0),
                                'trial_value': existing_t + (ctrl_num if is_trial else 0)
                            })
                        else:
                            features_detail[iname] = {
                                'value': ctrl_num,
                                'display': ctrl_val_str,
                                'item_trial_days': tdays,
                                'item_expired_date': current_item_dict.get('item_expired_date', ''),
                                'is_trial': is_trial,
                                'is_permanent': is_perm,
                                'perm_value': ctrl_num if (is_perm and not is_trial) else 0,
                                'trial_value': ctrl_num if is_trial else 0
                            }

        return normalized_features, license_info, bundles, display_values, features_detail

    def _normalize_feature_name(self, name: str) -> str:
        if not name:
            return ""
        n = name.upper().strip()
        # Remove Huawei model/bundle prefixes (ANGS, ANK, ANG, CR8S, CR8, CR5, NE8, NE5, LANK, LANG, LANS, NE-, EV, LIC-, L)
        n = re.sub(r'^(ANGS|ANK|ANG|CR8S|CR8|CR5|NE8|NE5|LANK|LANG|LANS|NE-|EV|LIC-|L)', '', n)
        n = re.sub(r'[^A-Z0-9]', '', n)
        return n

    def _fuzzy_feature_match(self, feat_name: str, norm_features_map: Dict[str, int]) -> Optional[int]:
        if feat_name in norm_features_map:
            return norm_features_map[feat_name]
        norm_feat = self._normalize_feature_name(feat_name)
        if norm_feat in norm_features_map:
            return norm_features_map[norm_feat]
        
        # Substring / partial match fallback
        if len(norm_feat) >= 6:
            for k, val in norm_features_map.items():
                if norm_feat in k or k in norm_feat:
                    return val
        return None

    def compare_license_features(
        self,
        new_features: Dict[str, int],
        active_features: Dict[str, int],
        new_license_info: Dict = None,
        current_license_info: Dict = None,
        current_bundles: Dict = None,
        current_display: Dict[str, str] = None,
        new_display: Dict[str, str] = None,
        new_features_detail: Dict[str, dict] = None,
        current_features_detail: Dict[str, dict] = None
    ) -> Tuple[bool, List[str]]:
        if current_display is None: current_display = {}
        if new_display is None: new_display = {}
        if current_license_info is None: current_license_info = {}
        if new_license_info is None: new_license_info = {}
        if new_features_detail is None: new_features_detail = {}
        if current_features_detail is None: current_features_detail = {}

        issues = []
        cur_exp = current_license_info.get('expired_date', 'Unknown')
        new_exp = new_license_info.get('expired_date', 'Unknown')

        # Build normalized lookup map for new_features & new_features_detail
        norm_new_features = {}
        norm_new_details = {}
        for k, v in new_features.items():
            norm_k = self._normalize_feature_name(k)
            if norm_k:
                norm_new_features[norm_k] = max(v, norm_new_features.get(norm_k, 0))
            norm_new_features[k] = v

        for k, v in new_features_detail.items():
            norm_k = self._normalize_feature_name(k)
            if norm_k:
                norm_new_details[norm_k] = v
            norm_new_details[k] = v

        # Expiry comparison
        if new_exp.upper() == 'PERMANENT' and cur_exp.upper() != 'PERMANENT':
            self.log("✅ Expiry check: New license is PERMANENT.")
        elif cur_exp.upper() == 'PERMANENT' and new_exp.upper() == 'PERMANENT':
            # Both PERMANENT: check if active router has any trial items that need review
            trial_items = [k for k, v in current_features_detail.items() if v.get('is_trial', False)]
            if trial_items:
                rows = []
                for item in trial_items:
                    c_det = current_features_detail.get(item, {})
                    c_val = c_det.get('value', 0)
                    
                    c_perm = c_det.get('perm_value', c_val if c_det.get('is_permanent') else 0)
                    c_trial = c_det.get('trial_value', c_val if c_det.get('is_trial') else 0)

                    norm_item = self._normalize_feature_name(item)
                    n_det = new_features_detail.get(item, norm_new_details.get(norm_item, {}))
                    
                    # If item exists in new license XML, resolve permanent vs trial status
                    if n_det:
                        n_perm = n_det.get('perm_value', n_det.get('value', 0) if n_det.get('is_permanent') else 0)
                        n_trial = n_det.get('trial_value', n_det.get('value', 0) if n_det.get('is_trial') else 0)
                    else:
                        n_perm = 0
                        n_trial = 0

                    rows.append({
                        "item": item,
                        "c_perm": c_perm,
                        "c_trial": c_trial,
                        "n_perm": n_perm,
                        "n_trial": n_trial
                    })

                table_lines = [f"{'Item Name':<20} | {'Cur Perm':<8} | {'Cur Trial':<9} | {'New Perm':<8} | {'New Trial':<9}", "-"*65]
                for r in rows:
                    table_lines.append(f"{r['item']:<20} | {r['c_perm']:<8} | {r['c_trial']:<9} | {r['n_perm']:<8} | {r['n_trial']:<9}")

                table_str = "\n".join(table_lines)
                warn_msg = f"Current license is PERMANENT but contains {len(trial_items)} trial item(s):\n{table_str}"
                
                self.log(f"⚠️ Current license is PERMANENT but contains {len(trial_items)} trial item(s):\n{table_str}", "warn")
                issues.append(warn_msg)
            else:
                self.log("✅ Both licenses PERMANENT with no active trial items.")
        elif cur_exp.upper() == 'PERMANENT' and new_exp.upper() != 'PERMANENT':
            self.log("⚠️ Expiry check: Current license is already PERMANENT, new license is non-permanent.", "warn")
            issues.append("Current license is PERMANENT, new is not PERMANENT")
        elif new_exp != 'Unknown' and cur_exp != 'Unknown' and new_exp >= cur_exp:
            self.log(f"✅ Expiry check: New expiry ({new_exp}) >= current ({cur_exp}).")
        else:
            self.log(f"⚠️ Expiry check: New expiry ({new_exp}) < current ({cur_exp}).", "warn")
            issues.append(f"New expiry ({new_exp}) < current ({cur_exp})")

        cur_pn = current_license_info.get('product_name', 'Unknown')
        new_pn = new_license_info.get('product_name', 'Unknown')
        cur_pv = current_license_info.get('product_version', 'Unknown')
        new_pv = new_license_info.get('product_version', 'Unknown')

        if not self._product_names_match(cur_pn, new_pn) or not self._product_versions_match(cur_pv, new_pv):
            mismatch_msg = f"Product info mismatch: Current='{cur_pn} {cur_pv}', New='{new_pn} {new_pv}'"
            self.log(f"⚠️ {mismatch_msg}", "warn")
            issues.append(mismatch_msg)
        else:
            self.log("✅ Product info matches.")

        # Build normalized lookup map for new_features & new_features_detail
        norm_new_features = {}
        norm_new_details = {}
        for k, v in new_features.items():
            norm_k = self._normalize_feature_name(k)
            if norm_k:
                norm_new_features[norm_k] = max(v, norm_new_features.get(norm_k, 0))
            norm_new_features[k] = v

        for k, v in new_features_detail.items():
            norm_k = self._normalize_feature_name(k)
            if norm_k:
                norm_new_details[norm_k] = v
            norm_new_details[k] = v

        # Check active features for decrease or reduction of permanent capacity
        for leaf, cur_norm in active_features.items():
            matched_new_val = self._fuzzy_feature_match(leaf, norm_new_features)
            new_norm = matched_new_val if matched_new_val is not None else 0

            cur_det = current_features_detail.get(leaf, {})
            norm_leaf = self._normalize_feature_name(leaf)
            new_det = new_features_detail.get(leaf, norm_new_details.get(norm_leaf, {}))

            # 1. Direct value decrease check
            if new_norm < cur_norm:
                cur_is_trial = cur_det.get('is_trial', False) or bool(cur_det.get('item_trial_days') and cur_det.get('item_trial_days') != '0')
                new_is_trial = new_det.get('is_trial', False) or bool(new_det.get('trial_days') and new_det.get('trial_days') != '0')

                dec_msg = f"Feature decrease for {leaf}: current={cur_norm}, new={new_norm}"
                if cur_is_trial:
                    cur_info = cur_det.get('item_expired_date') or cur_det.get('item_trial_days') or 'N/A'
                    dec_msg += f" (Current had trial/demo item: validDate/trialDays={cur_info})"
                if new_is_trial:
                    new_info = new_det.get('valid_date') or new_det.get('trial_days') or 'N/A'
                    dec_msg += f" (New has trial/demo item: validDate/trialDays={new_info})"
                
                self.log(f"❌ {dec_msg}", "error")
                issues.append(dec_msg)

            # 2. Permanent feature converted/reduced to trial check
            elif cur_norm > 0 and cur_det.get('is_permanent', False) and new_det.get('is_trial', False) and not new_det.get('is_permanent', False):
                expiry_info = new_det.get('valid_date') or new_det.get('trial_days') or 'N/A'
                trial_msg = f"Permanent feature converted to trial for {leaf}: current=Permanent ({cur_norm}), new=Trial ({new_norm}, validDate/trialDays={expiry_info})"
                self.log(f"❌ {trial_msg}", "error")
                issues.append(trial_msg)

        is_valid = len(issues) == 0
        return is_valid, issues

    def _generate_renamed_license_path(self, router_name: str, esn: str, expiry_date: str) -> str:
        safe_router = re.sub(r'[^\w\-]', '_', router_name)
        safe_esn = re.sub(r'[^\w]', '', esn) if esn else 'UNKNOWN'
        safe_expiry = re.sub(r'[^\d\-]', '', expiry_date) if expiry_date else 'UNKNOWN'
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        if safe_expiry.upper() == 'PERMANENT' or safe_expiry == 'UNKNOWN':
            return f"{safe_router}_{safe_esn}_{safe_expiry}_{timestamp}.xml"
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
        license_file_path = router_info.get('license_file_path', '')
        license_file_name = os.path.basename(license_file_path) if license_file_path else 'Unknown'

        self.log(f"🔌 Starting renewal for {router_name} ({ip}) [ESN: {esn}, File: {license_file_name}]...")

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
            return {
                'router_name': router_name,
                'ip': ip,
                'esn': esn,
                'license_file': license_file_name,
                'status': 'Failed',
                'details': f'File read error: {e}'
            }

        new_features, new_license_info, new_display, new_features_detail = self.parse_xml_license(xml_content)
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
                current_status_res = self.get_license_status(conn)
                if current_status_res:
                    current_output, current_verbose = current_status_res
                    current_features, current_info, current_bundles, current_display, current_features_detail = self.parse_active_license_features(current_output, current_verbose)
                    current_expiry = current_info.get('expired_date', 'Unknown')
                else:
                    current_features, current_info, current_bundles, current_display, current_features_detail = {}, {}, {}, {}, {}
                    current_expiry = 'Unknown'

                # Compare
                is_valid, issues = self.compare_license_features(
                    new_features=new_features,
                    active_features=current_features,
                    new_license_info=new_license_info,
                    current_license_info=current_info,
                    current_bundles=current_bundles,
                    current_display=current_display,
                    new_display=new_display,
                    new_features_detail=new_features_detail,
                    current_features_detail=current_features_detail
                )

                if not is_valid:
                    reason_msg = "; ".join([i if isinstance(i, str) else i.get("title", "") for i in issues])
                    user_confirmed = False

                    # Dry run logic inside processing
                    dry_run = getattr(self, 'dry_run_flag', False)
                    if dry_run:
                        self.log(f"⚠️ DRY RUN: License issues detected for {router_name}: {reason_msg}. Auto-renew would fail.", "warn")
                        return {
                            'router_name': router_name,
                            'ip': ip,
                            'esn': esn,
                            'license_file': license_file_name,
                            'current_expiry': current_expiry,
                            'new_expiry': new_expiry,
                            'status': 'Skipped (Dry Run)',
                            'details': f'Would skip due to: {reason_msg}'
                        }

                    if self.confirm_callback:
                        self.log(f"⚠️ License issues detected for {router_name}. Asking user confirmation...", "warn")
                        user_confirmed = self.confirm_callback(router_name, issues)
                    else:
                        # CLI interactive fallback if confirm_callback not provided
                        self.log(f"⚠️ License issues detected for {router_name}: {reason_msg}", "warn")
                        
                        # CHANGED: If no confirm callback, default to False instead of pausing thread for stdin
                        self.log("⚠️ No interactive confirmation available. Defaulting to SKIP.", "warn")
                        user_confirmed = False

                    if not user_confirmed:
                        self.log(f"🛑 Skipping renewal for {router_name}: User declined or skipped due to issues [{reason_msg}]", "warn")
                        return {
                            'router_name': router_name,
                            'ip': ip,
                            'esn': esn,
                            'license_file': license_file_name,
                            'current_expiry': current_expiry,
                            'new_expiry': new_expiry,
                            'status': 'Skipped (Needs Review)',
                            'details': f'Skipped by user/policy. Issues: {reason_msg}'
                        }
                    else:
                        self.log(f"⚠️ User explicitly confirmed to proceed with renewal for {router_name} despite issues.", "warn")

                # Remote filename
                new_filename = self._generate_renamed_license_path(router_name, esn, new_expiry)

                # Check if file exists on router to avoid collision
                if self._check_file_exists_on_router(conn, new_filename):
                    timestamp_extra = datetime.now().strftime("%Y%m%d%H%M%S")
                    new_filename = f"{new_filename.rsplit('.', 1)[0]}_{timestamp_extra}.xml"

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
                    archived_name = self._archive_license_file(license_file_path, router_name, esn, new_expiry)
                    return {
                        'router_name': router_name,
                        'ip': ip,
                        'esn': esn,
                        'license_file': license_file_name,
                        'archived_file': archived_name,
                        'current_expiry': current_expiry,
                        'new_expiry': new_expiry,
                        'renewal_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'Completed',
                        'details': 'Activated'
                    }
                else:
                    self.log(f"❌ License activation FAILED on {router_name}: {activation_output}", "error")
                    return {
                        'router_name': router_name,
                        'ip': ip,
                        'esn': esn,
                        'license_file': license_file_name,
                        'current_expiry': current_expiry,
                        'new_expiry': new_expiry,
                        'status': 'Failed',
                        'details': activation_output
                    }

        except Exception as conn_err:
            self.log(f"❌ Processing failed for {router_name} ({ip}): {conn_err}", "error")
            return {
                'router_name': router_name,
                'ip': ip,
                'esn': esn,
                'license_file': license_file_name,
                'current_expiry': 'Unknown',
                'new_expiry': new_expiry,
                'status': 'Failed',
                'details': str(conn_err)
            }

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
        self._generate_csv_report(self.report_rows)

        # Summary of skipped / needs review
        skipped_items = [r for r in self.report_rows if 'Skipped' in r.get('status', '') or r.get('status') == 'Failed']
        if skipped_items:
            self.log("=" * 60, "warn")
            self.log(f"⚠️ ITEMS NEEDING REVIEW ({len(skipped_items)} router(s)):", "warn")
            for item in skipped_items:
                r_name = item.get('router_name', 'Unknown')
                r_status = item.get('status', 'Unknown')
                r_details = item.get('details', '')
                self.log(f"  • {r_name} [{r_status}]: {r_details}", "warn")
            self.log("=" * 60, "warn")
        else:
            self.log("✨ All selected routers processed cleanly with no review flags.", "success")

        return self.report_rows

    def _archive_license_file(self, license_file_path: str, router_name: str, esn: str, expiry_date: str):
        archive_dir = self.settings.get('license_archive_dir', 'license_archive')
        os.makedirs(archive_dir, exist_ok=True)

        safe_router = re.sub(r'[^\w\-]', '_', router_name)
        safe_esn = re.sub(r'[^\w]', '', esn) if esn else 'UNKNOWN'
        safe_expiry = re.sub(r'[^\d\-]', '', expiry_date) if expiry_date else 'UNKNOWN'
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        if safe_expiry.upper() == 'PERMANENT' or safe_expiry == 'UNKNOWN':
            archive_filename = f"{safe_router}_{safe_esn}_{safe_expiry}_{timestamp}.xml"
        else:
            archive_filename = f"{safe_router}_{safe_esn}_{safe_expiry}.xml"
            if os.path.exists(os.path.join(archive_dir, archive_filename)):
                archive_filename = f"{safe_router}_{safe_esn}_{safe_expiry}_{timestamp}.xml"
        archive_path = os.path.join(archive_dir, archive_filename)

        try:
            if '#' in license_file_path:
                zip_path, xml_path = license_file_path.split('#', 1)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    with z.open(xml_path) as src, open(archive_path, 'wb') as dst:
                        dst.write(src.read())
            else:
                with open(license_file_path, 'rb') as src, open(archive_path, 'wb') as dst:
                    dst.write(src.read())
            self.log(f"License file archived to {archive_path}", "info")
            return archive_filename
        except Exception as e:
            self.log(f"Error archiving license file {license_file_path}: {e}", "error")
            return None

    def _generate_csv_report(self, report_data: List[Dict], filename: str = None):
        if not report_data:
            self.log("No data to generate report.", "info")
            return

        report_dir = self.settings.get('report_dir', 'reports')
        os.makedirs(report_dir, exist_ok=True)

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(report_dir, f"license_renewal_report_{timestamp}.csv")
        else:
            filename = os.path.join(report_dir, filename)

        fieldnames = list(report_data[0].keys())
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(report_data)
            self.log(f"CSV report generated at {filename}", "success")
        except Exception as e:
            self.log(f"Error generating CSV report: {e}", "error")
