"""
samsung_flash_keepdata.py — Samsung 4-file flash, HOME_CSC.

Download Mode me odin4 se BL/AP/CP/HOME_CSC flash — HOME_CSC
userdata mehfooz rakhta hai (data wipe nahi hota). HOME_CSC na
ho to op FAIL deta hai; CSC wala (data mitane wala) op khud se
nahi chalaya jata — wo customer se pooch kar chalana hai.
Asal flow core/samsung_odin.run_flash me hai.
"""

from core import samsung_odin

OP = {
    "id": "samsung_flash_keepdata",
    "category": "Samsung",
    "name": "Flash 4-File (HOME_CSC = Data Mehfooz)",
    "engine": "odin4",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    return samsung_odin.run_flash(ctx, "HOME_CSC")
