#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RegFF_OB55 - Fixed version for Render deployment
Reads config from environment variables.
"""
import os
import sys
import json
import time
import hmac
import base64
import random
import string
import hashlib
import signal
import threading
import queue
import re
import ipaddress
import urllib3
from datetime import datetime
from typing import Optional, Tuple, Dict

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
except ImportError:
    print("ERROR: pycryptodome not installed. Run: pip install pycryptodome")
    sys.exit(1)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== CONSTANTS ====================
AES_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
AES_IV = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
HEX_KEY = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
API_KEY = HEX_KEY.encode('utf-8')

# ==================== ENV CONFIG ====================
ACCOUNT_COUNT = int(os.environ.get("ACCOUNT_COUNT", "100"))
THREAD_COUNT = int(os.environ.get("THREAD_COUNT", "3"))
RARITY_SCORE_THRESHOLD = int(os.environ.get("RARITY_THRESHOLD", "8"))
SELECTED_REGION = os.environ.get("REGION", "VN")
BASE_NAME = os.environ.get("BASE_NAME", "WJXAZ")
BASE_PASSWORD = os.environ.get("BASE_PASSWORD", "TELE@WJXAZ")
RUN_ONCE = os.environ.get("RUN_ONCE", "true").lower() == "true"

# ==================== GLOBALS ====================
EXIT_FLAG = False
accounts_dict: Dict[str, list] = {}
accounts_lock = threading.Lock()
success_count = 0
success_lock = threading.Lock()
fail_count = 0
fail_lock = threading.Lock()
save_queue: "queue.Queue" = queue.Queue()
save_thread_running = True
RARE_COUNTER = 0
COUPLES_COUNTER = 0
COUPLES_DATA: Dict[str, dict] = {}
COUPLES_LOCK = threading.Lock()
print_lock = threading.Lock()

# ==================== FOLDERS ====================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_FOLDER = os.path.join(CURRENT_DIR, "DATA_ACCOUNTS")
ACCOUNTS_FOLDER = os.path.join(BASE_FOLDER, "ACCOUNTS")
for folder in [BASE_FOLDER, ACCOUNTS_FOLDER]:
    os.makedirs(folder, exist_ok=True)


def safe_print(*args, **kwargs):
    with print_lock:
        try:
            print(*args, **kwargs, flush=True)
        except Exception:
            pass


# ==================== PATTERNS ====================
PATTERNS = {
    "R4": [r"(\d)\1{3,}", 3],
    "R3": [r"(\d)\1\1(\d)\2\2", 2],
    "S5": [r"(12345|23456|34567|45678|56789)", 4],
    "S4": [r"(0123|1234|2345|3456|4567|5678|6789|9876|8765|7654|6543|5432|4321|3210)", 3],
    "P6": [r"^(\d)(\d)(\d)\3\2\1$", 5],
    "P4": [r"^(\d)(\d)\2\1$", 3],
    "SPH": [r"(69|420|1337|007)", 4],
    "SPM": [r"(100|200|300|400|500|666|777|888|999)", 2],
    "QD": [r"(1111|2222|3333|4444|5555|6666|7777|8888|9999|0000)", 4],
    "MH": [r"^(\d{2,3})\1$", 3],
    "MM": [r"(\d{2})0\1", 2],
    "GD": [r"1618|0618", 3],
}

_B64_KEY = b'X1NUQVJf'


def generate_exponent() -> str:
    exp_digits = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
                  '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
    num = random.randint(1, 9999)
    return ''.join(exp_digits[d] for d in f"{num:04d}")


def generate_account_name(base: str) -> str:
    if base:
        return f"{base}{generate_exponent()}"
    return f"STARRッ~{generate_exponent()}"


def _gen_rnd(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    sysrand = random.SystemRandom()
    return ''.join(sysrand.choice(alphabet) for _ in range(length))


def generate_password(base_password: str) -> str:
    try:
        clean = base_password.split('WX')[0] if base_password else "WX"
        prefix = base64.b64decode(_B64_KEY).decode('utf-8')
        return f"{clean}{prefix}{_gen_rnd(9)}"
    except Exception:
        clean = base_password.split('WX')[0] if base_password else "WX"
        return f"{clean}WX{_gen_rnd(8)}"


# ==================== IP ROTATOR ====================
class IPRotator:
    REGION_IP_CIDRS = {"VN": ["1.52.0.0/14", "14.160.0.0/11", "27.64.0.0/12", "113.160.0.0/12"]}
    _cache: Dict[str, list] = {}

    @classmethod
    def get_random_ip(cls, region: str = "VN") -> str:
        region = region.upper()
        if region not in cls._cache or not cls._cache[region]:
            cidrs = cls.REGION_IP_CIDRS.get(region, ["27.0.0.0/8"])
            hosts = []
            for cidr in cidrs:
                try:
                    net = ipaddress.ip_network(cidr, strict=False)
                    for _ in range(3):
                        ip_int = int(net.network_address) + random.randint(1, max(1, 2 ** (32 - net.prefixlen) - 2))
                        hosts.append(str(ipaddress.IPv4Address(ip_int)))
                except Exception:
                    continue
            if not hosts:
                hosts = [f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}"]
            cls._cache[region] = hosts
        return random.choice(cls._cache[region])

    @classmethod
    def get_ip_headers(cls, region: str = "VN") -> Dict[str, str]:
        ip = cls.get_random_ip(region)
        return {'X-Forwarded-For': ip, 'X-Real-IP': ip, 'Client-IP': ip}


# ==================== RARITY ====================
def check_rarity(account_data: dict) -> Tuple[bool, Optional[str], Optional[str], int]:
    account_id = str(account_data.get("account_id", ""))
    if not account_id or account_id == "N/A":
        return False, None, None, 0
    score = 0
    found = []
    for ptype, (pattern, pts) in PATTERNS.items():
        if re.search(pattern, account_id):
            score += pts
            found.append(ptype)
    digits = [int(d) for d in account_id if d.isdigit()]
    if len(set(digits)) == 1 and len(digits) >= 4:
        score += 5
        found.append("UNIFORM")
    if len(digits) >= 4:
        diffs = [digits[i+1] - digits[i] for i in range(len(digits)-1)]
        if len(set(diffs)) == 1:
            score += 4
            found.append("ARITHMETIC")
    if len(account_id) <= 8 and account_id.isdigit() and int(account_id) < 1000000:
        score += 3
        found.append("LOW_ID")
    if score >= RARITY_SCORE_THRESHOLD:
        return True, "RARE", f"ID:{account_id} | Score:{score} | {','.join(found)}", score
    return False, None, None, score


def check_couple(account_data: dict, thread_id: int):
    account_id = str(account_data.get("account_id", ""))
    if not account_id or account_id == "N/A":
        return False, None, None
    with COUPLES_LOCK:
        for stored_id, stored in list(COUPLES_DATA.items()):
            stored_aid = str(stored.get('account_id', ''))
            if not stored_aid or not stored_aid.isdigit() or not account_id.isdigit():
                continue
            if abs(int(account_id) - int(stored_aid)) == 1:
                del COUPLES_DATA[stored_id]
                return True, f"Sequential: {account_id} & {stored_aid}", stored
            if account_id == stored_aid[::-1]:
                del COUPLES_DATA[stored_id]
                return True, f"Mirror: {account_id} & {stored_aid}", stored
        COUPLES_DATA[account_id] = {
            'uid': str(account_data.get('uid', '')),
            'account_id': account_id,
            'name': str(account_data.get('name', '')),
            'password': str(account_data.get('password', '')),
            'region': str(account_data.get('region', '')),
            'thread_id': thread_id,
        }
    return False, None, None


# ==================== SAVE / LOAD ====================
def load_region_accounts(region: str) -> int:
    global accounts_dict
    filename = os.path.join(ACCOUNTS_FOLDER, f"accounts-{region}.json")
    accounts_dict[region] = []
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    accounts_dict[region] = data
                    safe_print(f"✅ Loaded {len(data)} existing accounts for {region}")
                    return len(data)
    except Exception as e:
        safe_print(f"⚠️ Load error for {region}: {e}")
    return 0


def save_region_accounts(region: str) -> bool:
    filename = os.path.join(ACCOUNTS_FOLDER, f"accounts-{region}.json")
    tmp = filename + ".tmp"
    with accounts_lock:
        data = list(accounts_dict.get(region, []))
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, filename)
        return True
    except Exception as e:
        safe_print(f"❌ Save error for {region}: {e}")
        return False


def save_all_regions():
    for region in list(accounts_dict.keys()):
        if accounts_dict.get(region):
            save_region_accounts(region)


def queue_save():
    save_queue.put(True)


def save_worker():
    global save_thread_running
    while save_thread_running:
        try:
            item = save_queue.get(timeout=1)
            if item is None:
                break
            save_all_regions()
            save_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            safe_print(f"⚠️ Save worker error: {e}")


def account_exists(uid: str, region: str) -> bool:
    with accounts_lock:
        for acc in accounts_dict.get(region, []):
            if str(acc.get('uid')) == str(uid):
                return True
    return False


def get_next_count() -> int:
    global success_count
    with success_lock:
        success_count += 1
        return success_count


# ==================== PROTOBUF ====================
def create_vr(N: int) -> bytes:
    if N < 0:
        return b''
    out = []
    while True:
        b = N & 0x7F
        N >>= 7
        if N:
            b |= 0x80
        out.append(b)
        if not N:
            break
    return bytes(out)


def create_variant(field_number: int, value: int) -> bytes:
    return create_vr((field_number << 3) | 0) + create_vr(value)


def create_length(field_number: int, value) -> bytes:
    encoded = value.encode() if isinstance(value, str) else value
    return create_vr((field_number << 3) | 2) + create_vr(len(encoded)) + encoded


def create_proto(fields: dict) -> bytearray:
    packet = bytearray()
    for field, value in fields.items():
        if isinstance(value, bool):
            packet.extend(create_variant(field, 1 if value else 0))
        elif isinstance(value, int):
            packet.extend(create_variant(field, value))
        elif isinstance(value, (str, bytes)):
            packet.extend(create_length(field, value))
    return packet


def decode_varint(data: bytes, offset: int):
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        if not (byte & 0x80):
            return result, offset
        shift += 7
        if shift > 63:
            return None, offset
    return None, offset


def decode_protobuf(data: bytes) -> dict:
    result = {}
    offset = 0
    n = len(data)
    while offset < n:
        header, offset = decode_varint(data, offset)
        if header is None:
            break
        field_number = header >> 3
        wire_type = header & 0x7
        if wire_type == 0:
            value, offset = decode_varint(data, offset)
            if value is not None:
                result[field_number] = value
        elif wire_type == 2:
            length, offset = decode_varint(data, offset)
            if length is None or offset + length > n:
                break
            value = data[offset:offset + length]
            offset += length
            try:
                result[field_number] = value.decode('utf-8')
            except Exception:
                result[field_number] = value.hex()
        elif wire_type == 1:
            offset += 8
        elif wire_type == 5:
            offset += 4
        elif wire_type == 3:
            depth = 1
            while offset < n and depth > 0:
                h, offset = decode_varint(data, offset)
                if h is None:
                    break
                wt = h & 0x7
                if wt == 3:
                    depth += 1
                elif wt == 4:
                    depth -= 1
                elif wt == 0:
                    _, offset = decode_varint(data, offset)
                elif wt == 2:
                    ln, offset = decode_varint(data, offset)
                    if ln is None:
                        break
                    offset += ln
                elif wt == 1:
                    offset += 8
                elif wt == 5:
                    offset += 4
        else:
            break
    return result


def encrypt_aes(hex_data: str) -> str:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(bytes.fromhex(hex_data), AES.block_size)).hex()


# ==================== API ====================
PIXEL_UA = "GarenaMSDK/4.0.44(Pixel ;Android 10;en;US;app 1.132.1 2019121229;)"


def register_account(password: str, region: str):
    url = "https://100067.connect.garena.com/api/v2/oauth/guest:register"
    ip_headers = IPRotator.get_ip_headers(region)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    payload = json.dumps({"app_id": 100067, "client_type": 2, "password": password_hash, "source": 2}, separators=(',', ':'))
    signature = hmac.new(API_KEY, payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        "User-Agent": PIXEL_UA,
        "Authorization": f"Signature {signature}",
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Connection": "Keep-Alive",
        "Host": "100067.connect.garena.com",
        "X-Garena-Timestamp": str(int(time.time() * 1000) + random.randint(-999, 999)),
        **ip_headers,
    }
    try:
        r = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        if r.status_code == 200:
            jd = r.json()
            if jd.get("code") == 0 and "data" in jd:
                return str(jd["data"]["uid"]), str(password)
            safe_print(f"  ↳ Register error: {jd}")
        else:
            safe_print(f"  ↳ Register HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        safe_print(f"  ↳ Register exception: {e}")
    return None, None


def get_access_token(uid: str, password: str, region: str, device_id: Optional[str] = None):
    url = "https://100067.connect.garena.com/api/v2/oauth/guest/token:grant"
    ip_headers = IPRotator.get_ip_headers(region)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if not device_id:
        device_id = device_id_generate("", region)
    headers = {
        "Host": "100067.connect.garena.com",
        "User-Agent": PIXEL_UA,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
        **ip_headers,
    }
    data = {
        "client_id": 100067,
        "client_secret": HEX_KEY,
        "client_type": 2,
        "device_id": device_id,
        "password": password_hash,
        "response_type": "token",
        "uid": int(uid),
    }
    try:
        r = requests.post(url, headers=headers, json=data, verify=False, timeout=30)
        if r.status_code == 200:
            jd = r.json()
            if jd.get("code") == 0 and "data" in jd:
                d = jd["data"]
                return d.get("access_token"), d.get("open_id"), int(d.get("platform") or 4)
            safe_print(f"  ↳ TokenGrant error: {jd}")
        else:
            safe_print(f"  ↳ TokenGrant HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        safe_print(f"  ↳ TokenGrant exception: {e}")
    return None, None, None


def device_id_generate(open_id: str, region: str) -> str:
    import uuid as _uuid
    url = "https://100067.msdk.garena.com/device/api/v1/android/device-id:generate"
    ip_headers = IPRotator.get_ip_headers(region)
    payload = json.dumps({
        "app_id": 100067,
        "data": {
            "ad_aaid": "", "android_id": "01b05346c944b5e6",
            "android_version_release": "10", "android_version_sdk": "29",
            "brand": "Google", "build_date": "1697185398000",
            "build_display": "NHG47O release-keys", "build_id": "NHG47O",
            "cpu_abis": "arm64-v8a,armeabi-v7a,armeabi", "drm_id": "", "drm_vendor": "",
            "fingerprint": "Google/sailfish/sailfish:10/NHG47O/eng.build.20231013.013027:user/release-keys",
            "gcbooster_uuid": "", "hardware": "msm8996", "imei": "", "model": "Pixel",
            "key_mqs_uuid": "", "product_name": "sailfish", "random_uuid": str(_uuid.uuid4()),
            "soc_manufacturer": "", "soc_model": "",
        },
    }, separators=(',', ':'))
    signature = hmac.new(API_KEY, payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        "User-Agent": PIXEL_UA, "Authorization": f"Signature {signature}",
        "Accept": "application/json", "Content-Type": "application/json; charset=utf-8",
        "Host": "100067.msdk.garena.com", "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip", **ip_headers,
    }
    try:
        r = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        if r.status_code == 200:
            jd = r.json()
            if jd.get("code") == 0:
                return jd["data"].get("device_id", "")
    except Exception:
        pass
    return ""


def generate_nickname(open_id: str, region: str) -> str:
    url = "https://loginbp.ppmainecoonghj.com/GenerateNickname"
    ip_headers = IPRotator.get_ip_headers(region)
    payload = bytes.fromhex(encrypt_aes(create_proto({1: "en", 2: open_id}).hex()))
    headers = {
        "Accept-Encoding": "gzip", "Authorization": "Bearer", "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded", "Expect": "100-continue",
        "Host": "loginbp.ppmainecoonghj.com", "ReleaseVersion": "OB55",
        "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "X-GA": "v1 1", "X-GA-SV": str(int(time.time())),
        "X-Unity-Version": "2018.4.12f1", **ip_headers,
    }
    try:
        r = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        if r.status_code == 200:
            return r.text.strip()
    except Exception as e:
        safe_print(f"  ↳ GenerateNickname exception: {e}")
    return ""


_KEYSTREAM = bytes([0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37, 0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37,
                    0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37, 0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30])

_FIELD22 = bytes.fromhex(
    '474752450101010067020000a6a42db7bc5516876af3d1ba4adc337bac558af092eb3757d59d65c9323bba42c6593a48b74f33b2b5b3dc45cbd7ac02040db58f394045be4835213e12c35e5566445a5224f39d205fcf91c0e6bec797e7b3968ac00e90d7500b5865828a9d6f2091c3070f5319a130748e407ed57e6638974670ac045631b3d08c310cf1256cebcf1aed2d97d177534603d1c95d9c5d698340e797e72aa7ecc67a33122e48b0dfda050a1649586aca5e979be1fd9d99f48cd8cf59630e0ff60f67d4ed2ec4e5e7475970449a6c06329009ee0ce2567892587675781a31e4bb2774403b2f78e9811df2cb397fa602572266747704c6258077910902eb7420bcb4ab743d1610cddba9019e7867aaad3aa7ba9b04968064a409b66733f9f78c566a25ff478cba37a2ffe23203d4b05bceef826f174b0be7912d19432cc759325251fa094d70693fb672d6f9e799284081b3adb541dd8f27ef80dcf1e7f0ff30f2fd976659457ce41e175a2d6301b777981ccc16b9a8247abaab8de0867836c27de0146fe4d0e1fd39b86ba51f0b58601cfcbd7f6f3451fe4184b26ed44ac2f6f7bb4ce5d9a80f88c2cbfe7553e5ab97c8b028ae16b4f70f037753b8c229a6e5e9038fcbb9b4c2abb954894f8f2faf177bfdaab3b0ed537156633621d16b62d58ba4ebe518997c33e2304976ba6af9df7e7e34302c7910ae559c7e3d20a30d71c14f85c0e86f26291bbf18c2d9dfe9a908592eea4523e6c1e5d9bb5abfbebfccd5c4e136f9be777723e932b06c029df5125191000c90fde62a8e5f8fceb28648f0c69ec3037d09302b2ade908a20dbd42761ca449b2743fc362649e16235769d9fbd7f87cd64972b58d69c0441abb5d22ddc6ed059f7ac1bdbfaef8c60e64631809c5e08c7cb4074c8ce6170d94b411604986be4ae163a')


def _encode_open_id(open_id: str) -> bytes:
    return bytes((ord(ch) ^ _KEYSTREAM[i % len(_KEYSTREAM)]) for i, ch in enumerate(open_id))


def major_register(access_token: str, open_id: str, name: str, region: str, LANG: str = 'en') -> dict:
    url = "https://loginbp.ppmainecoonghj.com/MajorRegister"
    ip_headers = IPRotator.get_ip_headers(region)
    payload = bytes.fromhex(encrypt_aes(create_proto({
        1: name, 2: access_token, 3: open_id, 5: 102000007, 6: 4, 7: 1, 13: 1,
        14: _encode_open_id(open_id), 15: LANG, 16: 1, 17: 1, 20: "1.132.6", 21: 1, 22: _FIELD22,
    }).hex()))
    headers = {
        "Accept-Encoding": "gzip", "Authorization": "Bearer", "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded", "Expect": "100-continue",
        "Host": "loginbp.ppmainecoonghj.com", "ReleaseVersion": "OB55",
        "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "X-GA": "v1 1", "X-GA-SV": str(int(time.time())),
        "X-Unity-Version": "2018.4.12f1", **ip_headers,
    }
    try:
        r = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        if r.status_code == 200:
            return decode_protobuf(r.content)
        safe_print(f"  ↳ MajorRegister HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        safe_print(f"  ↳ MajorRegister exception: {e}")
    return {}


def choose_newbie_choice(account_id: str, region: str) -> bool:
    if not account_id:
        return False
    url = "https://loginbp.ppmainecoonghj.com/ChooseNewbieChoice"
    ip_headers = IPRotator.get_ip_headers(region)
    payload = bytes.fromhex(encrypt_aes(create_proto({1: int(account_id), 2: 1, 3: 3}).hex()))
    headers = {
        "Accept-Encoding": "gzip", "Authorization": "Bearer", "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded", "Expect": "100-continue",
        "Host": "loginbp.ppmainecoonghj.com", "ReleaseVersion": "OB55",
        "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "X-GA": "v1 1", "X-GA-SV": str(int(time.time())),
        "X-Unity-Version": "2018.4.12f1", **ip_headers,
    }
    try:
        r = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        return r.status_code == 200
    except Exception:
        return False


_LOGIN_BASE = {
    3: None, 4: "free fire", 5: 1, 7: "1.132.6",
    8: "Android OS 10 / API-29 (NHG47O/eng.build.20231013.013027)",
    9: "Handheld", 10: "TelKila", 11: "WIFI", 12: 1708, 13: 750, 14: "440",
    15: "ARM64 FP ASIMD AES | 2850 | 8", 16: 3968, 17: "Mali-G610 MC6",
    18: "OpenGL ES 3.2 v1.r32p1-01eac0.54329dee8f160f288c574caaf67bbe3f",
    19: "Google|0ecc7b3b-6c41-462e-9050-26d835e84c53", 20: "116.97.105.60",
    21: "en", 22: None, 23: None, 24: "Handheld", 25: "Google Pixel", 26: "SG",
    29: None, 30: 1, 41: "TelKila", 42: "WIFI",
    57: "7428b253defc164018c604a1ebbfebdf",
    60: 109029, 61: 37616, 62: 2048, 63: 804, 64: 37616, 65: 109029, 66: 37616, 67: 109029,
    73: 3, 74: "/data/app/com.dts.freefireth-oiglMJkEoNJlsRci10280Q==/lib/arm64", 76: 1,
    77: "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/com.dts.freefireth-oiglMJkEoNJlsRci10280Q==/base.apk",
    78: 3, 79: 2, 81: "64", 83: "2019121229", 85: 3, 86: "OpenGLES2", 87: 511,
    88: None, 92: 36711, 93: "android",
    94: "KqsHT8at0g7Na/G7iOeF1IpesHMf+HoePFMFFE8Tq/dSk4fIbJ1j8TdV8OAyWIVnSmD2rM6vfFMtCD8Ig7iROgDJmIMrdtcB6orwuNRpMr4MVu3D7FoTcuQdq/8EyOkRQiUrbg==",
    96: '{"cur_rate":null,"support_etc2":false}', 97: 1, 99: None, 100: None,
    102: bytes.fromhex('4000434f07555f0637'), 104: 1797, 105: 1,
    106: "https://dl.cdn.freefiremobile.com/live/ABHotUpdates/|https://dl-core.cdn.freefiremobile.com/live/ABHotUpdates/|4a0070ac356973792f002e0b25b96c3b",
    107: "c8e41b7a93f02d56e1a94c7b8203f5d1",
}


def major_login_payload(access_token: str, open_id: str, platform_type: int) -> bytes:
    f = dict(_LOGIN_BASE)
    f[3] = str(datetime.now())[:-7]
    f[22] = open_id
    f[23] = str(platform_type)
    f[29] = access_token
    f[88] = platform_type
    f[99] = str(platform_type)
    f[100] = str(platform_type)
    return bytes.fromhex(encrypt_aes(create_proto(f).hex()))


def _extract_jwt(raw: bytes) -> Optional[bytes]:
    o = 0
    n = len(raw)
    while o < n - 1:
        idx = raw.find(b"\x42", o)
        if idx < 0:
            break
        length, after = decode_varint(raw, idx + 1)
        if length is None:
            o = idx + 1
            continue
        end = after + length
        if end <= n and raw[after:after + 3] == b"eyJ":
            return raw[after:end]
        o = idx + 1
    return None


def major_login(payload: bytes, region: str) -> dict:
    url = "https://loginbp.ppmainecoonghj.com/MajorLogin"
    ip_headers = IPRotator.get_ip_headers(region)
    headers = {
        'X-Unity-Version': '2018.4.12f1', 'ReleaseVersion': 'OB55',
        'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Bearer',
        'Accept': '*/*', 'Expect': '100-continue', 'X-GA': 'v1 1',
        'X-GA-SV': str(int(time.time())),
        'User-Agent': 'UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)',
        'Host': 'loginbp.ppmainecoonghj.com', 'Connection': 'Keep-Alive',
        'Accept-Encoding': 'deflate, gzip', **ip_headers,
    }
    try:
        r = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        if r.status_code == 200:
            jwt_bytes = _extract_jwt(r.content)
            if jwt_bytes is None:
                s = r.text.find("eyJ")
                if s != -1:
                    jwt = r.text[s:]
                    d2 = jwt.find(".", jwt.find(".") + 1)
                    if d2 != -1:
                        jwt_bytes = jwt[:d2 + 44].encode('utf-8', 'replace')
            if jwt_bytes:
                login_token = jwt_bytes.decode('utf-8', 'replace')
                account_id = ""
                try:
                    parts = login_token.split('.')
                    if len(parts) >= 2:
                        p = parts[1] + '=' * ((4 - len(parts[1]) % 4) % 4)
                        jd = json.loads(base64.urlsafe_b64decode(p))
                        account_id = str(jd.get('account_id', ''))
                except Exception:
                    pass
                return {"login_token": login_token, "account_id": account_id,
                        "server_url": "https://clientbp.ppmainecoonghj.com"}
            safe_print("  ↳ MajorLogin: JWT not found")
            return {}
        safe_print(f"  ↳ MajorLogin HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        safe_print(f"  ↳ MajorLogin exception: {e}")
    return {}


def create_full_account(thread_id: int, region: str, base_name: str, base_password: str, max_retries: int = 2):
    global fail_count, RARE_COUNTER, COUPLES_COUNTER, EXIT_FLAG
    if EXIT_FLAG:
        return None

    for attempt in range(max_retries):
        if EXIT_FLAG:
            return None
        try:
            password = generate_password(base_password)
            name = generate_account_name(base_name)

            register_uid, password = register_account(password, region)
            if not register_uid:
                time.sleep(0.5)
                continue

            access_token, open_id, platform_type = get_access_token(register_uid, password, region)
            if not access_token:
                time.sleep(0.5)
                continue

            device_id_generate(open_id, region)
            major_login(major_login_payload(access_token, open_id, platform_type), region)

            nickname = generate_nickname(open_id, region)
            if nickname:
                name = nickname

            reg = major_register(access_token, open_id, name, region)
            if not reg:
                time.sleep(0.5)
                continue

            account_id = str(reg.get(3, ""))
            if not account_id:
                time.sleep(0.5)
                continue

            choose_newbie_choice(account_id, region)
            login = major_login(major_login_payload(access_token, open_id, platform_type), region)
            if not login or "login_token" not in login:
                time.sleep(0.5)
                continue

            jwt_token = login["login_token"]
            account_id = login.get("account_id", account_id)

            if account_exists(register_uid, region):
                return None

            count = get_next_count()
            account = {
                'uid': str(register_uid), 'password': str(password),
                'name': str(name), 'account_id': str(account_id),
                'region': str(region), 'jwt_token': str(jwt_token),
                'created_at': datetime.now().isoformat(), 'thread_id': str(thread_id),
            }

            with accounts_lock:
                accounts_dict.setdefault(region, []).append(account)

            queue_save()

            safe_print(f"✅ [{count}/{ACCOUNT_COUNT}] UID={register_uid} | ID={account_id} | {name}")

            is_rare, _, reason, rscore = check_rarity(account)
            if is_rare:
                with success_lock:
                    RARE_COUNTER += 1
                safe_print(f"💎 RARE! Score={rscore} | {reason}")

            is_couple, creason, partner = check_couple(account, thread_id)
            if is_couple and partner:
                with success_lock:
                    COUPLES_COUNTER += 1
                safe_print(f"💑 COUPLE! {creason}")

            return account
        except Exception as e:
            safe_print(f"❌ [T{thread_id}] Error: {e}")
            time.sleep(1)

    with fail_lock:
        fail_count += 1
    return None


def worker(thread_id: int, region: str, base_name: str, base_password: str):
    global EXIT_FLAG, success_count, ACCOUNT_COUNT
    while not EXIT_FLAG:
        with success_lock:
            if success_count >= ACCOUNT_COUNT:
                break
        create_full_account(thread_id, region, base_name, base_password)
        time.sleep(random.uniform(0.5, 1.0))


def _signal_handler(sig, frame):
    global EXIT_FLAG
    safe_print("\n⚠️ Stopping...")
    EXIT_FLAG = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def main():
    global save_thread_running, EXIT_FLAG

    safe_print("=" * 60)
    safe_print("  STAR GUEST GENERATOR PRO - RENDER EDITION")
    safe_print("=" * 60)
    safe_print(f"  Region: {SELECTED_REGION}")
    safe_print(f"  Target: {ACCOUNT_COUNT}")
    safe_print(f"  Threads: {THREAD_COUNT}")
    safe_print(f"  Rarity Threshold: {RARITY_SCORE_THRESHOLD}+")
    safe_print("=" * 60)

    load_region_accounts(SELECTED_REGION)

    save_thread = threading.Thread(target=save_worker, daemon=True)
    save_thread.start()

    t0 = time.time()
    threads = []
    for i in range(THREAD_COUNT):
        t = threading.Thread(target=worker, args=(i, SELECTED_REGION, BASE_NAME, BASE_PASSWORD), daemon=True)
        t.start()
        threads.append(t)

    try:
        while not EXIT_FLAG:
            time.sleep(1)
            with success_lock:
                current = success_count
            if current >= ACCOUNT_COUNT:
                break
    except KeyboardInterrupt:
        EXIT_FLAG = True

    for t in threads:
        t.join(timeout=3)

    elapsed = time.time() - t0
    safe_print("\n" + "=" * 60)
    safe_print("   📊 SUMMARY")
    safe_print("=" * 60)
    safe_print(f"   ✅ Success: {success_count}")
    safe_print(f"   ❌ Failed: {fail_count}")
    safe_print(f"   💎 Rare: {RARE_COUNTER}")
    safe_print(f"   💑 Couples: {COUPLES_COUNTER}")
    safe_print(f"   ⏱️  Time: {elapsed:.2f}s")
    safe_print("=" * 60)

    save_all_regions()
    save_thread_running = False
    save_queue.put(None)
    safe_print("✅ DONE. Worker exiting.")

    if RUN_ONCE:
        sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        safe_print("\n⚠️ Interrupted")
        try:
            save_all_regions()
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        safe_print(f"\n❌ CRITICAL: {e}")
        import traceback
        traceback.print_exc()
        try:
            save_all_regions()
        except Exception:
            pass
        sys.exit(1)
