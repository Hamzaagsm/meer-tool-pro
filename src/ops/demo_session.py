"""demo_session.py — Demo operation ka plugin wrapper (asal logic src/demo.py me hai)."""

import demo as _demo

OP = {
    "id": "demo_session",
    "category": "Demo",
    "name": "DEMO: Full Session (Detect → Info → FRP)",
    "engine": "demo",
    "modes": (),
    "server_required": False,
}


def run(ctx) -> bool:
    return _demo.run_demo_session(ctx)
