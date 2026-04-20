# Configuration Reference

[← README](../../Readme.md) | [Commands & Macros →](klipper-functions.md)

---

## Config File Overview

Three files, included in this order from `printer.cfg`:

```ini
[include NFC/nfc_vars.cfg]    ; base settings — edit this
[include NFC/nfc_macros.cfg]  ; Happy Hare event macros — edit only if needed
[include NFC/pn532_i2C.cfg]   ; one section per physical gate — edit this
```

**How inheritance works:** `nfc_vars.cfg` defines the base `[nfc_gate]` section with all defaults. Each `[nfc_gate laneN]` in `pn532_i2C.cfg` inherits every key automatically. Override a key in a lane section only when that lane needs a different value.

---

## `nfc_vars.cfg` — Base Settings

### Spoolman

```ini
[nfc_gate]
spoolman_url:       auto
spoolman_rfid_key:  rfid_tag
spoolman_timeout:   5.0
spoolman_cache_ttl: 300
```

| Setting | Default | Description |
|---|---|---|
| `spoolman_url` | `auto` | `auto` reads the URL from Moonraker's `[spoolman]` config. Set to `http://host:port` to use a direct URL. Leave empty to disable Spoolman lookup. |
| `spoolman_rfid_key` | `rfid_tag` | Name of the extra field on Spoolman spool records that holds the tag UID. Must match exactly — case-sensitive. |
| `spoolman_timeout` | `5.0` | HTTP request timeout in seconds. Increase if you see timeouts on a slow network. |
| `spoolman_cache_ttl` | `300` | How long (seconds) a UID→spool lookup is cached. `0` disables caching. |

---

### Polling

```ini
[nfc_gate]
startup_polling:    -1
startup_poll_delay: 0.0
poll_interval:      30
absent_threshold:   3
```

| Setting | Default | Description |
|---|---|---|
| `startup_polling` | `-1` | `-1` = manual start only. `1` = start polling automatically after PN532 init. `0` = explicitly disabled (useful as a lane override). |
| `startup_poll_delay` | `0.0` | Seconds to wait before the first automatic poll. Stagger this across lanes to avoid simultaneous reads. |
| `poll_interval` | `30` | Seconds between polls while background polling is active. |
| `absent_threshold` | `3` | Consecutive missed reads before `_NFC_SPOOL_REMOVED` fires. At 30s interval, default = ~90s before removal. |

> [!TIP]
> For bench testing, use `poll_interval: 5` and `absent_threshold: 1` so state changes fire quickly. Restore production values before a real print run.

**Effective removal time:**
```
poll_interval × absent_threshold = seconds before removal fires
30 × 3 = 90 seconds  (default)
```

---

### PN532 I2C Address

```ini
[nfc_gate]
i2c_address: 36
```

Decimal address of the PN532 module. Default `0x24` = decimal `36`. Only change this if you set the PN532 address pads (A0/A1). For the per-lane design, every PN532 is on its own bus so all can stay at the default.

| Pad setting (A1/A0) | Decimal | Hex |
|---|:---:|:---:|
| 0/0 | `36` | `0x24` |
| 0/1 | `37` | `0x25` |
| 1/0 | `38` | `0x26` |
| 1/1 | `39` | `0x27` |

---

### PN532 Timing

```ini
[nfc_gate]
transceive_delay: 0.250
crc_delay:        0.050
```

These are tuned for CAN bus round-trip latency on the EBB42. Leave them at defaults unless you're debugging timing-related failures.

| Setting | Default | Description |
|---|---|---|
| `transceive_delay` | `0.250` | Seconds to wait after `InListPassiveTarget` before reading the response. The PN532 scans for tags during this window. Increase if you see spurious `i2c_read_response` timeouts. |
| `crc_delay` | `0.050` | Seconds after `InRelease` before the next command. |

---

### Logging

```ini
[nfc_gate]
log_file:          nfc_reader.log
debug:             2
console_output:    False
console_log_level: warning
```

| Setting | Default | Description |
|---|---|---|
| `log_file` | `nfc_reader.log` | Log filename. Relative paths resolve to `~/printer_data/logs/`. Set to an absolute path to write elsewhere. Leave empty to use the main Klipper log only. |
| `debug` | `2` | `0` (or `off`) = no logging. `1` (or `error`) = errors only. `2` (or `warning`) = warnings and errors. `3` (or `info`) = state changes, Spoolman lookups, HH handoff. `4` (or `debug`) = full I2C protocol trace. |
| `console_output` | `False` | Send NFC log messages to the Fluidd/Mainsail console. Errors always appear in the console regardless of this setting. |
| `console_log_level` | `warning` | Minimum level to show in console when `console_output: True`. Accepts string (`error`, `warning`, `info`, `debug`) or numeric (`1`–`4`). |

**Recommended for normal printing:**
```ini
console_output:    False
console_log_level: warning
```

**Recommended during setup or debugging:**
```ini
console_output:    True
console_log_level: info
debug:             3
```

---

### Expert Debug Flag

```ini
[nfc_gate]
low_level_debug: False
```

When `True`, exposes manual PN532 I2C bus commands (`STEP`, `RAW_READ`, `RAW_WRITE`, etc.) on the `NFC_GATE` command for step-by-step bring-up debugging.

> [!WARNING]
> These commands bypass the normal state machine. Set back to `False` before printing.

See [Commands & Macros](klipper-functions.md#expert-low-level-debug-commands) and [Expert: Low-Level I2C Debugging](expert-low-level-i2c-debugging.md).

---

## `pn532_i2C.cfg` — Lane Hardware

One `[nfc_gate laneN]` section per physical gate:

```ini
[nfc_gate lane0]
mmu_gate:   0
i2c_mcu:    lane0
i2c_bus:    i2c3_PB3_PB4
```

| Key | Required | Description |
|---|:---:|---|
| `mmu_gate` | Yes | Happy Hare gate number (0-based integer). Gate 0 = first MMU gate. |
| `i2c_mcu` | Yes | Klipper MCU name. Must exactly match an `[mcu laneN]` section in your config. |
| `i2c_bus` | Yes | Hardware I2C bus on that MCU. For PB3/PB4 on EBB42: `i2c3_PB3_PB4`. |

Any `nfc_vars.cfg` key can be overridden per lane. Example — verbose logging and auto-polling on one lane only:

```ini
[nfc_gate lane2]
mmu_gate:           2
i2c_mcu:            lane2
i2c_bus:            i2c3_PB3_PB4
debug:              2
startup_polling:    1
startup_poll_delay: 4.0
```

---

## `nfc_macros.cfg` — Event Macros

These macros are called by NFC_Manager when gate state changes. Edit them to adjust Happy Hare command calls for your Happy Hare version. Do not put Happy Hare commands anywhere else.

### `_NFC_SPOOL_CHANGED`

Called when a new tag UID resolves to a Spoolman spool. Parameters: `GATE`, `SPOOL_ID`, `UID`.

Default:
```gcode
MMU_GATE_MAP GATE={gate} SPOOLID={spool_id} AVAILABLE=1 SYNC=1 QUIET=1
MMU_GATE_MAP GATE={gate} APPLY=1
```

### `_NFC_SPOOL_REMOVED`

Called after `absent_threshold` consecutive missed polls. Parameter: `GATE`.

Default:
```gcode
MMU_GATE_MAP GATE={gate} SPOOLID=-1 AVAILABLE=0 SYNC=1 QUIET=1
MMU_GATE_MAP GATE={gate} APPLY=1
```

### `_NFC_TAG_NO_SPOOL`

Called when a tag is detected but no matching spool is found in Spoolman. Parameters: `GATE`, `UID`.

Default: prints the unknown UID to the console with instructions to register it.

---

*Copyright (C) 2026 WoodWorker. Licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — see [LICENSE](../../LICENSE).*
