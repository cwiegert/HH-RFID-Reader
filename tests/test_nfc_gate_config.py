"""
tests/test_nfc_gate_config.py
==============================
Unit tests for NfcGateDefaults — the [nfc_gate] base section handler.

These tests exercise the config-reading layer without any Klipper runtime or
hardware.  NfcGate itself is not tested here because it requires MCU_I2C.lookup()
which pulls in the full Klipper bus stack.

Run from the project root:
    python3 -m pytest tests/test_nfc_gate_config.py -v
or without pytest:
    python3 tests/test_nfc_gate_config.py
"""

import sys
import os
import types

# ── Stub Klipper and driver dependencies so manager.py can be imported ────────
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

_stub('extras')
_stub('extras.bus')

_nfc_pkg = _stub('nfc_gates')
_nfc_pkg.__path__    = [os.path.join(_EXTRAS, 'nfc_gates')]
_nfc_pkg.__package__ = 'nfc_gates'

_stub('nfc_gates.log',            logger=_NullLogger(), configure=lambda p: None)
_stub('nfc_gates.pn532_driver',   PN532Driver=object)
_stub('nfc_gates.rc522_driver',   RC522Driver=object)
_stub('nfc_gates.spoolman_client', SpoolmanClient=object)

from nfc_gates.NFC_manager import NfcGateDefaults


# ─────────────────────────────────────────────────────────────────────────────
# Minimal mock Klipper config object
# ─────────────────────────────────────────────────────────────────────────────

class MockConfig:
    """
    Lightweight stand-in for Klipper's ConfigWrapper.

    Supports the same get / getfloat / getint signatures used by
    NfcGateDefaults, including minval / maxval validation.
    """

    def __init__(self, values=None, name='nfc_gate'):
        self._values = dict(values or {})
        self._name   = name

    def get_name(self):
        return self._name

    def error(self, msg):
        return ValueError(msg)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def getfloat(self, key, default=None, minval=None, maxval=None):
        raw = self._values.get(key, default)
        val = float(raw) if raw is not None else default
        if val is not None:
            if minval is not None and val < minval:
                raise ValueError(f"{key}={val} below minval={minval}")
            if maxval is not None and val > maxval:
                raise ValueError(f"{key}={val} above maxval={maxval}")
        return val

    def getint(self, key, default=None, minval=None, maxval=None):
        raw = self._values.get(key, default)
        val = int(raw) if raw is not None else default
        if val is not None:
            if minval is not None and val < minval:
                raise ValueError(f"{key}={val} below minval={minval}")
            if maxval is not None and val > maxval:
                raise ValueError(f"{key}={val} above maxval={maxval}")
        return val


# ─────────────────────────────────────────────────────────────────────────────
# NfcGateDefaults — built-in defaults (empty base section)
# ─────────────────────────────────────────────────────────────────────────────

def test_defaults_built_in_values():
    """Empty [nfc_gate] section yields the documented built-in defaults."""
    d = NfcGateDefaults(MockConfig())
    assert d.spoolman_url       == ''
    assert d.spoolman_rfid_key  == 'rfid'
    assert d.spoolman_timeout   == 5.0
    assert d.spoolman_cache_ttl == 300.0
    assert d.poll_interval      == 30.0
    assert d.absent_threshold   == 3
    assert d.transceive_delay   == 0.250
    assert d.crc_delay          == 0.050
    assert d.debug              == 1


def test_defaults_all_keys_overridden():
    """Every key in [nfc_gate] can be set and is reflected in the object."""
    d = NfcGateDefaults(MockConfig({
        'spoolman_url':       'http://192.168.1.50:7912',
        'spoolman_rfid_key':  'nfc_uid',
        'spoolman_timeout':   10.0,
        'spoolman_cache_ttl': 600.0,
        'poll_interval':      60.0,
        'absent_threshold':   5,
        'transceive_delay':   0.5,
        'crc_delay':          0.1,
        'debug':              2,
    }))
    assert d.spoolman_url       == 'http://192.168.1.50:7912'
    assert d.spoolman_rfid_key  == 'nfc_uid'
    assert d.spoolman_timeout   == 10.0
    assert d.spoolman_cache_ttl == 600.0
    assert d.poll_interval      == 60.0
    assert d.absent_threshold   == 5
    assert d.transceive_delay   == 0.5
    assert d.crc_delay          == 0.1
    assert d.debug              == 2


def test_defaults_partial_override():
    """Only the keys present in the section are changed; others stay at defaults."""
    d = NfcGateDefaults(MockConfig({
        'spoolman_url': 'http://mainsailos.local:7912',
        'debug':        0,
    }))
    assert d.spoolman_url     == 'http://mainsailos.local:7912'
    assert d.debug            == 0
    assert d.poll_interval    == 30.0
    assert d.absent_threshold == 3


# ─────────────────────────────────────────────────────────────────────────────
# NfcGateDefaults — range validation
# ─────────────────────────────────────────────────────────────────────────────

def test_defaults_poll_interval_below_min_raises():
    try:
        NfcGateDefaults(MockConfig({'poll_interval': 0.5}))
        assert False, "Expected ValueError for poll_interval below minval"
    except (ValueError, Exception):
        pass


def test_defaults_debug_above_max_raises():
    try:
        NfcGateDefaults(MockConfig({'debug': 3}))
        assert False, "Expected ValueError for debug above maxval"
    except (ValueError, Exception):
        pass


def test_defaults_absent_threshold_zero_raises():
    try:
        NfcGateDefaults(MockConfig({'absent_threshold': 0}))
        assert False, "Expected ValueError for absent_threshold=0"
    except (ValueError, Exception):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
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
