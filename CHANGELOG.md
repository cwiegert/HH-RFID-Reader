# Changelog

All notable changes to the EMU NFC Gate Reader are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [05/18/2026]

### Shared Reader Improvements

- Added full shared-reader command coverage through `NFC_SHARED`, including help, status, summary, cancel, replace, LED test, cache sync, polling, scan, and raw poll actions.
- `NFC_SHARED HELP=1` now documents the required `=1` action flag style so commands match Klipper's parser and avoid malformed bare commands.
- Shared-reader installs now include the base `nfc_reader.cfg` along with `nfc_reader_shared.cfg`, so the standard NFC commands and shared commands are both available after install.
- Shared-reader polling uses the scan-jog reader interval, not the slower base polling interval. The config comments now call this out so tuning the shared reader is less mysterious.
- The shared reader now prints a green `[OK]` line as soon as a tag is successfully read and staged, before the later Happy Hare preload messages.
- `nfc_reader_shared.cfg` now defaults `i2c_mcu: mmu` so the most common wiring works without editing the hardware config.

### LED Behavior

- Fixed indefinitely looping unresolved-tag strobe — it now plays a fixed number of flashes and stops cleanly.
- `mmu_RFID_ready` (green strobe) now persists continuously while a spool is staged and waiting to load; previously it blinked twice and stopped.
- Added `mmu_RFID_warning` amber strobe: plays when the pending timeout is 80% elapsed, giving the user a visible countdown before the spool is dropped.
- Amber warning strobe stops exactly when the pending timeout expires — no overshoot.
- After all NFC effects finish, HH gate LEDs are restored via `MMU_GATE_MAP QUIET=1` only when no spool is pending, preventing HH's gate repaint from killing the active ready effect mid-wait.
- On pending timeout, polling always restarts automatically (equivalent to issuing `NFC_SHARED REPLACE=1`).

### Klipper Deadlock Fix

- Eliminated a class of Klipper deadlocks caused by calling `run_script()` from inside GCode command handlers. All LED, respond, and HH gate-map calls that originate from GCode handlers are now deferred via `register_async_callback`. Affected commands: `NFC_SHARED LED_TEST`, `REPLACE`, `CANCEL`, `CLEAR`, `PRELOAD_CLEAR_ASSIGNED`.

### Happy Hare Preload Behavior

- Fixed the pure shared-reader stale assignment path. If Happy Hare still has a spool assigned to a gate when the shared reader stages that same spool, NFC now clears the stale Happy Hare gate assignment and gets ready for the next tag.
- Hybrid installs are still protected: when per-lane readers are present, the shared reader does not overwrite or clear legitimate per-lane assignments.
- `NFC_SHARED PRELOAD_CLEAR_ASSIGNED=1` now receives the assigned gate number so the automatic cleanup can target the correct Happy Hare gate.
- `force_spool_id` no longer throws a Klipper command error when no spool is staged. It now shows one red `[ERROR]` console advisory instead of duplicated `!!` error lines.
- `_NFC_SHARED_PRELOAD` macro cross-checks `gate_status` when evaluating already-assigned spools — a gate with status 0 (filament absent) is no longer treated as occupied, fixing the case where a spool ejected from a gate with no per-lane reader left a stale HH assignment that blocked future loads of the same spool.

### Console Output

- All NFC console messages now route through the logger rather than inline `RESPOND` GCode calls, eliminating `echo:` format output and removing a second source of deadlocks.
- Standardized console tag colors:
  - `[OK]` renders green.
  - `[WARN]` renders yellow.
  - `[ERROR]` renders red text without forcing a Klipper error unless the command truly fails.
- Reduced duplicate shared-reader warnings by keeping recovered stale-assignment details in the internal log and showing only one concise console warning.
- Replaced stop-sign precondition glyphs with `[ERROR]` for clearer, consistent console messages.

### Documentation

- README and quick-install guide updated with the correct Happy Hare hook parameter: `variable_user_post_preload_extension: '_NFC_SHARED_PRELOAD'` in `mmu_macro_vars.cfg`.
- Install instructions now list the required config includes for shared-reader installs.
- Command reference updated to cover `NFC_SHARED` commands users are expected to run day-to-day.
