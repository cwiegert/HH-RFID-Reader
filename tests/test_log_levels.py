"""
tests/test_log_levels.py
========================
Unit tests for log._normalise_level — the function that maps
console_log_level config values to Python logging levels.

Numeric scale:
    1  (or 'error')   -> logging.ERROR    errors only
    2  (or 'warning') -> logging.WARNING  warnings + errors
    3  (or 'info')    -> logging.INFO     info + warnings + errors (real-time debug)

Run from the project root:
    python3 tests/test_log_levels.py
"""

import sys
import os
import logging
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                '..', 'klippy', 'extras', 'nfc_gates'))

# log.py creates a FileHandler at module import time (~/printer_data/logs/).
# That path does not exist in CI / dev environments, so we replace it with a
# NullHandler factory so _build_logger() runs without touching the filesystem.
with unittest.mock.patch('logging.FileHandler',
                         side_effect=lambda *a, **k: logging.NullHandler()):
    import log as _log_module

_normalise_level = _log_module._normalise_level


# ── Numeric string keys (as read from config file) ───────────────────────────

def test_numeric_string_1_is_error():
    assert _normalise_level('1') == logging.ERROR

def test_numeric_string_2_is_warning():
    assert _normalise_level('2') == logging.WARNING

def test_numeric_string_3_is_info():
    assert _normalise_level('3') == logging.INFO


# ── Integer keys (passed programmatically) ────────────────────────────────────

def test_int_1_is_error():
    assert _normalise_level(1) == logging.ERROR

def test_int_2_is_warning():
    assert _normalise_level(2) == logging.WARNING

def test_int_3_is_info():
    assert _normalise_level(3) == logging.INFO


# ── Named string keys ─────────────────────────────────────────────────────────

def test_string_error_is_error():
    assert _normalise_level('error') == logging.ERROR

def test_string_warning_is_warning():
    assert _normalise_level('warning') == logging.WARNING

def test_string_warn_is_warning():
    assert _normalise_level('warn') == logging.WARNING

def test_string_info_is_info():
    assert _normalise_level('info') == logging.INFO


# ── Case insensitivity ────────────────────────────────────────────────────────

def test_uppercase_warning():
    assert _normalise_level('WARNING') == logging.WARNING

def test_mixed_case_error():
    assert _normalise_level('Error') == logging.ERROR


# ── Unknown values fall back to default ──────────────────────────────────────

def test_unknown_string_returns_default():
    assert _normalise_level('bogus') == logging.WARNING

def test_unknown_string_custom_default():
    assert _normalise_level('bogus', logging.ERROR) == logging.ERROR

def test_unknown_int_returns_default():
    assert _normalise_level(99) == logging.WARNING


# ── Ordering sanity: 1 is quieter than 2, 2 is quieter than 3 ───────────────

def test_level_ordering():
    """Higher numeric value = more output = lower logging threshold."""
    assert _normalise_level(1) > _normalise_level(2) > _normalise_level(3)


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
