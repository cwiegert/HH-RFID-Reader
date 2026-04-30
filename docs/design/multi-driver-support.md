# INITIAL THOUGHTS FOR MULTI-READER PLATFORM SUPPORT

> Engineering reference — not end-user documentation.

---

## Goal

Allow a single installation to support more than one NFC reader hardware platform.
The first supported platforms are PN532 over I2C and RC522 over SPI.  Future
platforms must be addable without changing user-facing config files or the core
gate management logic.

---

## Config Model

A `driver:` key is added to the `[nfc_gate]` base section in `nfc_reader.cfg`.
Each `[nfc_gate laneN]` section in `nfc_reader_hw.cfg` inherits it and may
override it if that lane uses different hardware.

```ini
# nfc_reader.cfg — base section, sets the default for all lanes
[nfc_gate]
driver: pn532_i2c

# nfc_reader_hw.cfg — lane sections inherit driver: pn532_i2c unless overridden
[nfc_gate lane0]
mmu_gate: 0
i2c_mcu:  lane0

[nfc_gate lane3]
mmu_gate: 3
spi_mcu:  lane3
driver:   rc522_spi   # overrides the base default for this lane only
```

---

## Driver Registry

`nfc_manager.py` maintains an explicit mapping from driver name string to driver
class.  Both modules are imported at the top of the file regardless of which
drivers are active — the modules are small and the cost is negligible.

```
_DRIVERS = {
    'pn532_i2c': pn532_driver.PN532Driver,
    'rc522_spi': rc522_driver.RC522Driver,
}
```

Adding a new platform requires:
1. A new `<name>_driver.py` file in the `nfc_gates/` package.
2. An import at the top of `nfc_manager.py`.
3. A new entry in `_DRIVERS`.
4. A new driver name string documented in `nfc_reader.cfg` comments.

No changes to user config files or gate management logic are required.

---

## Transport Selection

Each driver owns its own transport setup.  `NFCGate.__init__` selects the
transport based on the driver name before constructing the reader:

| driver key   | transport call                  | driver class       |
|--------------|---------------------------------|--------------------|
| `pn532_i2c`  | `bus.MCU_I2C_from_config(...)`  | `PN532Driver`      |
| `rc522_spi`  | `bus.MCU_SPI_from_config(...)`  | `RC522Driver`      |

The `i2c_bus` inheritance proxy (`_BusDefaultConfig`) applies only when the
selected transport is I2C.  SPI lanes read `spi_bus`, `spi_speed`, and
`spi_software_*` directly via the standard Klipper SPI config helpers.

An unknown driver name raises a Klipper config error at startup with the list
of valid names so the user gets an immediate, actionable message.

---

## Inheritance Rules

`driver:` follows the same inheritance path as every other key:

- Default set once in `[nfc_gate]` in `nfc_reader.cfg`.
- Each `[nfc_gate laneN]` inherits it via `NFCGateDefaults`.
- A lane may override it by setting `driver:` explicitly.
- `NFCGateDefaults` stores `self.driver` the same way it stores `self.i2c_address`.

---

## Constraints

- A lane may use only one driver.  Mixed transports within a single lane are not supported.
- The driver name is validated at Klipper startup, not at poll time.  A bad driver name is a hard config error.
- Driver modules must not import each other and must not depend on gate management logic — they are transport adapters only.
- The public interface every driver must implement is `read_tag() -> uid_hex | None`.
