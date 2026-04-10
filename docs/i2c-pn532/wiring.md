# I2C / PN532 — Wiring Diagram & Pin Reference

[← Back to I2C Setup](setup.md) | [← Back to Index](../../Readme.md)

---

## Overview

One **PN532 NFC module** is wired to each EBB42 lane board using the board's
**software I2C bus** on PB3 (SCL) and PB4 (SDA). The PN532 shares these two wires
with the existing BME280 temperature sensor at address 118 (0x76) — there is no conflict
because the PN532 uses a different I2C address 36 (0x24).

No separate MCU or CAN transceiver is needed. The EBB42 lane MCUs are already on
the CAN bus via Happy Hare's `mmu_hardware.cfg`.

---

## Per-Gate Wiring (repeat for each lane)

```
EBB42 Lane Board                  PN532 Module
┌──────────────────┐              ┌──────────────────┐
│  PB3 (SCL) ──────┼──────────────┼─► SCL            │
│  PB4 (SDA) ──────┼──────────────┼─► SDA            │
│  3V3       ──────┼──────────────┼─► VCC (3.3V)     │
│  GND       ──────┼──────────────┼─► GND            │
└──────────────────┘              └──────────────────┘
                                  (also wired to BME280
                                   on PB3/PB4 — different
                                   I2C address 118 (0x76))
```

> **Address:** The PN532 default I2C address is `36` (0x24).
> The BME280 is at `118` (0x76) — both devices are on the same two wires with no conflict.

---

## PN532 Module Pinout

PN532 breakout boards vary by manufacturer, but all expose these connections:

| PN532 Pin | Function | Connect to (EBB42) |
|---|---|---|
| VCC | Power (3.3V) | 3V3 |
| GND | Ground | GND |
| SDA | I2C data | PB4 |
| SCL | I2C clock | PB3 |

> **Mode selection:** Some PN532 modules have DIP switches or solder jumpers to
> select between SPI, I2C, and UART modes. Set the module to **I2C mode** before
> wiring. On SparkFun / Adafruit boards this is typically:
> - SPI: `SEL0=L, SEL1=L`
> - **I2C: `SEL0=H, SEL1=L`**
> - HSU: `SEL0=L, SEL1=H`
>
> Consult your module's datasheet if the switches are labelled differently.

---

## I2C Address Selection

The PN532's I2C address is hardware-selectable via address pads on some modules:

| A1 pad | A0 pad | I2C Address |
|---|---|---|
| 0 | 0 | 36 (0x24) — default |
| 0 | 1 | 37 (0x25) |
| 1 | 0 | 38 (0x26) |
| 1 | 1 | 39 (0x27) |

All gates in this configuration use address 36 (0x24) because each PN532 is on its own
dedicated I2C bus (one EBB42 per gate). Address selection only matters if you are
putting multiple PN532 readers on a shared bus (not this configuration).

---

## Multi-Gate Wiring Summary

Each gate is completely independent — the PB3/PB4 bus on lane 0 has no connection to
the PB3/PB4 bus on lane 1, etc. Each bus carries:

- One BME280 at address 118 (0x76) — already installed by Happy Hare
- One PN532 at address 36 (0x24) — new, added by this project

```
CAN bus
  │
  ├─ lane0 MCU (EBB42)  ←── PB3/PB4 ──→  BME280@118  +  PN532@36  (Gate 0)
  ├─ lane1 MCU (EBB42)  ←── PB3/PB4 ──→  BME280@118  +  PN532@36  (Gate 1)
  ├─ lane2 MCU (EBB42)  ←── PB3/PB4 ──→  BME280@118  +  PN532@36  (Gate 2)
  ├─ lane3 MCU (EBB42)  ←── PB3/PB4 ──→  BME280@118  +  PN532@36  (Gate 3)
  └─ lane4 MCU (EBB42)  ←── PB3/PB4 ──→  BME280@118  +  PN532@36  (Gate 4)
```

---

## Pull-up Resistors

I2C requires pull-up resistors on SDA and SCL. Most PN532 breakout boards include
on-board pull-ups (typically 10 kΩ). If your module does not, add 4.7 kΩ resistors
from SDA to 3V3 and SCL to 3V3 at the PN532 end.

> Do not add external pull-ups if the module already has them — doubling up reduces
> the effective pull-up resistance and can cause communication errors.
