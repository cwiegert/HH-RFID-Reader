# Debugging

[Back to README](../../Readme.md)

Start with normal commands:

```gcode
NFC_GATE_STATUS
NFC_GATE NAME=lane0 STATUS=1
NFC_GATE NAME=lane0 INIT=1
NFC_GATE NAME=lane0 SCAN=1
NFC_GATE NAME=lane0 POLL=1
```

## Logging

Set in `nfc_vars.cfg`:

```ini
[nfc_gate]
debug: 1
log_file: nfc_reader.log
```

Debug levels:

| Level | Meaning |
|---:|---|
| `0` | warnings and errors |
| `1` | normal state changes and lookup results |
| `2` | protocol-level trace |

Console output:

```ini
console_output: True
console_log_level: info
```

Errors always go to the console once the NFC module is loaded.

## Fast Bench Testing

```ini
poll_interval: 5
absent_threshold: 1
```

Restore production values when finished:

```ini
poll_interval: 30
absent_threshold: 3
```

## Simulate Happy Hare Calls

```gcode
_NFC_SPOOL_CHANGED GATE=0 SPOOL_ID=1042 UID=04AABBCCDD
_NFC_SPOOL_REMOVED GATE=0
_NFC_TAG_NO_SPOOL GATE=0 UID=04AABBCCDD
```

## Expert Debug

For bus-level PN532 I2C work, see [Expert: low-level PN532 I2C debugging](expert-low-level-i2c-debugging.md).
