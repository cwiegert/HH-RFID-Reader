# EMU NFC Gate Reader

Automatic spool detection for the Extended Multi-Material Unit (EMU).
NFC tags on filament spools are detected at each gate and matched to Spoolman
spool records via UID lookup. Happy Hare's gate map is updated automatically
via `MMU_GATE_MAP` — no manual updates and no writing to tags needed.

---

## How It Works

1. An NFC reader scans a tag and reads its factory UID.
2. The UID is looked up against your Spoolman instance via its REST API.
3. When a match is found, `MMU_GATE_MAP GATE=N SPOOLMAN_ID=X` updates Happy Hare.
4. When a tag is removed (after `absent_threshold` consecutive missed polls), `MMU_GATE_MAP GATE=N SPOOLMAN_ID=-1` clears the gate.

Tags are **never written to**. Any blank NFC sticker works — register its UID in Spoolman once and you're done.

---

## Choose Your Hardware Path

Four configurations are supported. **Pick one.**

---

### Path A — SPI / RC522 on Pico

Use this if you have a dedicated **Raspberry Pi Pico** on the CAN bus with **RC522 readers** on its SPI bus.

```
RC522 (SPI) → Pico (CAN) → [nfc_gates] → Happy Hare
```

| | |
|---|---|
| Extra hardware | Raspberry Pi Pico + SN65HVD230 CAN transceiver |
| Readers | RC522 — one per gate, shared SPI bus, individual CS pins |
| Klipper config | `[nfc_gates]` section |
| Config files | `nfc_vars.cfg` + `nfc_macros.cfg` + `rc522_spi.cfg` |

→ **[Path A Setup Guide](docs/spi-rc522/setup.md)**

---

### Path B — SPI / PN532 on Pico

Use this if you have a dedicated **Raspberry Pi Pico** on the CAN bus with **PN532 readers** on its SPI bus. The PN532 handles the full ISO14443A stack in hardware — simpler protocol than the RC522 and lower CAN bus traffic.

```
PN532 (SPI) → Pico (CAN) → [nfc_gates] → Happy Hare
```

| | |
|---|---|
| Extra hardware | Raspberry Pi Pico + SN65HVD230 CAN transceiver |
| Readers | PN532 — one per gate, shared SPI bus, individual CS pins |
| Klipper config | `[nfc_gates]` section |
| Config files | `nfc_vars.cfg` + `nfc_macros.cfg` + `pn532_spi.cfg` |

→ **[Path B Setup Guide](docs/spi-pn532/setup.md)**

---

### Path C — I2C / PN532 on Pico

Use this if you have a dedicated **Raspberry Pi Pico** on the CAN bus and want **PN532 readers over I2C**. Requires PN532 modules with addressable ADDR pins for unique I2C addresses per gate.

```
PN532 (I2C) → Pico (CAN) → [nfc_gates] → Happy Hare
```

| | |
|---|---|
| Extra hardware | Raspberry Pi Pico + SN65HVD230 CAN transceiver |
| Readers | PN532 — one per gate, shared I2C bus, unique addresses via ADDR pins |
| Klipper config | `[nfc_gates]` section with `gate_i2c_addresses` |
| Config files | `nfc_vars.cfg` + `nfc_macros.cfg` + `pn532_pico_i2c.cfg` |

→ **[Path C Setup Guide](docs/i2c-pn532/setup.md)**

---

### Path D — I2C / PN532 on EBB42

Use this if you have **EBB42 lane boards** already on the CAN bus. A PN532 module wires directly to each lane board's I2C pins — no separate Pico needed.

```
PN532 (I2C on EBB42) → lane MCU (CAN) → [nfc_gate laneN] → Happy Hare
```

| | |
|---|---|
| Extra hardware | One PN532 module per gate, wired to EBB42 PB3/PB4 |
| Readers | PN532 — one per lane board, dedicated I2C bus per gate |
| Klipper config | One `[nfc_gate laneN]` section per gate |
| Config files | `nfc_vars.cfg` + `nfc_macros.cfg` + `pn532_i2C.cfg` |

→ **[Path D Setup Guide](docs/i2c-pn532/setup.md)**

---

## Install

All paths use the same install process.

### 1 — Clone the repository

The sparse clone skips the `tests/` directory (development only — not needed on the printer):

```bash
cd ~
git clone --filter=blob:none --sparse https://github.com/cwiegert/NFC-Reader.git emu-nfc-reader
cd ~/emu-nfc-reader
git sparse-checkout set klippy config docs tools
cd ~
bash ~/emu-nfc-reader/install.sh
```

The install script creates two symlinks in `~/klipper/klippy/extras/`:

```
nfc_gate.py  →  ~/emu-nfc-reader/klippy/extras/nfc_gate.py
nfc_gates/   →  ~/emu-nfc-reader/klippy/extras/nfc_gates/
```

It also creates `~/printer_data/config/NFC/` and copies all config files into it.
On subsequent runs it merges any new sections into your existing config files — your settings are never overwritten.

### 2 — Set your Spoolman URL

Edit `~/printer_data/config/NFC/nfc_vars.cfg`:

```ini
[nfc_gate]
spoolman_url: http://your-pi.local:7912    # ← set this
```

This is the only file you need to edit for a basic install.

### 3 — Add includes to printer.cfg

Pick **one** hardware config and add these three lines to `printer.cfg` in this order:

**Path A — SPI / RC522 on Pico:**
```ini
[include NFC/nfc_vars.cfg]
[include NFC/nfc_macros.cfg]
[include NFC/rc522_spi.cfg]
```

**Path B — SPI / PN532 on Pico:**
```ini
[include NFC/nfc_vars.cfg]
[include NFC/nfc_macros.cfg]
[include NFC/pn532_spi.cfg]
```

**Path C — I2C / PN532 on Pico:**
```ini
[include NFC/nfc_vars.cfg]
[include NFC/nfc_macros.cfg]
[include NFC/pn532_pico_i2c.cfg]
```

**Path D — I2C / PN532 on EBB42:**
```ini
[include NFC/nfc_vars.cfg]
[include NFC/nfc_macros.cfg]
[include NFC/pn532_i2C.cfg]
```

### 4 — Restart Klipper

```bash
sudo systemctl restart klipper
```

Then follow the setup guide for your path to complete wiring and MCU configuration.

### 5 — Verify

From the Klipper console (Mainsail / Fluidd terminal):

```
NFC_GATE_STATUS
```

All gates should show `empty`. Place a tag and wait one poll cycle (default 30 s) to confirm detection.

---

## Moonraker Auto-Update

Add this block to `~/printer_data/config/moonraker.conf`:

```ini
[update_manager emu_nfc_reader]
type: git_repo
path: ~/emu-nfc-reader
origin: https://github.com/cwiegert/NFC-Reader.git
primary_branch: main
managed_services: klipper
install_script: install.sh
```

```bash
sudo systemctl restart moonraker
```

When an update is available, Moonraker pulls the latest code, runs `install.sh` to refresh the symlinks and merge updated config files, then restarts Klipper. Your settings are always preserved.

---

## Uninstall

```bash
bash ~/emu-nfc-reader/uninstall.sh
```

The script removes the Klipper symlinks, backs up and removes the `NFC/` config directory, and restarts Klipper. It prompts before deleting the repo clone.

After running the script, remove the `[include NFC/...]` lines from `printer.cfg` and the `[update_manager emu_nfc_reader]` block from `moonraker.conf` manually.

---

## Quick Reference

### Gate status

```
NFC_GATE_STATUS
```

### Live log

NFC events are written to a dedicated log file separate from `klippy.log`:

```bash
tail -f ~/printer_data/logs/nfc_reader.log
```

### Speed up testing

In `~/printer_data/config/NFC/nfc_vars.cfg`, temporarily set:

```ini
poll_interval:    5
absent_threshold: 1
```

Restart Klipper. Restore production values when done.

### GCode macros

| Macro | When it fires | What it does |
|---|---|---|
| `_NFC_SPOOL_CHANGED` | Tag placed, UID found in Spoolman | `MMU_GATE_MAP GATE=N SPOOLMAN_ID=X` |
| `_NFC_SPOOL_REMOVED` | Tag absent for `absent_threshold` polls | `MMU_GATE_MAP GATE=N SPOOLMAN_ID=-1` |
| `_NFC_TAG_NO_SPOOL` | Tag UID not registered in Spoolman | Logs the UID — register it in Spoolman |

Macro bodies are in `NFC/nfc_macros.cfg`. Edit them to match your Happy Hare version.

---

## Repository Layout

```
emu-nfc-reader/
│
├── install.sh                        ← run once after cloning; re-run after git pull
├── uninstall.sh                      ← removes symlinks, backs up config, restarts Klipper
│
├── klippy/
│   └── extras/
│       ├── nfc_gate.py               ← Klipper entry point for [nfc_gate] / [nfc_gate laneN]
│       │                                (Path D — I2C/PN532 on EBB42)
│       │                                Thin shim — all logic is in nfc_gates/
│       └── nfc_gates/                ← Klipper package for [nfc_gates]
│           │                            (Paths A, B, C — SPI or I2C on Pico)
│           ├── __init__.py           ← load_config → NFCGateManager
│           ├── NFC_manager.py        ← NFCGateDefaults, NFCGate, NFCGateManager,
│           │                            GateState, KlipperInterface
│           ├── rc522_driver.py       ← RC522 ISO14443A driver (SPI)
│           ├── pn532_driver.py       ← PN532 ISO14443A driver (I2C + SPI)
│           ├── spoolman_client.py    ← Spoolman REST API client (UID lookup)
│           └── log.py               ← dedicated logger → nfc_reader.log
│
├── config/                           ← install.sh copies these to printer_data/config/NFC/
│   ├── nfc_vars.cfg                  ← your settings (Spoolman URL, poll interval, debug)
│   ├── nfc_macros.cfg                ← Happy Hare GCode macros — same for all paths
│   ├── rc522_spi.cfg                 ← Path A hardware config
│   ├── pn532_spi.cfg                 ← Path B hardware config
│   ├── pn532_pico_i2c.cfg            ← Path C hardware config
│   └── pn532_i2C.cfg                 ← Path D hardware config
│
├── tests/                            ← development only — not deployed to printer
│   ├── simulate.py                   ← interactive full-pipeline simulator
│   ├── lookup_uid.py                 ← live Spoolman UID lookup test
│   ├── test_gate_state.py            ← GateState debounce logic tests
│   ├── test_nfc_gate_config.py       ← NFCGateDefaults config handler tests
│   ├── test_pn532_driver.py          ← PN532 driver tests (mock I2C)
│   └── test_rc522_driver.py          ← RC522 driver tests (mock SPI)
│
└── docs/
    ├── spi-rc522/
    │   ├── setup.md                  ← Path A install walkthrough
    │   ├── wiring.md                 ← RC522 + Pico + CAN transceiver wiring
    │   └── troubleshooting.md
    ├── spi-pn532/
    │   ├── setup.md                  ← Path B install walkthrough
    │   └── wiring.md                 ← PN532 SPI + Pico + CAN transceiver wiring
    ├── i2c-pn532/
    │   ├── setup.md                  ← Paths C & D install walkthrough
    │   ├── wiring.md                 ← PN532 + EBB42 I2C wiring
    │   └── troubleshooting.md
    └── shared/
        ├── spoolman-integration.md   ← Spoolman setup, rfid field, UID registration
        ├── tag-writing.md
        └── debugging.md              ← nfc_reader.log, debug levels, NFC_GATE_STATUS
```

---

## Documentation Index

| Document | Contents |
|---|---|
| [Path A Setup — SPI / RC522 on Pico](docs/spi-rc522/setup.md) | Flash Pico, configure UUID, Moonraker updater |
| [Path A Wiring](docs/spi-rc522/wiring.md) | RC522 pinout, Pico GPIO, CAN transceiver |
| [Path A Troubleshooting](docs/spi-rc522/troubleshooting.md) | Reader init failures, SPI errors |
| [Path B Setup — SPI / PN532 on Pico](docs/spi-pn532/setup.md) | Flash Pico, configure UUID, Moonraker updater |
| [Path B Wiring](docs/spi-pn532/wiring.md) | PN532 SPI pinout, Pico GPIO, CAN transceiver |
| [Path C Setup — I2C / PN532 on Pico](docs/i2c-pn532/setup.md) | Flash Pico, I2C addresses, Moonraker updater |
| [Path D Setup — I2C / PN532 on EBB42](docs/i2c-pn532/setup.md) | Configure gate sections, Moonraker updater |
| [Path D Wiring](docs/i2c-pn532/wiring.md) | PN532 pinout, EBB42 I2C pins, pull-up resistors |
| [Path D Troubleshooting](docs/i2c-pn532/troubleshooting.md) | PN532 init failures, I2C address conflicts |
| [Spoolman Integration](docs/shared/spoolman-integration.md) | Add rfid extra field, read UIDs, register spools |
| [Debugging & Logs](docs/shared/debugging.md) | nfc_reader.log, debug levels, NFC_GATE_STATUS |
