"""
finance_locks.py — Financing-lock pehchan (detection) ka database
aur classifier. Sirf PEHCHAN hai — removal ka koi daawa yahan
nahi banta; har lock ke saath imaandar verdict line rehti hai ke
public removal rasta hai ya nahi (COMPETITOR-RESEARCH-3 §3).

Database sources (project research se):
  - PayJoy: com.payjoy.access — mdm_payjoy op pehle se yehi
    package istemal karta hai; Samsung Knox partner solution.
  - Easybuy / Transsion Security Plugin: FENIX-FEATURES-RESEARCH
    §1 ki documented family — com.financial.service,
    com.mixtel.manager (mdm_security_plugin ke researched
    packages). EXACT plugin ID public documented nahi; ye family
    packages hain, is liye finding me ye wazahat rehti hai.
  - NuovoPay: com.promobitech.nuovo (M-KOPA-jaisi device
    financing platforms ka agent).
  - d.light PayGo: com.dlight.paygo.
  - Samsung Knox Guard: com.samsung.android.kgclient — KG ki
    halat server-side state hai; package ki maujoodgi sirf
    client ki maujoodgi hai, lock ki halat KG Status op batata hai.
  - Google Device Lock Controller:
    com.google.android.devicelockcontroller — Google ka apna
    financing-lock controller; M-KOPA jaisi financing aksar isi
    ya Knox Guard ke zariye lock karti hai (brand-naam par koi
    tool removal advertise nahi karta — research §3).

Classifier khalis logic hai (koi I/O nahi) — testable.
"""

# Har entry: id, name, packages (exact), prefixes, kind, verdict.
LOCK_DB = (
    {
        "id": "payjoy",
        "name": "PayJoy",
        "packages": ("com.payjoy.access",),
        "prefixes": ("com.payjoy.",),
        "kind": "finance",
        "verdict": (
            "Public removal rasta NAHI hai — sirf BYPASS / "
            "anti-relock level ke public daaway hain, is liye "
            "natija hamesha 'BYPASSED' label hoga, PERMANENT "
            "kabhi nahi. Mustaqil release qarz mukammal hone par "
            "PayJoy ki apni authorized release se hoti hai."),
    },
    {
        "id": "easybuy",
        "name": "Easybuy — Transsion Security Plugin (finance)",
        "packages": ("com.financial.service", "com.mixtel.manager"),
        "prefixes": (),
        "kind": "finance-plugin",
        "verdict": (
            "Public rasta MOJOOD hai — yehi tool ka MDM Pack: "
            "proinfo/prodnv state-layer patch + Security Plugin "
            "flow. Lekin PERMANENT sirf state-patch ke baad asal "
            "factory-reset survival check se kehlayega; sirf app "
            "disable = BYPASS."),
    },
    {
        "id": "nuovopay",
        "name": "NuovoPay",
        "packages": ("com.promobitech.nuovo",),
        "prefixes": ("com.promobitech.",),
        "kind": "finance",
        "verdict": (
            "Public removal rasta documented NAHI mila — ye "
            "sirf pehchan (detection) hai; is tool me is ka koi "
            "removal button ya daawa nahi hai."),
    },
    {
        "id": "dlight",
        "name": "d.light PayGo",
        "packages": ("com.dlight.paygo",),
        "prefixes": ("com.dlight.",),
        "kind": "finance",
        "verdict": (
            "Public removal rasta documented NAHI mila — ye "
            "sirf pehchan (detection) hai; is tool me is ka koi "
            "removal button ya daawa nahi hai."),
    },
    {
        "id": "knox_guard",
        "name": "Samsung Knox Guard (KG)",
        "packages": ("com.samsung.android.kgclient",),
        "prefixes": (),
        "kind": "platform-finance",
        "verdict": (
            "KG ki asal halat Samsung ke server par rehti hai — "
            "ye package sirf client hai. Halat parhne ke liye is "
            "tool ka 'KG Status (Samsung)' op hai; KG state ka "
            "removal/edit public NAHI hai (server category hai)."),
    },
    {
        "id": "google_dlc",
        "name": "Google Device Lock Controller (DLC)",
        "packages": ("com.google.android.devicelockcontroller",),
        "prefixes": (),
        "kind": "platform-finance",
        "verdict": (
            "Google ka apna financing-lock controller hai — "
            "public removal rasta NAHI; release finance provider "
            "ki taraf se hoti hai. M-KOPA jaisi financing aksar "
            "isi DLC ya Knox Guard ke zariye lock karti hai."),
    },
)

# Jab platform lock (KG / DLC) mile to ye note bhi lagta hai —
# research §3 ki sab se bari finding.
PLATFORM_NOTE = (
    "Note: M-KOPA jaisi financing brand-naam par lock nahi karti — "
    "lock hamesha neeche wali platform state (Knox Guard / Google "
    "DLC / MDM) se hota hai. Koi bara tool M-KOPA/NuovoPay/d.light "
    "ke NAAM par removal advertise nahi karta; jo shop-keeper "
    "'M-KOPA remove wala tool' dhoondhta hai wo asal me KG/MDM "
    "wala kaam dhoondh raha hota hai.")


def _owner_packages(dumpsys_text):
    """dumpsys device_policy text se owner package naam (heuristic)."""
    owners = set()
    for raw in (dumpsys_text or "").splitlines():
        low = raw.lower()
        if "owner" in low and "package" in low:
            # 'Device Owner: package=com.example/.Receiver' jaisi
            # lines — component wala hissa (/...) hata kar sirf
            # package naam rakho.
            for tok in raw.replace("=", " ").replace(":", " ").split():
                tok = tok.strip().strip(",;").split("/")[0]
                if tok.count(".") >= 2 and tok[0].isalpha():
                    owners.add(tok.lower())
    return owners


def classify_finance_locks(packages, dumpsys_text=""):
    """Package list (+ optional dumpsys) se finance-lock findings.

    Wapas: list of dicts — {lock_id, name, package, kind,
    is_device_owner, verdict}. Koi lock na mile to khali list.
    """
    installed = [str(p).strip() for p in (packages or []) if str(p).strip()]
    by_lower = {}
    for pkg in installed:
        by_lower.setdefault(pkg.lower(), pkg)
    owners = _owner_packages(dumpsys_text)

    findings = []
    seen_locks = set()
    for entry in LOCK_DB:
        matched = None
        for pkg in entry["packages"]:
            if pkg.lower() in by_lower:
                matched = by_lower[pkg.lower()]
                break
        if matched is None:
            for prefix in entry["prefixes"]:
                for low, orig in by_lower.items():
                    if low.startswith(prefix.lower()):
                        matched = orig
                        break
                if matched:
                    break
        if matched is None or entry["id"] in seen_locks:
            continue
        seen_locks.add(entry["id"])
        findings.append({
            "lock_id": entry["id"],
            "name": entry["name"],
            "package": matched,
            "kind": entry["kind"],
            "is_device_owner": matched.lower() in owners,
            "verdict": entry["verdict"],
        })
    return findings
