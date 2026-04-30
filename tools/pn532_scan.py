#!/usr/bin/env python3
# pn532_scan.py
#
# Standalone PN532 I2C scanner for Raspberry Pi.
# No Klipper, no MMU, no Spoolman — just the PN532.
#
# Wiring (Pi GPIO header):
#   PN532 VCC → Pin 1  (3.3V)
#   PN532 GND → Pin 6  (GND)
#   PN532 SDA → Pin 3  (GPIO2, I2C1 SDA)
#   PN532 SCL → Pin 5  (GPIO3, I2C1 SCL)
#
# PN532 must be in I2C mode (DIP switch / solder jumper).
#
# Prerequisites:
#   sudo apt install python3-smbus2
#   sudo raspi-config → Interface Options → I2C → Enable
#
# Usage:
#   python3 pn532_scan.py [--bus N] [--address 0x24] [--debug] [--scan-bus]

import argparse
import json
import sys
import time

from pathlib import Path

try:
    from smbus2 import SMBus, i2c_msg
except ImportError:
    print("ERROR: smbus2 is not installed.")
    print("       Run:  sudo apt install python3-smbus2")
    sys.exit(1)

SpoolmanClient = None
for _client_dir in (
        Path(__file__).resolve().parents[1] / 'klippy' / 'extras' / 'nfc_gates',
        Path.cwd() / 'klippy' / 'extras' / 'nfc_gates'):
    if (_client_dir / 'spoolman_client.py').exists():
        sys.path.insert(0, str(_client_dir))
        try:
            from spoolman_client import SpoolmanClient
        except ImportError:
            SpoolmanClient = None
        break

# ─────────────────────────────────────────────────────────────────────────────
# PN532 frame constants
# ─────────────────────────────────────────────────────────────────────────────

_TFI_HOST  = 0xD4   # direction byte: host → PN532
_TFI_PN532 = 0xD5   # direction byte: PN532 → host

_CMD_GETFIRMWAREVERSION  = 0x02
_CMD_SAMCONFIGURATION    = 0x14
_CMD_INLISTPASSIVETARGET = 0x4A
_CMD_INRELEASE           = 0x52

_STATUS_READY = 0x01
_STATUS_BUSY  = 0x00

_MAX_RESPONSE = 32

# The PN532 ACK frame (I2C form): status byte + ACK pattern
# STATUS(0x01) + 00 00 FF 00 FF 00
_ACK_FRAME = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])


# ─────────────────────────────────────────────────────────────────────────────
# Frame construction
# ─────────────────────────────────────────────────────────────────────────────

def build_frame(cmd_and_params):
    """
    Build a complete PN532 host-to-chip command frame.

    Format: [0x00, 0x00, 0xFF, LEN, LCS, TFI, CMD, params..., DCS, 0x00]
    """
    data   = [_TFI_HOST] + list(cmd_and_params)
    length = len(data)
    lcs    = (-length) & 0xFF
    dcs    = (-sum(data)) & 0xFF
    return [0x00, 0x00, 0xFF, length, lcs] + data + [dcs, 0x00]


# ─────────────────────────────────────────────────────────────────────────────
# Raw I2C primitives
# ─────────────────────────────────────────────────────────────────────────────

def i2c_write(bus, address, data):
    """Write a list of bytes to the device."""
    msg = i2c_msg.write(address, data)
    bus.i2c_rdwr(msg)


def i2c_read(bus, address, read_len):
    """Read read_len bytes from the device. Returns bytes."""
    msg = i2c_msg.read(address, read_len)
    bus.i2c_rdwr(msg)
    return bytes(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Frame parsing and detection
# ─────────────────────────────────────────────────────────────────────────────

def is_ack_frame(raw):
    """
    Return True if raw (without the leading status byte) matches the PN532
    ACK pattern: 00 00 FF 00 FF 00

    The PN532 sends ACK to confirm it received a command. It is NOT a
    response — the actual response comes in a subsequent ready+read cycle.
    """
    # raw may include trailing zeros; only the first 6 bytes matter
    return len(raw) >= 6 and bytes(raw[:6]) == _ACK_FRAME


def parse_response_frame(raw, expected_cmd_resp):
    """
    Validate a full read buffer (without the leading status byte) and return
    the payload bytes, or None if the frame is invalid or not the expected cmd.

    I2C response frame layout (after stripping the leading status byte):
      [0x00, 0x00, 0xFF, LEN, LCS, TFI, CMD_RESP, payload..., DCS, 0x00]

    expected_cmd_resp is the command code + 1 (e.g. 0x03 for GetFirmwareVersion).
    """
    if len(raw) < 8:
        return None
    if raw[0] != 0x00 or raw[1] != 0x00 or raw[2] != 0xFF:
        return None    # bad preamble / start code
    if raw[5] != _TFI_PN532:
        return None    # wrong direction byte
    if raw[6] != expected_cmd_resp:
        return None    # not the response we're waiting for
    length  = raw[3]
    payload = list(raw[7: 7 + length - 2])
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# PN532 send / receive
# ─────────────────────────────────────────────────────────────────────────────

def pn532_send(bus, address, cmd_and_params, debug=False):
    """Write a command frame to the PN532."""
    frame = build_frame(cmd_and_params)
    if debug:
        print(f"    TX cmd=0x{cmd_and_params[0]:02X}  "
              f"frame={' '.join('%02X' % b for b in frame)}")
    i2c_write(bus, address, frame)


def pn532_recv(bus, address, expected_cmd_resp,
               read_len=_MAX_RESPONSE, timeout=2.0,
               poll_interval=0.010, debug=False):
    """
    Poll the PN532 until it is ready, then read and validate the response.

    The PN532 uses a two-step response sequence after receiving a command:
      Step 1: poll returns 0x01 (ready) → full read returns the ACK frame
              (00 00 FF 00 FF 00) — this confirms receipt of the command,
              NOT the actual response.
      Step 2: poll returns 0x01 (ready) → full read returns the actual
              response frame (D5 CMD+1 payload...).

    We must not mistake the ACK for the response. This function keeps
    cycling through poll → read until it gets a valid response frame
    or the timeout expires.

    Returns the payload bytes on success, or None on timeout/error.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        # ── Poll: 1-byte read to check readiness ──────────────────────────
        try:
            status_byte = i2c_read(bus, address, 1)[0]
        except Exception as e:
            if debug:
                print(f"    poll error: {e}")
            time.sleep(poll_interval)
            continue

        if debug:
            print(f"    poll  status=0x{status_byte:02X}  "
                  f"({'ready' if status_byte == _STATUS_READY else 'busy'})")

        if status_byte != _STATUS_READY:
            time.sleep(poll_interval)
            continue

        # ── Full read ──────────────────────────────────────────────────────
        # The first byte of the full read is the status byte again (I2C mode).
        # Remaining bytes are the frame.
        try:
            full = i2c_read(bus, address, 1 + read_len)
        except Exception as e:
            if debug:
                print(f"    full read error: {e}")
            time.sleep(poll_interval)
            continue

        status_byte2 = full[0]
        frame_bytes  = full[1:]

        if debug:
            print(f"    RX  status=0x{status_byte2:02X}  "
                  f"data={' '.join('%02X' % b for b in frame_bytes)}")

        # ── ACK detection ──────────────────────────────────────────────────
        if is_ack_frame(frame_bytes):
            if debug:
                print("    ACK received — waiting for actual response")
            # ACK is not the response; go back and poll again
            time.sleep(poll_interval)
            continue

        # ── Response frame validation ──────────────────────────────────────
        payload = parse_response_frame(frame_bytes, expected_cmd_resp)
        if payload is not None:
            if debug:
                print(f"    response OK  cmd=0x{expected_cmd_resp:02X}  "
                      f"payload={' '.join('%02X' % b for b in payload)}")
            return payload

        # Frame received but not the one we want — keep waiting
        if debug:
            print(f"    unexpected frame (expected cmd=0x{expected_cmd_resp:02X}) — continuing")
        time.sleep(poll_interval)

    if debug:
        remaining = deadline - time.time()
        print(f"    timeout waiting for cmd=0x{expected_cmd_resp:02X} response")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PN532 commands
# ─────────────────────────────────────────────────────────────────────────────

def pn532_get_firmware_version(bus, address, debug=False):
    """
    Send GetFirmwareVersion and return (IC, Ver, Rev, Support) or None.

    Also serves as the wake command — send it first on startup to bring
    the PN532 out of power-save mode.
    """
    pn532_send(bus, address, [_CMD_GETFIRMWAREVERSION], debug)
    # Response command code = 0x02 + 1 = 0x03
    payload = pn532_recv(bus, address, 0x03, read_len=15, timeout=1.0, debug=debug)
    if payload and len(payload) >= 4:
        return tuple(payload[:4])   # (IC, Ver, Rev, Support)
    return None


def pn532_sam_configuration(bus, address, debug=False):
    """
    Send SAMConfiguration: Normal mode, no timeout, no IRQ.
    Returns True on success.
    """
    pn532_send(bus, address, [_CMD_SAMCONFIGURATION, 0x01, 0x00, 0x00], debug)
    # Response command code = 0x14 + 1 = 0x15
    payload = pn532_recv(bus, address, 0x15, read_len=12, timeout=0.500, debug=debug)
    return payload is not None


def pn532_read_passive_target(bus, address, debug=False):
    """
    Send InListPassiveTarget (MaxTg=1, ISO14443A 106kbps).
    Returns a parsed tag-read dict if a tag is present, else None.
    """
    pn532_send(bus, address, [_CMD_INLISTPASSIVETARGET, 0x01, 0x00], debug)
    # Response command code = 0x4A + 1 = 0x4B
    # Allow up to 350ms for the PN532 to scan + extra for two-step response
    payload = pn532_recv(bus, address, 0x4B, read_len=_MAX_RESPONSE,
                         timeout=0.800, debug=debug)

    if not payload or payload[0] == 0:
        return None   # NbTg == 0: no tag found

    # payload layout: [NbTg, Tg, ATQA(2), SAK, NFCIDLen, NFCID...]
    if len(payload) < 7:
        return None

    nfcid_len = payload[5]
    if nfcid_len == 0 or len(payload) < 6 + nfcid_len:
        return None

    uid = payload[6:6 + nfcid_len]
    extra_data = payload[6 + nfcid_len:]
    return {
        'raw_payload': payload,
        'nbtg': payload[0],
        'target_number': payload[1],
        'atqa': payload[2:4],
        'sak': payload[4],
        'nfcid_len': nfcid_len,
        'uid': uid,
        'extra_data': extra_data,
    }


def hex_to_ascii(hex_string):
    """
    Convert a hex byte string to printable ASCII for terminal output.

    RFID/NFC UIDs are binary identifiers, so many bytes are not printable text.
    Printable ASCII bytes are emitted as characters; all others are escaped.
    """
    try:
        data = bytes.fromhex(hex_string)
    except ValueError:
        return ''

    chars = []
    for byte in data:
        if 0x20 <= byte <= 0x7E:
            chars.append(chr(byte))
        else:
            chars.append('\\x{:02X}'.format(byte))
    return ''.join(chars)


def bytes_to_hex(data):
    """Format bytes as an uppercase hex string without separators."""
    return ''.join('{:02X}'.format(b) for b in data)


def bytes_to_spaced_hex(data):
    """Format bytes as uppercase hex with spaces between bytes."""
    return ' '.join('{:02X}'.format(b) for b in data)


def bytes_to_ascii(data):
    """Convert bytes to printable ASCII with non-printable bytes escaped."""
    return hex_to_ascii(bytes_to_hex(data))


def print_tag_read(tag):
    """Print every field parsed from the PN532 tag-read response."""
    uid_hex = bytes_to_hex(tag['uid'])

    print("TAG READ", flush=True)
    print(f"  UID:          hex={uid_hex}  ascii={bytes_to_ascii(tag['uid'])}", flush=True)
    print(f"  NbTg:         {tag['nbtg']}", flush=True)
    print(f"  Target:       {tag['target_number']}", flush=True)
    print(f"  ATQA:         hex={bytes_to_spaced_hex(tag['atqa'])}  ascii={bytes_to_ascii(tag['atqa'])}", flush=True)
    print(f"  SAK:          hex={tag['sak']:02X}  ascii={bytes_to_ascii([tag['sak']])}", flush=True)
    print(f"  NFCID length: {tag['nfcid_len']}", flush=True)
    if tag['extra_data']:
        print(f"  Extra data:   hex={bytes_to_spaced_hex(tag['extra_data'])}  ascii={bytes_to_ascii(tag['extra_data'])}", flush=True)
    else:
        print("  Extra data:   none", flush=True)
    print(f"  Raw payload:  hex={bytes_to_spaced_hex(tag['raw_payload'])}  ascii={bytes_to_ascii(tag['raw_payload'])}", flush=True)


def ascii_text(value):
    """Return a terminal-safe ASCII representation for scalar values."""
    if value is True:
        text = 'true'
    elif value is False:
        text = 'false'
    elif value is None:
        text = 'null'
    else:
        text = str(value)
    return text.encode('ascii', 'backslashreplace').decode('ascii')


def flatten_metadata(value, prefix='spool'):
    """Yield flattened name/value pairs for nested dict/list metadata."""
    if isinstance(value, dict):
        for key in sorted(value):
            name = f"{prefix}.{key}" if prefix else str(key)
            yield from flatten_metadata(value[key], name)
    elif isinstance(value, list):
        if not value:
            yield prefix, '[]'
        else:
            for index, item in enumerate(value):
                yield from flatten_metadata(item, f"{prefix}.{index}")
    elif isinstance(value, (str, int, float, bool)) or value is None:
        yield prefix, ascii_text(value)
    else:
        yield prefix, ascii_text(json.dumps(value, sort_keys=True, ensure_ascii=True))


def print_spoolman_lookup(uid_hex, spool, spoolman_url, rfid_key):
    """Print a Spoolman lookup result as clean ASCII named value pairs."""
    print("SPOOLMAN LOOKUP", flush=True)
    print(f"  lookup.uid: {ascii_text(uid_hex)}", flush=True)
    print(f"  lookup.url: {ascii_text(spoolman_url)}", flush=True)
    print(f"  lookup.rfid_key: {ascii_text(rfid_key)}", flush=True)

    if not spool:
        print("  lookup.status: not_found", flush=True)
        return

    print("  lookup.status: found", flush=True)
    for name, value in flatten_metadata(spool):
        print(f"  {ascii_text(name)}: {ascii_text(value)}", flush=True)


def read_config_value(paths, section_name, key):
    """Read a simple Klipper-style key from config files."""
    in_section = False
    for path in paths:
        try:
            with open(path, 'r') as fh:
                for raw_line in fh:
                    line = raw_line.split('#', 1)[0].strip()
                    if not line:
                        continue
                    if line.startswith('[') and line.endswith(']'):
                        in_section = line[1:-1].strip() == section_name
                        continue
                    if not in_section or ':' not in line:
                        continue
                    found_key, value = line.split(':', 1)
                    if found_key.strip() == key:
                        return value.strip()
        except OSError:
            continue
    return ''


def spoolman_config_paths():
    """Return likely nfc_reader.cfg locations for repo and installed use."""
    script_path = Path(__file__).resolve()
    return [
        script_path.parents[1] / 'config' / 'nfc_reader.cfg',
        Path.home() / 'printer_data' / 'config' / 'NFC' / 'nfc_reader.cfg',
    ]


def make_spoolman_client(url, rfid_key, timeout, cache_ttl, debug):
    """Create a Spoolman client, or return None if lookup is not configured."""
    if not url:
        return None
    if SpoolmanClient is None:
        print("WARNING: Spoolman client could not be imported; lookup disabled")
        return None
    return SpoolmanClient(url, rfid_key=rfid_key, timeout=timeout,
                          cache_ttl=cache_ttl, debug=2 if debug else 1)


def pn532_release(bus, address, debug=False):
    """
    Send InRelease to deselect all targets.
    Must be called after each successful tag read so the next scan starts clean.
    """
    pn532_send(bus, address, [_CMD_INRELEASE, 0x00], debug)
    # Response command code = 0x52 + 1 = 0x53
    pn532_recv(bus, address, 0x53, read_len=12, timeout=0.300, debug=debug)
    # Errors here are non-fatal — next scan will recover


def pn532_flush(bus, address, duration=1.0, poll_interval=0.010, debug=False):
    """
    Drain any ready bytes from the PN532 for up to duration seconds.

    This keeps the next scan cycle from seeing stale buffered data after a tag
    read/release sequence. The duration is a maximum window, not a fixed delay.
    """
    deadline = time.time() + duration

    while time.time() < deadline:
        try:
            status_byte = i2c_read(bus, address, 1)[0]
        except Exception as e:
            if debug:
                print(f"    flush poll error: {e}")
            time.sleep(poll_interval)
            continue

        if status_byte != _STATUS_READY:
            return

        try:
            full = i2c_read(bus, address, 1 + _MAX_RESPONSE)
        except Exception as e:
            if debug:
                print(f"    flush read error: {e}")
            time.sleep(poll_interval)
            continue

        if debug:
            frame_bytes = full[1:]
            print(f"    flush status=0x{full[0]:02X}  "
                  f"data={' '.join('%02X' % b for b in frame_bytes)}")

        time.sleep(poll_interval)


# ─────────────────────────────────────────────────────────────────────────────
# Bus scan
# ─────────────────────────────────────────────────────────────────────────────

def scan_bus(bus_num):
    """Probe every valid I2C address and print devices that respond."""
    print(f"Scanning I2C bus {bus_num}...")
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


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

POLL_INTERVAL = 5   # seconds between InListPassiveTarget scans


def main():
    config_paths = spoolman_config_paths()
    default_spoolman_url = (
        read_config_value(config_paths, 'nfc_gate', 'spoolman_url') or
        read_config_value(config_paths, 'nfc_gates', 'spoolman_url'))
    default_rfid_key = (
        read_config_value(config_paths, 'nfc_gate', 'spoolman_rfid_key') or
        read_config_value(config_paths, 'nfc_gates', 'spoolman_rfid_key') or
        'rfid_tag')

    parser = argparse.ArgumentParser(description='PN532 I2C scanner for Raspberry Pi')
    parser.add_argument('--bus',      type=int,  default=1,
                        help='I2C bus number (default: 1 = /dev/i2c-1, GPIO2/3)')
    parser.add_argument('--address',  default='0x24',
                        help='PN532 I2C address in hex (default: 0x24)')
    parser.add_argument('--debug',    action='store_true',
                        help='Show full I2C protocol trace')
    parser.add_argument('--scan-bus', action='store_true',
                        help='Scan I2C bus for all responding devices then exit')
    parser.add_argument('--once',     action='store_true',
                        help='Exit after first tag read')
    parser.add_argument('--spoolman-url', default=default_spoolman_url,
                        help='Spoolman base URL (default: value from config/nfc_reader.cfg)')
    parser.add_argument('--rfid-key', default=default_rfid_key,
                        help='Spoolman extra-field key containing the UID')
    parser.add_argument('--spoolman-timeout', type=float, default=5.0,
                        help='Spoolman HTTP timeout in seconds')
    parser.add_argument('--spoolman-cache-ttl', type=float, default=300.0,
                        help='Seconds to cache successful Spoolman lookups')
    parser.add_argument('--no-spoolman', action='store_true',
                        help='Disable Spoolman lookup')
    args = parser.parse_args()

    address = int(args.address, 16) if args.address.startswith('0x') \
              else int(args.address)

    if args.scan_bus:
        scan_bus(args.bus)
        return

    print(f"PN532 scanner  bus={args.bus}  address=0x{address:02X}  "
          f"poll={POLL_INTERVAL}s  debug={args.debug}")
    spoolman = None
    if not args.no_spoolman:
        spoolman = make_spoolman_client(args.spoolman_url, args.rfid_key,
                                        args.spoolman_timeout,
                                        args.spoolman_cache_ttl,
                                        args.debug)
        if spoolman:
            print(f"Spoolman lookup  url={args.spoolman_url}  "
                  f"rfid_key={args.rfid_key}")
        else:
            print("Spoolman lookup disabled (no URL configured)")
    else:
        print("Spoolman lookup disabled")
    print("Ctrl+C to stop\n")

    with SMBus(args.bus) as bus:

        # ── Initialise ────────────────────────────────────────────────────
        print("Initialising PN532...")
        fw = None
        for attempt in range(3):
            wait = 0.150 if attempt == 0 else 0.075
            if args.debug:
                print(f"  Wake attempt {attempt+1}/3  (post-TX wait={wait*1000:.0f}ms)")
            try:
                fw = pn532_get_firmware_version(bus, address, debug=args.debug)
                if fw:
                    break
            except Exception as e:
                if args.debug:
                    print(f"  attempt {attempt+1} error: {e}")
            time.sleep(wait)

        if not fw:
            print("\nERROR: PN532 did not respond.")
            print(f"  Run with --scan-bus to check bus {args.bus}")
            print("  Check I2C mode jumper (SEL0=H, SEL1=L), wiring, and 3.3V power")
            sys.exit(1)

        print(f"  IC=0x{fw[0]:02X}  Ver={fw[1]}.{fw[2]}")

        if not pn532_sam_configuration(bus, address, debug=args.debug):
            print("WARNING: SAMConfiguration got no response — reader may be unstable")
        else:
            print("  SAMConfiguration OK")

        print(f"\nReady — scanning every {POLL_INTERVAL} seconds.\n")

        # ── Polling loop ──────────────────────────────────────────────────
        tag_was_present = False
        try:
            while True:
                if args.debug:
                    print("--- InListPassiveTarget ---")

                tag = pn532_read_passive_target(bus, address, debug=args.debug)

                if tag:
                    pn532_release(bus, address, debug=args.debug)
                    uid = bytes_to_hex(tag['uid'])
                    print_tag_read(tag)
                    if spoolman:
                        spool = spoolman.lookup_spool_record_by_uid(uid)
                        print_spoolman_lookup(uid, spool, args.spoolman_url,
                                              args.rfid_key)
                    pn532_flush(bus, address, duration=1.0, debug=args.debug)
                    tag_was_present = True
                    if args.once:
                        break
                else:
                    if tag_was_present:
                        print("removed")
                        tag_was_present = False

                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == '__main__':
    main()
