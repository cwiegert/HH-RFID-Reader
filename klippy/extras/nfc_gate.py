# klippy/extras/nfc_gate.py
#
# Klipper entry point for [nfc_gate] and [nfc_gate laneN] config sections.
#
# This file must live at the top level of extras/ so Klipper can find it
# by config section name.  All implementation lives in nfc_gates/manager.py.
#
# Hardware path: one PN532 per EBB42 lane board (I2C, per-lane MCU).
# For the shared-MCU / Pico path (RC522 or PN532 on one MCU), use [nfc_gates].
#
# Install
# ───────
# 1. Copy klippy/extras/nfc_gates/  →  ~/klipper/klippy/extras/nfc_gates/
# 2. Copy klippy/extras/nfc_gate.py →  ~/klipper/klippy/extras/nfc_gate.py
# 3. Copy config/nfc_macros.cfg     →  ~/printer_data/config/
# 4. Add to printer.cfg:
#      [include nfc_vars.cfg]
#      [include nfc_macros.cfg]
#      [include nfc_gate_i2c_pn532.cfg]
# 5. sudo systemctl restart klipper

from nfc_gates.NFC_manager import NfcGate, NfcGateDefaults, _lane_instances


def load_config(config):
    # Handles the base [nfc_gate] section — shared defaults only, no hardware.
    return NfcGateDefaults(config)


def load_config_prefix(config):
    # Handles [nfc_gate lane0], [nfc_gate lane1], etc.
    printer  = config.get_printer()
    defaults = printer.lookup_object('nfc_gate', None)
    gate     = NfcGate(config, defaults)
    _lane_instances.append(gate)
    return gate
