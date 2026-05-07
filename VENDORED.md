# Vendored Files

Files copied from upstream repos. GPLv3 headers are preserved in each file.
Small local compatibility patches may be applied where noted below.

## lameandboard/rfid

| Source | Destination | Used for |
|---|---|---|
| `extras/rfid_tag_parser.py` | `klippy/extras/nfc_gates/vendor/rfid_tag_parser.py` | Tag payload parsing (all formats) |
| `extras/spoolman_client.py` | `klippy/extras/nfc_gates/vendor/lameandboard_spoolman.py` | Vendor/filament/spool CRUD building blocks |

```
upstream_repo:   https://github.com/lameandboard/rfid.git
upstream_branch: main
upstream_commit: c1aadffa8d58abc92eaa674e66a57b2998a44386
synced_date:     2026-04-30
ignored_upstream_commits: 5b9b81797786
```

### Usage notes

`rfid_tag_parser.py` is used as the rich tag parser. Entry point:
`parse_tag(raw_bytes_or_blocks, uid_hex)`. The local copy also accepts an optional
trace callback so NFC debug logging can follow parser decisions without adding a
dependency on this project to the vendor module.

`lameandboard_spoolman.py` is used by the Spoolman auto-create path. The NFC adapter
instantiates the vendored `SpoolmanClient` with the resolved Spoolman URL and timeout,
then calls `auto_create_spool(meta, uid_hex=None)`.

Passing `uid_hex=None` is intentional: it lets the vendored helper create or find the
vendor, filament, and spool from tag metadata without writing the upstream
`rfid_uid_N` multi-slot UID fields. After the spool is created, this project patches
the UID onto the newly-created spool using its configured single Spoolman extra field
(`spoolman_rfid_key`, default `rfid_tag`) through the local NFC Spoolman adapter.

If that UID patch fails, the read is treated as unresolved so the system does not lose
the UID-to-spool link.

`ignored_upstream_commits` lists upstream revisions that were reviewed and
intentionally not merged because this project keeps local compatibility patches
that upstream has not accepted yet. The sync workflow skips PR creation when
upstream `main` is at one of those commits.

### Updating

A GitHub Action runs weekly and opens a PR automatically if upstream changes either file.
To update manually:

```bash
git fetch lameandboard
git show lameandboard/main:extras/rfid_tag_parser.py > klippy/extras/nfc_gates/vendor/rfid_tag_parser.py
git show lameandboard/main:extras/spoolman_client.py > klippy/extras/nfc_gates/vendor/lameandboard_spoolman.py
```

Review the diff against `nfc_manager.py` adapter code before committing, then update
`upstream_commit` and `synced_date` above.
