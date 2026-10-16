"""TechStream for StarView: Toyota diagnostics (trouble codes, hidden settings, live data, battery) on the tablet.

Taken from toyopilot (github.com/lochuan/lean-mici, openpilot/system/lanlinkd/toyota, MIT) and translated to English.
Their catalog (data/sienna_catalog.json, 4th-gen Sienna) is their Carista-derived data, translated.
Changes for StarPilot: served by starviewd over the tablet link (not lanlinkd/Sanic on the hotspot), and pandad is paused
with a /dev/shm flag file instead of a new params key (see session.py and system/manager/process_config.py).
"""
