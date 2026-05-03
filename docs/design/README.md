# Engineering Design Documents

Internal engineering references. Not part of the user-facing documentation.

| Document | What it covers |
|---|---|
| [Polling State Machine](polling-state-machine.md) | Timer heartbeat, suspend/resume logic, GateState debounce, startup seed suppression, CLEAR_CACHE suppress |
| [Klipper Integration](klipper-integration.md) | Reactor thread model, timer registration, I2C bus access, GCode dispatch chain, Jinja2 render-time limits, MCU firmware version dependency |
| [Config Architecture](config-architecture.md) | NFCGateDefaults → NFCGate inheritance, `load_config_prefix`, parameter override model, SpoolmanClient lifecycle |
| [HH Interaction](hh-interaction.md) | Unidirectional NFC→HH GCode push, HH status polling via `mmu.get_status()`, suspend/resume cycle trace, startup seeding |
| [Error Handling and Logging](error-logging.md) | `_failed` flag, poll error containment, SpoolmanClient circuit breaker, debug levels 0–4, console output |
| [Scan-and-Jog Mode](scan-jog-mode.md) | Trigger on HH gate_status 0→1 + 2s idle settle, `scan_jog.py` module drives `MMU_TEST_MOVE` jog chunks with timing from `gear_short_move_speed`, class-level scan lock prevents multi-lane race, dead-reckoning rewind via negative `MMU_TEST_MOVE`, print guard, miss count suppressed during scan |
| [Vendor Integration](vendor-integration.md) | lameandboard/rfid library wiring, tag parsing pipeline (NTAG/MIFARE), five-step resolution ladder, DIRECT_METADATA_SPOOL sentinel, auto-create + MMU_SPOOLMAN refresh, `get_status()` fields |

### Module Map

| Module | Owns |
|---|---|
| `gate_state.py` | `CurrentTag` dataclass, `GateState` debounce state machine, event constants, `DIRECT_METADATA_SPOOL` sentinel |
| `klipper_interface.py` | `KlipperInterface` — reactor-thread GCode macro dispatcher, `_macro_value()` sanitiser |
| `tag_handler.py` | Tag classification, hardware capture (NTAG/MIFARE), `parse_tag()` adapter, spool resolution ladder |
| `nfc_manager.py` | `NFCGateDefaults`, `NFCGate` — config, polling lifecycle, scan-jog delegates, `get_status()` |
| `scan_jog.py` | Scan-and-jog mode state machine, jog/rewind GCode, deferred event dispatch after rewind |
| `hh_status.py` | `HHGateStatus` adapter — isolates all raw `mmu.get_status()` dict access |
| `spoolman_client.py` | UID → spool lookup, TTL cache, circuit breaker, Moonraker URL discovery |
| `pn532_driver.py` | PN532 I2C wire protocol, UID read, NTAG page reads, MIFARE block reads |
