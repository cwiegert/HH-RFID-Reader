# klippy/extras/nfc_gates/log.py
#
# Dedicated logger for all NFC gate modules.
#
# All nfc_gate / nfc_gates output goes to nfc_reader.log (same directory as
# klippy.log).  Operational messages that call info()/warning()/error() also
# go to klippy.log.  Optional UI console output is configured by NFC_manager
# after reading printer.cfg.
#
# Usage (from any module in this package):
#   from .log import logger           # inside nfc_gates/
#   from nfc_gates.log import logger  # from nfc_gate.py (top-level extra)

import logging
import os

_LOGGER_NAME = 'nfc_gate'
_LOG_FILENAME = 'nfc_reader.log'
_CONSOLE_HANDLER_NAME = 'nfc_gate_console'
_LEVELS = {
    'debug': logging.DEBUG,
    '0': logging.DEBUG,
    'error': logging.ERROR,
    '1': logging.ERROR,     # 1 = errors only
    'warning': logging.WARNING,
    'warn': logging.WARNING,
    '2': logging.WARNING,   # 2 = warnings and errors
    'info': logging.INFO,
    '3': logging.INFO,      # 3 = info, warnings, and errors (real-time debug)
}

_console_gcode = None
_console_reactor = None
_console_enabled = False
_console_level = logging.WARNING


def _normalise_level(level, default=logging.WARNING):
    if isinstance(level, int):
        return {
            0: logging.DEBUG,
            1: logging.ERROR,    # 1 = errors only
            2: logging.WARNING,  # 2 = warnings and errors
            3: logging.INFO,     # 3 = info, warnings, and errors (real-time debug)
        }.get(level, default)
    return _LEVELS.get(str(level).strip().lower(), default)


def _format_record_message(record):
    try:
        return record.getMessage()
    except Exception:
        return str(record.msg)


def _respond_to_console(record):
    """
    Send selected NFC log messages to the Klipper console.

    Info/warning output is controlled by console_output + console_log_level.
    Errors are always sent once a gcode object is configured, matching the
    troubleshooting behavior we want during hardware bring-up.
    """
    global _console_gcode, _console_reactor
    if _console_gcode is None:
        return
    if record.levelno < logging.INFO:
        return
    if record.levelno < logging.ERROR:
        if not _console_enabled or record.levelno < _console_level:
            return

    msg = _format_record_message(record)

    def _send(_eventtime=None, message=msg, levelno=record.levelno):
        try:
            if levelno >= logging.ERROR:
                if hasattr(_console_gcode, 'respond'):
                    _console_gcode.respond("NFC: %s" % message)
                elif hasattr(_console_gcode, 'respond_raw'):
                    _console_gcode.respond_raw("!! NFC: %s" % message)
                else:
                    _console_gcode.respond_info("ERROR: NFC: %s" % message)
            else:
                _console_gcode.respond_info("NFC: %s" % message)
        except Exception:
            # Never allow UI notification failure to recurse through logging.
            pass

    if _console_reactor is not None:
        try:
            _console_reactor.register_callback(_send)
            return
        except Exception:
            pass
    _send()


class _GCodeConsoleHandler(logging.Handler):
    name = _CONSOLE_HANDLER_NAME

    def emit(self, record):
        _respond_to_console(record)


def _find_klipper_log_dir():
    """
    Return the directory that klippy.log lives in by inspecting the root
    logger's FileHandler(s).  Falls back to ~/printer_data/logs if none found.
    """
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            return os.path.dirname(os.path.abspath(handler.baseFilename))
    return os.path.expanduser('~/printer_data/logs')


def _build_logger():
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger  # Already configured (e.g. reloaded config)

    log_path = os.path.join(_find_klipper_log_dir(), _LOG_FILENAME)

    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'))

    logger.addHandler(fh)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # Do not forward to klippy.log / root logger

    return logger


def configure(path='', printer=None, console_output=None, console_log_level=None):
    """
    Redirect the NFC logger to *path*.

    Called from NFCGateManager.__init__ after reading log_file from config.
    Replaces the existing FileHandler so the configured path takes effect
    even though the logger was created at import time.
    Expands ~ automatically.  If *path* is a bare filename (no directory
    component), it is placed in the same directory as klippy.log.
    """
    if path:
        expanded = os.path.expanduser(path)
        if not os.path.dirname(expanded):
            expanded = os.path.join(_find_klipper_log_dir(), expanded)
        _lg = logging.getLogger(_LOGGER_NAME)
        for h in _lg.handlers[:]:
            if isinstance(h, logging.FileHandler):
                _lg.removeHandler(h)
                h.close()
        _lg.propagate = False
        fh = logging.FileHandler(expanded)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)-8s %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'))
        _lg.addHandler(fh)

    if (printer is not None or console_output is not None or
            console_log_level is not None):
        configure_console(printer, console_output, console_log_level)


def configure_console(printer=None, enabled=None, level=None):
    """
    Configure optional Fluidd/Mainsail console output.

    Errors are always sent to the console once *printer* is available.  Info
    and warning records are sent only when *enabled* is true and the record
    level is at or above *level*.
    """
    global _console_gcode, _console_reactor, _console_enabled, _console_level

    if printer is not None:
        try:
            _console_gcode = printer.lookup_object('gcode')
        except Exception:
            _console_gcode = None
        try:
            _console_reactor = printer.get_reactor()
        except Exception:
            _console_reactor = None
    if enabled is not None:
        _console_enabled = bool(enabled)
    if level is not None:
        _console_level = _normalise_level(level, _console_level)

    _lg = logging.getLogger(_LOGGER_NAME)
    for h in _lg.handlers:
        if isinstance(h, _GCodeConsoleHandler):
            return
    _lg.addHandler(_GCodeConsoleHandler())


def log_both(level, msg, *args, **kwargs):
    """
    Write a message to the dedicated NFC logger and to Klipper's root logger.

    High-volume trace logging should continue to call logger.debug() directly
    so it stays in nfc_reader.log only.  Operational info/warning/error
    messages can call this helper to appear in both nfc_reader.log and
    klippy.log.
    """
    getattr(logger, level)(msg, *args, **kwargs)
    getattr(logging.getLogger(), level)(msg, *args, **kwargs)


def info(msg, *args, **kwargs):
    log_both('info', msg, *args, **kwargs)


def warning(msg, *args, **kwargs):
    log_both('warning', msg, *args, **kwargs)


def error(msg, *args, **kwargs):
    log_both('error', msg, *args, **kwargs)


# Module-level singleton — imported by every nfc_gate* module.
logger = _build_logger()
