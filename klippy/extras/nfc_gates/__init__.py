# klippy/extras/nfc_gates/__init__.py
#
# EMU NFC Gate Reader — Klipper extras package entry point.
#
# Handles the [nfc_gates] config section (SPI/RC522 or I2C/PN532 path,
# all readers on a single shared MCU).
#
# For the per-lane I2C/PN532 path (one reader per EBB42 lane board),
# see the sibling module: klippy/extras/nfc_gate.py

from .NFC_manager import NFCGateManager


def load_config(config):
    return NFCGateManager(config)
