# pn532_scan.py — Standalone PN532 Scanner

[← Back to Index](../../Readme.md)

---

## What It Does

`tools/pn532_scan.py` lets you test a PN532 wired directly to a Raspberry Pi's
GPIO I2C pins — no Klipper, no MCU, no CAN bus required.

Use it to confirm:
- The PN532 is wired correctly and responding on the I2C bus
- The PN532 is in I2C mode
- Tags are detected and UIDs are read correctly

before attempting to integrate with Klipper.

---

## Prerequisites

### 1 — Enable I2C on the Pi

```bash
sudo raspi-config
```

Navigate to **Interface Options → I2C → Enable**, then reboot.

Verify the I2C device appears:

```bash
ls /dev/i2c-*
```

You should see `/dev/i2c-1` (hardware I2C1 on GPIO2/GPIO3).

### 2 — Install smbus2

```bash
sudo apt install python3-smbus2
```

Or with pip:

```bash
pip3 install smbus2
```

---

## Wiring

Wire the PN532 directly to the Pi GPIO header:

| PN532 Pin | Pi Pin | Pi GPIO |
|---|---|---|
| VCC | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 (I2C1 SDA) |
| SCL | Pin 5 | GPIO3 (I2C1 SCL) |

> **I2C mode:** The PN532 must be set to I2C mode before wiring.
> On most breakout boards there is a DIP switch or solder jumper:
>
> | SEL0 | SEL1 | Mode |
> |---|---|---|
> | L | L | SPI |
> | **H** | **L** | **I2C ← use this** |
> | L | H | HSU (UART) |

> **Pull-ups:** Most PN532 breakout boards include on-board 10 kΩ pull-ups on
> SDA and SCL. If yours does not, add 4.7 kΩ resistors from SDA to 3.3V and
> SCL to 3.3V.

> **Address:** The PN532 default I2C address is `0x24`. If your module has
> ADDR pads set, calculate the address:
> A1=0, A0=0 → 0x24 / A1=0, A0=1 → 0x25 / A1=1, A0=0 → 0x26 / A1=1, A0=1 → 0x27

---

## Usage

All commands are run from the repository root on the Pi.

### Scan the I2C bus

Probe all I2C addresses and print any devices that respond.
Run this first to confirm the PN532 is wired and visible before doing anything else.

```bash
python3 tools/pn532_scan.py --scan-bus
```

Expected output when PN532 is present:

```
Scanning I2C bus 1 for devices...
  0x24  (36)

1 device(s) found.
```

If nothing is found, check wiring and I2C mode jumper.

---

### Continuous tag polling

Poll for tags every 2 seconds (default) and print UIDs as tags are placed and removed:

```bash
python3 tools/pn532_scan.py
```

Expected output:

```
PN532 scanner — I2C bus 1, address 0x24
Poll interval: 2.0s   Debug: 1
Press Ctrl+C to stop.

Initialising PN532...
PN532 ready.

TAG DETECTED  UID=A3F200CC
Tag removed.
TAG DETECTED  UID=04AB12DE3F2180
```

Press **Ctrl+C** to stop.

---

### Read one tag then exit

```bash
python3 tools/pn532_scan.py --once
```

Useful for scripting — exits with code 0 after the first successful tag read.

---

### Change poll interval

```bash
python3 tools/pn532_scan.py --poll 0.5
```

---

### Full protocol trace

Print every I2C transaction — useful when debugging communication problems:

```bash
python3 tools/pn532_scan.py --debug
```

Example output:

```
PN532 scanner — I2C bus 1, address 0x24
Poll interval: 2.0s   Debug: 2
Press Ctrl+C to stop.

Initialising PN532...
init: gate 0 (PN532) starting wake sequence
_wake_pn532: gate 0 (PN532) attempt 1/3 — sending GetFirmwareVersion (post-TX wait=150ms)
_send: gate 0 (PN532) TX  cmd=0x02  frame=00 00 FF 02 FE D4 02 2A 00
_recv: gate 0 (PN532) poll result=01 pn_status=0x01
_recv: gate 0 (PN532) DATA: expect=0x03 pn_status=0x01 raw=01 00 00 FF 06 FA D5 03 07 07 00 18 C0 00
_recv: gate 0 (PN532) payload: 07 07 00 18
_wake_pn532: gate 0 (PN532) OK on attempt 1 — IC=0x07 Ver=7.0
...
```

---

### Use a different I2C bus or address

```bash
python3 tools/pn532_scan.py --bus 0 --address 0x25
```

| Option | Default | Description |
|---|---|---|
| `--bus N` | `1` | I2C bus number (`/dev/i2c-N`) |
| `--address 0xNN` | `0x24` | PN532 I2C address |
| `--poll N` | `2.0` | Poll interval in seconds |
| `--debug` | off | Full protocol trace |
| `--once` | off | Exit after first tag read |
| `--scan-bus` | off | Scan bus for devices and exit |

---

## Troubleshooting

### "smbus2 is not installed"

```bash
sudo apt install python3-smbus2
```

### "ERROR: PN532 gate 0 did not respond"

1. Run `--scan-bus` — if 0x24 does not appear, the wiring or mode jumper is wrong
2. Confirm I2C is enabled: `sudo raspi-config → Interface Options → I2C`
3. Check the PN532 is in **I2C mode** — the most common cause of no response
4. Check VCC is 3.3V (not 5V), SDA → Pin 3, SCL → Pin 5

### "Permission denied: /dev/i2c-1"

```bash
sudo usermod -aG i2c $USER
```

Log out and back in, then retry.

### Tag not detected

- Hold the tag flat and close (< 3 cm) to the antenna coil
- Try `--debug` to see whether `InListPassiveTarget` is completing
- Some tag types need the NFC antenna oriented correctly — try rotating the tag
