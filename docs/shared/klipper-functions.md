# Klipper Commands & Macros

[← Back to README](../../Readme.md)

---

## Overview

NFC Gate Reader exposes one Klipper GCode command: `NFC_GATE`. All operations route through it using named parameters. There is also a status command `NFC_GATE_STATUS`.

The Python layer (`NFC_Manager`) dispatches three GCode macros to Happy Hare when gate state changes. Those macros live in `nfc_macros.cfg` and are the only place Happy Hare commands should appear.

---

## User Commands

### `NFC_GATE_STATUS`

Prints the NFC_Manager's in-memory gate state for every configured lane.

```gcode
NFC_GATE_STATUS
```

**Example output:**

```
NFC gate status  (4 gates configured):
  Gate 0  [lane0]:  spool 1042    UID 04AABBCCDD
  Gate 1  [lane1]:  empty
  Gate 2  [lane2]:  spool 7       UID 04112233
  Gate 3  [lane3]:  empty
```

> [!NOTE]
> This shows the NFC module's last known state. It reflects what the PN532 most recently read, combined with what Spoolman returned. It is not a live I2C bus read when you run the command.

---

### `NFC_GATE NAME=<lane> STATUS=1`

Shows the state of one specific lane.

```gcode
NFC_GATE NAME=lane0 STATUS=1
```

---

### `NFC_GATE NAME=<lane> INIT=1`

Runs the PN532 initialization sequence for the named lane: wakes the PN532, sends `GetFirmwareVersion`, and sends `SAMConfiguration`.

```gcode
NFC_GATE NAME=lane0 INIT=1
```

**Use when:**
- First time wiring a new PN532.
- A lane shows "reader failed" state after a power cycle or Klipper restart.
- After a wiring change or MCU firmware flash.

If `INIT=1` fails, check wiring, PN532 mode selection, and MCU firmware version. See [Troubleshooting](../i2c-pn532/troubleshooting.md).

---

### `NFC_GATE NAME=<lane> SCAN=1`

Reads the PN532 hardware once and reports the tag identity directly. **Does not run the Spoolman lookup, state machine, or macro dispatch.**

```gcode
NFC_GATE NAME=lane0 SCAN=1
```

**Use when:**
- Confirming the hardware reads a tag.
- Getting the raw UID of an unregistered tag to copy into Spoolman.
- Isolating a hardware problem from a Spoolman or Happy Hare problem.

**Example output (tag present):**

```
NFC lane0 scan: UID 04AABBCCDD  ATQA=4400  SAK=00
```

**Example output (no tag):**

```
NFC lane0 scan: no tag detected
```

---

### `NFC_GATE NAME=<lane> POLL=1`

Runs one complete NFC_Manager poll cycle for the named lane:

1. PN532 hardware read.
2. UID normalization.
3. Spoolman lookup (if UID is new).
4. Gate state machine update.
5. Macro dispatch (`_NFC_SPOOL_CHANGED`, `_NFC_SPOOL_REMOVED`, or `_NFC_TAG_NO_SPOOL`) if state changed.

```gcode
NFC_GATE NAME=lane0 POLL=1
```

**Use when:**
- Testing the full pipeline end-to-end.
- Confirming Spoolman lookup works for a specific tag.
- Checking that the macro fires and Happy Hare receives the update.

---

### `NFC_GATE NAME=<lane> READ=1`

Starts continuous reactor-timer polling for the named lane at `poll_interval` seconds.

```gcode
NFC_GATE NAME=lane0 READ=1
```

### `NFC_GATE NAME=<lane> READ=0`

Stops reactor-timer polling for the named lane.

```gcode
NFC_GATE NAME=lane0 READ=0
```

---

## Manager-to-Macro Calls (Happy Hare Boundary)

NFC_Manager dispatches these three macros from Python. They are defined in `nfc_macros.cfg`. This is the **only** place Happy Hare commands should be called — not in `PN532Driver` or `SpoolmanClient`.

---

### `_NFC_SPOOL_CHANGED`

**Triggered when:** A UID is read that resolves to a Spoolman spool, and the gate's previous state was either empty or a different spool.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `GATE` | int | Happy Hare gate number |
| `SPOOL_ID` | int | Spoolman spool ID |
| `UID` | string | Normalized UID (e.g. `04AABBCCDD`) |

**Default macro body:**

```gcode
[gcode_macro _NFC_SPOOL_CHANGED]
gcode:
    {% set gate     = params.GATE     | int %}
    {% set spool_id = params.SPOOL_ID | int %}
    {% set uid      = params.UID %}
    { action_respond_info("NFC gate %d: spool %d detected (UID %s)" % (gate, spool_id, uid)) }
    MMU_GATE_MAP GATE={gate} SPOOLMAN_ID={spool_id}
```

---

### `_NFC_SPOOL_REMOVED`

**Triggered when:** A gate has had `absent_threshold` consecutive missed reads after a previously detected spool.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `GATE` | int | Happy Hare gate number |

**Default macro body:**

```gcode
[gcode_macro _NFC_SPOOL_REMOVED]
gcode:
    {% set gate = params.GATE | int %}
    { action_respond_info("NFC gate %d: spool removed" % gate) }
    MMU_GATE_MAP GATE={gate} SPOOLMAN_ID=-1
```

---

### `_NFC_TAG_NO_SPOOL`

**Triggered when:** A tag UID is detected but Spoolman returns no matching spool for that UID.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `GATE` | int | Happy Hare gate number |
| `UID` | string | Normalized UID that was not found in Spoolman |

**Default macro body:**

```gcode
[gcode_macro _NFC_TAG_NO_SPOOL]
gcode:
    {% set gate = params.GATE | int %}
    {% set uid  = params.UID %}
    { action_respond_info(
        "NFC gate %d: tag UID %s is not registered in Spoolman.\n"
        "Open the spool record in Spoolman, set the '%s' extra field to: %s" %
        (gate, uid, spoolman_rfid_key, uid)) }
```

The default behaviour is informational. If you want to clear the gate when a tag is unregistered, uncomment the `MMU_GATE_MAP GATE={gate} SPOOLMAN_ID=-1` line in `nfc_macros.cfg`.

---

## Testing the Macro Boundary Without Hardware

You can invoke the macros directly from the GCode console to verify Happy Hare integration without a physical PN532:

```gcode
_NFC_SPOOL_CHANGED GATE=0 SPOOL_ID=1042 UID=04AABBCCDD
_NFC_SPOOL_REMOVED GATE=0
_NFC_TAG_NO_SPOOL  GATE=0 UID=04AABBCCDD
```

This is useful for:
- Confirming `MMU_GATE_MAP` accepts the parameters.
- Verifying your Happy Hare version responds correctly.
- Debugging macro edits before deploying with live hardware.

---

## Customising the Happy Hare Calls

Edit `nfc_macros.cfg` to match your Happy Hare version or workflow.

**Common adjustments:**

- Call `MMU_SPOOLMAN UPDATE=1 GATE={gate} SPOOLID={spool_id}` alongside `MMU_GATE_MAP` if your version requires explicit Spoolman sync.
- Add a console beep or LED macro alongside the existing calls.
- Change the informational message format.

**Do not** move Happy Hare calls into `PN532Driver` or `SpoolmanClient`. The layering is intentional — see [Architecture Decisions](architecture-decisions.md) for the reasoning.

---

## Expert Debug Commands

Enable in `nfc_vars.cfg`:

```ini
[nfc_gate]
low_level_debug: True
```

Then restart Klipper and run:

```gcode
NFC_GATE NAME=lane0 HELP=1
```

This prints the full list of available low-level commands for manual PN532 bus control.

See [Expert: Low-Level I2C Debugging](expert-low-level-i2c-debugging.md) for the complete guide.
