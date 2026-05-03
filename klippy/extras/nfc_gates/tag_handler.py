# klippy/extras/nfc_gates/tag_handler.py
#
# EMU NFC Gate Reader — tag reading and spool resolution pipeline
# Copyright (C) 2026  WoodWorker
# SPDX-License-Identifier: GPL-3.0-or-later
#
# All functions follow the scan_jog.py convention: receive the NFCGate instance
# as their first argument so they can access gate state without subclassing.
#
# Pipeline order (called from NFCGate._poll via delegates):
#
#   read_current_tag(gate)   — hardware read + metadata capture
#   resolve_spool(gate, uid) — resolution ladder: embedded ID → UID → auto-create → metadata-direct

from .gate_state import CurrentTag, DIRECT_METADATA_SPOOL
from .log import logger


# ── Tag classification ────────────────────────────────────────────────────────

def classify_tag_target(gate, target_info):
    if not isinstance(target_info, dict):
        return 'uid_only'
    try:
        sak = int(target_info.get('sak', 0)) & 0xFF
        uid_length = int(target_info.get('uid_length', 0))
    except (TypeError, ValueError):
        return 'uid_only'
    # Conservative ISO14443A split:
    #   SAK bit 0x08 marks MIFARE Classic-compatible targets.
    #   SAK 0x00 is the common Type-2 / Ultralight / NTAG case.
    if sak & 0x08:
        return 'mifare_classic'
    if sak == 0x00 and uid_length in (4, 7, 10):
        return 'ntag_type2'
    return 'uid_only'


# ── Hardware helpers ──────────────────────────────────────────────────────────

def release_reader_target(gate, reason):
    release = getattr(gate._reader, '_release_current_target', None)
    if release is not None:
        try:
            release(reason=reason)
        except TypeError:
            release()
        except Exception as e:
            if gate._debug >= 4:
                logger.debug(
                    "nfc_gate: [%s] gate %d — target release failed "
                    "(%s): %s", gate._name, gate._gate, reason, e)


# ── Metadata capture ─────────────────────────────────────────────────────────

def parse_current_tag(gate, tag):
    uid_hex = tag.uid
    if not tag.raw_tag_data:
        tag.meta = {'uid': uid_hex}
        return
    try:
        from .vendor.rfid_tag_parser import parse_tag
        raw = (bytes(tag.raw_tag_data)
               if isinstance(tag.raw_tag_data, (bytes, bytearray))
               else tag.raw_tag_data)
        info = parse_tag(raw, uid_hex=uid_hex)
        if isinstance(info, dict) and 'uid' not in info:
            info = dict(info)
            info['uid'] = uid_hex
        if info is None:
            tag.meta = {'uid': uid_hex}
            tag.parse_error = None
        else:
            tag.meta = info
            tag.parse_error = info.get('parse_error') or info.get('error')
        if gate._debug >= 3:
            logger.info("nfc_gate: [%s] gate %d — uid=%s  parse_tag → %s",
                        gate._name, gate._gate, uid_hex,
                        {k: v for k, v in tag.meta.items()
                         if k in ('material', 'vendor', 'color_hex',
                                  'spoolman_id', 'parse_error')})
        if gate._debug >= 4:
            logger.debug("nfc_gate: [%s] gate %d — uid=%s  full meta: %s",
                         gate._name, gate._gate, uid_hex, tag.meta)
    except Exception as e:
        tag.parse_error = 'parse failed: {}'.format(e)
        logger.error("nfc_gate: [%s] gate %d — uid=%s  parse_tag raised: %s",
                     gate._name, gate._gate, uid_hex, e)


def capture_ntag_metadata(gate, tag):
    uid_hex = tag.uid
    try:
        raw = gate._reader.ntag_read_user_memory(
            start_page=4, end_page=4 + gate._tag_max_pages - 1)
        tag.raw_tag_data = raw
        if gate._debug >= 3:
            logger.info("nfc_gate: [%s] gate %d — uid=%s  NTAG read %d bytes",
                        gate._name, gate._gate, uid_hex, len(raw))
    except Exception as e:
        tag.parse_error = 'ntag read failed: {}'.format(e)
        tag.meta = {'uid': uid_hex}
        logger.warning("nfc_gate: [%s] gate %d — uid=%s  NTAG read failed: %s",
                       gate._name, gate._gate, uid_hex, e)
        return
    if not raw:
        tag.parse_error = 'empty ntag read'
        tag.meta = {'uid': uid_hex}
        logger.warning("nfc_gate: [%s] gate %d — uid=%s  NTAG read returned no data",
                       gate._name, gate._gate, uid_hex)
        return
    parse_current_tag(gate, tag)


def resolve_auth_keys(gate, tag):
    """Derive MIFARE sector Key-A values for a Bambu tag via HKDF.

    Returns (keys, None) on success, (None, reason_str) on failure.
    """
    try:
        from .vendor.rfid_tag_parser import _bambu_derive_keys
        uid_bytes = bytes((tag.target_info or {}).get('uid_bytes') or [])
        if len(uid_bytes) < 4:
            return None, ('uid_bytes too short for Bambu key derivation '
                          '(%d bytes)' % len(uid_bytes))
        keys = _bambu_derive_keys(uid_bytes)
        return keys, None
    except ImportError as e:
        return None, 'pycryptodome not installed: %s' % e
    except Exception as e:
        return None, 'key derivation failed: %s' % e


def capture_mifare_metadata(gate, tag, sector_keys):
    uid_hex   = tag.uid
    uid_bytes = bytes((tag.target_info or {}).get('uid_bytes') or [])
    try:
        block_dict = gate._reader.mifare_read_authenticated_blocks(
            sector_keys, sectors=[0, 1, 2, 3, 4], uid_bytes=uid_bytes)
    except Exception as e:
        tag.parse_error = 'mifare read failed: %s' % e
        tag.meta = {'uid': uid_hex}
        logger.warning(
            "nfc_gate: [%s] gate %d — uid=%s  MIFARE read failed: %s",
            gate._name, gate._gate, uid_hex, e)
        return
    if not block_dict or not block_dict.get('blocks'):
        tag.parse_error = 'mifare read returned no blocks'
        tag.meta = {'uid': uid_hex}
        logger.warning(
            "nfc_gate: [%s] gate %d — uid=%s  MIFARE read returned no "
            "blocks (auth failed on all sectors?)",
            gate._name, gate._gate, uid_hex)
        return
    tag.raw_tag_data = block_dict
    if gate._debug >= 3:
        logger.info(
            "nfc_gate: [%s] gate %d — uid=%s  MIFARE read %d blocks",
            gate._name, gate._gate, uid_hex, len(block_dict['blocks']))
    parse_current_tag(gate, tag)


# ── Tag read entry point ──────────────────────────────────────────────────────

def read_current_tag(gate):
    if not gate._tag_parsing:
        return gate._reader.read_tag()

    target_info = gate._reader.read_target()
    if target_info is None:
        return None

    uid_hex = target_info.get('uid')
    if not uid_hex:
        release_reader_target(gate, "missing_uid")
        return None

    tag = CurrentTag(uid=uid_hex, target_info=dict(target_info))
    tag.meta = {'uid': uid_hex}
    gate._state.current_tag = tag

    strategy = classify_tag_target(gate, target_info)
    if gate._debug >= 3:
        logger.info(
            "nfc_gate: [%s] gate %d — uid=%s  target strategy=%s "
            "SAK=0x%02X ATQA=0x%04X",
            gate._name, gate._gate, uid_hex, strategy,
            int(target_info.get('sak', 0) or 0),
            int(target_info.get('atqa', target_info.get('sens_res', 0)) or 0))

    if strategy == 'ntag_type2':
        capture_ntag_metadata(gate, tag)
    elif strategy == 'mifare_classic':
        if not gate._bambu_reads:
            tag.parse_error = 'mifare_classic rich read disabled; uid-only fallback'
            release_reader_target(gate, "mifare_disabled")
            if gate._debug >= 3:
                logger.info(
                    "nfc_gate: [%s] gate %d — uid=%s  MIFARE Classic "
                    "target seen but bambu_reads is disabled; UID-only fallback",
                    gate._name, gate._gate, uid_hex)
            return uid_hex
        keys, reason = resolve_auth_keys(gate, tag)
        if keys is None:
            tag.parse_error = 'mifare auth key derivation failed: %s' % reason
            release_reader_target(gate, "mifare_key_failure")
            if gate._debug >= 3:
                logger.info(
                    "nfc_gate: [%s] gate %d — uid=%s  MIFARE key "
                    "derivation failed: %s; UID-only fallback",
                    gate._name, gate._gate, uid_hex, reason)
        else:
            if gate._debug >= 3:
                logger.info(
                    "nfc_gate: [%s] gate %d — uid=%s  MIFARE Classic "
                    "Bambu keys derived; reading sectors 0-4",
                    gate._name, gate._gate, uid_hex)
            capture_mifare_metadata(gate, tag, keys)
    else:
        tag.parse_error = 'unsupported target; uid-only fallback'
        release_reader_target(gate, "unsupported_uid_only_fallback")
        if gate._debug >= 3:
            logger.info(
                "nfc_gate: [%s] gate %d — uid=%s  unsupported target; "
                "UID-only fallback", gate._name, gate._gate, uid_hex)

    return uid_hex


# ── Spool resolution ladder ───────────────────────────────────────────────────

def resolve_spool(gate, uid_hex):
    if uid_hex is None:
        return None
    tag = gate._state.current_tag
    if tag is not None and tag.uid != uid_hex:
        tag = None
    meta = {}
    if gate._tag_parsing and tag is not None and isinstance(tag.meta, dict):
        meta = tag.meta
    material = str(meta.get('material') or meta.get('type') or '').strip()
    color    = str(meta.get('color_hex') or meta.get('color') or '').strip()

    if gate._spoolman is None:
        if material or color:
            if tag is not None:
                tag.resolution = {'path': 'metadata_direct'}
            if gate._debug >= 3:
                logger.info(
                    "nfc_gate: [%s] gate %d — uid=%s  no Spoolman; "
                    "using tag metadata material=%s color=%s",
                    gate._name, gate._gate, uid_hex, material, color)
            return DIRECT_METADATA_SPOOL
        if gate._debug >= 3:
            logger.info("nfc_gate: [%s] gate %d — uid=%s  no Spoolman configured",
                        gate._name, gate._gate, uid_hex)
        return None

    spoolman_id = meta.get('spoolman_id')
    if spoolman_id not in (None, ''):
        try:
            spoolman_id = int(spoolman_id)
        except (TypeError, ValueError):
            spoolman_id = None
            logger.warning(
                "nfc_gate: [%s] gate %d — uid=%s  invalid embedded "
                "spoolman_id=%r; falling back to UID lookup",
                gate._name, gate._gate, uid_hex, meta.get('spoolman_id'))
        if spoolman_id is not None:
            spool = gate._spoolman.lookup_spool_by_id(spoolman_id)
            if spool:
                raw_id = spool.get('id', spoolman_id)
                try:
                    resolved_id = int(raw_id)
                except (TypeError, ValueError):
                    resolved_id = spoolman_id
                if tag is not None:
                    tag.resolution = {'path': 'embedded_spoolman_id',
                                      'spool_id': resolved_id}
                if gate._debug >= 3:
                    logger.info(
                        "nfc_gate: [%s] gate %d — uid=%s  "
                        "embedded spoolman_id=%s resolved",
                        gate._name, gate._gate, uid_hex, resolved_id)
                return resolved_id
            if gate._debug >= 3:
                logger.info(
                    "nfc_gate: [%s] gate %d — uid=%s  "
                    "embedded spoolman_id=%s not found; falling back",
                    gate._name, gate._gate, uid_hex, spoolman_id)

    spool_id = gate._spoolman.lookup_spool_by_uid(uid_hex)
    if spool_id is not None:
        if tag is not None:
            tag.resolution = {'path': 'uid_lookup', 'spool_id': spool_id}
        if gate._debug >= 3:
            logger.info("nfc_gate: [%s] gate %d — uid=%s  Spoolman→spool_id=%s",
                        gate._name, gate._gate, uid_hex, spool_id)
        return spool_id

    try:
        base_url = gate._spoolman._resolve_base_url()
    except Exception as e:
        base_url = None
        logger.warning(
            "nfc_gate: [%s] gate %d — uid=%s  Spoolman URL resolution failed: %s",
            gate._name, gate._gate, uid_hex, e)
    if not base_url and (material or color):
        if tag is not None:
            tag.resolution = {'path': 'metadata_direct'}
        if gate._debug >= 3:
            logger.info(
                "nfc_gate: [%s] gate %d — uid=%s  Spoolman disabled "
                "or undiscovered; using tag metadata material=%s color=%s",
                gate._name, gate._gate, uid_hex, material, color)
        return DIRECT_METADATA_SPOOL

    if gate._spoolman_auto_create and material:
        if base_url:
            try:
                from .vendor.lameandboard_spoolman import (
                    SpoolmanClient as LBSpoolmanClient)
                lb = LBSpoolmanClient(base_url=base_url,
                                      timeout=gate._spoolman._timeout)
                if gate._debug >= 3:
                    logger.info(
                        "nfc_gate: [%s] gate %d — uid=%s  "
                        "auto-create via lameandboard client "
                        "(uid_hex=None; patching %s next)",
                        gate._name, gate._gate, uid_hex,
                        gate._spoolman._rfid_key)
                new_spool_id = lb.auto_create_spool(meta, uid_hex=None)
                if new_spool_id is not None:
                    new_spool_id = int(new_spool_id)
                    if gate._debug >= 3:
                        logger.info(
                            "nfc_gate: [%s] gate %d — uid=%s  "
                            "auto-created Spoolman spool_id=%s; patching extra[%s]",
                            gate._name, gate._gate, uid_hex, new_spool_id,
                            gate._spoolman._rfid_key)
                    if not gate._spoolman.set_spool_uid(new_spool_id, uid_hex):
                        if tag is not None:
                            tag.resolution = {
                                'path': 'auto_create_uid_patch_failed',
                                'spool_id': new_spool_id,
                            }
                        logger.warning(
                            "nfc_gate: [%s] gate %d — uid=%s  "
                            "auto-created Spoolman spool_id=%s but "
                            "failed to patch extra[%s]; treating as "
                            "unresolved so the next read does not lose "
                            "the UID link",
                            gate._name, gate._gate, uid_hex,
                            new_spool_id, gate._spoolman._rfid_key)
                        return None
                    gate._spoolman.clear_cache()
                    if tag is not None:
                        tag.resolution = {'path': 'auto_create',
                                          'spool_id': new_spool_id}
                    if gate._debug >= 3:
                        logger.info(
                            "nfc_gate: [%s] gate %d — uid=%s  "
                            "auto-created Spoolman spool_id=%s and patched extra[%s]",
                            gate._name, gate._gate, uid_hex, new_spool_id,
                            gate._spoolman._rfid_key)
                    return new_spool_id
                logger.warning(
                    "nfc_gate: [%s] gate %d — uid=%s  auto-create returned no spool_id",
                    gate._name, gate._gate, uid_hex)
            except Exception as e:
                logger.warning(
                    "nfc_gate: [%s] gate %d — uid=%s  Spoolman auto-create failed: %s",
                    gate._name, gate._gate, uid_hex, e)
        elif material or color:
            if tag is not None:
                tag.resolution = {'path': 'metadata_direct'}
            if gate._debug >= 3:
                logger.info(
                    "nfc_gate: [%s] gate %d — uid=%s  Spoolman unavailable; "
                    "using tag metadata material=%s color=%s",
                    gate._name, gate._gate, uid_hex, material, color)
            return DIRECT_METADATA_SPOOL

    if tag is not None:
        tag.resolution = {'path': 'unresolved'}
    if gate._debug >= 3:
        logger.info("nfc_gate: [%s] gate %d — uid=%s  Spoolman→spool_id=None",
                    gate._name, gate._gate, uid_hex)
    return None
