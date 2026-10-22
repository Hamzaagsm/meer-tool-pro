"""
samsung_flash.py — Samsung 4-file flash, CSC = Full Reset.

Download Mode me odin4 se BL/AP/CP/CSC flash. CSC userdata
MITATA hai (factory reset jaisa asar) — is liye naam me hi
warning hai. Asal flow + saboot-wali SUCCESS core/samsung_odin
.run_flash me hai; ye op sirf CSC key ke saath use bulata hai.
"""

from core import samsung_odin

OP = {
    "id": "samsung_flash",
    "category": "Samsung",
    "name": "Flash 4-File (Download Mode, CSC = Full Reset)",
    "engine": "odin4",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    return samsung_odin.run_flash(ctx, "CSC")
