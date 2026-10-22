"""
ops package — har operation aik plugin file hai.

Plugin ka usool (contract):
  OP = {
      "id": "adb_info",              # unique id
      "category": "ADB / Fastboot",  # tree me kis khane me ayega
      "name": "Read Device Info",    # button/tree label
      "engine": "adb",               # kis engine par mabni hai
      "modes": ("ADB",),             # kin device modes me chalega (khali = sab)
      "server_required": False,      # True ho to UI par SERVER REQUIRED tag
  }
  def run(ctx) -> bool:              # asal kaam; True = SUCCESS
      ...

Registry is folder ki tamam plugin files ko khud dhoondh leti hai —
naya operation jorna = aik nayi file jorna.
"""

import importlib
import pkgutil
from types import SimpleNamespace

CATEGORIES = ["MTK", "Qualcomm", "Samsung", "ADB / Fastboot", "SPD / Unisoc", "Demo"]


def load_operations():
    """Tamam plugins load karke modules ki list wapas karo (tartib: category order).

    Har module me OP dict + run(ctx) hota hai. stubs.py apne SERVER REQUIRED
    stubs STUB_OPS list me deta hai — wo bhi yahin shamil hote hain (lekin
    dohra count nahi: stubs.py ka module-level OP usi list ka pehla stub hai,
    is liye module wali entry sirf tab lenge jab STUB_OPS na ho).
    """
    ops = []
    for mod_info in pkgutil.iter_modules(__path__):
        if mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{mod_info.name}")
        stub_ops = getattr(module, "STUB_OPS", None)
        if stub_ops:
            seen = set()
            for entry in stub_ops:
                if entry["OP"]["id"] not in seen:
                    seen.add(entry["OP"]["id"])
                    ops.append(SimpleNamespace(OP=entry["OP"], run=entry["run"]))
            continue
        op = getattr(module, "OP", None)
        if op and callable(getattr(module, "run", None)):
            ops.append(module)

    def sort_key(m):
        cat = m.OP.get("category", "")
        idx = CATEGORIES.index(cat) if cat in CATEGORIES else 99
        return (idx, m.OP.get("name", ""))

    return sorted(ops, key=sort_key)
