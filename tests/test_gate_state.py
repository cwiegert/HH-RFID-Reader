"""
tests/test_gate_state.py
========================
Unit tests for GateState — no hardware, no Klipper, no mocking required.

Run from the project root:
    python3 -m pytest tests/test_gate_state.py -v
or without pytest:
    python3 tests/test_gate_state.py
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
_stub('bus',
      MCU_I2C_from_config=lambda *a, **k: None,
      MCU_SPI_from_config=lambda *a, **k: None,
      MCU_I2C=object,
      MCU_SPI=object)

_nfc_pkg = _stub('nfc_gates')
_nfc_pkg.__path__    = [os.path.join(_EXTRAS, 'nfc_gates')]
_nfc_pkg.__package__ = 'nfc_gates'

_null = _NullLogger()
_stub('nfc_gates.log',
      logger=_null, configure=lambda *a, **k: None,
      info=lambda *a, **k: None,
      warning=lambda *a, **k: None,
      error=lambda *a, **k: None)
_stub('nfc_gates.pn532_driver',
      PN532Driver=object,
      PN532_COMMAND_GETFIRMWAREVERSION=0x02,
      PN532_COMMAND_SAMCONFIGURATION=0x14,
      PN532_COMMAND_INLISTPASSIVETARGET=0x4A)
_stub('nfc_gates.rc522_driver',  RC522Driver=object)
_stub('nfc_gates.spoolman_client', SpoolmanClient=object)

from nfc_gates.NFC_manager import GateState, EVENT_CHANGED, EVENT_UID_ONLY, EVENT_REMOVED


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def assert_event(event, expected_type, gate=0, uid=None, spool=None):
    assert event is not None, "Expected an event but got None"
    etype, egate, euid, espool = event
    assert etype  == expected_type, f"Event type: got {etype!r}, want {expected_type!r}"
    assert egate  == gate,          f"Gate: got {egate}, want {gate}"
    if uid   is not None: assert euid   == uid,   f"UID: got {euid!r}, want {uid!r}"
    if spool is not None: assert espool == spool, f"Spool: got {espool}, want {spool}"

def assert_silent(event):
    assert event is None, f"Expected no event but got {event!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_gate_stays_silent():
    gs = GateState(gate=0)
    assert_silent(gs.process_read(None, None))
    assert_silent(gs.process_read(None, None))

def test_spool_placed_emits_changed():
    gs = GateState(gate=0)
    event = gs.process_read('A3F200CC', 1042)
    assert_event(event, EVENT_CHANGED, gate=0, uid='A3F200CC', spool=1042)

def test_same_spool_stays_silent():
    gs = GateState(gate=0)
    gs.process_read('A3F200CC', 1042)
    assert_silent(gs.process_read('A3F200CC', 1042))
    assert_silent(gs.process_read('A3F200CC', 1042))

def test_different_spool_same_uid_emits_changed():
    """Same physical tag but spool ID changed (shouldn't happen, but handle it)."""
    gs = GateState(gate=0)
    gs.process_read('A3F200CC', 1042)
    event = gs.process_read('A3F200CC', 9999)
    assert_event(event, EVENT_CHANGED, spool=9999)

def test_different_tag_emits_changed():
    gs = GateState(gate=0)
    gs.process_read('A3F200CC', 1042)
    event = gs.process_read('B1D4A209', 207)
    assert_event(event, EVENT_CHANGED, uid='B1D4A209', spool=207)

def test_tag_without_spool_emits_uid_only():
    gs = GateState(gate=0)
    event = gs.process_read('A3F200CC', None)
    assert_event(event, EVENT_UID_ONLY, uid='A3F200CC', spool=None)

def test_debounce_suppresses_early_removal():
    """Removal is only reported after absent_threshold consecutive misses."""
    gs = GateState(gate=0, absent_threshold=3)
    gs.process_read('A3F200CC', 1042)
    assert_silent(gs.process_read(None, None))   # miss 1
    assert_silent(gs.process_read(None, None))   # miss 2
    event = gs.process_read(None, None)           # miss 3 → removed
    assert_event(event, EVENT_REMOVED, gate=0)

def test_removal_with_threshold_1():
    gs = GateState(gate=0, absent_threshold=1)
    gs.process_read('A3F200CC', 1042)
    event = gs.process_read(None, None)
    assert_event(event, EVENT_REMOVED)

def test_removal_clears_state():
    gs = GateState(gate=0, absent_threshold=1)
    gs.process_read('A3F200CC', 1042)
    gs.process_read(None, None)                  # removal
    event = gs.process_read('B1D4A209', 207)
    assert_event(event, EVENT_CHANGED, uid='B1D4A209', spool=207)

def test_intermittent_miss_resets_counter():
    """A single successful read resets the miss counter — no false removal."""
    gs = GateState(gate=0, absent_threshold=3)
    gs.process_read('A3F200CC', 1042)
    gs.process_read(None, None)   # miss 1
    gs.process_read(None, None)   # miss 2
    gs.process_read('A3F200CC', 1042)  # tag back — counter resets
    gs.process_read(None, None)   # miss 1 again
    assert_silent(gs.process_read(None, None))   # miss 2, still below threshold

def test_removal_only_fires_once():
    """After removal, further None reads should not emit additional events."""
    gs = GateState(gate=0, absent_threshold=1)
    gs.process_read('A3F200CC', 1042)
    gs.process_read(None, None)          # removal fires
    assert_silent(gs.process_read(None, None))
    assert_silent(gs.process_read(None, None))

def test_gate_index_preserved_in_event():
    for gate_num in range(5):
        gs = GateState(gate=gate_num)
        event = gs.process_read('A3F200CC', 1042)
        assert_event(event, EVENT_CHANGED, gate=gate_num)

def test_uid_only_to_spool_update():
    """Tag gains a spool ID between polls — should emit CHANGED."""
    gs = GateState(gate=0)
    gs.process_read('A3F200CC', None)
    event = gs.process_read('A3F200CC', 1042)
    assert_event(event, EVENT_CHANGED, spool=1042)


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
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
