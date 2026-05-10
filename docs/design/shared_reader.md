# Design: Shared Reader

> Status: In progress
> Scope: No IRQ/data-ready pin support in this phase.

---

> Working memory for auditing the shared reader implementation against
> `docs/design/shared_reader.md`.
>
> Green means the current tree has an implementation matching the baseline.
> Red means the item is missing, incomplete, or still requires validation.

| Implemented | Baseline requirement | Files affected | Comments / Feedback |
|:---:|---|---|---|
| ✅ | Shared reader is configured as `[nfc_gate shared]` with `shared: true`. | `klippy/extras/nfc_gates/nfc_manager.py`, `install.sh`, `docs/shared/configuration.md` | |
| ✅ | Shared reader does not require or accept a user-facing `mmu_gate`; code uses internal sentinel gate `255`. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | Only one shared reader may be configured. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | `scan_enabled` is forced off for the shared reader; shared must not enter scan-jog. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | Shared reader does not register `NFC GATE=` mux commands; all user control goes through `NFC_SHARED`. `NFC_STATUS` is registered globally by `NFCGateDefaults` when a base `[nfc_gate]` section exists, or as a fallback by the first entry in `_lane_instances` — which in a shared-only install is the shared reader itself. | `klippy/extras/nfc_gates/nfc_manager.py`, `klippy/extras/nfc_gate.py` | |
| ✅ | `NFC_SHARED` supports `READ`, `STATUS`, `CLEAR`, `PRELOAD_CHECK`, `POLL`, `SCAN`, `INIT`, and `CLEAR_CACHE`. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` | |
| ✅ | Shared state tracks pending UID, pending spool ID, pending deadline, auto-created flag, last error, and read deadline. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | Successful tag resolution stores a pending spool, starts `shared_pending_timeout`, stops polling, and keeps the pending spool after tag removal. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | UID-only / unresolved tag records an error without clearing a previously pending spool. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | `shared_pending_timeout` defaults to `120.0` seconds and expires stale pending spools before preload staging. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/configuration.md` | |
| ✅ | `shared_read_timeout` defaults to `120.0` seconds and stops manual/eject-triggered polling when no valid tag resolves. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/configuration.md` | |
| ✅ | `startup_polling: 1` starts polling after PN532 init without applying the manual read timeout. | `klippy/extras/nfc_gates/nfc_manager.py`, `install.sh` | |
| ✅ | Shared polling skips I2C reads while printing. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | Shared polling skips I2C reads while Happy Hare reports active load, unload, or homing. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | `PRELOAD_CHECK` uses the existing safety posture: check printing / HH busy state, but do not read NFC during preload check. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | `PRELOAD_CHECK` stages the pending spool with `MMU_GATE_MAP NEXT_SPOOLID=<id>` and never blocks normal loading when no spool is pending. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | After successful `PRELOAD_CHECK`, shared polling restarts for the next spool with no read deadline. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | `READ=0` stops polling but keeps any pending spool; `CLEAR=1` stops polling and clears pending/shared state. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` | |
| ✅ | `CLEAR_CACHE=1` clears the `GateState` tag cache without clearing pending shared spool state. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` | |
| ✅ | Successful tag read can trigger a named HH LED effect via `shared_tag_read_effect`; design example is blinking yellow `mmu_RFID_read`. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/configuration.md` | |
| ✅ | `NFC_SHARED STATUS=1` reports idle, polling, pending, expired, error, and reader-failed shared states. | `klippy/extras/nfc_gates/nfc_manager.py`, `docs/shared/klipper-functions.md` | |
| ✅ | `NFC_STATUS` output includes the shared reader; in a shared-only install it appears alone (no lane rows), in a mixed install it appears after the lane rows. The shared instance is in `_lane_instances` but filtered from the lane loop by the `_shared` flag; `_append_shared_status` adds it separately. | `klippy/extras/nfc_gates/nfc_manager.py`, `klippy/extras/nfc_gate.py` | |
| ✅ | Shared reader ready/init messages use `NFC_SHARED` commands and do not include lane HH seed notes. | `klippy/extras/nfc_gates/nfc_manager.py` | |
| ✅ | Happy Hare pre-load hook bridge exists as `_NFC_SHARED_PRELOAD` and calls `NFC_SHARED PRELOAD_CHECK=1`. | `config/nfc_macros.cfg`, `install.sh`, `docs/shared/configuration.md` | |
| ✅ | Happy Hare post-unload hook bridge exists as `_NFC_SHARED_POST_UNLOAD` and calls `NFC_SHARED READ=1`. | `config/nfc_macros.cfg`, `install.sh`, `docs/shared/configuration.md` | |
| ✅ | Installer supports an upfront lane/shared branch, defaults lane, and writes a shared-only hardware config when selected. | `install.sh` | |
| ✅ | Installer detects existing `[nfc_gate shared]` config and existing shared MCU for reinstall defaults. | `install.sh` | |
| ✅ | Installer next steps call out shared MCU flash and HH hook wiring. | `install.sh` | |
| ✅ | Normal PN532 driver waits use injectable `sleep_fn`, and `NFCGate` supplies a reactor-cooperative sleep using `reactor.pause`. | `klippy/extras/nfc_gates/pn532_driver.py`, `klippy/extras/nfc_gates/nfc_manager.py` | |
| ❌ | Installer generated shared config should expose every important shared timeout/effect knob clearly; current output comments `shared_tag_read_effect` and `shared_pending_timeout`, but not `shared_read_timeout`. | `install.sh` | |
| ❌ | Shared reader behavior should have direct tests for config parsing, command handling, timeout behavior, pending spool staging, status output, and no-op preload behavior. Current tests only set `_shared = False` in scan-jog fixtures. | `tests/` | |
| ✅ | PN532 low-level debug helpers still contain direct `time.sleep()` calls; either convert them to `sleep_fn` or document them as an explicit debug-only exception. | `klippy/extras/nfc_gates/pn532_driver.py` | this is fine, will not implement a change |
| ❌ | Lane-only wiring / architecture docs need a shared-reader exception so they do not imply shared installs are unsupported. | `docs/i2c-pn532/wiring.md`, `docs/shared/architecture-decisions.md` | |
| ❌ | HH post-unload timing needs hardware validation to confirm shared polling starts after the gate is empty. | Happy Hare runtime, printer hardware | |
| ❌ | HH LED effect invocation needs hardware validation for `MMU_SET_LED EXIT_EFFECT=<shared_tag_read_effect> DURATION=3`. | Happy Hare runtime, LED config | |
| ❌ | Auto-created Spoolman spool IDs still need hardware / HH validation to confirm `MMU_GATE_MAP NEXT_SPOOLID=<id>` works without an explicit `MMU_SPOOLMAN REFRESH=1`. | `klippy/extras/nfc_gates/nfc_manager.py`, Happy Hare runtime | |

## Audit Notes

- The active terminology is **shared** throughout this feature.
- The design says shared-only installs do not need `[nfc_gate laneN]` sections.
  The installer path matches that by writing only `[nfc_gate shared]` hardware.
- The biggest implementation risk is not the core path; it is validation. The
  shared path needs unit tests and one real Happy Hare integration pass for
  `NEXT_SPOOLID`, post-unload timing, LED effect invocation, and auto-created
  Spoolman IDs.

---

## Goal

Add one NFC reader inside the MMU body that is **not tied to an EMU lane**.
The reader acts as a staging point for the next manually loaded spool:

1. User taps a tag on the hidden MMU reader.
2. NFC resolves the tag to a Spoolman spool ID, creating the spool first if
   `spoolman_auto_create` is enabled and the tag carries enough metadata.
3. NFC gives user feedback through LEDs.
4. User loads a spool through the normal MMU/pre-gate path.
5. Happy Hare assigns the staged spool ID to whichever gate is preloaded next.

Happy Hare already has the desired primitive:

```gcode
MMU_GATE_MAP NEXT_SPOOLID=<spool_id>
```

If a gate is preloaded within Happy Hare's timeout window after that command,
HH assigns that spool ID to the loaded gate. The shared reader should use that
mechanism instead of trying to determine the destination gate itself.

---

## Non-goals

- Do not make the shared reader part of the EMU lane reader set.
- Do not add PN532 IRQ/data-ready support yet.
- Do not scan-jog from the shared reader.
- Do not infer gate assignment by inspecting NFC gate polling state.
- Do not duplicate Spoolman create/lookup logic already used by lane readers.
- Do not duplicate the existing NFC reader timer, read, resolve, debounce, or
  debug command machinery.
- Do not call Happy Hare Python internals directly. Use HH's public GCode
  command surface.

---

## Key Decision

Use a normal `NFCGate` instance for the physical reader and put it in shared
mode. The reader is configured as `[nfc_gate shared]` with `shared: true`.
No `mmu_gate` value is needed or accepted from the user — the shared reader has
no Happy Hare gate assignment. An internal sentinel (255) is used only for
PN532Driver and GateState logging and is never passed to Happy Hare.

**No per-lane readers are required.** A shared-only installation needs only the
base `[nfc_gate]` section (optional, for Spoolman config) and the
`[nfc_gate shared]` section. No `[nfc_gate lane0]` or similar sections are
needed.

The shared reader has no physical EMU lane, so its dispatch behavior differs
from a normal lane:

```text
lane reader:
  physical gate -> read tag -> resolve spool -> assign that same gate

shared reader:
  existing NFCGate poll -> resolve spool -> remember pending spool
  preload hook -> stage NEXT_SPOOLID
```

That means the shared reader only needs to know:

- the most recently scanned spool ID
- whether that staged spool is still within the timeout window

It does **not** need to know:

- which gate is currently loaded
- which gate is about to preload
- whether an EMU lane reader is paused
- whether a lane reader has cached NFC state

The preload hook is primarily a timing signal. NFC should wait until Happy Hare
reports that a pregate-triggered preload is about to start, then issue
`MMU_GATE_MAP NEXT_SPOOLID=<id>` if a valid pending spool exists. Happy Hare
still decides which gate receives that staged spool.

`shared` is the NFC object name. Scan-jog edge detection and HH gate-map
matching are disabled for this reader. All user interaction goes through
`NFC_SHARED`.

---

## Proposed Config

The shared reader is configured as a regular `[nfc_gate ...]` section with a
single shared flag. This avoids a second config namespace and lets the
reader share the existing PN532 driver, Spoolman client, tag parser, logging,
status, debug, and polling controls.

**Minimal config — only hardware addressing and the shared flag are required:**

```ini
[nfc_gate shared]
i2c_mcu: mmu
i2c_bus: i2c1
i2c_address: 0x24
shared: true
startup_polling: 1
```

`mmu_gate` and `scan_enabled` are not written and are not accepted from the
user when `shared: true`. `scan_enabled` is forced to `false` (no physical EMU
lane). `mmu_gate` is replaced by an internal sentinel and is never user-facing.
`startup_polling` remains an explicit user choice.

Full config with all optional keys shown:

```ini
[nfc_gate shared]
i2c_mcu: mmu
i2c_bus: i2c1
i2c_address: 0x24
shared: true
startup_polling: 1
poll_interval: 3.0
shared_pending_timeout: 120.0
shared_read_timeout:    120.0
shared_tag_read_effect: mmu_RFID_read
```

Keys:

| Key | Default when `shared: true` | Meaning |
|---|---:|---|
| `shared` | `false` | Enables shared dispatch. Setting to `true` forces `scan_enabled: false` and removes the `mmu_gate` requirement. |
| `mmu_gate` | N/A — not user-configurable | An internal sentinel is used. `mmu_gate` is not read from config when `shared: true`. |
| `scan_enabled` | `false` (forced) | Always `false` for shared reader; scan-jog cannot run without a physical EMU lane. |
| `startup_polling` | `0` | Set to `1` to poll at Klipper boot. Explicit user choice — not implied by `shared`. |
| `poll_interval` | `3.0` | Poll interval while the reader is active. 3 s is imperceptible for a human loading spools; see Reactor Cooperation. |
| `shared_pending_timeout` | `120.0` | Seconds a scanned spool remains eligible for the next preload. Governs the window from tag scan to `PRELOAD_CHECK` firing. |
| `shared_read_timeout` | `120.0` | Seconds polling may remain active after `READ=1` without a valid tag resolving. No effect when polling starts via `startup_polling` or PRELOAD_CHECK auto-restart. |
| `shared_tag_read_effect` | `''` | HH LED effect name for a successful tag read. Leave empty to skip LED feedback. |

### Config Validation

```text
if shared == true:
    mmu_gate     → not read from config; internal sentinel used
    scan_enabled → always false; user value ignored
    all shared_* keys are optional with the defaults above
    only one nfc_gate section may have shared == true
    NFC GATE= mux command is NOT registered (NFC_SHARED is the sole interface)
```

### Implementation

Read `shared` first in `NFCGate.__init__`, validate uniqueness, then assign
gate and scan_enabled without reading them from config:

```python
self._shared = config.getboolean('shared', False)
if self._shared:
    for existing in _lane_instances:
        if getattr(existing, '_shared', False):
            raise config.error(
                "nfc_gate [%s]: only one shared reader may be configured" % self._name)

# Gate number: required for lane readers; internal sentinel for shared.
# Not user-configurable for shared — never passed to Happy Hare.
if self._shared:
    self._gate = _SHARED_GATE_SENTINEL   # module constant = 255
else:
    self._gate = config.getint('mmu_gate', minval=0)

# scan_enabled: forced false for shared (no physical EMU lane for jog)
if self._shared:
    self._scan_enabled = False
else:
    self._scan_enabled = config.getboolean('scan_enabled',
                                           d.scan_enabled if d else True)
```

In `_handle_connect`, skip `NFC GATE=` mux registration for shared:

```python
if not self._shared:
    self._gcode.register_mux_command(
        cmd='NFC', key='GATE', value=str(self._gate),
        func=self.cmd_NFC, ...)
```

### Why Not Reuse Happy Hare's Pending Timeout

HH has an internal `pending_spool_id_timeout` that governs how long HH keeps a
`NEXT_SPOOLID` pending after `MMU_GATE_MAP NEXT_SPOOLID=<id>` is called. These
two timeouts govern different phases and are sequential:

```
tag scanned
  ← shared_pending_timeout (NFC) ─────────────────────────────────────────→
  user inserts filament → PRELOAD_CHECK fires
  NFC calls MMU_GATE_MAP NEXT_SPOOLID=42
    ← HH's pending_spool_id_timeout (HH internal) →
    HH applies 42 to the gate and clears its pending state
```

NFC's `shared_pending_timeout` is a user-facing window measured in minutes —
the time between scanning a spool on the bench and physically inserting it into
a gate. HH's internal timeout is effectively zero in this flow because
`PRELOAD_CHECK` fires inside `variable_user_pre_load_extension`, which runs at
the moment preload starts. By the time NFC calls `MMU_GATE_MAP NEXT_SPOOLID`,
HH is already executing the preload and will apply it immediately. The two
timeouts do not conflict and cannot be unified.

### startup_polling and the Read Deadline

How polling starts determines whether `shared_read_timeout` applies:

| How polling started | `_shared_read_deadline` | Auto-stops after timeout? |
|---|---|---|
| `startup_polling: 1` at boot | `0.0` — no deadline | No — runs until `NFC_SHARED READ=0` or `CLEAR` |
| `NFC_SHARED READ=1` (manual or eject hook) | set to `now + shared_read_timeout` | Yes — stops after `shared_read_timeout` seconds if no tag resolves |
| PRELOAD_CHECK auto-restart | `0.0` — deadline cleared | No — runs until `NFC_SHARED READ=0` or `CLEAR` |

With `startup_polling: 1`, the shared reader behaves like a continuous tap point:
the user can tap a spool at any time and the preload will pick it up. The post-unload
eject hook is optional in this mode — `READ=1` will simply find polling already
running, which `_set_reading` handles by clearing any pending spool and
restarting. The `shared_read_timeout` config value is still valid but only
applies when the user or a hook explicitly calls `READ=1`.

The reader should inherit global tag-resolution settings where possible:

- `spoolman_url`
- `spoolman_rfid_key`
- `tag_parsing`
- `spoolman_auto_create`
- metadata read limits and parser settings
- logging/debug settings

---

## State Model

The shared reader should keep using `GateState` for the current physical tag.
`GateState.process_read()` already handles changed tags, UID-only tags, repeated
reads, metadata-only reads, and absent debounce.

Shared mode only adds small pending-spool fields to the `NFCGate` instance:

```python
self._shared_pending_uid = None
self._shared_pending_spool = None
self._shared_pending_deadline = 0.0
self._shared_pending_auto_created = False
self._shared_last_error = None
self._shared_read_deadline = 0.0   # set when READ=1 starts; enforces shared_read_timeout
```

State meanings:

| State | Meaning |
|---|---|
| Inactive | Existing NFC polling is stopped. This is the default after startup. |
| Active | Existing NFC polling is running because `READ=1` was issued manually or from a gate-ejected hook. |
| Idle | Active, but no valid pending spool. |
| Pending | A tag resolved to a spool and is waiting for the next preload hook. |
| Expired | The pending timeout elapsed before preload. Pending state clears. |
| Error | Tag read succeeded but did not resolve, parse failed, or Spoolman was unavailable. |

The state should not track a gate number. Happy Hare owns the destination gate.

---

## Existing Poll Loop Reuse

For v1, the shared reader uses the existing `NFCGate` timer and `_poll()` flow.
The PN532 data-ready/IRQ pin is intentionally left out.

Activation uses the `NFC_SHARED` GCode command. There are two activation modes:

1. Manual start, when the user wants continuous scanning before loading.
2. Automatic start from a Happy Hare hook when an exit/eject is recognized.

```gcode
NFC_SHARED READ=1   ; start polling the shared reader
NFC_SHARED READ=0   ; stop polling the shared reader
NFC_SHARED POLL=1   ; force one full read/resolve cycle
NFC_SHARED SCAN=1   ; low-level hardware scan only
```

The hook path uses the macros shipped in `nfc_macros.cfg`:

```ini
; stage NEXT_SPOOLID before a pregate-triggered automatic preload
variable_user_pre_load_extension:    '_NFC_SHARED_PRELOAD'

; start shared polling after a gate is ejected/unloaded
; not needed when startup_polling: 1
variable_user_post_unload_extension: '_NFC_SHARED_POST_UNLOAD'
```

`variable_user_post_unload_extension` fires after both `MMU_UNLOAD` and
`MMU_EJECT`. Happy Hare's `mmu_macro_vars.cfg` groups these under the "unload"
operation (comment at the `variable_user_post_unload_extension` line: "unload —
individual MMU_UNLOAD/MMU_EJECT operation"). This hook is confirmed correct for
starting shared polling.

`variable_user_pre_load_extension` fires before a pregate-triggered automatic
preload starts. This is the preload hook that calls `NFC_SHARED PRELOAD_CHECK`
to stage `NEXT_SPOOLID` if a valid pending spool exists. This resolves Open
Question #2.

This macro is the bridge from the Happy Hare macro layer into NFC Python. Happy
Hare does not call an NFC Python method directly. It runs a user GCode macro,
which runs the registered `NFC` GCode command. The existing
`NFCGate.cmd_NFC()` handler then calls the Python method for the requested
operation. For `READ=1`, that means `_set_reading(..., True)` starts the
existing poll timer. `POLL=1` remains useful for debugging or a forced immediate
single read.

### Scan Requirements

Shared RFID reads must use the same safety posture as the main NFC path:

1. Do not read while `print_stats.state == 'printing'`. For normal lanes this
   check lives in the scan-jog block, which shared never enters. For shared,
   `_is_printing()` must be checked at the top of the shared `_poll()` branch
   before any I2C read is attempted.
2. Do not start scan-jog; `scan_enabled: false` is required.
3. Do not use HH gate ownership, spool assignment, or lane cache state to decide
   what the shared reader means.
4. When started by the eject hook, only start polling after Happy Hare has
   completed the unload/eject sequence.
5. If HH reports an active load/unload/homing action when shared polling fires,
   skip that poll and try again on the next normal poll interval.
6. Once a valid tag resolves to a pending spool, stop shared polling using the
   same internal path as `NFC_SHARED READ=0`.
7. `POLL=1` follows the same shared scan requirements as timer polling. It must
   not skip print/action checks or read RFID during unsafe states.
8. If `READ=1` is active for `shared_read_timeout` seconds without resolving a
   valid tag, stop polling using the same internal path as `NFC_SHARED READ=0`.
9. If a preload hook fires while shared polling is still active (tag seen but
   Spoolman resolution not yet complete), `PRELOAD_CHECK` will find no pending
   spool and will do nothing — the preload proceeds without shared staging. The
   user can re-scan after the load. This window is bounded by `poll_interval`
   plus Spoolman response time and is not treated as an error.

`NFC_SHARED PRELOAD_CHECK` uses the existing mainline safety precheck style, but
it must not read RFID. It checks only whether printing or active MMU
load/unload/homing should prevent staging. If safe, it inspects the already
pending spool and, if valid, stages it with `MMU_GATE_MAP NEXT_SPOOLID=<id>`.

The reused flow is:

```text
NFCGate._poll_timer_event()
  -> NFCGate._poll()
  -> _read_current_tag()
  -> _resolve_spool()
  -> GateState.process_read()
  -> _poll_dispatch_event()
```

Only the last step changes in shared mode. Instead of dispatching a normal
gate assignment event, an `EVENT_CHANGED` records a pending shared spool and
emits LED feedback:

```python
def _poll_dispatch_event(event):
    if self._shared:
        return self._shared_handle_event(event)
    return self._normal_gate_dispatch(event)
```

Shared-specific behavior:

- `EVENT_CHANGED` with a real spool stores pending UID/spool/deadline.
- `EVENT_CHANGED` from auto-create records that the spool was newly created so
  the preload path can assess whether Happy Hare needs a Spoolman refresh before
  `NEXT_SPOOLID`.
- After a valid pending spool is stored, shared mode stops polling
  automatically. The user has received the tag-read confirmation, and the
  pending spool should now survive the tag being removed from the reader.
- `EVENT_UID_ONLY` records an error only when there is no valid pending spool.
  It must not clear an already pending spool.
- `EVENT_REMOVED` must not clear an already pending spool. Tag removal after a
  successful scan is expected.
- Repeated reads of the same tag stay quiet because `GateState` already returns
  no event for unchanged UID/spool.
- Shared `_poll()` should skip HH lane-specific logic:
  `_poll_hh_pause_check()`, `_check_hh_cleared()`, startup seeding from HH, and
  any HH gate-map matching.
- `startup_polling` remains false, so no scan happens at Klipper startup.
- `scan_enabled` remains false, so scan-jog never runs for `shared`.

This keeps the shared path on the same reader lifecycle and error handling as
normal lanes, while changing only what happens after a tag resolves.

---

## Reactor Cooperation

### The Problem

The PN532 driver uses `time.sleep()` while waiting for the chip to respond.
`time.sleep()` blocks the Klipper reactor thread completely — no temperature
reads, no move scheduling, no console responses, nothing else runs.

Each `read_target()` call involves a status-byte polling loop:

```python
while time.time() < deadline:
    status = i2c_read([], 1)   # ~2 ms MCU round-trip
    if status == 0x01:
        return read_full_response()
    time.sleep(0.005)          # blocks reactor for 5 ms
```

The PN532 takes ~250 ms to report "no tag." That is ~50 iterations of
(2 ms I2C + 5 ms sleep) on the reactor thread — one continuous 300 ms stall
per poll tick.

For lane readers polling at 10 s intervals this is 3% stall time and is
acceptable. For the shared reader polling continuously with `startup_polling: 1`
and `poll_interval: 3.0`, each poll stalls the reactor for ~300 ms out of every
3 s — 10% stall time during the entire loading session.

### The Fix: Reactor-Cooperative Sleep Function

Pass a `sleep_fn` callable into `PN532Driver.__init__`. The driver calls
`self._sleep(duration)` instead of `time.sleep(duration)`. `NFCGate` provides a
reactor-cooperative implementation:

```python
# In NFCGate.__init__:
def _reactor_sleep(self, duration):
    self.reactor.pause(self.reactor.monotonic() + duration)

self._reader = PN532Driver(i2c, self._gate, ..., sleep_fn=self._reactor_sleep)
```

`reactor.pause(waketime)` suspends the current reactor greenlet and lets all
other reactor callbacks run during the wait, then resumes. The 50 × 5 ms stalls
become 50 × 5 ms yields — the reactor is free during each gap, and only the
~2 ms I2C round-trips per iteration remain as brief holds.

The driver change is one line per `time.sleep` call site:

```python
# Before:
time.sleep(poll_interval)

# After:
self._sleep(poll_interval)
```

`sleep_fn` defaults to `time.sleep` so the driver is backward-compatible with
any caller that does not supply one.

### Scope

This fix applies to all readers — lane readers and shared reader — because the
driver is shared. Lane readers gain the same benefit at their next poll tick.
The shared reader benefits on every tick of the loading session.

### What This Does Not Fix

The `i2c_read([], 1)` status poll itself (~2 ms MCU serial round-trip per
iteration) may also hold the reactor briefly depending on whether Klipper's MCU
I2C implementation uses the reactor's greenlet suspension mechanism or a direct
blocking wait. If it uses greenlet suspension, each I2C call already yields
automatically. If not, ~100 ms of the 300 ms stall remains as 50 × 2 ms
micro-holds even after the sleep fix. Either way, the fix converts one 300 ms
hard stall into at most 50 short interruptions spread across the poll window,
which is substantially better from Klipper's scheduler perspective.

A fully non-blocking implementation would restructure `read_target` as a
reactor timer state machine — one timer per protocol step, zero blocking between
steps. This eliminates all stall but requires changing the driver API from
synchronous to callback-based and restructuring every call site including the
scan-jog step loop. This is not planned.

---

## Tag Resolution

The shared reader should use the same resolution path as lane readers:

```text
PN532 read
  -> tag_handler / parser
  -> Spoolman UID lookup
  -> optional auto-create
  -> spool_id or UID-only result
```

If `spoolman_auto_create` creates a new spool, the shared path should remember
that fact. Because the shared assignment uses `MMU_GATE_MAP NEXT_SPOOLID=<id>`,
it may not need the same HH Spoolman refresh path as a direct gate assignment.
This should be assessed during implementation instead of run automatically.

```gcode
MMU_GATE_MAP NEXT_SPOOLID=<spool_id>
```

If testing shows HH needs to refresh its Spoolman cache before accepting an
auto-created spool ID as `NEXT_SPOOLID`, the refresh should happen at preload
check time. It should not run automatically just because a tag was scanned.

If the tag cannot resolve:

- keep any previously pending valid spool
- do not make a pending `NEXT_SPOOLID` available
- allow later preloads to continue normally without a shared spool assignment

Pending state is cleared only by:

- timeout
- successful `NFC_SHARED PRELOAD_CHECK`
- explicit `NFC_SHARED CLEAR`
- a new valid tag replacing the previous pending spool

---

## Happy Hare Integration

### Hook Macros

NFC ships default hook macros in `nfc_macros.cfg`. These are the bridge between
Happy Hare's extension variables and the NFC Python commands. Users wire the HH
variables to these macros once; the macros call NFC. Users can override the
macros in their own cfg to add pre/post logic without touching the HH variable
or the NFC command itself.

```ini
[gcode_macro _NFC_SHARED_PRELOAD]
description: Called by Happy Hare pre-load hook to stage NEXT_SPOOLID if a shared spool is pending
gcode:
    NFC_SHARED PRELOAD_CHECK=1

[gcode_macro _NFC_SHARED_POST_UNLOAD]
description: Called by Happy Hare post-unload hook to start shared reader polling
gcode:
    NFC_SHARED READ=1
```

HH variable wiring in `_MMU_SEQUENCE_VARS`:

```ini
variable_user_pre_load_extension:    '_NFC_SHARED_PRELOAD'
variable_user_post_unload_extension: '_NFC_SHARED_POST_UNLOAD'
```

`variable_user_post_unload_extension` is optional when `startup_polling: 1` is
set — the reader is already polling at boot. It is useful when
`startup_polling: 0` is preferred and polling should activate only after an
unload or eject.

**Why macros instead of calling `NFC_SHARED PRELOAD_CHECK=1` directly in the
variable:** HH's extension variables accept any GCode string. Setting the
variable to a macro name rather than a raw command gives the user an override
point. A user who wants to log the preload, flash an LED, or conditionally skip
the NFC check can redefine `_NFC_SHARED_PRELOAD` in their own cfg without
changing the HH variable or NFC internals. Direct calls in the variable string
offer no such seam.

In Klipper, `NFC_SHARED` is a Python-registered GCode command. When HH runs
`_NFC_SHARED_PRELOAD`, Klipper dispatches it to the macro, which calls
`NFC_SHARED PRELOAD_CHECK=1`, which Klipper dispatches directly to Python
`cmd_NFC_SHARED()`. No cfg intermediary sits between the macro call and the
Python handler.

### What Python Does

```python
def _shared_preload_check(self):
    if self._is_printing():
        return True
    if self._hh_action_is_loading_unloading_or_homing():
        return True
    self._shared_expire_pending_if_needed()
    if not self._shared_pending_spool_is_valid():
        return True

    gcode.run_script(
        "MMU_GATE_MAP NEXT_SPOOLID=%d" % self._shared_pending_spool)
    self._shared_clear_pending()
    # restart immediately so the reader is ready for the next spool
    self._shared_read_deadline = 0.0
    self._polling = True
    self.reactor.update_timer(self._poll_timer, self.reactor.NOW)
    return True
```

`MMU_SPOOLMAN REFRESH=1` is intentionally not part of the default path. The
implementation should assess whether it is needed for auto-created spools when
using `NEXT_SPOOLID`.

### Responsibility Split

| Owner | Responsibility |
|---|---|
| NFC shared reader | Detect tag, resolve spool, maintain pending timeout, stage `NEXT_SPOOLID` when preload hook fires and a pending spool exists. |
| Happy Hare | Detect that pregate preload is starting and apply `NEXT_SPOOLID` to the loaded gate. |
| `_NFC_SHARED_PRELOAD` macro | Bridge from HH extension variable to `NFC_SHARED PRELOAD_CHECK=1`. Override point for user customisation. |
| `_NFC_SHARED_POST_UNLOAD` macro | Bridge from HH post-unload hook to `NFC_SHARED READ=1`. Override point for user customisation. |

---

## No-Pending Behavior

When no valid shared tag is pending:

- pregate-triggered preload proceeds normally
- no `NEXT_SPOOLID` is staged by NFC
- Happy Hare remains fully usable for manual spool assignment and normal loading

The shared reader must never block filament loading. A missing scan only means
there is no shared spool to stage.

---

## Timeout Behavior

`pending_timeout` starts when a tag resolves. `NEXT_SPOOLID` is not issued until
the preload hook fires.

If a gate is preloaded before the timeout:

```text
scan tag -> pending spool 42
HH preload hook/event occurs
NFC issues MMU_GATE_MAP NEXT_SPOOLID=42
HH applies NEXT_SPOOLID=42 to the gate being loaded
NFC clears pending state
LED success/ready feedback ends
```

After `scan tag -> pending spool 42`, shared polling should already be stopped.
Removing the tag from the reader must not clear the pending spool.

If the timeout expires first:

```text
scan tag -> pending spool 42
no preload before pending_deadline
NFC clears pending state
LED returns to idle/default
```

After timeout:

- preloading works normally
- no spool assignment happens from the shared reader until a new tag is scanned
- Happy Hare remains available for manual spool assignment

Scanning is activation-based, not startup-based. A gate-ejected hook is the
normal automatic activation path, because ejecting a gate is the moment the user
is likely preparing the next spool. Manual activation remains available with
`NFC_SHARED READ=1`.

Polling can be stopped with `NFC_SHARED READ=0`. If no valid tag is found
after `shared_read_timeout` seconds, shared mode stops polling automatically.
The default timeout is 120 seconds.

---

## Sequential Load Session

The shared reader supports loading multiple spools into multiple lanes in a single
uninterrupted workflow. The user starts one read session, then taps and loads
repeatedly until all lanes are loaded.

After `PRELOAD_CHECK` successfully stages a spool, polling restarts automatically.
The reader is immediately ready for the next tap without any user action.

Example — 4 spools, 4 lanes, `startup_polling: 1`:

```text
Klipper boots → shared reader begins polling automatically

tap spool 1 on shared reader
  → tag resolves: pending spool 42
  → polling stops (tag confirmed; LED feedback fires)

insert filament into any gate
  → HH pregate sensor fires → variable_user_pre_load_extension runs
  → NFC_SHARED PRELOAD_CHECK=1
      → MMU_GATE_MAP NEXT_SPOOLID=42
      → clear pending
      → restart polling          ← auto-restart, no read deadline

tap spool 2
  → tag resolves: pending spool 17
  → polling stops

insert filament into next gate
  → PRELOAD_CHECK → MMU_GATE_MAP NEXT_SPOOLID=17
  → clear pending → restart polling

tap spool 3, insert, tap spool 4, insert ...
```

### Auto-Restart Behavior

The auto-restart inside `PRELOAD_CHECK` clears `_shared_read_deadline` to `0.0`
before restarting the timer. This means:

- The original 120 s deadline from `NFC_SHARED READ=1` is not re-applied after
  the first successful preload. All subsequent polling within the session runs
  indefinitely.
- No second `NFC_SHARED READ=1` is needed between spools.
- The session ends only when the user explicitly calls `NFC_SHARED READ=0` or
  `NFC_SHARED CLEAR=1`.

`PRELOAD_CHECK` restarts polling **only when a spool was actually staged**. If
`PRELOAD_CHECK` finds no pending spool (nothing was scanned, or the timeout
expired), no restart occurs. Polling continues in whatever state it was already
in.

### Eject-Hook Path

With `startup_polling: 1`, the post-unload eject hook is not required — the
reader is already polling. If `READ=1` fires from the hook while polling is
already active, `_set_reading` clears any stale pending spool and restarts
cleanly.

If `startup_polling` is left at `0`, the eject hook is the normal automatic
activation path: `NFC_SHARED READ=1` starts polling after each unload with a
`shared_read_timeout` deadline. After the first successful PRELOAD_CHECK the
deadline clears and polling is indefinite for the rest of the session.

### Stopping the Session

| Command | Effect |
|---|---|
| `NFC_SHARED READ=0` | Stop polling. Keep any pending spool. |
| `NFC_SHARED CLEAR=1` | Stop polling. Clear pending spool and gate state. |

---

## LED Feedback

LED feedback should be minimal. The only required shared LED indication is:

```text
tag read successfully -> blinking yellow LED response
```

This should follow the same model as the EMU LED configuration: define a named
`[mmu_led_effect ...]`, then reference that effect by name from the NFC config.
NFC should not need a dedicated LED macro.

Example NFC config:

```ini
shared_tag_read_effect: mmu_RFID_read
```

Example effect definition, in the same style as `emu_macros.cfg`:

```ini
[mmu_led_effect mmu_RFID_read]
define_on: gates,exit
layers: strobe 1 0 top (1.0, 0.75, 0.0)
```

When a tag resolves and becomes the pending shared spool, NFC issues:

```gcode
MMU_SET_LED EXIT_EFFECT=<shared_tag_read_effect> DURATION=3
```

`MMU_SET_LED` is the public HH LED command (`mmu_led_manager.py`). Passing
`EXIT_EFFECT=<name>` with a base effect name causes HH to internally invoke
`_MMU_SET_LED_EFFECT EFFECT=unit0_<name>_exit`, which plays the
`[mmu_led_effect]` defined effect on all exit LEDs. `DURATION` limits how long
the effect runs before HH returns exit LEDs to their default state.

The effect name in config (`shared_tag_read_effect`) is the bare `[mmu_led_effect]`
section name without the `unit0_` prefix and segment suffix that HH appends
internally. NFC passes the name exactly as configured; HH handles the rest.

Example full invocation from `_shared_handle_event`:
```python
gcode.run_script(
    "MMU_SET_LED EXIT_EFFECT=%s DURATION=3" % self._shared_tag_read_effect)
```

If `MMU_SET_LED` is not available (no `[mmu_leds]` configured), the
`run_script` call will fail silently with a GCode error logged to the console.
NFC should not treat LED failure as a fatal error — the shared spool is already
staged at this point and the preload will proceed regardless.

---

## Commands

Proposed user/debug commands:

```gcode
NFC_SHARED STATUS
NFC_SHARED CLEAR
NFC_SHARED PRELOAD_CHECK
```

Meanings:

| Command | Purpose |
|---|---|
| `STATUS` | Report pending UID/spool, timeout remaining, and last error. |
| `CLEAR` | Clear pending state and return LEDs to idle. |
| `PRELOAD_CHECK` | Hook command used by HH/user macros before automatic preload. |

`NFC_SHARED` operates on the single configured shared reader. Because v1 permits
only one shared reader, the command does not need a reader parameter.

`CLEAR` clears both the shared pending state (`_shared_pending_*` fields) and
the `GateState` tag cache, then returns LEDs to idle. It is the correct command
to fully reset shared state.

`NFC_SHARED CLEAR_CACHE=1` clears only the `GateState` tag cache (UID and
spool). It does **not** clear `_shared_pending_*` fields. Use it when you want
to force a fresh hardware read on the next poll without discarding a pending
spool assignment.

`PRELOAD_CHECK` should be intentionally small. It should only answer:

- is a valid pending spool available?
- has it expired?
- is the printer/MMU in a safe state to stage `NEXT_SPOOLID`?
- should `MMU_GATE_MAP NEXT_SPOOLID=<id>` be issued?

It should not inspect lane NFC state, and it must not read RFID.

Status output should include shared state. `NFC_SHARED STATUS` should report one
of:

```text
shared: idle
shared: polling, no tag pending
shared: pending spool 42 uid=ABCDEF expires in 87s
shared: expired spool 42 uid=ABCDEF
shared: error <last_error>
```

`NFC_STATUS` should include the shared reader after the numbered EMU lanes.
`_lane_status_lines()` currently iterates `_lane_instances` matched against
`lane<N>` MCU names. A shared reader (`_name == 'shared'`) will never match a
lane MCU and would be silently omitted from the primary path. The fix: after
the lane MCU loop, scan `_lane_instances` for any gate where `_shared is True`
and append its status line. No separate section header is needed — one
appended line using the same `NFC_SHARED STATUS` output format is sufficient.

General reader activation and debug use `NFC_SHARED`:

```gcode
NFC_SHARED READ=1
NFC_SHARED READ=0
NFC_SHARED POLL=1
NFC_SHARED STATUS=1
NFC_SHARED CLEAR_CACHE=1
NFC_SHARED SCAN=1
NFC_SHARED INIT=1
```

---

## Installer / Uninstaller

### Upfront Branch

The first interactive question in `install.sh` becomes a reader-type selection.
Lane is the default because it covers the existing majority of installs:

```
1. Reader type
   lane   = per-lane PN532, one per EBB42 board (default)
   shared = single reader inside MMU body for staging spools
```

The `prompt_choice` helper already handles this pattern. The selection drives
the rest of the flow:

```bash
prompt_choice READER_TYPE \
    "1. Reader type" \
    "lane" \
    "lane" "shared"
```

Everything after this question is conditional on `READER_TYPE`.

---

### Lane Path (existing flow, renumbered)

No changes to the lane logic. Questions renumber from 1 onward after the new
Q1 type branch:

| # | Question | Default |
|---|---|---|
| 1 | Reader type | `lane` |
| 2 | How many lanes? | detected from existing hw cfg |
| 3 | Spoolman connection | `auto` |
| 4 | Startup polling? | yes |
| 5 | Scan-jog? | yes |
| 6 | Tag read mode | `spoolman` |
| 7 | Bambu reads? (rich only) | no |
| 8 | Auto-create spools? (rich only) | yes |

Settings applied to `nfc_reader.cfg`:
- `spoolman_url`, `startup_polling`, `scan_enabled`, `tag_parsing`,
  `bambu_reads`, `spoolman_auto_create`

Hardware written by `write_lane_config "${NFC_READER_HW_CFG}" "${LANE_COUNT}"`.

---

### Shared Path (new)

When `READER_TYPE=shared`, the following questions replace the lane flow:

| # | Question | Default |
|---|---|---|
| 1 | Reader type | `lane` |
| 2 | Spoolman connection | `auto` |
| 3 | Poll at Klipper boot? | yes |
| 4 | Tag read mode | `spoolman` |
| 5 | Bambu reads? (rich only) | no |
| 6 | Auto-create spools? (rich only) | yes |

Questions dropped vs lane path:
- **Number of lanes** — there is only one shared reader, never a count.
- **Scan-jog** — always disabled; not a user choice.

**Question 3 framing for shared** differs from the lane equivalent. Lane
startup polling is about whether lanes start reading on boot. For shared the
question is "Tap a spool at any time — start polling at boot?":

```
3. Start polling at Klipper boot so you can tap a spool at any time?
   Recommended for shared readers — no NFC command needed before loading.
   [Y/n]:
```

Default is `yes` because `startup_polling: 1` is the recommended shared
reader mode.

**I2C hardware prompt** — the shared reader sits on the MMU main board, not an
EBB42. Ask for the MCU name with a sensible default:

```
3b. I2C MCU for the shared reader (the Klipper MCU that hosts the PN532 bus)
    [mmu]:
```

---

### Shared Config Generation

The lane path calls `write_lane_config` to overwrite `nfc_reader_hw.cfg`.
The shared path calls a parallel `write_shared_config`:

```bash
write_shared_config() {
    local file_path="$1"
    local i2c_mcu="$2"
    local startup_polling="$3"

    cat > "${file_path}" <<SHARED_CFG
# =============================================================================
# EMU NFC Gate Reader — Shared PN532 Hardware
# =============================================================================
# Single reader mounted inside the MMU body.  Tap a tagged spool before
# loading; NFC stages the spool ID for the next pregate preload automatically.
#
# Include after nfc_reader.cfg and nfc_macros.cfg:
#   [include nfc/nfc_reader.cfg]
#   [include nfc/nfc_macros.cfg]
#   [include nfc/nfc_reader_hw.cfg]
# =============================================================================

[nfc_gate shared]
i2c_mcu:                ${i2c_mcu}
i2c_bus:                i2c1
i2c_address:            0x24
shared:                 true
startup_polling:        ${startup_polling}

# Optional: uncomment and set to a named [mmu_led_effect] for tag-read feedback
# shared_tag_read_effect: mmu_RFID_read

# Optional: adjust staging window (seconds a scanned spool stays pending)
# shared_pending_timeout: 120.0
SHARED_CFG
}
```

Called in place of `write_lane_config`:

```bash
if [ "${READER_TYPE}" = "shared" ]; then
    write_shared_config "${NFC_READER_HW_CFG}" "${I2C_MCU}" \
        "$( [ "${STARTUP_POLLING}" = "yes" ] && echo "1" || echo "0" )"
else
    write_lane_config "${NFC_READER_HW_CFG}" "${LANE_COUNT}"
fi
```

---

### Settings Applied to nfc_reader.cfg

For the shared path, `startup_polling` and `scan_enabled` are **not** written
to `[nfc_gate]`. They are already handled in the generated `[nfc_gate shared]`
section. Writing them to the base `[nfc_gate]` defaults would have no effect
(no lane readers inherit them) and would mislead users reading the file.

| Key | Lane path | Shared path |
|---|---|---|
| `spoolman_url` | written to `[nfc_gate]` | written to `[nfc_gate]` |
| `startup_polling` | written to `[nfc_gate]` | written to `[nfc_gate shared]` by `write_shared_config` |
| `scan_enabled` | written to `[nfc_gate]` | not written (implied false) |
| `tag_parsing` | written to `[nfc_gate]` | written to `[nfc_gate]` |
| `bambu_reads` | written to `[nfc_gate]` | written to `[nfc_gate]` |
| `spoolman_auto_create` | written to `[nfc_gate]` | written to `[nfc_gate]` |

---

### Summary and Next Steps (Shared)

The summary block after install differs for the shared path:

```
Install complete.

  Selected options:
    reader type:        shared
    spoolman_url:       auto
    startup_polling:    yes
    tag_resolution:     Spoolman UID lookup
    i2c_mcu:            mmu

  Python extras (symlinked — auto-updates with git pull):
    ~/klipper/klippy/extras/nfc_gate.py  -> ...
    ~/klipper/klippy/extras/nfc_gates    -> ...

  Config files in ~/printer_data/config/nfc/:
    nfc_reader.cfg       ← Spoolman URL and shared settings
    nfc_macros.cfg       ← Happy Hare handoff macros (already has NFC_SHARED hooks)
    nfc_reader_hw.cfg    ← [nfc_gate shared] hardware config

Next steps (first install only):

  1. Confirm i2c_mcu and i2c_bus in nfc_reader_hw.cfg match your hardware.

  2. Add includes to printer.cfg:
       [include nfc/nfc_reader.cfg]
       [include nfc/nfc_macros.cfg]
       [include nfc/nfc_reader_hw.cfg]

  3. Restart Klipper:
     sudo systemctl restart klipper

  4. Update and flash the MCU hosting the shared PN532 reader.
     The PN532 uses Klipper's I2C bus layer — the MCU must be running
     the same Klipper version as the host. For most shared installs
     this is the MMU main board (e.g. the `mmu` MCU). Flash it the
     same way you flash any other Klipper MCU.

  5. Wire Happy Hare hooks in mmu_macro_vars.cfg:
       variable_user_pre_load_extension:    '_NFC_SHARED_PRELOAD'
       variable_user_post_unload_extension: '_NFC_SHARED_POST_UNLOAD'
     (post_unload hook is optional when startup_polling: 1)

  6. Moonraker update_manager — added automatically by this script.
```

The flash step is worded differently from the lane path. Lane readers use
dedicated EBB42 boards; the shared reader uses whichever MCU the user wired
the PN532 to, named by the `i2c_mcu` they entered at question 3b. The step
reflects that MCU name in the summary output so the user knows exactly what
to flash.

---

### Uninstaller Changes

The uninstaller (`uninstall.sh`) requires **no logic changes**. It removes the
same two symlinks (`nfc_gate.py`, `nfc_gates/`) and backs up the same
`~/printer_data/config/nfc/` directory regardless of whether the install was
lane mode, shared mode, or mixed. The backed-up directory contains
`nfc_reader_hw.cfg` with whichever sections were present; the user can recover
their config from that backup if needed.

Update the uninstaller header comment to mention the shared config:

```
# What this script does automatically:
#   1. Removes nfc_gate.py symlink
#   2. Removes nfc_gates/ symlink
#   3. Backs up ~/printer_data/config/nfc/ (includes nfc_reader_hw.cfg
#      whether it contains [nfc_gate laneN] or [nfc_gate shared] sections)
#   4. Restarts Klipper
```

---

## Minimal Implementation Shape

Prefer a small extension of `NFCGate` rather than a new reader module.

Reuse:

- `NFCGate._poll_timer_event()`
- `NFCGate._poll()`
- `GateState`
- `pn532_driver.py` / `rc522_driver.py`
- `tag_handler.py`
- `spoolman_client.py`
- `klipper_interface.py` dispatch style
- existing logging setup
- existing tag parser and auto-create behavior

The shared reader is an NFC gate object with shared dispatch enabled. It is not
a Happy Hare gate.

New code should be mostly:

- config keys on `[nfc_gate shared]`: `shared`, `shared_pending_timeout`,
  `shared_read_timeout`, and `shared_tag_read_effect`
- pending-spool fields on `NFCGate`
- a shared branch in `_poll_dispatch_event()`
- a small `_shared_handle_event()` helper
- `NFC_SHARED STATUS/CLEAR/PRELOAD_CHECK` command handling
- a helper to run `MMU_GATE_MAP NEXT_SPOOLID=<id>` from `PRELOAD_CHECK`
- `NFC_SHARED` command handling for READ, STATUS, CLEAR, PRELOAD_CHECK, POLL,
  SCAN, INIT, CLEAR_CACHE
- shared status output in both `NFC_SHARED STATUS` and `NFC_STATUS`

---

## Open Questions

1. ~~Confirm on hardware that `variable_user_post_unload_extension` fires after
   `MMU_EJECT`.~~ **Resolved.** HH `mmu_macro_vars.cfg` explicitly groups
   `MMU_UNLOAD`/`MMU_EJECT` under the same "unload" operation; this hook covers
   both. Confirm timing on hardware (gate empty before first poll tick) during
   integration testing.
2. ~~What exact Happy Hare hook fires before pregate-triggered automatic
   preload?~~ **Resolved.** `variable_user_pre_load_extension` fires before a
   pregate-triggered preload. Set it to `'NFC_SHARED PRELOAD_CHECK'`.
3. Does `MMU_GATE_MAP NEXT_SPOOLID=<id>` accept a newly auto-created spool ID
   without `MMU_SPOOLMAN REFRESH=1`, or is a refresh required at preload-check
   time?
4. ~~What is the exact HH LED command that plays a named `mmu_led_effect`?~~
   **Resolved.** `MMU_SET_LED EXIT_EFFECT=<name> DURATION=<seconds>`. HH's
   `mmu_led_manager.py` maps the base effect name to the internal
   `unit0_<name>_exit` effect and invokes `_MMU_SET_LED_EFFECT`. See LED
   Feedback section for the full invocation.
