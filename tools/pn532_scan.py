#!/usr/bin/env python3
# tools/pn532_scan.py
#
# Standalone PN532 scanner for Raspberry Pi.
#
# Reads the PN532 directly over native Linux I2C (smbus2) — no Klipper,
# no MCU, no CAN bus required.  Useful for bench-testing a PN532 wired
# directly to the Pi's GPIO I2C pins before integrating with Klipper.
#
# Wiring (Pi GPIO header):
#   PN532 VCC  → Pin 1  (3.3V)
#   PN532 GND  → Pin 6  (GND)
#   PN532 SDA  → Pin 3  (GPIO2, I2C1 SDA)
#   PN532 SCL  → Pin 5  (GPIO3, I2C1 SCL)
#
# PN532 must be in I2C mode (DIP switch / solder jumper).
#
# Prerequisites:
#   sudo apt install python3-smbus2    # or: pip3 install smbus2
#   sudo raspi-config → Interface Options → I2C → Enable
#
# Usage:
#   python3 tools/pn532_scan.py [--bus N] [--address 0x24] [--debug]
#
# Examples:
#   python3 tools/pn532_scan.py
#   python3 tools/pn532_scan.py --bus 1 --address 0x24 --debug
#   python3 tools/pn532_scan.py --scan-bus        # scan I2C bus for any devices
# =============================================================================

import argparse
import logging
import os
import sys
import time

# ── smbus2 import with friendly error ────────────────────────────────────────
try:
    from smbus2 import SMBus, i2c_msg
except ImportError:
    print("ERROR: smbus2 is not installed.")
    print("       Run:  sudo apt install python3-smbus2")
    print("         or: pip3 install smbus2")
    sys.exit(1)

# ── Add the klippy extras package to sys.path so we can import pn532_driver ──
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'klippy', 'extras'))

# ── Set up a stdout logger that satisfies pn532_driver's `from .log import logger` ──
# We monkey-patch the log module before importing pn532_driver so the driver's
# logger points at our stdout handler.
import types

_stdout_logger = logging.getLogger('pn532_scan')
_stdout_logger.setLevel(logging.DEBUG)
if not _stdout_logger.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(message)s',
                                      datefmt='%H:%M:%S'))
    _stdout_logger.addHandler(_h)

# Inject a fake nfc_gates package with a log module so pn532_driver's
# relative import (from .log import logger) resolves correctly.
_nfc_gates_pkg = types.ModuleType('nfc_gates')
_nfc_gates_pkg.__path__ = [os.path.join(_REPO_ROOT, 'klippy', 'extras', 'nfc_gates')]
_nfc_gates_pkg.__package__ = 'nfc_gates'
sys.modules['nfc_gates'] = _nfc_gates_pkg

_log_mod = types.ModuleType('nfc_gates.log')
_log_mod.logger = _stdout_logger
_log_mod.configure = lambda path: None
sys.modules['nfc_gates.log'] = _log_mod

# Now import the real driver
from nfc_gates.pn532_driver import PN532Driver  # noqa: E402


# =============================================================================
# NativeI2C — drop-in replacement for Klipper's MCU_I2C using smbus2
# =============================================================================

class NativeI2C:
    """
    Wraps smbus2 raw I2C messages to mimic Klipper's MCU_I2C interface.

    MCU_I2C methods used by PN532Driver:
        i2c_write(data)           — write bytes with no preceding register byte
        i2c_read(write, read_len) — optional preceding write, then read N bytes
                                    returns {'response': bytes}
    Both use raw i2c_msg transactions so no register/command byte is prepended
    by the transport layer — the PN532 frame is sent exactly as built.
    """

    def __init__(self, bus_num, address):
        self._bus_num  = bus_num
        self._address  = address
        self.i2c_address = address
        self._bus      = SMBus(bus_num)

    def i2c_write(self, data):
        msg = i2c_msg.write(self._address, data)
        self._bus.i2c_rdwr(msg)

    def i2c_read(self, write, read_len):
        if write:
            wr_msg = i2c_msg.write(self._address, write)
            rd_msg = i2c_msg.read(self._address, read_len)
            self._bus.i2c_rdwr(wr_msg, rd_msg)
        else:
            rd_msg = i2c_msg.read(self._address, read_len)
            self._bus.i2c_rdwr(rd_msg)
        return {'response': bytes(rd_msg)}

    def close(self):
        self._bus.close()


# =============================================================================
# Bus scan helper
# =============================================================================

def scan_bus(bus_num):
    """Probe every valid I2C address and print the ones that respond."""
    print(f"Scanning I2C bus {bus_num} for devices...")
    found = []
    with SMBus(bus_num) as bus:
        for addr in range(0x03, 0x78):
            try:
                msg = i2c_msg.read(addr, 1)
                bus.i2c_rdwr(msg)
                found.append(addr)
                print(f"  0x{addr:02X}  ({addr})")
            except OSError:
                pass
    if not found:
        print("  No devices found.")
    else:
        print(f"\n{len(found)} device(s) found.")
    return found


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Scan for NFC tags using a PN532 on the Raspberry Pi I2C bus.')
    parser.add_argument('--bus',     type=int,  default=1,
                        help='I2C bus number (default: 1 = /dev/i2c-1, GPIO2/3)')
    parser.add_argument('--address', default='0x24',
                        help='PN532 I2C address in hex (default: 0x24)')
    parser.add_argument('--debug',   action='store_true',
                        help='Enable verbose PN532 protocol trace (debug=2)')
    parser.add_argument('--scan-bus', action='store_true',
                        help='Scan the I2C bus for all responding devices and exit')
    parser.add_argument('--poll',    type=float, default=2.0,
                        help='Polling interval in seconds (default: 2.0)')
    parser.add_argument('--once',    action='store_true',
                        help='Read one tag then exit (default: poll continuously)')
    args = parser.parse_args()

    address = int(args.address, 16) if args.address.startswith('0x') \
              else int(args.address)

    if args.scan_bus:
        scan_bus(args.bus)
        return

    debug_level = 2 if args.debug else 1

    print(f"PN532 scanner — I2C bus {args.bus}, address 0x{address:02X}")
    print(f"Poll interval: {args.poll}s   Debug: {debug_level}")
    print("Press Ctrl+C to stop.\n")

    i2c = NativeI2C(args.bus, address)
    driver = PN532Driver(i2c, gate=0, debug=debug_level)

    try:
        print("Initialising PN532...")
        driver.init()
        print("PN532 ready.\n")
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        print("\nTroubleshooting:")
        print(f"  1. Run with --scan-bus to confirm the device is visible on bus {args.bus}")
        print("  2. Check PN532 is in I2C mode (DIP switch / solder jumper)")
        print("  3. Check SDA→GPIO2 (Pin 3), SCL→GPIO3 (Pin 5), 3.3V, GND")
        print("  4. Confirm I2C is enabled: sudo raspi-config → Interface Options → I2C")
        i2c.close()
        sys.exit(1)

    last_uid = None
    try:
        while True:
            uid = driver.read_tag()
            if uid and uid != last_uid:
                print(f"TAG DETECTED  UID={uid}")
                last_uid = uid
                if args.once:
                    break
            elif not uid and last_uid:
                print("Tag removed.")
                last_uid = None
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        i2c.close()


if __name__ == '__main__':
    main()
