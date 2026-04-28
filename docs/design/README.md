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
