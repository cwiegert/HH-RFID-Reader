# Install & Uninstall

[← Back to README](../../Readme.md)

---

## How the Install Works

The installer does **not copy code to Klipper**. It creates symlinks. This means:

- `git pull` in the repo directory is all that is needed to update the Python code.
- No file copying, no Klipper directory edits beyond the symlinks themselves.
- Config files in `~/printer_data/config/NFC/` are yours — the installer never overwrites sections you have already configured.

### What the installer creates

```
~/klipper/klippy/extras/nfc_gate.py    →  symlink to repo/klippy/extras/nfc_gate.py
~/klipper/klippy/extras/nfc_gates/     →  symlink to repo/klippy/extras/nfc_gates/
~/printer_data/config/NFC/             →  config directory (created if absent)
~/printer_data/config/NFC/nfc_vars.cfg
~/printer_data/config/NFC/nfc_macros.cfg
~/printer_data/config/NFC/pn532_i2C.cfg
~/pn532_scan.py                        →  standalone host-side PN532 scan tool
```

### Config merge behaviour

Config files use a non-destructive merge:

- If the file **does not exist**: copied from the repo template.
- If the file **already exists**: the installer checks which `[section]` blocks exist. Any section in the template that is **missing** from your file is appended. Sections you have already configured are never touched.

Running `bash install.sh` again after an update is safe.

---

## Install

### 1. Clone the repository

```bash
cd ~
git clone --filter=blob:none --sparse git@github.com:<your-github-username>/NFC-Reader.git emu-nfc-reader
cd ~/emu-nfc-reader
git sparse-checkout set klippy config docs tools
```

The sparse checkout skips large binary assets and keeps only what Klipper and the Pi need.

### 2. Run the installer

```bash
bash install.sh
```

The installer confirms what it created. If Klipper extras or printer config directories are not found, it exits with an error message before making any changes.

### 3. Add includes to `printer.cfg`

Open `~/printer_data/config/printer.cfg` and add these three lines, **in this order**:

```ini
[include NFC/nfc_vars.cfg]
[include NFC/nfc_macros.cfg]
[include NFC/pn532_i2C.cfg]
```

Order matters. `nfc_vars.cfg` defines the base `[nfc_gate]` section. Each lane section in `pn532_i2C.cfg` inherits those defaults.

### 4. Configure Spoolman

Edit `~/printer_data/config/NFC/nfc_vars.cfg`:

```ini
[nfc_gate]
spoolman_url:      auto
spoolman_rfid_key: rfid_tag
```

Use `auto` when Moonraker has a `[spoolman]` section. Use a direct URL when testing against a remote instance:

```ini
spoolman_url: http://192.168.1.50:7912
```

See [Spoolman Integration](spoolman-integration.md) for how to create the extra field and register UIDs.

### 5. Configure lane hardware

Edit `~/printer_data/config/NFC/pn532_i2C.cfg`. The default file has four lanes configured. Adjust the MCU names and gate numbers to match your Happy Hare setup:

```ini
[nfc_gate lane0]
mmu_gate:   0
i2c_mcu:    lane0
i2c_bus:    i2c3_PB3_PB4
```

See [Setup](../i2c-pn532/setup.md) and [Configuration Reference](configuration.md) for all options.

### 6. Update and flash lane MCU firmware

> [!CAUTION]
> **Do this step.** Klipper MCU firmware on the EBB42 / lane boards must match the host checkout. If the host is updated but the lane boards are not flashed, PN532 I2C transactions fail with errors that look like hardware problems.

Build and flash Klipper firmware for each lane MCU before testing NFC.

### 7. Restart Klipper and verify

```bash
sudo systemctl restart klipper
```

```gcode
NFC_GATE_STATUS
```

Expected output with four empty lanes:

```
NFC gate status  (4 gates configured):
  Gate 0  [lane0]:  empty
  Gate 1  [lane1]:  empty
  Gate 2  [lane2]:  empty
  Gate 3  [lane3]:  empty
```

---

## Moonraker Update Manager

Add to `moonraker.conf` so Fluidd/Mainsail can update NFC Gate Reader alongside Klipper:

```ini
[update_manager emu_nfc_reader]
type:            git_repo
path:            ~/emu-nfc-reader
origin:          git@github.com:<your-github-username>/NFC-Reader.git
primary_branch:  main
managed_services: klipper
install_script:  install.sh
```

Restart Moonraker:

```bash
sudo systemctl restart moonraker
```

> [!IMPORTANT]
> The update manager runs `install.sh` automatically after a `git pull`. Because the Python extras are symlinks, the new code is live immediately. **You still need to rebuild and flash lane MCU firmware manually** when a Klipper MCU protocol change is included in an update.

---

## Updating

```bash
cd ~/emu-nfc-reader
git pull
bash install.sh
sudo systemctl restart klipper
```

If the update notes mention a Klipper MCU protocol change: rebuild and flash each lane MCU before restarting Klipper.

---

## Uninstall

```bash
cd ~/emu-nfc-reader
bash uninstall.sh
```

The uninstaller:

1. Removes the `nfc_gate.py` symlink from Klipper extras.
2. Removes the `nfc_gates/` symlink from Klipper extras.
3. Removes the legacy `nfc_gates.py` symlink if present from an older install.
4. Removes `~/pn532_scan.py`.
5. Moves `~/printer_data/config/NFC/` to `NFC_removed_<timestamp>/` (your config is preserved, not deleted).
6. Restarts Klipper.
7. Optionally removes the repo clone.

### Manual steps after uninstall

The uninstaller cannot edit your config files. Complete these manually:

**1. Remove NFC includes from `printer.cfg`:**

```ini
# Remove these three lines:
[include NFC/nfc_vars.cfg]
[include NFC/nfc_macros.cfg]
[include NFC/pn532_i2C.cfg]
```

**2. Remove the update manager block from `moonraker.conf`:**

```ini
# Remove this block:
[update_manager emu_nfc_reader]
type:            git_repo
...
```

**3. Restart Moonraker:**

```bash
sudo systemctl restart moonraker
```

**4. Delete the config backup when no longer needed:**

```bash
rm -rf ~/printer_data/config/NFC_removed_*
```

---

## Standalone PN532 Scanner

The installer places `~/pn532_scan.py` on the Pi. This is a host-side scan tool for testing a PN532 wired directly to the Pi's GPIO I2C pins — it does not require Klipper to be running.

```bash
# Scan all I2C buses for a PN532:
python3 ~/pn532_scan.py --scan-bus

# Read tags continuously:
python3 ~/pn532_scan.py
```

Useful for confirming a PN532 module is alive before wiring it to a lane MCU.
