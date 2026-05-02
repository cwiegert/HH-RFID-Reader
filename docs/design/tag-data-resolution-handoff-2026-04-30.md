# Tag Data Resolution Handoff — 2026-04-30

## Current State

The implementation now has the manager-owned deep-read orchestration path:

- `tag_parsing: False` keeps the UID-only path and calls `read_tag()`.
- `tag_parsing: True` calls `read_target()`, creates `CurrentTag`, stores `target_info`, classifies the target, and deep-reads supported tag families while the tag is still present.
- NTAG/Type-2 metadata and Bambu/MIFARE authenticated block reads happen before scan-jog rewind because scan-jog calls `_poll()`, and `_poll()` now completes `_read_current_tag()` before returning `tag_found=True`.
- `_resolve_spool()` walks the resolution ladder:
  - embedded `spoolman_id`
  - UID lookup
  - opt-in auto-create via vendored `auto_create_spool(meta, uid_hex=None)`,
    followed immediately by patching our configured `spoolman_rfid_key`
  - metadata-direct fallback when Spoolman is disabled or unavailable
- Metadata-only scan-jog dispatch preserves metadata through rewind.

## Bambu / MIFARE Status

Bambu-style tags are implemented behind `tag_parsing: True` plus `bambu_reads: True`:

- Conservative classification treats `SAK & 0x08` as `mifare_classic`.
- MIFARE Classic does not attempt NTAG page reads.
- The manager derives Bambu sector Key-A values with the vendored parser's HKDF helper only when `bambu_reads` is enabled.
- The PN532 driver authenticates and reads sectors 0-4, returning a block dict to `rfid_tag_parser.parse_tag()`.
- If pycryptodome is missing, UID bytes are invalid, authentication fails, no blocks are readable, or parsing fails, the tag falls back to UID-only Spoolman resolution with a clear `parse_error`.

Factory-tagged Bambu rich reads require pycryptodome in the Klipper Python environment. The installer now asks specifically about Bambu rich reads, writes `bambu_reads`, and installs `pycryptodome` only for that selected path.

## What Is Still Missing

1. More precise target classification:
   - current table is conservative, not exhaustive
   - unknown targets intentionally fall back UID-only

2. Hardware validation:
   - UID-only with `tag_parsing: False`
   - NTAG/OpenSpool deep read with `tag_parsing: True`
   - blank NTAG fallback
   - Bambu/MIFARE successful authenticated read with pycryptodome installed
   - Bambu/MIFARE UID-only fallback with pycryptodome missing or auth failure
   - scan-jog waits for deep read before rewind

3. Optional richer Happy Hare metadata forwarding:
   - current direct metadata path forwards material/color/vendor/uid
   - temps/weight are not forwarded to HH macros yet

## Tomorrow Starting Point

Start by checking the implementation against `docs/design/tag-data-resolution.md`, especially:

- Requirements 1, 2, 5, 6, 7, 9, 10
- "Read Strategy Responsibilities"
- "When parsing runs"
- "Resolution Result Summary"

Then decide whether we are ready for live NTAG hardware testing or whether to add more ugly-case tests first.

Recommended first command:

```bash
python3 -m pytest -q
```

Current local result at handoff:

```text
144 passed after vendored top-level auto-create plus `rfid_tag` patch; rerun after each change.
```

## Agent Pickup Prompts

Use one of these prompts when restarting work so the next agent anchors on the design and current implementation instead of guessing from isolated files.

### Prompt for Codex

```text
Read docs/design/tag-data-resolution.md and docs/design/tag-data-resolution-handoff-2026-04-30.md first. Then inspect klippy/extras/nfc_gates/nfc_manager.py, klippy/extras/nfc_gates/pn532_driver.py, klippy/extras/nfc_gates/scan_jog.py, klippy/extras/nfc_gates/spoolman_client.py, and tests/test_gate_state.py.

Goal: continue the NFC tag-data integration from the handoff. Confirm that tag_parsing False remains UID-only, tag_parsing True uses the manager-owned _read_current_tag() path, NTAG/Type-2 and Bambu/MIFARE deep reads happen before scan-jog rewind, and unsupported/failed targets fall back UID-only.

Before changing code, state whether the next best step is live hardware validation, richer classification, or Happy Hare metadata expansion. Preserve the original design requirements, especially feature gating, UID-only compatibility, conservative fallback, no tag writes, and our configured spoolman_rfid_key convention.
```

### Prompt for Claude Code

```text
You are picking up the NFC tag-data resolution implementation. Start by reading:
- docs/design/tag-data-resolution.md
- docs/design/tag-data-resolution-handoff-2026-04-30.md

Then inspect:
- klippy/extras/nfc_gates/nfc_manager.py
- klippy/extras/nfc_gates/pn532_driver.py
- klippy/extras/nfc_gates/scan_jog.py
- klippy/extras/nfc_gates/spoolman_client.py
- tests/test_gate_state.py
- tests/test_vendor_contract.py

Current intended state:
- tag_parsing False: UID-only via read_tag(), no metadata read.
- tag_parsing True: manager calls read_target(), stores CurrentTag.target_info, classifies, reads supported metadata while the tag is still present, parses cached bytes/blocks, then resolves.
- MIFARE/Bambu: authenticated Bambu Key-A sector reads are wired through the PN532 driver when `bambu_reads: True`. Requires pycryptodome. Do not attempt NTAG reads for MIFARE targets.
- Unknown targets: UID-only fallback.
- _resolve_spool() ladder: embedded spoolman_id, UID lookup, optional auto-create, metadata-direct fallback.
- scan-jog must not rewind until _poll() completes the deep-read attempt.

Run python3 -m pytest -q before and after changes. Current known local result after vendored top-level auto-create plus `rfid_tag` patch was 144 passed. If tests differ, investigate runner/environment before making broad assumptions.

Recommended next work: live NTAG and Bambu hardware validation, then tighten target classification only from observed reader data. Keep code changes small and design-driven.
```

## Suggested Next Work

If staying in non-Bambu scope tomorrow:

1. Add ugly-case tests for failed/empty NTAG reads and parser exceptions.
2. Add live-reader debug logging checklist for NTAG validation.
3. Test actual OpenSpool/metadata NTAG through scan-jog.

If validating Bambu/MIFARE scope tomorrow:

1. Confirm installer selection `rich` + Bambu `yes` installs `pycryptodome` into the Klipper Python environment.
2. Scan a factory-tagged Bambu spool and capture `target_info`, auth/read logs, and parsed `tag_format=bambu` metadata.
3. Confirm failures remain UID-only when crypto is absent or auth fails.
4. Keep all write paths out of scope.
