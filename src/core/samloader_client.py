"""
samloader_client.py — Samsung FUS firmware client (stdlib only).

Samsung ke official FUS (Firmware Update Server) se firmware
download karne ka minimal client — **2026 protocol**
(SamLoader-RS, github.com/topjohnwu/samloader-rs, Apache-2.0,
Feb 2026 se active) par mabni, stdlib se dobara likha gaya
(urllib + ElementTree + hashlib + pure-Python AES).

PROTOCOL NOTE (live verify 2026-10-25): purana samloader
(github.com/samloader/samloader, archived 2023) ka protocol
2026 me TOOT gaya — live NONCE header classic KEY_1 AES-CBC
scheme se decrypt NAHI hota (OpenSSL se cross-check: crypto
sahi hai, server ne scheme badal di hai). Naya protocol:
  * UA: "SMART 2.0" (Kies2.0_FUS nahi) — FOTA bhi isi UA par
    200 deta hai, urllib default UA par 403.
  * Nonce: POST NF_SmartDownloadGenerateNonce.do — NONCE header
    ki pehli 16 ASCII bytes ('0' se pad) ko AES-128-ECB se
    AUTH_AES_KEY se encrypt karke hex karo → auth token; nonce
    (LOGIC_CHECK ke liye) khud NONCE header string hai.
  * BinaryInform: POST NF_SmartDownloadBinaryInform.do (naya XML:
    ACCESS_MODE 1, REQUEST_TYPE 2, BINARY_SW_VERSION /
    BINARY_LOCAL_CODE / BINARY_MODEL_NAME; status "200"/"S00").
  * BinaryInit: POST NF_SmartDownloadBinaryInitForMass.do
    (checkinp = filename[-25:-9]).
  * Download: GET cloud-neofussvr.samsungmobile.com/
    NF_SmartDownloadBinaryForMass.do?file={path}{filename}.
  * Decrypt key: .enc2 → MD5("{region}:{model}:{fw}"); warna →
    MD5(get_logic_check(fw, LOGIC_VALUE_FACTORY/HOME)).
    AES-128-ECB + PKCS#7 unpad (wahi rehta hai).
  * History: POST SmartHistory.do — MD5-based history headers.

SECURITY / RULES:
  * Koi Samsung account / password tool me store NAHI hota —
    FUS anonymous hai (koi login nahi mangta).
  * Sirf firmware files download hoti hain (Samsung ke official
    server se) — koi crack/shared login nahi.
  * AUTH_AES_KEY SamLoader-RS ke public source (Apache-2.0) se
    hai — protocol ka hissa, koi leaked key nahi.

AES: stdlib me AES NAHI hai — is liye pure-Python AES yahin
likha gaya hai (S-box runtime par GF(2^8) se generate hoti hai;
FIPS-197 + NIST CBC vectors se verify). Agar `Cryptodome`
(pycryptodome, optional dependency) maujood ho to wo fast path
istemal hota hai; warna pure-Python fallback (kaam karta hai,
bara firmware decrypt karne me slow hota hai).
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Pure-Python AES (FIPS-197) — S-box GF(2^8) se generate hoti hai
# ---------------------------------------------------------------------------

_GF_POLY = 0x11B


def _gf_mul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= _GF_POLY & 0xFF
        b >>= 1
    return p


def _gf_pow(a, e):
    r = 1
    while e:
        if e & 1:
            r = _gf_mul(r, a)
        a = _gf_mul(a, a)
        e >>= 1
    return r


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _build_sbox():
    sbox = []
    inv_sbox = [0] * 256
    for i in range(256):
        inv = 0 if i == 0 else _gf_pow(i, 254)
        s = inv ^ _rotl8(inv, 1) ^ _rotl8(inv, 2) \
            ^ _rotl8(inv, 3) ^ _rotl8(inv, 4) ^ 0x63
        sbox.append(s)
        inv_sbox[s] = i
    return sbox, inv_sbox


_SBOX, _INV_SBOX = _build_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
         0x6C, 0xD8, 0xAB, 0x4D, 0x9A]


def _expand_key(key):
    """Key (16/24/32 bytes) → (round keys, nr).

    AES-128: 11 round keys, AES-192: 13, AES-256: 15.
    Firmware decrypt MD5 key 16-byte (AES-128) hoti hai; 2026
    nonce-auth bhi AES-128 hai.
    """
    nk = len(key) // 4
    if nk not in (4, 6, 8) or len(key) % 4:
        raise ValueError("AES key 16, 24 ya 32 bytes honi chahiye")
    nr = nk + 6
    w = [list(key[i * 4:(i + 1) * 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = [_SBOX[temp[1]] ^ _RCON[i // nk - 1], _SBOX[temp[2]],
                    _SBOX[temp[3]], _SBOX[temp[0]]]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[t] for t in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    rounds = []
    for r in range(nr + 1):
        rk = []
        for c in range(4):
            rk.extend(w[r * 4 + c])
        rounds.append(bytes(rk))
    return rounds, nr


def _add_rk(state, rk):
    return bytes(s ^ k for s, k in zip(state, rk))


def _sub_bytes(state, box):
    return bytes(box[b] for b in state)


def _shift_rows(state):
    # state column-major: index = col*4 + row
    out = bytearray(16)
    for row in range(4):
        for col in range(4):
            out[col * 4 + row] = state[((col + row) % 4) * 4 + row]
    return bytes(out)


def _inv_shift_rows(state):
    out = bytearray(16)
    for row in range(4):
        for col in range(4):
            out[col * 4 + row] = state[((col - row) % 4) * 4 + row]
    return bytes(out)


def _mix_columns(state):
    out = bytearray(16)
    for col in range(4):
        a = state[col * 4:col * 4 + 4]
        out[col * 4 + 0] = _gf_mul(a[0], 2) ^ _gf_mul(a[1], 3) ^ a[2] ^ a[3]
        out[col * 4 + 1] = a[0] ^ _gf_mul(a[1], 2) ^ _gf_mul(a[2], 3) ^ a[3]
        out[col * 4 + 2] = a[0] ^ a[1] ^ _gf_mul(a[2], 2) ^ _gf_mul(a[3], 3)
        out[col * 4 + 3] = _gf_mul(a[0], 3) ^ a[1] ^ a[2] ^ _gf_mul(a[3], 2)
    return bytes(out)


def _inv_mix_columns(state):
    out = bytearray(16)
    for col in range(4):
        a = state[col * 4:col * 4 + 4]
        out[col * 4 + 0] = _gf_mul(a[0], 14) ^ _gf_mul(a[1], 11) \
            ^ _gf_mul(a[2], 13) ^ _gf_mul(a[3], 9)
        out[col * 4 + 1] = _gf_mul(a[0], 9) ^ _gf_mul(a[1], 14) \
            ^ _gf_mul(a[2], 11) ^ _gf_mul(a[3], 13)
        out[col * 4 + 2] = _gf_mul(a[0], 13) ^ _gf_mul(a[1], 9) \
            ^ _gf_mul(a[2], 14) ^ _gf_mul(a[3], 11)
        out[col * 4 + 3] = _gf_mul(a[0], 11) ^ _gf_mul(a[1], 13) \
            ^ _gf_mul(a[2], 9) ^ _gf_mul(a[3], 14)
    return bytes(out)


def aes_encrypt_block(key, block):
    """AES encrypt, aik 16-byte block (key 16/24/32 bytes)."""
    if len(block) != 16:
        raise ValueError("AES block 16 bytes hona chahiye")
    rks, nr = _expand_key(key)
    s = _add_rk(block, rks[0])
    for rnd in range(1, nr):
        s = _sub_bytes(s, _SBOX)
        s = _shift_rows(s)
        s = _mix_columns(s)
        s = _add_rk(s, rks[rnd])
    s = _sub_bytes(s, _SBOX)
    s = _shift_rows(s)
    return _add_rk(s, rks[nr])


def aes_decrypt_block(key, block):
    """AES decrypt, aik 16-byte block (key 16/24/32 bytes)."""
    if len(block) != 16:
        raise ValueError("AES block 16 bytes hona chahiye")
    rks, nr = _expand_key(key)
    s = _add_rk(block, rks[nr])
    for rnd in range(nr - 1, 0, -1):
        s = _inv_shift_rows(s)
        s = _sub_bytes(s, _INV_SBOX)
        s = _add_rk(s, rks[rnd])
        s = _inv_mix_columns(s)
    s = _inv_shift_rows(s)
    s = _sub_bytes(s, _INV_SBOX)
    return _add_rk(s, rks[0])


def aes128_encrypt_block(key, block):
    """AES-128 encrypt, aik 16-byte block. (Pure Python.)"""
    if len(key) != 16 or len(block) != 16:
        raise ValueError("AES-128: key aur block 16 bytes hone chahiyein")
    return aes_encrypt_block(key, block)


def aes128_decrypt_block(key, block):
    """AES-128 decrypt, aik 16-byte block. (Pure Python.)"""
    if len(key) != 16 or len(block) != 16:
        raise ValueError("AES-128: key aur block 16 bytes hone chahiyein")
    return aes_decrypt_block(key, block)


def _aes_cipher(key, use_fast=True):
    """(encrypt_block, decrypt_block) — fast path Cryptodome ho to."""
    if use_fast:
        try:
            from Cryptodome.Cipher import AES
            enc = AES.new(key, AES.MODE_ECB).encrypt
            dec = AES.new(key, AES.MODE_ECB).decrypt
            return enc, dec
        except Exception:  # noqa: BLE001 — fallback pure Python
            pass
    return (lambda b: aes_encrypt_block(key, b),
            lambda b: aes_decrypt_block(key, b))


def aes_cbc_encrypt(key, data):
    """AES-CBC encrypt, IV = key ke pehle 16 bytes."""
    if len(data) % 16:
        data = _pkcs7_pad(data)
    enc, _ = _aes_cipher(key)
    iv = key[:16]
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
        prev = enc(block)
        out += prev
    return bytes(out)


def aes_cbc_decrypt(key, data):
    """AES-CBC decrypt, IV = key ke pehle 16 bytes."""
    if len(data) % 16:
        raise ValueError("CBC decrypt: data 16 ka multiple hona chahiye")
    _, dec = _aes_cipher(key)
    iv = key[:16]
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        out += bytes(a ^ b for a, b in zip(dec(block), prev))
        prev = block
    return bytes(out)


def aes_ecb_decrypt(key, data):
    """AES-ECB decrypt (firmware decrypt ke liye)."""
    if len(data) % 16:
        raise ValueError("ECB decrypt: data 16 ka multiple hona chahiye")
    _, dec = _aes_cipher(key)
    return b"".join(dec(data[i:i + 16])
                    for i in range(0, len(data), 16))


def _pkcs7_pad(data):
    pad = 16 - (len(data) % 16)
    return data + bytes([pad]) * pad


def _pkcs7_unpad(data):
    if not data:
        raise ValueError("unpad: khaali data")
    pad = data[-1]
    if pad < 1 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise ValueError("unpad: ghalat PKCS#7 padding")
    return data[:-pad]


# ---------------------------------------------------------------------------
# FUS auth — 2026 protocol (SamLoader-RS, Apache-2.0, public source)
# ---------------------------------------------------------------------------

# Auth key SamLoader-RS ke auth.rs se (henr1kas / ducthoe ki taraf
# se di gayi, public repo me hai) — protocol constant hai.
AUTH_AES_KEY = bytes([
    0x42, 0x2E, 0x73, 0x73, 0x36, 0x17, 0xAE, 0x2B,
    0x19, 0x89, 0x40, 0xFD, 0x4E, 0x32, 0xB0, 0xA5,
])

FUS_HOST = "https://neofussvr.sslcs.cdngc.net/"
FUS_CLOUD_HOST = "http://cloud-neofussvr.samsungmobile.com/"
FOTA_HOST = "https://fota-cloud-dn.ospserver.net/firmware/"
USER_AGENT = "SMART 2.0"

# Legacy (classic samloader, 2023 se pehle) constants — sirf
# reference ke liye rakhe hain; 2026 server in se kaam NAHI karta.
LEGACY_KEY_1 = "hqzdurufm2c8mf6bsjezu1qgveouv7c7"
LEGACY_KEY_2 = "w13r4cvf4hctaujv"


def decrypt_nonce(encnonce):
    """2026 nonce → auth token (SamLoader-RS auth.rs).

    NONCE header string ki pehli 16 ASCII bytes lo ('0' se pad
    karo agar chhoti ho), AES-128-ECB se AUTH_AES_KEY se encrypt
    karo, hex-encode karo. Yehi 'signature' banta hai; nonce
    (LOGIC_CHECK ke liye) khud NONCE header string rehta hai.
    """
    raw = str(encnonce or "").encode("ascii", "ignore")
    block = bytearray(b"0" * 16)
    take = min(len(raw), 16)
    block[:take] = raw[:take]
    enc, _ = _aes_cipher(AUTH_AES_KEY)
    return enc(bytes(block)).hex()


def generate_client_nonce():
    """History headers ke liye random 16-char client nonce
    ([a-z0-9])."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(16))


def _md5_hex(text):
    return hashlib.md5(text.encode()).hexdigest()


def compute_history_headers(model, client_nonce=None):
    """SmartHistory.do ke liye (client_nonce, signature).

    auth_hash = MD5("auth:{nonce}:00000001")
    interface_hash = MD5("interface:{MODEL}")
    signature = MD5("{auth_hash}:FUS:{interface_hash}")
    (SamLoader-RS auth.rs — compute_history_headers.)
    """
    nonce = client_nonce or generate_client_nonce()
    auth_hash = _md5_hex("auth:%s:00000001" % nonce)
    interface_hash = _md5_hex("interface:%s" % str(model).upper())
    signature = _md5_hex("%s:FUS:%s" % (auth_hash, interface_hash))
    return nonce, signature


def get_logic_check(inp, nonce):
    """Request checksum: nonce ke har char ke low nibble se inp
    ke us index wala char uthao; index bahar ho to '.'.
    (SamLoader-RS xml.rs — get_logic_check.)"""
    inp = str(inp or "")
    out = ""
    for c in str(nonce or ""):
        idx = ord(c) & 0xF
        out += inp[idx] if idx < len(inp) else "."
    return out


# Classic naam ka alias (purani samloader code se milta-julta).
getlogiccheck = get_logic_check


# ---------------------------------------------------------------------------
# FUS XML requests / responses (pure helpers — testable)
# ---------------------------------------------------------------------------

def normalize_vercode(vercode):
    """Version code ko 4-part form me lao (3-part ho to pehla dobara)."""
    ver = str(vercode or "").split("/")
    if len(ver) == 3:
        ver.append(ver[0])
    if len(ver) >= 3 and ver[2] == "":
        ver[2] = ver[0]
    return "/".join(ver)


def build_binary_inform_xml(model, region, fw, nonce):
    """BinaryInform request XML — 2026 format (SamLoader-RS xml.rs).

    ACCESS_MODE 1, REQUEST_TYPE 2, BINARY_SW_VERSION /
    BINARY_LOCAL_CODE / BINARY_MODEL_NAME; Get me khaali
    BINARY_SW_VERSION.
    """
    fw = normalize_vercode(fw)
    logic = get_logic_check(fw, nonce)
    return (
        "<FUSMsg>\n"
        "<FUSHdr><ProtoVer>1.0</ProtoVer><SessionID>0</SessionID>"
        "<MsgID>1</MsgID></FUSHdr>\n"
        "<FUSBody>\n"
        "    <Put>\n"
        "        <CmdID>1</CmdID>\n"
        "        <ACCESS_MODE><Data>1</Data></ACCESS_MODE>\n"
        "        <BINARY_NATURE><Data>1</Data></BINARY_NATURE>\n"
        "        <REQUEST_TYPE><Data>2</Data></REQUEST_TYPE>\n"
        "        <LOGIC_CHECK><Data>%s</Data></LOGIC_CHECK>\n"
        "        <BINARY_SW_VERSION><Data>%s</Data></BINARY_SW_VERSION>\n"
        "        <BINARY_LOCAL_CODE><Data>%s</Data></BINARY_LOCAL_CODE>\n"
        "        <BINARY_MODEL_NAME><Data>%s</Data></BINARY_MODEL_NAME>\n"
        "    </Put>\n"
        "    <Get>\n"
        "        <CmdID>2</CmdID>\n"
        "        <BINARY_SW_VERSION></BINARY_SW_VERSION>\n"
        "    </Get>\n"
        "</FUSBody>\n"
        "</FUSMsg>" % (logic, fw, region, model)
    ).encode()


def build_binary_init_xml(filename, nonce, fw, model_type, region):
    """BinaryInit request XML — 2026 format.

    checkinp = filename[-25:-9]; fields: BINARY_NAME,
    BINARY_SW_VERSION, DEVICE_LOCAL_CODE, DEVICE_MODEL_TYPE,
    LOGIC_CHECK.
    """
    start = max(0, len(filename) - 25)
    end = max(0, len(filename) - 9)
    checkinp = filename[start:end]
    logic = get_logic_check(checkinp, nonce)
    return (
        "<FUSMsg>\n"
        "<FUSHdr><ProtoVer>1.0</ProtoVer><SessionID>0</SessionID>"
        "<MsgID>1</MsgID></FUSHdr>\n"
        "<FUSBody>\n"
        "    <Put>\n"
        "        <BINARY_NAME><Data>%s</Data></BINARY_NAME>\n"
        "        <BINARY_SW_VERSION><Data>%s</Data></BINARY_SW_VERSION>\n"
        "        <DEVICE_LOCAL_CODE><Data>%s</Data></DEVICE_LOCAL_CODE>\n"
        "        <DEVICE_MODEL_TYPE><Data>%s</Data></DEVICE_MODEL_TYPE>\n"
        "        <LOGIC_CHECK><Data>%s</Data></LOGIC_CHECK>\n"
        "    </Put>\n"
        "</FUSBody>\n"
        "</FUSMsg>" % (filename, normalize_vercode(fw), region,
                       model_type, logic)
    ).encode()


def build_history_xml(model, region):
    """SmartHistory.do request XML — 2026 format."""
    return (
        "<FUSMsg>\n"
        "<FUSHdr><ProtoVer>1</ProtoVer><SessionID>0</SessionID>"
        "<MsgID>1</MsgID></FUSHdr>\n"
        "<FUSBody>\n"
        "    <Put>\n"
        "        <CmdID>1</CmdID>\n"
        "        <ACCESS_MODE><Data>1</Data></ACCESS_MODE>\n"
        "        <BINARY_LOCAL_CODE><Data>%s</Data></BINARY_LOCAL_CODE>\n"
        "        <BINARY_MODEL_NAME><Data>%s</Data></BINARY_MODEL_NAME>\n"
        "    </Put>\n"
        "</FUSBody>\n"
        "</FUSMsg>" % (region, model)
    ).encode()


def _find_text(root, path):
    el = root.find(path)
    return el.text if el is not None else None


def parse_version_xml(xml_text):
    """FOTA version.xml → normalized latest version code."""
    root = ET.fromstring(xml_text)
    vercode = _find_text(root, "./firmware/version/latest")
    if vercode is None:
        raise ValueError("version.xml me latest version nahi mili")
    return normalize_vercode(vercode)


def parse_version_info(xml_text):
    """FOTA version.xml → (latest, previous[]) — previous list
    rcount/fwsize se sort (SamLoader-RS parse_version_xml jaisa)."""
    root = ET.fromstring(xml_text)
    latest = parse_version_xml(xml_text)
    entries = []
    upgrade = root.find("./firmware/version/upgrade")
    if upgrade is not None:
        for value_node in upgrade.findall("value"):
            text = (value_node.text or "").strip()
            if not text:
                continue
            try:
                rcount = int(value_node.get("rcount") or 0)
            except ValueError:
                rcount = 0
            try:
                fwsize = int(value_node.get("fwsize") or 0)
            except ValueError:
                fwsize = 0
            entries.append((rcount, fwsize, normalize_vercode(text)))
    entries.sort(key=lambda e: (e[0], e[1]))
    return latest, [e[2] for e in entries]


def _collect_data_map(root):
    """Har <Tag><Data>value</Data></Tag> ko dict me jama karo
    (SamLoader-RS get_xml_node_data jaisa)."""
    kv = {}
    for data_el in root.iter("Data"):
        text = data_el.text
        if text is None:
            continue
        # Parent tag ka naam chahiye — ElementTree me parent nahi
        # hota, is liye poora tree walk karke dhoondho.
        for parent in root.iter():
            for child in parent:
                if child is data_el:
                    kv[parent.tag] = text
                    break
    return kv


def parse_binary_inform(xml_text):
    """BinaryInform jawab → dict (version, filename, path, size,
    key, model_type, region). Status "200"/"S00" ke ilawa
    ValueError. Key: .enc2 → MD5(region:model:fw); warna →
    MD5(get_logic_check(fw, LOGIC_VALUE_FACTORY/HOME))."""
    root = ET.fromstring(xml_text)
    status = _find_text(root, "./FUSBody/Results/Status")
    if status not in ("200", "S00"):
        raise ValueError(
            "DownloadBinaryInform ne status %s diya — firmware "
            "nahi mili (model/region ghalat ho sakta hai, ya "
            "Samsung ne API badal di hai)" % (status,))
    kv = _collect_data_map(root)
    fw_ver = kv.get("BINARY_SW_VERSION") or kv.get("LATEST_FW_VERSION")
    if not fw_ver:
        raise ValueError("BinaryInform: version nahi mili")
    filename = kv.get("BINARY_NAME")
    if not filename:
        raise ValueError("BinaryInform: BINARY_NAME nahi mila")
    region = kv.get("BINARY_LOCAL_CODE") or kv.get("DEVICE_LOCAL_CODE")
    if not region:
        raise ValueError("BinaryInform: region nahi mili")
    path = kv.get("MODEL_PATH")
    size_raw = kv.get("BINARY_BYTE_SIZE")
    model_type = kv.get("DEVICE_MODEL_TYPE")
    if not path or not size_raw or not model_type:
        raise ValueError("BinaryInform: MODEL_PATH / BINARY_BYTE_SIZE "
                         "/ DEVICE_MODEL_TYPE me se kuch nahi mila")
    if filename.lower().endswith(".enc2"):
        model = (kv.get("BINARY_MODEL_NAME")
                 or kv.get("DEVICE_MODEL_NAME")
                 or filename.split("_")[0])
        key = getv2key(fw_ver, model, region)
    else:
        logic_val = kv.get("LOGIC_VALUE_FACTORY") \
            or kv.get("LOGIC_VALUE_HOME")
        if not logic_val:
            raise ValueError("BinaryInform: LOGIC_VALUE nahi mila")
        key = getv4key_from_inform(fw_ver, logic_val)
    return {
        "status": status,
        "version": normalize_vercode(fw_ver),
        "filename": filename,
        "size": int(size_raw),
        "path": path,
        "key": key,
        "model_type": model_type,
        "region": region,
        "logic_value": kv.get("LOGIC_VALUE_FACTORY")
                         or kv.get("LOGIC_VALUE_HOME"),
    }


def parse_history_xml(xml_text):
    """SmartHistory.do jawab → (latest, previous[], beta[]) —
    BINARY_INFO entries sequence/open_date se sort (newest first);
    index '90' = beta. (SamLoader-RS parse_history_xml jaisa.)"""
    root = ET.fromstring(xml_text)
    entries = []
    for info in root.iter("BINARY_INFO"):
        kv = _collect_data_map(info)
        sw = kv.get("BINARY_SW_VERSION")
        index = kv.get("BINARY_INDEX")
        seq_raw = kv.get("BINARY_SEQUENCE")
        if not sw or not index or not seq_raw:
            continue
        try:
            seq = int(seq_raw)
        except ValueError:
            continue
        entries.append((sw, index, seq, kv.get("BINARY_OPEN_DATE")
                        or ""))
    if not entries:
        raise ValueError("History: koi BINARY_INFO nahi mila")
    # Dedup (sw, index, seq) — open_date taaza wali rakho.
    best = {}
    for sw, index, seq, odate in entries:
        k = (sw, index, seq)
        if k not in best or odate > best[k][3]:
            best[k] = (sw, index, seq, odate)
    # Newest first: sequence desc, phir open_date desc.
    merged = sorted(best.values(), key=lambda e: e[3], reverse=True)
    merged = sorted(merged, key=lambda e: e[2], reverse=True)
    stable = [normalize_vercode(e[0]) for e in merged if e[1] != "90"]
    beta = [normalize_vercode(e[0]) for e in merged if e[1] == "90"]
    if not stable:
        raise ValueError("History: koi stable version nahi mili")
    return stable[0], stable[1:], beta


def getv2key(version, model, region):
    """ENC2 key = MD5("{region}:{model}:{version}")."""
    deckey = "%s:%s:%s" % (region, model, version)
    return hashlib.md5(deckey.encode()).digest()


def getv4key_from_inform(latest_fw, logic_value):
    """ENC4 key = MD5(get_logic_check(latest_fw, logic_value))."""
    if not latest_fw or not logic_value:
        raise ValueError("ENC4 key ke liye LATEST_FW_VERSION aur "
                         "LOGIC_VALUE_FACTORY chahiyein")
    deckey = get_logic_check(latest_fw, logic_value)
    return hashlib.md5(deckey.encode()).digest()


def enc_version_of(filename):
    """File naam se ENC version (2/4) ya None."""
    name = str(filename or "").lower()
    if name.endswith(".enc4"):
        return 4
    if name.endswith(".enc2"):
        return 2
    return None


def decrypted_name(filename):
    """'x.zip.enc4' → 'x.zip'."""
    for suf in (".enc4", ".enc2"):
        if str(filename).lower().endswith(suf):
            return str(filename)[: -len(suf)]
    return str(filename)


def download_url_for(path, filename):
    """Cloud download URL — 2026 host (samsungmobile.com)."""
    return FUS_CLOUD_HOST + "NF_SmartDownloadBinaryForMass.do?file=" \
        + path + filename


# ---------------------------------------------------------------------------
# HTTP client (urllib, stdlib) — FUS session: nonce + JSESSIONID
# ---------------------------------------------------------------------------

class FUSError(Exception):
    """FUS server / network ki ghalti — imaandar FAIL ke liye."""


class FUSClient:
    """FUS API client, 2026 protocol (anonymous — koi Samsung
    login nahi)."""

    def __init__(self, timeout=30, opener=None):
        self.auth = ""
        self.nonce = ""      # LOGIC_CHECK ke liye: raw NONCE header
        self.encnonce = ""   # raw NONCE header string
        self.timeout = timeout
        if opener is not None:
            self._opener = opener
        else:
            # Cookie jar lazmi hai: nonce response ke session cookies
            # (Imperva/PWS) agle requests par wapas bhejne parte hain
            # — baghair in ke BinaryInform 401 deta hai (live verify).
            import http.cookiejar
            jar = http.cookiejar.CookieJar()
            self._opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar))
        # Pehli request nonce initialise karti hai.
        self.makereq("NF_SmartDownloadGenerateNonce.do")

    def _auth_header(self, enc_nonce="", auth=""):
        return ('FUS nonce="%s", signature="%s", nc="", type="", '
                'realm="", newauth="1"') % (enc_nonce, auth)

    def _headers(self, history=False, model=""):
        if history:
            nonce, sig = compute_history_headers(model)
            auth_val = ('FUS nonce="%s", signature="%s", '
                        'nc="00000001", type="auth", '
                        'realm="interface"') % (nonce, sig)
        else:
            auth_val = self._auth_header(self.encnonce, self.auth)
        return {"Authorization": auth_val, "User-Agent": USER_AGENT}

    def makereq(self, path, data=b"", history=False, model=""):
        """FUS POST — jawab text; NONCE header mile to auth update.

        Note: FUS server ko POST par Content-Type chahiye — khaali
        body par 411 (Length Required) milta hai, is liye body
        hamesha bheji jati hai (khaali ho to bhi).
        """
        url = FUS_HOST + path
        body = data if data else b""
        req = urllib.request.Request(
            url, data=body,
            headers=dict(self._headers(history, model),
                         **{"Content-Type":
                            "application/x-www-form-urlencoded"}),
            method="POST")
        try:
            resp = self._opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            raise FUSError("FUS %s: HTTP %s — Samsung ne request "
                           "radd kar di (API badal gaya ho sakta hai)"
                           % (path, e.code))
        except urllib.error.URLError as e:
            raise FUSError("FUS %s: network ghalti (%s) — internet "
                           "check karo" % (path, e.reason))
        headers = resp.headers
        nonce_hdr = headers.get("NONCE") or headers.get("Nonce")
        if nonce_hdr and nonce_hdr != self.encnonce:
            self.encnonce = nonce_hdr
            self.nonce = nonce_hdr
            try:
                self.auth = decrypt_nonce(nonce_hdr)
            except Exception as e:  # noqa: BLE001 — auth na bane to aage nahi
                raise FUSError("FUS nonce se auth token nahi bana "
                               "(%s) — Samsung ne auth badal diya ho "
                               "sakta hai" % e)
        return resp.read().decode("utf-8", "replace")

    def get_binary_info(self, model, region, fw_version):
        """BinaryInform → parse_binary_inform dict."""
        fw = normalize_vercode(fw_version)
        xml = build_binary_inform_xml(model, region, fw, self.nonce)
        resp = self.makereq("NF_SmartDownloadBinaryInform.do", xml)
        return parse_binary_inform(resp)

    def fetch_history(self, model, region):
        """SmartHistory.do → (latest, previous[], beta[])."""
        xml = build_history_xml(model, region)
        resp = self.makereq("SmartHistory.do", xml,
                            history=True, model=model)
        return parse_history_xml(resp)

    def init_download(self, filename, fw_version, model_type, region):
        """BinaryInit (download se pehle)."""
        xml = build_binary_init_xml(filename, self.nonce, fw_version,
                                    model_type, region)
        self.makereq("NF_SmartDownloadBinaryInitForMass.do", xml)

    def _reauthenticate(self):
        """401 par nonce dobara lo (download token expiry)."""
        self.makereq("NF_SmartDownloadGenerateNonce.do")

    def download_file(self, path, filename, out_path, start=0,
                      progress=None, chunk_size=0x10000,
                      init=None, end=None):
        """Cloud se file download karo (Range resume). progress
        callback: progress(downloaded_bytes, total_bytes). Total
        maloom na ho to total=0. init=(fw, model_type, region) ho
        to pehle BinaryInit bhi hota hai (401 par re-auth + retry).
        end diya ho to sirf bytes start..end download hote hain
        (range test / parallel chunks ke liye)."""
        if init is not None:
            fw, model_type, region = init
            self.init_download(filename, fw, model_type, region)
        url = download_url_for(path, filename)
        range_hdr = None
        if end is not None:
            range_hdr = "bytes=%d-%d" % (start, end)
        elif start > 0:
            range_hdr = "bytes=%d-" % start
        headers = dict(self._headers(),
                       **({"Range": range_hdr} if range_hdr else {}))
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            resp = self._opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code == 401 and init is not None:
                self._reauthenticate()
                self.init_download(filename, init[0], init[1], init[2])
                return self.download_file(path, filename, out_path,
                                          start, progress, chunk_size,
                                          init, end)
            raise FUSError("Download: HTTP %s — file nahi mili ya "
                           "Samsung ne rok diya" % e.code)
        except urllib.error.URLError as e:
            raise FUSError("Download: network ghalti (%s)" % e.reason)
        total = 0
        if end is not None:
            total = end - start + 1
        else:
            clen = resp.headers.get("Content-Length")
            if clen:
                try:
                    total = int(clen) + start
                except ValueError:
                    total = 0
        downloaded = start
        mode = "ab" if start > 0 else "wb"
        with open(out_path, mode) as fd:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                fd.write(chunk)
                fd.flush()
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
        return downloaded


def checkupdate(model, region, timeout=30, opener=None):
    """Latest firmware version (FOTA, anonymous GET).

    Note: FOTA server urllib ka default User-Agent dekh kar 403
    deta hai — SMART 2.0 UA lazmi hai (live verify 2026-10-25).
    """
    url = FOTA_HOST + region + "/" + model + "/version.xml"
    req = urllib.request.Request(
        url, method="GET", headers={"User-Agent": USER_AGENT})
    op = opener or urllib.request.build_opener()
    try:
        resp = op.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise FUSError("FOTA 403 — model ya region nahi mila "
                           "(%s / %s)" % (model, region))
        raise FUSError("FOTA: HTTP %s" % e.code)
    except urllib.error.URLError as e:
        raise FUSError("FOTA: network ghalti (%s)" % e.reason)
    return parse_version_xml(resp.read().decode("utf-8", "replace"))


def decrypt_file(in_path, out_path, key, progress=None,
                 chunk_size=4096):
    """ENC file ko AES-128-ECB decrypt karke ZIP likho (streaming).

    Aakhri block par PKCS#7 unpad. Pure-Python fallback slow hai —
    bara firmware ho to waqt lagega; Cryptodome ho to fast hai.
    """
    length = os.stat(in_path).st_size
    if length == 0 or length % 16 != 0:
        raise ValueError("decrypt: file size 16 ka multiple hona "
                         "chahiye (enc file kharab ya adhoori)")
    _, dec = _aes_cipher(key)
    done = 0
    with open(in_path, "rb") as inf, open(out_path, "wb") as outf:
        remaining = length
        while remaining > 0:
            block = inf.read(min(chunk_size, remaining))
            if not block:
                break
            plain = b"".join(dec(block[i:i + 16])
                             for i in range(0, len(block), 16))
            remaining -= len(block)
            done += len(block)
            if remaining == 0:
                plain = _pkcs7_unpad(plain)
            outf.write(plain)
            if progress:
                progress(done, length)
    return out_path
