"""
tests/simulate.py
=================
Interactive full-pipeline simulation — no Pico, no Klipper, no RC522 hardware.

Replaces MCU_SPI + RC522Driver with a scriptable mock so you can inject gate
events and watch GCode macros fire, exactly as they would on a real printer.

Run from the project root:
    python3 tests/simulate.py

Commands (type 'help' at the prompt for the full list):
    place <gate> <spool_id>        Simulate placing spool #spool_id on gate
    place <gate> uid <uid_hex>     Simulate a tag with no spool ID written
    place <gate> lookup <uid_hex>  Look up UID in Spoolman and place with resolved spool
    remove <gate>                  Simulate removing a tag (fires after threshold)
    status                         Show current gate state
    poll                           Manually trigger one poll cycle
    set poll_interval <s>          Change poll interval
    set absent_threshold <n>       Change debounce threshold
    set spoolman_url <url>         Change Spoolman base URL
    set spoolman_rfid_key <key>    Change Spoolman RFID extra-field name
    quit
"""

import sys
import os
import threading
import time
import types

# ── Stub Klipper-specific modules not needed by the simulator ─────────────────
for _name in ('extras', 'extras.bus'):
    sys.modules.setdefault(_name, types.ModuleType(_name))

_EXTRAS = os.path.join(os.path.dirname(__file__), '..', 'klippy', 'extras')
sys.path.insert(0, _EXTRAS)

from nfc_gates.NFC_manager   import GateState, EVENT_CHANGED, EVENT_UID_ONLY, EVENT_REMOVED
from nfc_gates.spoolman_client import SpoolmanClient


# ─────────────────────────────────────────────────────────────────────────────
# Fake GCode dispatcher — prints what the macro call would be
# ─────────────────────────────────────────────────────────────────────────────

class FakeGCode:
    def run_script(self, script):
        print(f"\n  [GCODE] {script}\n", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Scriptable gate hardware — replaces RC522Driver / PN532Driver
# ─────────────────────────────────────────────────────────────────────────────

class SimulatedGate:
    """
    Simulates one NFC reader.  Call set_tag() / clear_tag() from the
    interactive prompt; read_tag() returns the currently configured state.
    """

    def __init__(self, gate):
        self.gate   = gate
        self._uid   = None
        self._spool = None
        self._lock  = threading.Lock()

    def set_tag(self, uid, spool_id):
        with self._lock:
            self._uid   = uid
            self._spool = spool_id

    def clear_tag(self):
        with self._lock:
            self._uid   = None
            self._spool = None

    def read_tag(self):
        with self._lock:
            return self._uid, self._spool


# ─────────────────────────────────────────────────────────────────────────────
# Simulator — wires everything together
# ─────────────────────────────────────────────────────────────────────────────

class Simulator:

    GATE_COUNT        = 5
    SPOOLMAN_URL      = 'http://192.168.0.73:7912'
    SPOOLMAN_RFID_KEY = 'rfid_tag'

    def __init__(self):
        self._poll_interval     = 30.0
        self._absent_threshold  = 3
        self._spoolman_url      = self.SPOOLMAN_URL
        self._spoolman_rfid_key = self.SPOOLMAN_RFID_KEY
        self._gates  = [SimulatedGate(i) for i in range(self.GATE_COUNT)]
        self._states = [GateState(i, self._absent_threshold)
                        for i in range(self.GATE_COUNT)]
        self._gcode  = FakeGCode()
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._poll_loop,
                                        name='sim-poll', daemon=True)

    def start(self):
        print(f"Simulator started — {self.GATE_COUNT} gates, "
              f"poll={self._poll_interval}s, "
              f"absent_threshold={self._absent_threshold}")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _poll_loop(self):
        while not self._stop.is_set():
            self._poll_all()
            self._stop.wait(timeout=self._poll_interval)

    def _poll_all(self):
        for i in range(self.GATE_COUNT):
            uid, spool = self._gates[i].read_tag()
            event = self._states[i].process_read(uid, spool)
            if event:
                self._dispatch(event)

    def poll_once(self):
        print("  [SIM] Poll cycle triggered")
        self._poll_all()

    def _dispatch(self, event):
        event_type, gate, uid, spool = event
        if event_type == EVENT_CHANGED:
            self._gcode.run_script(
                f"_NFC_SPOOL_CHANGED GATE={gate} SPOOL_ID={spool} UID={uid}")
        elif event_type == EVENT_UID_ONLY:
            self._gcode.run_script(
                f"_NFC_TAG_NO_SPOOL GATE={gate} UID={uid}")
        elif event_type == EVENT_REMOVED:
            self._gcode.run_script(f"_NFC_SPOOL_REMOVED GATE={gate}")

    def cmd_place(self, args):
        if args and args[0].lower() == 'gate':
            args = args[1:]
        if len(args) < 2:
            print("Usage: place <gate> <spool_id>  or  place <gate> uid <uid_hex>")
            return
        try:
            gate = int(args[0])
        except ValueError:
            print("gate must be an integer (0–4)"); return
        if gate < 0 or gate >= self.GATE_COUNT:
            print(f"gate must be 0–{self.GATE_COUNT - 1}"); return

        if len(args) >= 3 and args[1].lower() == 'lookup':
            uid = args[2].upper()
            print(f"  [SIM] Looking up UID {uid} in Spoolman ({self._spoolman_url}) ...")
            client   = SpoolmanClient(self._spoolman_url,
                                      rfid_key=self._spoolman_rfid_key, debug=1)
            spool_id = client.lookup_spool_by_uid(uid)
            if spool_id is not None:
                self._gates[gate].set_tag(uid, spool_id)
                print(f"  [SIM] Gate {gate}: UID {uid} → spool {spool_id} placed")
            else:
                self._gates[gate].set_tag(uid, None)
                print(f"  [SIM] Gate {gate}: UID {uid} not found — placed as uid-only")
        elif len(args) >= 3 and args[1].lower() == 'uid':
            uid = args[2].upper()
            self._gates[gate].set_tag(uid, None)
            print(f"  [SIM] Gate {gate}: tag {uid} placed (no spool ID)")
        else:
            try:
                spool_id = int(args[1])
            except ValueError:
                print("spool_id must be an integer"); return
            uid = f"DEAD{gate:04X}"
            self._gates[gate].set_tag(uid, spool_id)
            print(f"  [SIM] Gate {gate}: spool {spool_id} placed (UID {uid})")

        self.poll_once()

    def cmd_remove(self, args):
        if not args:
            print("Usage: remove <gate>"); return
        try:
            gate = int(args[0])
        except ValueError:
            print("gate must be an integer"); return
        if gate < 0 or gate >= self.GATE_COUNT:
            print(f"gate must be 0–{self.GATE_COUNT - 1}"); return

        self._gates[gate].clear_tag()
        print(f"  [SIM] Gate {gate}: tag removed "
              f"(REMOVED fires after {self._absent_threshold} more polls)")
        for _ in range(self._absent_threshold):
            self.poll_once()

    def cmd_status(self, _args):
        print(f"\nGate status (poll={self._poll_interval}s, "
              f"absent_threshold={self._absent_threshold}):")
        for i in range(self.GATE_COUNT):
            hw_uid, hw_spool = self._gates[i].read_tag()
            state = self._states[i]
            hw = (f"hw=spool {hw_spool} UID {hw_uid}" if hw_uid else "hw=empty")
            sw = (f"tracked=spool {state.current_spool} UID {state.current_uid}"
                  if state.current_uid else "tracked=empty")
            misses = f"  miss_count={state.miss_count}" if state.miss_count else ""
            print(f"  Gate {i}:  {hw}   {sw}{misses}")
        print()

    def cmd_set(self, args):
        if len(args) < 2:
            print("Usage: set poll_interval <s>  |  set absent_threshold <n>")
            return
        key, val = args[0], args[1]
        if key == 'poll_interval':
            try:
                self._poll_interval = float(val)
                print(f"  [SIM] poll_interval = {self._poll_interval}s")
            except ValueError:
                print("Value must be a number")
        elif key == 'absent_threshold':
            try:
                n = int(val)
                self._absent_threshold = n
                for gs in self._states:
                    gs.absent_threshold = n
                print(f"  [SIM] absent_threshold = {n}")
            except ValueError:
                print("Value must be an integer")
        elif key == 'spoolman_url':
            self._spoolman_url = val
            print(f"  [SIM] spoolman_url = {val}")
        elif key == 'spoolman_rfid_key':
            self._spoolman_rfid_key = val
            print(f"  [SIM] spoolman_rfid_key = {val}")
        else:
            print(f"Unknown setting: {key}")

    def cmd_poll(self, _args):
        self.poll_once()

    def cmd_help(self, _args):
        print(f"""
Commands:
  place <gate> <spool_id>          Simulate placing a spool on a gate
  place <gate> uid <uid_hex>       Simulate a tag with no spool ID written
  place <gate> lookup <uid_hex>    Look up UID in Spoolman and place with resolved spool
  remove <gate>                    Simulate removing a tag (debounce auto-applied)
  status                           Show hardware and tracked state of all gates
  poll                             Manually run one poll cycle
  set poll_interval <s>            Change poll interval (affects background thread)
  set absent_threshold <n>         Change debounce threshold (gates adapt live)
  set spoolman_url <url>           Change Spoolman URL (current: {self._spoolman_url})
  set spoolman_rfid_key <key>      Change RFID extra-field name (current: {self._spoolman_rfid_key})
  help                             Show this message
  quit / exit                      Stop the simulator
""")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("EMU NFC Gate Simulator")
    print("Type 'help' for available commands.\n")

    sim = Simulator()
    sim.start()

    DISPATCH = {
        'place':  sim.cmd_place,
        'remove': sim.cmd_remove,
        'status': sim.cmd_status,
        'set':    sim.cmd_set,
        'poll':   sim.cmd_poll,
        'help':   sim.cmd_help,
    }

    while True:
        try:
            raw = input("sim> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        parts = raw.split()
        cmd   = parts[0].lower()
        args  = parts[1:]
        if cmd in ('quit', 'exit'):
            break
        elif cmd in DISPATCH:
            DISPATCH[cmd](args)
        else:
            print(f"Unknown command: {cmd!r}  (type 'help')")

    sim.stop()
    print("Simulator stopped.")


if __name__ == '__main__':
    main()
