"""
samsung_frp_router.py — Samsung FRP ke liye imaandar method router.

Ye op khud FRP NAHI hatata — device ki asal halat (mode + chipset +
security patch level) dekh kar SAHI rasta batata hai, aur jahan free
rasta band ho wahan saaf keh deta hai ke ye server-required kaam hai.
Yahi imaandari is op ki value hai: nakli "FRP removed" kabhi nahi.
"""

from core import device_watch, engines

OP = {
    "id": "samsung_frp_router",
    "category": "Samsung",
    "name": "FRP Method Router (Samsung)",
    "engine": "router",
    "modes": (),
    "server_required": False,
}

_TEST_MODE_STEPS = [
    "1) Phone on rakho, WiFi se connect karo, FRP (Google account) wali screen par raho.",
    "2) Emergency Dialer khol kar *#0*# dial karo — agar rang-biranga TEST MENU khul jaye to rasta khula hai; na khule to is patch par ye tareeqa band hai.",
    "3) Test menu khul jaye to Samsung section ka 'FRP Remove — Test Mode *#0*# (Free)' op chalao — wo ADB milte hi FRP reset khud karega aur tasdeeq bhi karega (SamFw v6.2 wala public rasta, MEER ke apne engine me).",
    "4) Kaam ke baad phone restart karke normal setup karo.",
]

# One UI 8.5 (S26/Z Fold 7, builds "xxC3") — Download Mode khatam
# NAHI hua, sirf Maintenance Mode ke peeche chhupa hai (Research-2
# §3.1, verified: Android Authority + PiunikaWeb, Mar 2026).
_ONEUI85_DOWNLOAD_MODE_STEPS = [
    "One UI 8.5 par Download Mode (S26 / Z Fold 7): pehle phone on "
    "karke Settings → Device care → Maintenance Mode ON karo.",
    "Phir phone band karo, Vol Down + Vol Up dono dabaye hue USB "
    "cable lagao — warning screen par Vol Up dabao (Download Mode).",
    "Download Mode khul jaye to Odin flash waisa hi chalta hai jaisa "
    "pehle tha — 'khatam' wali khabar ghalat thi.",
    "Maintenance Mode band karne ke baad Download Mode dobara chhup "
    "jata hai — har dafa pehle Maintenance Mode ON karna parta hai.",
]


def oneui85_download_mode_steps():
    """One UI 8.5 Download Mode steps (pure — testable)."""
    return list(_ONEUI85_DOWNLOAD_MODE_STEPS)


def _log_oneui85_guide(ctx):
    for step in _ONEUI85_DOWNLOAD_MODE_STEPS:
        ctx.log(step, "INFO")


def _log_test_mode_guide(ctx):
    for step in _TEST_MODE_STEPS:
        ctx.log(step, "INFO")


def _log_decision_tree(ctx):
    ctx.log("Pehchano ke device kis chipset par hai — rasta usi se banta hai:",
            "INFO")
    ctx.log("Samsung MTK (A12/M12 waghera) → MTK tab ki operations dekho.", "INFO")
    ctx.log("Qualcomm Samsung → EDL tab ki operations dekho.", "INFO")
    ctx.log("Exynos + purana patch → test mode wala rasta koshish ke qabil hai.",
            "INFO")
    ctx.log("Exynos/Qualcomm + Dec 2022 ke baad ka patch → free rasta nahi, "
            "ye server wala kaam hai.", "INFO")
    ctx.log("One UI 8.5 (S26 / Z Fold 7) par Download Mode khatam NAHI "
            "hua — sirf Maintenance Mode ke peeche hai:", "INFO")
    _log_oneui85_guide(ctx)


def run(ctx) -> bool:
    dev = ctx.device
    mode = getattr(dev, "mode", None) if dev else None

    if not mode:
        _log_decision_tree(ctx)
        ctx.log("Device connected nahi — pehle phone kisi mode me lagao.", "ERROR")
        return False

    if mode in ("BROM", "PRELOADER"):
        ctx.log("Ye Samsung asal me MediaTek chipset par hai — MTK tab ki "
                "'FRP Erase + Factory Reset' operation is par chalegi.", "OK")
        return True

    if mode == "EDL":
        ctx.log("Device Qualcomm EDL me hai — Qualcomm tab ki 'EDL FRP Erase' "
                "operation istemal karo (us model ka firehose loader library "
                "me hona chahiye).", "OK")
        return True

    if mode == "ADB":
        try:
            props = device_watch.adb_getprops(
                engines.find_platform_tool("adb"), dev.serial)
        except Exception:
            props = {}
        patch = props.get("ro.build.version.security_patch", "") if props else ""
        oneui = props.get("ro.build.version.oneui", "") if props else ""
        if oneui:
            ctx.log(f"One UI version (raw): {oneui}", "DATA")
        if patch:
            ctx.log(f"Security Patch: {patch}", "DATA")

        # Patch boundary: Dec 2022 (SamFw v6.2 free/paid line,
        # research §4.3a) — mahina-ahem hai, sirf saal nahi:
        # 2022-12 free hai, 2023-01 server hai. Helper executor
        # op se ata hai taake boundary aik hi jagah rahe.
        from ops.samsung_frp_testmode import patch_is_free
        free = patch_is_free(patch)

        if free is None:
            ctx.log("Security patch level parha nahi gaya — saal ka pata nahi "
                    "chal saka, is liye pakka rasta nahi bataya ja sakta.", "WARN")
            ctx.log("Aam guidance: purana patch (Dec 2022 ya us se pehle) "
                    "ho to test mode wala rasta ummeed deta hai; us ke "
                    "baad ka patch ho to test mode band hai aur free "
                    "rasta nahi hota.", "INFO")
            return False

        if free:
            _log_test_mode_guide(ctx)
            ctx.log("Patch Dec 2022 ya us se purana hai — test mode wala "
                    "rasta koshish ke qabil hai.", "OK")
            return True

        # free is False → patch 2023-01 ya us ke baad ka
        ctx.log("Patch Dec 2022 ke baad ka hai — Samsung ne One UI 5 ke saath "
                "test mode wala rasta band kar diya tha. Is device ka FRP free "
                "engines se nahi hoga; ye SERVER REQUIRED wala kaam hai "
                "(Samsung tab me is ka alag tag wala item dekho).", "ERROR")
        return False

    ctx.log(f"Device {mode} mode me hai — is mode se Samsung FRP ka koi rasta "
            "nahi. Phone ko ADB (on karke), BROM ya EDL me lao, phir ye router "
            "dobara chalao.", "WARN")
    return False
