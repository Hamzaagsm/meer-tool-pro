#!/usr/bin/env python3
# usb_backend_check.py — PC ke USB stack ki jaanch (bina phone ke).
#
# MEER Tool Pro ki UTILITY op "USB Backend Check (libusb)" is script
# ko engines/python se chalati hai. Maqsad: ye batana ke is PC par
# libusb enumeration chalti hai ya nahi — MTKClient ke "USB
# enumeration error: Operation not supported or unimplemented on
# this platform" ki asal wajah (Windows 11 25H2, build 26200) yahi
# check pakarti hai, poora FRP op chalaye baghair.
#
# Output: saada lines (koi rang nahi), aakhir me "NATEEJA: OK/FAIL".
# Exit code: 0 = kam az kam aik backend ne USB list ki; 1 = koi
# backend list nahi kar saka.
#
# Sirf pyusb istemal hota hai (MTKClient import NAHI) — is liye ye
# check MTKClient ki apni ghaltiyon se azad hai.

import os
import sys
from struct import calcsize

print("USB BACKEND CHECK")
print("Python: %d-bit (%s)" % (calcsize("P") * 8, sys.executable))

try:
    import usb.core
    import usb.backend.libusb1
    import usb.backend.libusb0
except Exception as err:
    print("pyusb import FAIL: %s" % err)
    print("NATEEJA: FAIL — pyusb maujood nahi (engines/python theek "
          "se extract nahi hua, ya requirements missing hain)")
    sys.exit(1)


def _bundled_dll():
    here = os.path.dirname(os.path.abspath(__file__))
    name = 'libusb-1.0.dll' if calcsize("P") * 8 == 64 else 'libusb32-1.0.dll'
    cand = os.path.join(here, "mtkclient", "mtkclient", "Windows", name)
    return cand if os.path.exists(cand) else name


def _check(label, backend):
    """(ok, count_or_error) — backend se device list ki koshish."""
    if backend is None:
        return False, "backend load hi nahi hua"
    try:
        devs = list(usb.core.find(find_all=True, backend=backend))
        return True, "%d devices" % len(devs)
    except Exception as err:
        return False, str(err)


results = {}

# --- libusb1 (bundled DLL, wahi jo MTKClient istemal karta hai) ---
dll = _bundled_dll()
print("libusb1 DLL: %s (%s)" % (dll, "mojood" if os.path.exists(dll) else "NAHI MILI"))
try:
    if sys.platform.startswith('win32'):
        b1 = usb.backend.libusb1.get_backend(find_library=lambda x: dll)
    else:
        b1 = usb.backend.libusb1.get_backend(
            find_library=lambda x: "libusb-1.0.so")
    if b1 is None:
        # Wazeh library na mile to pyusb ki default talash
        # (ctypes.util.find_library) azmao — Linux par .so symlink
        # na hone par pehla rasta None deta hai.
        b1 = usb.backend.libusb1.get_backend()
    print("libusb1 backend: %s" % ("LOAD OK" if b1 is not None else "LOAD FAIL (None)"))
except Exception as err:
    b1 = None
    print("libusb1 backend: LOAD FAIL — %s" % err)
ok1, info1 = _check("libusb1", b1)
print("libusb1 enumeration: %s — %s" % ("OK" if ok1 else "FAIL", info1))
results["libusb1"] = ok1

# --- libusb0 (libusb-win32 filter backend) ---
try:
    b0 = usb.backend.libusb0.get_backend()
    print("libusb0 backend: %s" % ("LOAD OK" if b0 is not None else "LOAD FAIL (None — libusb-win32 filter driver nahi)"))
except Exception as err:
    b0 = None
    print("libusb0 backend: LOAD FAIL — %s" % err)
ok0, info0 = _check("libusb0", b0)
print("libusb0 enumeration: %s — %s" % ("OK" if ok0 else "FAIL", info0))
results["libusb0"] = ok0

if results.get("libusb1") or results.get("libusb0"):
    print("NATEEJA: OK — kam az kam aik backend USB list kar raha hai")
    sys.exit(0)
print("NATEEJA: FAIL — koi backend USB list nahi kar raha")
sys.exit(1)
