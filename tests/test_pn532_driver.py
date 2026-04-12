"""
tests/test_pn532_driver.py
==========================
Tests for PN532Driver using a mock I2C object.

The mock I2C records every i2c_write() call and can be pre-loaded with
PN532 response frames so i2c_read() returns realistic byte sequences.
This lets us verify correct frame construction and UID parsing without
any real hardware.

Run from the project root:
    python3 -m pytest tests/test_pn532_driver.py -v
or without pytest:
    python3 tests/test_pn532_driver.py
"""

import sys
import os
import time
import types

# ── Stub Klipper dependencies before importing the package ────────────────────
_EXTRAS = os.path.join(os.path.dirname(__file__), '..', 'klippy', 'extras')
sys.path.insert(0, _EXTRAS)

def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

class _NullLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def exception(self, *a, **k): pass

# nfc_gates.log must be stubbed before importing pn532_driver so the
# relative import "from .log import logger" resolves to the stub.
_nfc_pkg = _stub('nfc_gates')
_nfc_pkg.__path__    = [os.path.join(_EXTRAS, 'nfc_gates')]
_nfc_pkg.__package__ = 'nfc_gates'
_stub('nfc_gates.log',
      logger=_NullLogger(), configure=lambda *a, **k: None,
      info=lambda *a, **k: None,
      warning=lambda *a, **k: None,
      error=lambda *a, **k: None)

# Suppress time.sleep so _ACK_DELAY_S and configurable delays don't slow tests
time.sleep = lambda _: None

from nfc_gates.pn532_driver import (
    PN532Driver,
    _CMD_SAMCONFIGURATION, _CMD_GETFIRMWAREVERSION,
    _CMD_INLISTPASSIVETARGET, _CMD_INRELEASE,
    _TFI_HOST_TO_PN532, _TFI_PN532_TO_HOST,
)


# ─────────────────────────────────────────────────────────────────────────────
# Mock I2C
# ─────────────────────────────────────────────────────────────────────────────

class MockI2C:
    """
    Mock MCU_I2C.

    Pre-load read_responses with a list of byte-lists;
    each call to i2c_read() pops the next one.  If the list is
    exhausted, returns STATUS=0x00 (busy) bytes, which the driver
    treats as a frame error.

    All i2c_write() calls are recorded in writes for inspection.
    """

    def __init__(self, read_responses=None):
        self.writes    = []
        self._responses = list(read_responses or [])

    def i2c_write(self, data):
        self.writes.append(list(data))

    def i2c_read(self, _params, read_len):
        if self._responses:
            resp = self._responses.pop(0)
        else:
            resp = [0x00] * read_len   # STATUS=0x00 = busy
        return {'response': resp}

    def wrote_cmd(self, cmd_byte):
        """Return True if any i2c_write() contained cmd_byte in a valid frame."""
        for w in self.writes:
            if (len(w) > 6
                    and w[5] == _TFI_HOST_TO_PN532
                    and w[6] == cmd_byte):
                return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Response frame builders
# ─────────────────────────────────────────────────────────────────────────────

def _make_response(cmd_resp, payload=()):
    """Build a PN532→host response frame as i2c_read() would return it."""
    data   = [_TFI_PN532_TO_HOST, cmd_resp] + list(payload)
    length = len(data)
    lcs    = (-length) & 0xFF
    dcs    = (-sum(data)) & 0xFF
    return [0x01, 0x00, 0x00, 0xFF, length, lcs] + data + [dcs, 0x00]


def _sam_ok():       return _make_response(0x15)
def _firmware_ok():  return _make_response(0x03, [0x07, 0x01, 0x06, 0x07])
def _release_ok():   return _make_response(0x53, [0x00])
def _busy():         return [0x00] * 32

def _inlist_tag(uid=(0xA3, 0xF2, 0x00, 0xCC)):
    payload = [1, 1, 0x00, 0x04, 0x08, len(uid)] + list(uid)
    return _make_response(0x4B, payload)

def _inlist_no_tag():
    return _make_response(0x4B, [0])


# ─────────────────────────────────────────────────────────────────────────────
# _transceive() response helpers
#
# Each PN532 command now goes through _transceive(), which makes 4 i2c_read()
# calls per command:
#   1. _read_ack() ready poll  — 1 byte,  expects [0x01]
#   2. _read_ack() ACK frame   — 7 bytes, expects [0x01, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00]
#   3. _recv()    ready poll   — 1 byte,  expects [0x01]
#   4. _recv()    response     — N bytes, the actual PN532 response frame
#
# Use _cmd(response_frame) to build the 4-entry list for one command.
# Chain multiple calls with + to build sequences for init(), read_tag(), etc.
# ─────────────────────────────────────────────────────────────────────────────

_ACK_FRAME = [0x01, 0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00]

def _cmd(response_frame):
    """4 mock i2c_read() returns needed for one successful _transceive() call."""
    return [
        [0x01],         # _read_ack: ready poll
        _ACK_FRAME,     # _read_ack: ACK frame
        [0x01],         # _recv: ready poll
        response_frame, # _recv: full response frame
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_init_sends_samconfiguration():
    # init() wakes the PN532 with GetFirmwareVersion, then sends SAMConfiguration.
    # Each _transceive() call needs 4 mock reads: ready, ACK, ready, response.
    i2c = MockI2C(read_responses=_cmd(_firmware_ok()) + _cmd(_sam_ok()))
    driver = PN532Driver(i2c, gate=0, crc_delay=0.0)
    driver.init()
    assert i2c.wrote_cmd(_CMD_SAMCONFIGURATION), \
        "init() did not send SAMConfiguration"

def test_is_alive_returns_true_on_firmware_response():
    i2c = MockI2C(read_responses=_cmd(_firmware_ok()))
    driver = PN532Driver(i2c, gate=0, crc_delay=0.0)
    assert driver.is_alive() is True

def test_is_alive_returns_false_on_bad_response():
    # Provide all-busy bytes so every read returns 0x00 (not ready); driver gives up.
    i2c = MockI2C(read_responses=[_busy()] * 8)
    driver = PN532Driver(i2c, gate=0, crc_delay=0.0)
    assert driver.is_alive() is False

def test_no_tag_returns_none():
    """InListPassiveTarget NbTg=0 → read_tag() returns None."""
    i2c = MockI2C(read_responses=_cmd(_inlist_no_tag()))
    driver = PN532Driver(i2c, gate=0, transceive_delay=0.0, crc_delay=0.0)
    assert driver.read_tag() is None

def test_tag_present_returns_uid():
    """Happy path: 4-byte UID → correct uppercase hex string returned."""
    i2c = MockI2C(read_responses=_cmd(_inlist_tag((0xA3, 0xF2, 0x00, 0xCC)))
                                 + _cmd(_release_ok()))
    driver = PN532Driver(i2c, gate=0, transceive_delay=0.0, crc_delay=0.0)
    result = driver.read_tag()
    assert result == 'A3F200CC', f"Expected 'A3F200CC', got {result!r}"

def test_tag_7byte_uid():
    """7-byte UID (NTAG216) is returned as 14-char hex string."""
    uid = (0x04, 0xA2, 0x3B, 0xC1, 0xD4, 0x5E, 0x80)
    i2c = MockI2C(read_responses=_cmd(_inlist_tag(uid)) + _cmd(_release_ok()))
    driver = PN532Driver(i2c, gate=0, transceive_delay=0.0, crc_delay=0.0)
    result = driver.read_tag()
    assert result == '04A23BC1D45E80', f"Expected '04A23BC1D45E80', got {result!r}"

def test_inlist_command_sent():
    """read_tag() must send InListPassiveTarget."""
    i2c = MockI2C(read_responses=_cmd(_inlist_tag()) + _cmd(_release_ok()))
    driver = PN532Driver(i2c, gate=0, transceive_delay=0.0, crc_delay=0.0)
    driver.read_tag()
    assert i2c.wrote_cmd(_CMD_INLISTPASSIVETARGET), \
        "read_tag() did not send InListPassiveTarget"

def test_inrelease_sent_after_tag_found():
    """read_tag() must send InRelease after successfully detecting a tag."""
    i2c = MockI2C(read_responses=_cmd(_inlist_tag()) + _cmd(_release_ok()))
    driver = PN532Driver(i2c, gate=0, transceive_delay=0.0, crc_delay=0.0)
    driver.read_tag()
    assert i2c.wrote_cmd(_CMD_INRELEASE), \
        "read_tag() did not send InRelease after tag detection"

def test_build_frame_structure():
    """_build_frame() produces correct preamble, LEN, LCS, TFI, and CMD."""
    frame = PN532Driver._build_frame([_CMD_SAMCONFIGURATION, 0x01, 0x00, 0x00])
    assert frame[0] == 0x00 and frame[1] == 0x00 and frame[2] == 0xFF, \
        "Missing preamble / start code"
    assert frame[3] == 5, f"LEN expected 5, got {frame[3]}"
    assert (frame[3] + frame[4]) & 0xFF == 0, "LCS checksum invalid"
    assert frame[5] == _TFI_HOST_TO_PN532, "TFI byte wrong"
    assert frame[6] == _CMD_SAMCONFIGURATION, "CMD byte wrong"

def test_check_frame_returns_payload():
    """Well-formed response frame → _check_frame returns payload bytes."""
    driver  = PN532Driver(MockI2C(), gate=0, crc_delay=0.0)
    raw     = bytearray(_make_response(0x03, [0x07, 0x01, 0x06, 0x07]))
    payload = driver._check_frame(raw, 0x03)
    assert payload == [0x07, 0x01, 0x06, 0x07], f"Payload mismatch: {payload}"

def test_check_frame_rejects_not_ready():
    """STATUS=0x00 (busy) → _check_frame returns None."""
    driver = PN532Driver(MockI2C(), gate=0, crc_delay=0.0)
    raw    = bytearray(_make_response(0x15))
    raw[0] = 0x00   # force STATUS = not ready
    assert driver._check_frame(raw, 0x15) is None

def test_check_frame_rejects_wrong_cmd():
    """Unexpected CMD_RESP byte → _check_frame returns None."""
    driver = PN532Driver(MockI2C(), gate=0, crc_delay=0.0)
    raw    = bytearray(_make_response(0x15))   # SAMConfiguration response
    assert driver._check_frame(raw, 0x03) is None  # but we expect firmware


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests  = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL  {fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
