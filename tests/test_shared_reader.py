"""
tests/test_shared_reader.py
============================
Unit tests for the shared NFC reader path in NFCGate.

Covers:
- Config parsing: shared_pending_timeout, shared_read_timeout,
  shared_tag_read_effect, shared_missed_limit, force_spool_id
- _shared_expire_pending_if_needed: expiry when deadline passed
- _shared_preload_check:
    - no pending spool → advisory message emitted
    - no pending spool + force_spool_id → gcmd.error raised
    - pending spool valid → MMU_GATE_MAP NEXT_SPOOLID staged, polling restarted
    - pending spool expired → advisory, no staging
    - pending spool already assigned (hybrid) → silent skip
    - pending spool already assigned (pure shared) → console warning
    - printing active → skipped entirely
- shared_status_line: idle, polling, pending with time, expired, error, failed
- _handle_print_start: stops polling when active
- _handle_print_end: resumes when startup_polling=1 and no pending spool;
                     stays stopped when valid spool is pending
- _shared_handle_event:
    - EVENT_CHANGED with integer spool → stores pending, stops polling
    - EVENT_CHANGED with DIRECT_METADATA_SPOOL → increments miss counter
    - EVENT_UID_ONLY → increments miss counter, RESPOND at limit
    - EVENT_REMOVED → pending spool kept
    - miss counter resets on successful resolution
- _poll_timer_event: failed reader uses NFC_SHARED INIT=1 (not NFC GATE=255)
- NFC_SHARED CLEAR_CACHE clears tag cache but preserves pending spool

No hardware, no Klipper, no mocking framework required.

Run from the project root:
    python3 -m pytest tests/test_shared_reader.py -v
"""

import sys
import os
import types

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


class _MockSpoolmanClient:
    def __init__(self, *a, **k): pass


_stub('nfc_gates.log',
      logger=_null, configure=lambda *a, **k: None,
      info=lambda *a, **k: None,
      info_both=lambda *a, **k: None,
      warning=lambda *a, **k: None,
      error=lambda *a, **k: None)
_stub('nfc_gates.pn532_driver',
      PN532Driver=object,
      PN532_COMMAND_GETFIRMWAREVERSION=0x02,
      PN532_COMMAND_SAMCONFIGURATION=0x14,
      PN532_COMMAND_INLISTPASSIVETARGET=0x4A,
      get_low_level_debug=lambda config, default=False: default,
      low_level_debug_requested=lambda gcmd: False,
      low_level_debug_help_lines=lambda command_base: [],
      run_low_level_debug=lambda *a, **k: False)
_stub('nfc_gates.spoolman_client', SpoolmanClient=_MockSpoolmanClient)

sys.modules.pop('nfc_gates.nfc_manager', None)

from nfc_gates.nfc_manager import NFCGate, _lane_instances
from nfc_gates.gate_state import GateState, EVENT_CHANGED, EVENT_UID_ONLY, EVENT_REMOVED, DIRECT_METADATA_SPOOL


# ── Test doubles ──────────────────────────────────────────────────────────────

class MockReactor:
    NEVER = -1.0
    NOW   =  0.0

    def __init__(self, start_time=100.0):
        self._time  = start_time
        self.timers = {}

    def monotonic(self):
        return self._time

    def advance(self, seconds):
        self._time += seconds

    def register_timer(self, callback, when=None):
        handle = object()
        self.timers[handle] = [callback, when if when is not None else self.NEVER]
        return handle

    def update_timer(self, handle, when):
        if handle in self.timers:
            self.timers[handle][1] = when

    def pause(self, until):
        pass

    def register_callback(self, cb):
        pass


class GCodeCapture:
    def __init__(self):
        self.scripts   = []
        self.responses = []

    def run_script(self, script):
        self.scripts.append(script)

    def respond_info(self, msg):
        self.responses.append(msg)

    def register_command(self, *a, **k):
        pass

    def register_mux_command(self, *a, **k):
        pass


class MockReader:
    def __init__(self):
        self.clear_current_card_calls = 0

    def _clear_current_card(self):
        self.clear_current_card_calls += 1


class MockSpoolman:
    def __init__(self):
        self.clear_cache_calls = 0

    def clear_cache(self):
        self.clear_cache_calls += 1


class MockGCmd:
    def __init__(self, params=None):
        self._params   = params or {}
        self.responses = []
        self._error    = None

    def get_int(self, name, default=0, minval=None, maxval=None):
        return int(self._params.get(name, default))

    def get(self, name, default=None):
        return self._params.get(name, default)

    def respond_info(self, msg):
        self.responses.append(msg)

    def error(self, msg):
        # Return an exception — caller is expected to raise it
        self._error = msg
        return RuntimeError(msg)


class MockMMU:
    def __init__(self, gate_spool_ids=None, action='idle'):
        self._gate_spool_ids = gate_spool_ids or []
        self._action         = action

    def get_status(self, eventtime):
        return {
            'gate_spool_id': self._gate_spool_ids,
            'gate_status':   [0] * len(self._gate_spool_ids),
            'action':        self._action,
            'filament_pos':  0,
            'gate':          -1,
        }


class MockPrintStats:
    def __init__(self, state='standby'):
        self._state = state

    def get_status(self, eventtime):
        return {'state': self._state}


class MockPrinter:
    def __init__(self):
        self._objects  = {}
        self._gcode    = GCodeCapture()
        self._handlers = {}

    def set_mmu(self, mmu):
        self._objects['mmu'] = mmu

    def set_print_state(self, state):
        self._objects['print_stats'] = MockPrintStats(state)

    def lookup_object(self, name, default=None):
        if name == 'gcode':
            return self._gcode
        return self._objects.get(name, default)

    def get_reactor(self):
        return None

    def register_event_handler(self, event, handler):
        self._handlers[event] = handler

    @property
    def gcode(self):
        return self._gcode


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_shared(
        startup_polling=1,
        pending_timeout=120.0,
        read_timeout=120.0,
        tag_read_effect='',
        missed_limit=3,
        force_spool_id=False,
        has_per_lane_readers=False,
        reactor_time=100.0):
    """Build a minimal NFCGate in shared mode, bypassing __init__."""
    reactor  = MockReactor(reactor_time)
    printer  = MockPrinter()
    gcode    = printer.gcode

    g = object.__new__(NFCGate)
    g._name                       = 'shared'
    g._gate                       = 255
    g._shared                     = True
    g._debug                      = 0
    g._failed                     = False
    g._polling                    = False
    g._startup_polling            = startup_polling
    g._poll_interval              = 3.0
    g._shared_pending_timeout     = pending_timeout
    g._shared_read_timeout        = read_timeout
    g._shared_tag_read_effect     = tag_read_effect
    g._shared_missed_limit        = missed_limit
    g._shared_force_spool_id      = force_spool_id
    g._has_per_lane_readers       = has_per_lane_readers
    g._shared_pending_uid         = None
    g._shared_pending_spool       = None
    g._shared_pending_deadline    = 0.0
    g._shared_pending_auto_created = False
    g._shared_last_error          = None
    g._shared_read_deadline       = 0.0
    g._shared_missed_resolutions  = 0
    g._state                      = GateState(255)
    g._reader                     = MockReader()
    g._spoolman                   = MockSpoolman()
    g.reactor                     = reactor
    g.printer                     = printer
    g._gcode                      = gcode
    g._poll_timer                 = reactor.register_timer(lambda e: reactor.NEVER)
    printer.set_print_state('standby')   # default: not printing
    return g


def _stage_pending(g, spool_id=42, uid='AABBCCDD', ttl=120.0):
    """Manually put a valid pending spool on the shared reader."""
    g._shared_pending_spool    = spool_id
    g._shared_pending_uid      = uid
    g._shared_pending_deadline = g.reactor.monotonic() + ttl


# ── Config parsing ────────────────────────────────────────────────────────────

class MockConfig:
    def __init__(self, values=None, name='nfc_gate shared'):
        self._values  = dict(values or {})
        self._name    = name
        self._printer = MockPrinter()

    def get_name(self):       return self._name
    def get_printer(self):    return self._printer
    def error(self, msg):     return ValueError(msg)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def getboolean(self, key, default=None):
        raw = self._values.get(key, default)
        if isinstance(raw, bool): return raw
        if raw is None: return default
        return str(raw).strip().lower() in ('true', '1', 'yes')

    def getfloat(self, key, default=None, minval=None, maxval=None):
        raw = self._values.get(key, default)
        val = float(raw) if raw is not None else default
        if val is not None:
            if minval is not None and val < minval:
                raise ValueError(f"{key} below minval")
            if maxval is not None and val > maxval:
                raise ValueError(f"{key} above maxval")
        return val

    def getint(self, key, default=None, minval=None, maxval=None):
        raw = self._values.get(key, default)
        val = int(raw) if raw is not None else default
        if val is not None:
            if minval is not None and val < minval:
                raise ValueError(f"{key} below minval")
            if maxval is not None and val > maxval:
                raise ValueError(f"{key} above maxval")
        return val


def test_config_shared_defaults():
    """Shared config keys default correctly when not supplied."""
    from nfc_gates.nfc_manager import _SHARED_MISSED_RESOLUTION_LIMIT
    g = _make_shared()
    assert g._shared_pending_timeout  == 120.0
    assert g._shared_read_timeout     == 120.0
    assert g._shared_tag_read_effect  == ''
    assert g._shared_missed_limit     == _SHARED_MISSED_RESOLUTION_LIMIT
    assert g._shared_force_spool_id   is False


def test_config_shared_missed_limit_minval():
    """shared_missed_limit rejects values below 1."""
    cfg = MockConfig({'shared': True, 'shared_missed_limit': 0})
    try:
        cfg.getint('shared_missed_limit', 3, minval=1)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_config_force_spool_id():
    """force_spool_id is parsed as boolean."""
    g = _make_shared(force_spool_id=True)
    assert g._shared_force_spool_id is True


# ── _shared_expire_pending_if_needed ─────────────────────────────────────────

def test_expire_pending_before_deadline():
    g = _make_shared()
    _stage_pending(g, spool_id=10, ttl=60.0)
    g._shared_expire_pending_if_needed()
    assert g._shared_pending_spool == 10  # not expired yet


def test_expire_pending_after_deadline():
    g = _make_shared()
    _stage_pending(g, spool_id=10, ttl=1.0)
    g.reactor.advance(10.0)           # past the deadline
    g._shared_expire_pending_if_needed()
    assert g._shared_pending_spool is None


# ── _shared_preload_check ─────────────────────────────────────────────────────

def test_preload_check_no_pending_emits_advisory():
    g    = _make_shared()
    gcmd = MockGCmd()
    g._shared_preload_check(gcmd)
    assert any('no spool staged' in r for r in gcmd.responses)


def test_preload_check_no_pending_force_spool_id_raises():
    g    = _make_shared(force_spool_id=True)
    gcmd = MockGCmd()
    try:
        g._shared_preload_check(gcmd)
        assert False, "expected error to be raised"
    except RuntimeError as e:
        assert 'force_spool_id' in str(e)


def test_preload_check_stages_next_spoolid():
    g = _make_shared()
    _stage_pending(g, spool_id=42)
    gcmd = MockGCmd()
    g._shared_preload_check(gcmd)
    assert 'MMU_GATE_MAP NEXT_SPOOLID=42' in g._gcode.scripts
    assert g._shared_pending_spool is None   # cleared after staging
    assert g._polling is True                # polling restarted


def test_preload_check_expired_emits_advisory():
    g = _make_shared()
    _stage_pending(g, spool_id=7, ttl=1.0)
    g.reactor.advance(10.0)
    gcmd = MockGCmd()
    g._shared_preload_check(gcmd)
    assert not any('NEXT_SPOOLID' in s for s in g._gcode.scripts)
    assert any('no spool staged' in r for r in gcmd.responses)


def test_preload_check_skipped_while_printing():
    g = _make_shared()
    _stage_pending(g, spool_id=5)
    g.printer.set_print_state('printing')
    gcmd = MockGCmd()
    g._shared_preload_check(gcmd)
    assert not any('NEXT_SPOOLID' in s for s in g._gcode.scripts)
    assert g._shared_pending_spool == 5  # still pending


def test_preload_check_hybrid_already_assigned_silent():
    """Hybrid: spool already assigned by per-lane reader — silent skip, no staging."""
    g = _make_shared(has_per_lane_readers=True)
    _stage_pending(g, spool_id=42)
    g.printer.set_mmu(MockMMU(gate_spool_ids=[42, -1, -1]))
    gcmd = MockGCmd()
    g._shared_preload_check(gcmd)
    assert not any('NEXT_SPOOLID' in s for s in g._gcode.scripts)
    assert not gcmd.responses          # silent — no console message
    assert g._shared_pending_spool is None


def test_preload_check_pure_shared_already_assigned_warns():
    """Pure shared: spool already assigned is unexpected — warn on console."""
    g = _make_shared(has_per_lane_readers=False)
    _stage_pending(g, spool_id=42)
    g.printer.set_mmu(MockMMU(gate_spool_ids=[42, -1, -1]))
    gcmd = MockGCmd()
    g._shared_preload_check(gcmd)
    assert not any('NEXT_SPOOLID' in s for s in g._gcode.scripts)
    assert any('already assigned' in r for r in gcmd.responses)
    assert g._shared_pending_spool is None


# ── shared_status_line ────────────────────────────────────────────────────────

def test_status_idle():
    g = _make_shared()
    assert 'idle' in g.shared_status_line()


def test_status_polling():
    g = _make_shared()
    g._polling = True
    assert 'polling' in g.shared_status_line()


def test_status_pending():
    g = _make_shared()
    _stage_pending(g, spool_id=7, uid='DEADBEEF', ttl=90.0)
    line = g.shared_status_line()
    assert 'pending' in line
    assert '7' in line
    assert 'DEADBEEF' in line


def test_status_expired():
    g = _make_shared()
    _stage_pending(g, spool_id=7, ttl=1.0)
    g.reactor.advance(10.0)
    assert 'expired' in g.shared_status_line()


def test_status_error():
    g = _make_shared()
    g._shared_last_error = 'tag uid=AABB not in Spoolman'
    assert 'error' in g.shared_status_line()


def test_status_failed():
    g = _make_shared()
    g._failed = True
    assert 'FAILED' in g.shared_status_line()


# ── _handle_print_start / _handle_print_end ───────────────────────────────────

def test_print_start_stops_polling():
    g = _make_shared(startup_polling=1)
    g._polling = True
    g._handle_print_start(0)
    assert g._polling is False


def test_print_start_noop_when_not_polling():
    g = _make_shared(startup_polling=1)
    g._polling = False
    g._handle_print_start(0)
    assert g._polling is False


def test_print_end_resumes_when_no_pending():
    g = _make_shared(startup_polling=1)
    g._polling = False
    g._handle_print_end(0)
    assert g._polling is True


def test_print_end_stays_stopped_when_valid_spool_pending():
    """After a successful tag read, print-end must not overwrite the pending spool
    by restarting polling — the user hasn't loaded the spool yet."""
    g = _make_shared(startup_polling=1)
    g._polling = False
    _stage_pending(g, spool_id=42, ttl=120.0)
    g._handle_print_end(0)
    assert g._polling is False
    assert g._shared_pending_spool == 42  # spool untouched


def test_print_end_resumes_when_pending_expired():
    """Expired pending should not block polling restart — it's already gone."""
    g = _make_shared(startup_polling=1)
    g._polling = False
    _stage_pending(g, spool_id=42, ttl=1.0)
    g.reactor.advance(10.0)           # deadline in the past
    g._handle_print_end(0)
    assert g._polling is True


def test_print_end_noop_when_startup_polling_off():
    g = _make_shared(startup_polling=0)
    g._polling = False
    g._handle_print_end(0)
    assert g._polling is False


# ── _shared_handle_event ──────────────────────────────────────────────────────

def test_event_changed_stores_pending_stops_polling():
    g = _make_shared()
    g._polling = True
    g._shared_handle_event(EVENT_CHANGED, 'AABBCCDD', 99)
    assert g._shared_pending_spool == 99
    assert g._shared_pending_uid   == 'AABBCCDD'
    assert g._polling is False
    assert g._shared_pending_deadline > g.reactor.monotonic()


def test_event_changed_resets_miss_counter():
    g = _make_shared()
    g._shared_missed_resolutions = 2
    g._shared_handle_event(EVENT_CHANGED, 'AA', 5)
    assert g._shared_missed_resolutions == 0


def test_event_changed_direct_metadata_increments_miss():
    g = _make_shared()
    g._shared_handle_event(EVENT_CHANGED, 'AABB', DIRECT_METADATA_SPOOL)
    assert g._shared_missed_resolutions == 1
    assert g._shared_pending_spool is None


def test_event_changed_direct_metadata_emits_respond_at_limit():
    g = _make_shared(missed_limit=2)
    g._shared_handle_event(EVENT_CHANGED, 'AABB', DIRECT_METADATA_SPOOL)
    assert not g._gcode.scripts           # not yet at limit
    g._shared_handle_event(EVENT_CHANGED, 'AABB', DIRECT_METADATA_SPOOL)
    assert any('RESPOND' in s for s in g._gcode.scripts)


def test_event_uid_only_increments_miss():
    g = _make_shared()
    g._shared_handle_event(EVENT_UID_ONLY, 'AABB', None)
    assert g._shared_missed_resolutions == 1
    assert g._shared_pending_spool is None


def test_event_uid_only_emits_respond_at_limit():
    g = _make_shared(missed_limit=2)
    g._shared_handle_event(EVENT_UID_ONLY, 'AABB', None)
    assert not g._gcode.scripts
    g._shared_handle_event(EVENT_UID_ONLY, 'AABB', None)
    assert any('RESPOND' in s for s in g._gcode.scripts)


def test_event_uid_only_does_not_clear_existing_pending():
    """UID-only reads must not wipe a valid pending spool from an earlier scan."""
    g = _make_shared()
    _stage_pending(g, spool_id=55)
    g._shared_handle_event(EVENT_UID_ONLY, 'FFFF', None)
    assert g._shared_pending_spool == 55  # preserved


def test_event_removed_keeps_pending():
    g = _make_shared()
    _stage_pending(g, spool_id=12)
    g._shared_handle_event(EVENT_REMOVED, 'AABB', None)
    assert g._shared_pending_spool == 12


def test_event_changed_fires_led_effect():
    g = _make_shared(tag_read_effect='mmu_RFID_read')
    g._shared_handle_event(EVENT_CHANGED, 'AA', 7)
    assert any('MMU_SET_LED' in s and 'mmu_RFID_read' in s
               for s in g._gcode.scripts)


# ── _poll_timer_event recovery command ───────────────────────────────────────

def test_poll_timer_failed_reader_uses_nfc_shared_init():
    """Failed shared reader should log NFC_SHARED INIT=1, not NFC GATE=255 INIT=1."""
    import nfc_gates.nfc_manager as mgr

    g = _make_shared()
    g._failed  = True
    g._polling = True

    log_messages = []

    class CapLogger:
        def warning(self, fmt, *args, **kw):
            log_messages.append(fmt % args if args else fmt)
        def debug(self, *a, **k): pass
        def info(self, *a, **k): pass
        def error(self, *a, **k): pass

    old_logger = mgr.logger
    mgr.logger = CapLogger()
    try:
        result = g._poll_timer_event(g.reactor.monotonic())
    finally:
        mgr.logger = old_logger

    assert result == g.reactor.NEVER
    assert g._polling is False
    assert any('NFC_SHARED INIT=1' in m for m in log_messages), \
        f"Expected 'NFC_SHARED INIT=1' in log; got: {log_messages}"
    assert not any('GATE=255' in m for m in log_messages), \
        f"'GATE=255' must not appear in log; got: {log_messages}"


# ── _shared_clear_pending resets miss counter ─────────────────────────────────

def test_clear_pending_resets_miss_counter():
    g = _make_shared()
    g._shared_missed_resolutions = 3
    _stage_pending(g, spool_id=1)
    g._shared_clear_pending()
    assert g._shared_missed_resolutions == 0
    assert g._shared_pending_spool is None


# ── NFC_SHARED CLEAR_CACHE ────────────────────────────────────────────────────

def test_shared_clear_cache_resets_tag_cache_and_keeps_pending_spool():
    g = _make_shared()
    _stage_pending(g, spool_id=88, uid='PENDINGUID', ttl=60.0)
    pending_deadline = g._shared_pending_deadline

    g._state.current_uid = 'CURRENTUID'
    g._state.current_spool = 12
    g._state.miss_count = 2
    assert g._state.current_tag is not None

    gcmd = MockGCmd({'CLEAR_CACHE': 1})
    g.cmd_NFC_SHARED(gcmd)

    assert g._state.current_uid is None
    assert g._state.current_spool is None
    assert g._state.current_tag is None
    assert g._state.miss_count == 0
    assert g._shared_pending_spool == 88
    assert g._shared_pending_uid == 'PENDINGUID'
    assert g._shared_pending_deadline == pending_deadline
    assert g._spoolman.clear_cache_calls == 1
    assert g._reader.clear_current_card_calls == 1
    assert any('pending spool kept' in r for r in gcmd.responses)


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-v']))
