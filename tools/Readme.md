# pn532_scan.py — Standalone PN532 Scanner

Reads a PN532 NFC reader directly from a Raspberry Pi using the native Linux
I2C layer — no Klipper, no MCU, no CAN bus required.

Use this to confirm wiring and tag detection before integrating with Klipper.

---

## Prerequisites

### Enable I2C on the Pi

```bash
sudo raspi-config
```

Navigate to **Interface Options → I2C → Enable**, then reboot.

Confirm the device is present:

```bash
ls /dev/i2c-*
# expected: /dev/i2c-1
```

### Install smbus2

```bash
sudo apt install python3-smbus2
```

---

## Wiring

| PN532 Pin | Pi Pin | Pi GPIO |
|---|---|---|
| VCC | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 (I2C1 SDA) |
| SCL | Pin 5 | GPIO3 (I2C1 SCL) |

> **I2C mode:** Set the PN532 to I2C mode before wiring (DIP switch or solder jumper).
>
> | SEL0 | SEL1 | Mode |
> |---|---|---|
> | L | L | SPI |
> | **H** | **L** | **I2C ← use this** |
> | L | H | HSU (UART) |

> **Default address:** `0x24` — change with `--address` if your ADDR pins are set differently.

---

## Usage

Run from the repository root on the Pi.

### Step 1 — Confirm the PN532 is visible on the bus

```bash
python3 tools/pn532_scan.py --scan-bus
```

Expected output:

```
Scanning I2C bus 1 for devices...
  0x24  (36)

1 device(s) found.
```

If nothing appears — check wiring and the I2C mode jumper.

---

### Step 2 — Poll for tags

```bash
python3 tools/pn532_scan.py
```

```
PN532 scanner — I2C bus 1, address 0x24
Poll interval: 2.0s   Debug: 1
Press Ctrl+C to stop.

Initialising PN532...
PN532 ready.

TAG DETECTED  UID=A3F200CC
Tag removed.
```

Press **Ctrl+C** to stop.

---

### Options

| Option | Default | Description |
|---|---|---|
| `--bus N` | `1` | I2C bus number (`/dev/i2c-N`) |
| `--address 0xNN` | `0x24` | PN532 I2C address |
| `--poll N` | `2.0` | Poll interval in seconds |
| `--debug` | off | Full protocol trace (every I2C transaction) |
| `--once` | off | Exit after first tag read |
| `--scan-bus` | off | Scan bus for all responding devices and exit |

---

### Full protocol trace

```bash
python3 tools/pn532_scan.py --debug
```

Prints every I2C transaction — useful when the PN532 initialises but tags are not detected.

---

### Read one tag and exit

```bash
python3 tools/pn532_scan.py --once
```

---

## Troubleshooting

**"smbus2 is not installed"**
```bash
sudo apt install python3-smbus2
```

**"ERROR: PN532 gate 0 did not respond"**
1. Run `--scan-bus` — if `0x24` is not listed the chip is not on the bus
2. Confirm the PN532 is in **I2C mode** — most common cause of no response
3. Check VCC is **3.3V** (not 5V), SDA → Pin 3, SCL → Pin 5
4. Confirm I2C is enabled: `sudo raspi-config → Interface Options → I2C`

**"Permission denied: /dev/i2c-1"**
```bash
sudo usermod -aG i2c $USER
# log out and back in, then retry
```

**Tag not detected**
- Hold tag flat and close (< 3 cm) to the antenna coil
- Run `--debug` to see whether `InListPassiveTarget` is completing
- Try rotating the tag — some tags are orientation-sensitive

---

*Copyright (C) 2026 WoodWorker. Licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) — see [LICENSE](../LICENSE).*
