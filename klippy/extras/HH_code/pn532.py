# Support for reading NTAG215 via PN532 NFC reader using I2C
#
# Place this module inside Klipper's `~/klipper/klippy/extras/` directory and reference it
# from your printer configuration as shown below.
#
# klipper config example:
# [pn532 mmu_reader]
# i2c_mcu: mmu
# i2c_bus: i2c2_PB10_PB11
# i2c_address: 36
## i2c_software_scl_pin:
## i2c_software_sda_pin:

# start read
# PN532 NAME=mmu_reader READ=1


# stop read
# It’s recommended to run this command during printing to disable the PN532 polling and reduce MMU resource usage.
# PN532 NAME=mmu_reader READ=0 
#
# When a tag provides a spool identifier the code will automatically dispatch
# HappyHare's MMU gate selection command:
#   MMU_GATE_MAP NEXT_SPOOLID=<ID>
# so no additional configuration is required on the Klipper side.

import logging
import json
import time
import re

# PN532 Constants
PN532_PREAMBLE = 0x00
PN532_STARTCODE1 = 0x00
PN532_STARTCODE2 = 0xFF
PN532_POSTAMBLE = 0x00

PN532_HOSTTOPN532 = 0xD4
PN532_PN532TOHOST = 0xD5

# PN532 Commands
PN532_COMMAND_GETFIRMWAREVERSION = 0x02
PN532_COMMAND_SAMCONFIGURATION = 0x14
PN532_COMMAND_RFCONFIGURATION = 0x32
PN532_COMMAND_INLISTPASSIVETARGET = 0x4A
PN532_COMMAND_INDATAEXCHANGE = 0x40
PN532_COMMAND_INRELEASE = 0x52

# PN532 I2C
PN532_I2C_ADDRESS = 0x24  # 0x48 >> 1
PN532_I2C_READY = 0x01
PN532_I2C_BUSY = 0x00

# MIFARE/NTAG Commands
MIFARE_CMD_READ = 0x30
MIFARE_ULTRALIGHT_CMD_WRITE = 0xA2

# ACK frame
PN532_ACK = [0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00]


class PN532Handler:
    """
    PN532 NFC/RFID reader handler using I2C interface.
    Supports NTAG215 reading.
    """
    def __init__(self, printer, i2c, auto_init=True):
        self.printer = printer
        self.gcode = self.printer.lookup_object('gcode')
        self.i2c = i2c
        
        self.retry_times = 3
        self.timeout = 1.0  # seconds
        self.initialized = False
        self.current_target = None
        self.current_uid = None
        self.current_uid_hex = ""
        
        # Initialize PN532 if requested
        if auto_init:
            self.initialized = self._init_pn532()
    
    def _init_pn532(self):
        """Initialize PN532 chip"""
        try:
            logging.info("PN532: === PN532 Initialization Debug ===")
            logging.info(f"PN532: I2C Address: 0x{PN532_I2C_ADDRESS:02X} (decimal: {PN532_I2C_ADDRESS})")

            # read pending data (tentative anti crash measure)
            self.read_passive_target_id(timeout=0.1)
            
            # Wake up PN532
            logging.info("PN532: Step 1: Waking up PN532...")
            self.wakeup()
            time.sleep(0.1)
            
            # Check if device responds
            logging.info("PN532: Step 2: Checking if PN532 is ready...")
            try:
                ready = self._is_ready()
                logging.info(f"PN532: ready status: {ready}")
                if not ready:
                    logging.warning("PN532: not ready after wakeup, trying again...")
                    self.wakeup()
                    time.sleep(0.2)
                    ready = self._is_ready()
                    logging.info(f"PN532: ready status (retry): {ready}")
            except Exception as e:
                logging.error(f"PN532: Cannot read from PN532 - check hardware connection: {e}")
                logging.error("PN532: Possible issues:")
                logging.error("PN532:   1. PN532 not in I2C mode (check SEL0=LOW, SEL1=HIGH)")
                logging.error("PN532:   2. Wrong I2C address (default is 0x24)")
                logging.error("PN532:   3. SDA/SCL pins swapped")
                logging.error("PN532:   4. No power to PN532")
                return False
            
            # Get firmware version
            logging.info("PN532: Step 3: Getting firmware version...")
            version = self.get_firmware_version()
            if version:
                logging.info(f"PN532: Firmware version: {version}")
                self.gcode.respond_info(f"PN532 Firmware: {version}")
            else:
                logging.error("PN532: Failed to get PN532 firmware version")
                logging.error("PN532: Device is not responding correctly - check mode switches")
                return False
            
            # Configure SAM
            logging.info("PN532: Step 4: Configuring SAM...")
            if not self.sam_config():
                logging.error("PN532: Failed to configure SAM")
                return False
            
            # Note: RF field will be automatically enabled by InListPassiveTarget command
            # No need to explicitly configure RF field (as per Adafruit/Filaman implementation)
            logging.info("PN532: Step 5: RF field will be enabled automatically during card detection")
            
            logging.info("PN532: PN532 initialized successfully!")
            logging.info("PN532: === PN532 Initialization Complete ===")
            return True
            
        except Exception as e:
            logging.error(f"PN532: PN532 initialization failed: {e}")
            import traceback
            logging.error(f"PN532: {traceback.format_exc()}")
            return False
    
    def _clear_current_card(self):
        """Clear cached target/card information"""
        self.current_target = None
        self.current_uid = None
        self.current_uid_hex = ""

    def _set_current_card(self, tg, uid_bytes):
        """Cache the currently selected target information"""
        if uid_bytes is None:
            uid_bytes = []
        self.current_target = tg
        self.current_uid = list(uid_bytes)
        self.current_uid_hex = ' '.join(f'{b:02X}' for b in self.current_uid)
        logging.debug(f"PN532: 🎯 Active target set: Tg={tg}, UID={self.current_uid_hex}")

    def _release_current_target(self, reason="manual"):
        """Send InRelease to drop the current target (if any)"""
        if self.current_target is None:
            return True

        try:
            logging.debug(f"PN532: Releasing current target Tg={self.current_target} (reason: {reason})")
            cmd = [PN532_COMMAND_INRELEASE, self.current_target]

            if not self._send_command_check_ack(cmd):
                logging.debug("PN532: InRelease ACK failed")
                self._clear_current_card()
                return False

            if not self._wait_ready(1.0):
                logging.debug("PN532: Timeout waiting InRelease response")
                self._clear_current_card()
                return False

            response = self._read_data(8)
            if response and len(response) >= 8:
                if (response[0] == 0x00 and response[1] == 0x00 and
                    response[2] == 0xFF and response[5] == 0xD5 and
                    response[6] == 0x53):
                    status = response[7]
                    if status != 0x00:
                        logging.debug(f"PN532: InRelease status: 0x{status:02X}")
                else:
                    logging.debug(f"PN532: Unexpected InRelease response: {response}")
            else:
                logging.debug("PN532: No response payload for InRelease")

        except Exception as e:
            logging.debug(f"PN532: Error during InRelease: {e}")
        finally:
            self._clear_current_card()
        return True

    def wakeup(self):
        """Wake up PN532 from power down mode"""
        try:
            # Send dummy write to wake up PN532
            # PN532 requires a dummy byte to wake from low power mode
            self.i2c.i2c_write([0x00])
            time.sleep(0.05)
        except Exception as e:
            logging.debug(f"PN532: Wakeup write error (may be normal): {e}")
            pass
    
    def _write_command(self, cmd):
        """
        Write command to PN532
        Format: [Preamble][Start1][Start2][LEN][~LEN+1][D4][CMD...][CheckSum][PostAmble]
        """
        if not isinstance(cmd, list):
            cmd = [cmd]
        
        cmdlen = len(cmd) + 1  # +1 for PN532_HOSTTOPN532
        
        # Build packet
        packet = []
        packet.append(PN532_PREAMBLE)
        packet.append(PN532_STARTCODE1)
        packet.append(PN532_STARTCODE2)
        packet.append(cmdlen)
        packet.append((~cmdlen + 1) & 0xFF)  # LEN checksum
        packet.append(PN532_HOSTTOPN532)
        
        # Calculate checksum
        checksum = PN532_HOSTTOPN532
        for byte in cmd:
            packet.append(byte)
            checksum += byte
        
        packet.append((~checksum + 1) & 0xFF)
        packet.append(PN532_POSTAMBLE)
        
        # Debug output (use debug level during periodic scanning)
        logging.debug(f"PN532: Write CMD: {' '.join(f'{b:02X}' for b in packet)}")
        
        # Write via I2C (Klipper's i2c_write takes just the data array)
        self.i2c.i2c_write(packet)
    
    def _is_ready(self):
        """
        Check if PN532 is ready
        IMPORTANT: In Klipper, i2c_read() is ASYNC - it sends command to MCU
        and waits for response. On busy I2C bus, this can take significant time.
        """
        try:
            # For PN532, we just read 1 byte without writing any register address
            # Empty list [] means no register address (direct read)
            response = self.i2c.i2c_read([], 1)
            ready = response['response'][0] == PN532_I2C_READY
            logging.debug(f"PN532: ready check: {ready} (0x{response['response'][0]:02X})")
            return ready
        except Exception as e:
            logging.debug(f"PN532: Ready check error: {e}")
            return False
    
    def _wait_ready(self, timeout=1.0):
        """
        Wait for PN532 to be ready
        Based on pn532pi reference: poll every 1ms
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self._is_ready():
                return True
            # Use 1ms polling interval (same as pn532pi reference)
            # Klipper's async I2C can handle this frequency
            time.sleep(0.001)
        
        # Use debug level to avoid spam during periodic scanning
        logging.debug("PN532: wait ready timeout")
        return False
    
    def _read_data(self, length):
        """
        Read data from PN532
        I2C reads have a leading RDY byte that must be skipped
        
        CRITICAL: Klipper I2C has packet size limits!
        Based on testing: reads >32 bytes may timeout on busy I2C bus
        """
        try:
            # Clamp to maximum safe read size for Klipper I2C
            # 32 bytes is typical limit, but use 30 to be safe (with RDY byte = 31)
            max_safe_length = 30
            actual_read_length = min(length, max_safe_length)
            total_length = actual_read_length + 1  # +1 for RDY byte
            
            if actual_read_length < length:
                logging.debug(f"PN532: Clamping read: requested {length}, reading {actual_read_length} (Klipper I2C limit)")
            
            logging.debug(f"PN532: Reading {total_length} bytes from PN532...")
            response = self.i2c.i2c_read([], total_length)
            data = list(response['response'])
            
            # Skip first byte (RDY byte)
            actual_data = data[1:]
            
            logging.debug(f"PN532: Read data ({len(actual_data)} bytes): {' '.join(f'{b:02X}' for b in actual_data[:16])}...")
            return actual_data
        
        except Exception as e:
            # For read failures during card detection, log as warning
            logging.warning(f"PN532: ❌ I2C read failed (tried {length+1} bytes): {e}")
            logging.warning(f"PN532: Possible causes: busy I2C bus, MCU timeout, PN532 not ready")
            return None
    
    def _read_ack(self):
        """Read and verify ACK frame"""
        try:
            ack = self._read_data(6)
            if ack and ack == PN532_ACK:
                logging.debug("PN532: ACK received")
                return True
            else:
                logging.warning(f"PN532: Invalid ACK: {ack}")
                return False
        except Exception as e:
            logging.error(f"PN532: Read ACK error: {e}")
            return False
    
    def _send_command_check_ack(self, cmd, timeout=1.0):
        """
        Send command and check for ACK
        Based on pn532pi: minimal delay after write
        """
        try:
            # Write command
            self._write_command(cmd)
            
            # Minimal delay for PN532 to start processing
            # pn532pi doesn't have explicit delay here
            time.sleep(0.01)  # 10ms
            
            # Wait ready
            if not self._wait_ready(timeout):
                logging.error("PN532: Timeout waiting for ready after command")
                return False
            
            # Read ACK
            return self._read_ack()
        
        except Exception as e:
            logging.error(f"PN532: Send command error: {e}")
            return False
    
    def get_firmware_version(self):
        """Get PN532 firmware version"""
        try:
            # Send GetFirmwareVersion command
            if not self._send_command_check_ack([PN532_COMMAND_GETFIRMWAREVERSION]):
                logging.error("PN532: Failed to get ACK for firmware version")
                return None
            
            # Wait for response
            if not self._wait_ready(1.0):
                logging.error("PN532: Timeout waiting for firmware version")
                return None
            
            # Read response (13 bytes)
            response = self._read_data(13)
            if not response:
                return None
            
            # Verify response format
            # Expected: [0x00, 0x00, 0xFF, LEN, ~LEN, 0xD5, 0x03, IC, Ver, Rev, Support]
            if (response[0] == 0x00 and response[1] == 0x00 and 
                response[2] == 0xFF and response[5] == 0xD5 and response[6] == 0x03):
                
                ic = response[7]
                ver = response[8]
                rev = response[9]
                support = response[10]
                
                version = f"v{ver}.{rev} (IC: 0x{ic:02X}, Support: 0x{support:02X})"
                return version
            
            logging.error(f"PN532: Invalid firmware response: {response}")
            return None
        
        except Exception as e:
            logging.error(f"PN532: Get firmware version error: {e}")
            return None
    
    def sam_config(self):
        """Configure SAM (Secure Access Module)"""
        try:
            # SAMConfiguration: Normal mode, timeout 50ms, use IRQ
            cmd = [PN532_COMMAND_SAMCONFIGURATION, 0x01, 0x14, 0x01]
            
            if not self._send_command_check_ack(cmd):
                return False
            
            # Wait for response
            if not self._wait_ready(1.0):
                return False
            
            # Read response
            response = self._read_data(9)
            if response and response[6] == 0x15:  # SAM response
                logging.info("PN532: SAM configured successfully")
                return True
            
            return False
        
        except Exception as e:
            logging.error(f"PN532: SAM config error: {e}")
            return False
    
    def rf_config(self):
        """Configure RF field for card detection"""
        try:
            # RFConfiguration: Configure RF field
            # ConfigItem = 0x01 (RF Field)
            # Data = 0x01 (Enable RF field)
            cmd = [PN532_COMMAND_RFCONFIGURATION, 0x01, 0x01]
            
            if not self._send_command_check_ack(cmd):
                logging.error("PN532: Failed to send RF config command")
                return False
            
            # Wait for response
            if not self._wait_ready(1.0):
                logging.error("PN532: Timeout waiting for RF config response")
                return False
            
            # Read response
            response = self._read_data(9)
            if response and response[6] == 0x33:  # RF Config response
                logging.info("PN532: RF field configured and enabled")
                return True
            logging.error("PN532: Invalid RF config response")
            return False
        
        except Exception as e:
            logging.error(f"PN532: RF config error: {e}")
            return False
    
    def read_passive_target_id(self, timeout=1.0):
        """
        Read passive target (card) ID
        Returns: (success, uid) where uid is a list of bytes
        Default timeout: 1s (same as pn532pi reference)
        """
        try:
            # InListPassiveTarget: MaxTg=1, BrTy=0x00 (106kbps Type A ISO14443A)
            cmd = [PN532_COMMAND_INLISTPASSIVETARGET, 0x01, 0x00]
            
            logging.debug("PN532: =" * 60)
            logging.debug("PN532: 🔍 CARD DETECTION DEBUG START")
            logging.debug(f"PN532: Command: InListPassiveTarget [{' '.join(f'0x{b:02X}' for b in cmd)}]")
            logging.debug(f"PN532: Timeout: {timeout}s")
            
            # Send command and wait for ACK
            if not self._send_command_check_ack(cmd, timeout):
                logging.debug("PN532: ❌ No ACK received from PN532")
                logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (NO ACK)")
                logging.debug("PN532: =" * 60)
                self._clear_current_card()
                return False, None
            
            logging.debug("PN532: ✓ ACK received")
            
            # Wait for card detection response
            if not self._wait_ready(timeout):
                logging.debug(f"PN532: ⏱ Timeout waiting for response ({timeout}s)")
                logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (TIMEOUT)")
                logging.debug("PN532: =" * 60)
                self._clear_current_card()
                return False, None
            
            logging.debug("✓ PN532 ready, reading response...")
            
            return self.read_inlist_response()
        
        except Exception as e:
            logging.error(f"PN532: ❌ Exception during card detection: {e}")
            import traceback
            logging.error(f"PN532: {traceback.format_exc()}")
            logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (EXCEPTION)")
            logging.debug("PN532: =" * 60)
            self._clear_current_card()
            return False, None

    def read_inlist_response(self):
        # Read response
            # For InListPassiveTarget: typical response is ~20 bytes for 7-byte UID
            # Read 30 bytes to be safe (limited by Klipper I2C packet size)
            response = self._read_data(30)
            if not response:
                logging.warning("❌ Failed to read card response data")
                logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (NO RESPONSE)")
                logging.debug("PN532: =" * 60)
                self._clear_current_card()
                return False, None
            
            # Print FULL response for debugging
            logging.debug(f"PN532: 📦 Response length: {len(response)} bytes")
            logging.debug(f"PN532: 📦 Response (first 32 bytes):")
            for i in range(0, min(len(response), 32), 16):
                chunk = response[i:i+16]
                hex_str = ' '.join(f'{b:02X}' for b in chunk)
                logging.debug(f"PN532:    [{i:02d}]: {hex_str}")
            
            # Verify response format
            # [0x00, 0x00, 0xFF, LEN, ~LEN, 0xD5, 0x4B, NumTags, ...]
            logging.debug(f"PN532: 🔍 Checking response format...")
            logging.debug(f"PN532:    response[0] = 0x{response[0]:02X} (expect 0x00)")
            logging.debug(f"PN532:    response[1] = 0x{response[1]:02X} (expect 0x00)")
            logging.debug(f"PN532:    response[2] = 0x{response[2]:02X} (expect 0xFF)")
            logging.debug(f"PN532:    response[5] = 0x{response[5]:02X} (expect 0xD5)")
            logging.debug(f"PN532:    response[6] = 0x{response[6]:02X} (expect 0x4B)")
            
            if (response[0] == 0x00 and response[1] == 0x00 and 
                response[2] == 0xFF and response[5] == 0xD5 and 
                response[6] == 0x4B):  # InListPassiveTarget response
                
                logging.debug("PN532: ✓ Response format valid")
                
                num_tags = response[7]
                logging.debug(f"PN532: 📋 NumTags = {num_tags}")
                
                if num_tags == 0:
                    logging.debug("PN532: ⚠ NumTags = 0: No card in RF field")
                    logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (NO CARD)")
                    logging.debug("PN532: =" * 60)
                    self._clear_current_card()
                    return False, None
                elif num_tags > 1:
                    logging.debug(f"PN532: ⚠ Multiple cards detected: {num_tags}")
                
                # Parse UID
                # response[8] = Tg (target number)
                # response[9-10] = SENS_RES
                # response[11] = SEL_RES (SAK)
                # response[12] = UID Length
                tg = response[8]
                sens_res = (response[9] << 8) | response[10]
                sak = response[11]
                uid_len = response[12]
                
                logging.debug(f"PN532: 📋 Card info:")
                logging.debug(f"PN532:    Tg (Target Number) = {tg}")
                logging.debug(f"PN532:    SENS_RES = 0x{sens_res:04X}")
                logging.debug(f"PN532:    SAK = 0x{sak:02X}")
                logging.debug(f"PN532:    UID Length = {uid_len} bytes")
                
                if uid_len > 0 and uid_len <= 10:
                    uid = response[13:13+uid_len]
                    uid_hex = ' '.join(f'{b:02X}' for b in uid)
                    logging.debug(f"PN532:    UID = {uid_hex}")
                    self._set_current_card(tg, uid)
                    logging.debug("PN532: ✅ CARD DETECTED SUCCESSFULLY!")
                    logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (SUCCESS)")
                    logging.debug("PN532: =" * 60)
                    
                    return True, list(uid)
                else:
                    logging.error(f"❌ Invalid UID length: {uid_len}")
                    logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (INVALID UID)")
                    logging.debug("PN532: =" * 60)
                    self._clear_current_card()
                    return False, None
            else:
                logging.error("❌ Invalid response format from PN532")
                logging.debug(f"PN532: Expected header: 00 00 FF xx xx D5 4B")
                logging.debug(f"PN532: Got header:      {' '.join(f'{b:02X}' for b in response[:7])}")
                logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (BAD FORMAT)")
                logging.debug("PN532: =" * 60)
                self._clear_current_card()
                return False, None

    def robust_page_read(self, page):
        """
        Robust page reading with error recovery
        Based on Filaman's robustPageRead implementation
        
        Reads 4 pages (16 bytes) from NTAG with automatic retry and card re-verification
        """
        MAX_READ_ATTEMPTS = 3

        if self.current_target is None:
            logging.debug(f"PN532: No active target before reading page {page}, attempting re-detection")
            success, uid = self.read_passive_target_id(timeout=0.5)
            if not success:
                logging.warning(f"PN532: Unable to detect tag before reading page {page}")
                return None

        expected_uid = self.current_uid[:] if self.current_uid else None
        
        for attempt in range(MAX_READ_ATTEMPTS):
            # Try to read the page
            page_data = self.ntag_read_page(page)
            
            if page_data:
                return page_data
            
            logging.debug(f"PN532: Page {page} read failed, attempt {attempt + 1}/{MAX_READ_ATTEMPTS}")
            
            # Try to stabilize connection between attempts
            if attempt < MAX_READ_ATTEMPTS - 1:
                # Release current target to force a clean re-select
                self._release_current_target(reason=f"page_{page}_retry_{attempt + 1}")
                time.sleep(0.025)  # 25ms delay (same as Filaman)

                # Re-verify tag presence with longer timeout for busy I2C bus
                success, uid = self.read_passive_target_id(timeout=0.5)
                if not success:
                    logging.debug(f"PN532: Tag re-verification failed, attempt {attempt + 1}")
                    # Try one more time with extra delay before giving up
                    time.sleep(0.05)  # Additional 50ms
                    success, uid = self.read_passive_target_id(timeout=0.5)
                    if not success:
                        logging.warning(f"PN532: Tag lost during page {page} read operation")
                        self._clear_current_card()
                        return None
                else:
                    # Confirm we're still dealing with the same tag
                    if expected_uid and uid != expected_uid:
                        logging.warning(f"PN532: Different tag detected during page {page} retry")
                        self._release_current_target(reason="uid_changed")
                        return None
                    # InListPassiveTarget: MaxTg=1, BrTy=0x00 (106kbps Type A ISO14443A)
                    cmd = [PN532_COMMAND_INLISTPASSIVETARGET, 0x01, 0x00]
                logging.debug(f"PN532: Tag re-verified, retrying page {page}")
        
        # If we exhaust retries, release target to force fresh detection next time
        self._release_current_target(reason=f"page_{page}_max_retries")
        return None
    
    def ntag_read_page(self, page):
        """
        Read 4 pages (16 bytes) from NTAG starting at page number
        NTAG215: pages 0-134
        
        Simple, direct read - one attempt only
        """
        try:
            # Ensure we have a target selected (default to 1 if unknown)
            target = self.current_target if self.current_target is not None else 0x01
            if self.current_target is None:
                logging.debug("PN532: No active target cached, defaulting to Tg=1")

            # InDataExchange: Read command
            cmd = [PN532_COMMAND_INDATAEXCHANGE, target, MIFARE_CMD_READ, page]
            
            if not self._send_command_check_ack(cmd):
                logging.debug(f"PN532: No ACK for read page {page}")
                return None
            
            # Wait for response
            if not self._wait_ready(1.0):
                logging.debug(f"PN532: Timeout reading page {page}")
                return None
            
            # Read response
            # For NTAG page read: response is ~26 bytes (header + 16 bytes data + footer)
            # Read 30 bytes to be safe (limited by Klipper I2C packet size)
            response = self._read_data(30)
            if not response:
                logging.debug(f"PN532: Failed to read response for page {page}")
                return None
            
            logging.debug(f"PN532: Read page {page} response: {' '.join(f'{b:02X}' for b in response[:26])}")
            
            # Verify response
            # [0x00, 0x00, 0xFF, LEN, ~LEN, 0xD5, 0x41, Status, Data...]
            if (response[0] == 0x00 and response[1] == 0x00 and 
                response[2] == 0xFF and response[5] == 0xD5 and 
                response[6] == 0x41):  # InDataExchange response
                
                status = response[7]
                if status != 0x00:
                    logging.debug(f"PN532: Read page {page} status error: 0x{status:02X}")
                    
                    # 0x01 error: Timeout (card not responding)
                    # Usually means reading past valid data - don't retry
                    if status == 0x01:
                        logging.debug(f"PN532: Read page {page}: Card timeout (0x01) - likely past valid data")
                        return None
                    
                    # Other errors (0x0B RF error, 0x27 protocol error, etc.)
                    logging.debug(f"PN532: Read page {page} status error: 0x{status:02X}")
                    return None
                
                # Extract 16 bytes of data (4 pages)
                data = response[8:24]
                return list(data)
            
            logging.error(f"PN532: Invalid read response for page {page}")
            return None
        
        except Exception as e:
            logging.error(f"PN532: NTAG read page error: {e}")
            return None
    
    def ntag_read_user_memory(self, start_page=4, end_page=67):
        """
        Read NTAG user memory with smart NDEF length detection
        NTAG215 user memory: pages 4-129 (504 bytes)
        
        NDEF TLV format:
        - Byte 0: TLV tag (0x03 = NDEF Message)
        - Byte 1: Length (if < 255) or 0xFF (if using 3-byte format)
        - Byte 2-N: NDEF message data
        - Last: 0xFE = Terminator TLV
        """
        user_data = bytearray()
        
        # Step 1: Read first block to detect NDEF length
        self.gcode.respond_info(f"📖 Reading NDEF header from page {start_page}...")
        first_block = self.robust_page_read(start_page)
        
        if not first_block:
            self.gcode.respond_info(f"❌ Failed to read first page after retries")
            self._release_current_target(reason="user_memory_header_fail")
            return user_data
        
        user_data.extend(first_block)
        
        # Parse NDEF TLV header
        actual_end_page = end_page  # Default to full range
        
        if len(first_block) >= 2:
            tlv_tag = first_block[0]
            tlv_length = first_block[1]
            
            self.gcode.respond_info(f"📋 NDEF TLV: Tag=0x{tlv_tag:02X}, Length={tlv_length}")
            
            if tlv_tag == 0x03:  # NDEF Message TLV
                if tlv_length < 0xFF:
                    # Total bytes needed: TLV tag (1) + Length (1) + Message (tlv_length) + Terminator (1)
                    total_bytes_needed = 1 + 1 + tlv_length + 1
                    # Round up to page boundary (4 bytes per page)
                    pages_needed = (total_bytes_needed + 3) // 4
                    actual_end_page = start_page + pages_needed - 1
                    
                    self.gcode.respond_info(f"✓ NDEF data size: {tlv_length} bytes")
                    self.gcode.respond_info(f"✓ Total read needed: {total_bytes_needed} bytes ({pages_needed} pages)")
                    self.gcode.respond_info(f"✓ Optimized read range: pages {start_page}-{actual_end_page}")
                else:
                    # 3-byte length format (for data > 254 bytes)
                    if len(first_block) >= 4:
                        tlv_length = (first_block[2] << 8) | first_block[3]
                        total_bytes_needed = 1 + 3 + tlv_length + 1
                        pages_needed = (total_bytes_needed + 3) // 4
                        actual_end_page = start_page + pages_needed - 1
                        self.gcode.respond_info(f"✓ NDEF data size: {tlv_length} bytes (3-byte format)")
            elif tlv_tag == 0x00:
                self.gcode.respond_info(f"⚠ Empty NTAG card (no NDEF data)")
                self._release_current_target(reason="user_memory_empty")
                return user_data
        
        # Limit to reasonable bounds
        actual_end_page = min(actual_end_page, end_page)
        
        # Step 2: Read remaining pages (using Filaman-style robust reading)
        current_page = start_page + 4  # Already read first 4 pages
        
        while current_page <= actual_end_page:
            try:
                # Small delay between page reads (increased for stability)
                if current_page > start_page:
                    time.sleep(0.005)  # 5ms delay (increased from 2ms for better stability)
                
                # Read 4 pages (16 bytes) with built-in retry and card re-verification
                page_data = self.robust_page_read(current_page)
                
                if page_data:
                    # Success!
                    # Calculate how many bytes to use
                    remaining_pages = actual_end_page - current_page + 1
                    if remaining_pages >= 4:
                        user_data.extend(page_data)
                    else:
                        bytes_needed = remaining_pages * 4
                        user_data.extend(page_data[:bytes_needed])
                    
                    # Show progress every 8 pages
                    if (current_page - start_page) % 8 == 0:
                        data_preview = ' '.join(f'{b:02X}' for b in page_data[:8])
                        self.gcode.respond_info(f"  Page {current_page}: {data_preview}...")
                    
                    # Check for NDEF terminator (0xFE) - can stop early
                    if 0xFE in page_data:
                        fe_index = page_data.index(0xFE)
                        self.gcode.respond_info(f"✓ Found NDEF terminator at byte {len(user_data) - len(page_data) + fe_index}")
                        self.gcode.respond_info(f"✓ NDEF read complete!")
                        break
                    
                    # Move to next block after successful read
                    current_page += 4
                else:
                    # Read failed after 3 retries (robust_page_read already tried)
                    self.gcode.respond_info(f"❌ Page {current_page} failed after 3 attempts")
                    self.gcode.respond_info(f"   Read {len(user_data)} bytes successfully")
                    logging.warning(f"PN532: Stopping read at page {current_page}, got {len(user_data)} bytes")
                    break
            
            except Exception as e:
                logging.error(f"PN532: Error reading page {current_page}: {e}")
                self.gcode.respond_info(f"❌ Exception at page {current_page}")
                self.gcode.respond_info(f"   Read {len(user_data)} bytes successfully")
                break
        
        # Summary
        expected_bytes = (actual_end_page - start_page + 1) * 4
        self.gcode.respond_info(f"📦 Total bytes read: {len(user_data)}")
        
        if len(user_data) >= expected_bytes * 0.9:  # Got at least 90%
            self.gcode.respond_info(f"✓ Read complete ({len(user_data)}/{expected_bytes} bytes)")
        else:
            self.gcode.respond_info(f"⚠ Partial read ({len(user_data)}/{expected_bytes} bytes)")
        
        # Release target after finishing read sequence to avoid stale selections
        self._release_current_target(reason="user_memory_complete")

        return user_data
    
    def format_data(self, data):
        """Format data as hex string"""
        return ' '.join(f'{b:02X}' for b in data)


class PN532Service:
    """Service for periodic NTAG reading"""
    def __init__(self, reactor):
        self.reactor = reactor
        
        self.running = False
        self.timer = None
        
        self.func = None
        self.params = None
        self.callback = None
        
        # Reschedule interval, seconds
        # Use 1 second interval (based on practical testing)
        # Faster polling with 1ms intervals should work better now
        self.period = 1.0  # 1 second between scans
    
    def start(self):
        if self.running:
            return False
        self.running = True
        
        self.reactor.register_timer(self.periodic_task,self.reactor.monotonic())
        waketime = self.reactor.monotonic() + self.period
        self.timer = self.reactor.register_timer(
            self.periodic_task, waketime)
        
        logging.info("PN532: Service started")
        return True
    
    def stop(self):
        if not self.running:
            return False
        self.running = False
        
        self.teardown()
        
        logging.info("PN532: Service stopped")
        return True
    
    def schedule(self, func, params=None, callback=None):
        if self.func and self.running:
            # Return to skip
            logging.warning(f"PN532: schedule func:{self.func} exists and running, skip...")
            return False
        
        self.func = func
        self.params = params
        self.callback = callback
    
    def teardown(self):
        if self.timer:
            self.reactor.unregister_timer(self.timer)
            self.timer = None
        
        if self.func:
            self.func = None
            self.params = None
    
    def periodic_task(self, eventtime):
        if self.func is None:
            logging.warning(f"PN532: Schedule func not exists, return")
            return self.reactor.NEVER
        
        if self.timer is None:
            logging.warning(f"PN532: Schedule timer not exists, return")
            return self.reactor.NEVER
        
        result = self.func(**self.params) \
            if self.params is not None \
            else self.func()
        
        if result and self.callback:
            self.callback(result)
        
        # Re-register the timer for the next execution
        next_waketime = self.reactor.monotonic() + self.period
        
        if self.timer:
            self.reactor.update_timer(self.timer, next_waketime)
            return next_waketime
        else:
            logging.info(f"PN532: Schedule timer not exists, return Never")
            return self.reactor.NEVER


class PN532Manager:
    """Manager for PN532 RFID operations"""
    def __init__(self, printer, i2c):
        self.printer = printer
        self.gcode = self.printer.lookup_object('gcode')
        self.handler = PN532Handler(printer, i2c)
        self.last_uid = None
        self.waiting_for_removal = False
        self.waiting_notice_sent = False
        self.waiting_for_interrupt = False
    
    def _search_spool_id_in_obj(self, obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in ('spool_id', 'spool', 'filament'):
                    if isinstance(value, (str, int, float)):
                        return str(value).strip()
                nested = self._search_spool_id_in_obj(value)
                if nested:
                    return nested
        elif isinstance(obj, list):
            for item in obj:
                nested = self._search_spool_id_in_obj(item)
                if nested:
                    return nested
        return None

    def _extract_spool_id(self, data_str):
        if not data_str:
            return None

        text = data_str.strip()

        # Try JSON parsing first
        try:
            obj = json.loads(text)
            spool_id = self._search_spool_id_in_obj(obj)
            if spool_id:
                return spool_id
        except Exception:
            pass

        # Fallback to regex search in plain text
        pattern = re.compile(r'"?(?:spool_id|spool|filament)"?\s*[:=]\s*["`]?([0-9A-Za-z_\-\s]+)["`]?', re.IGNORECASE | re.DOTALL)
        match = pattern.search(text)
        if match:
            raw_value = match.group(1)
            normalized = re.sub(r'\s+', '', raw_value)
            if normalized:
                return normalized

        return None

    def _apply_spool_id(self, spool_id):
        if not spool_id:
            return

        command = f"MMU_GATE_MAP NEXT_SPOOLID={spool_id}"
        try:
            self.gcode.run_script(command)
            self.gcode.respond_info(f"😊 HappyHare spool ID found: {spool_id}. Command dispatched to HappyHare.")
            logging.info(f"PN532: Pushed HappyHare spool ID via command: {command}")
        except Exception as e:
            logging.error(f"PN532: Failed to apply spool ID '{spool_id}': {e}")
            self.gcode.respond_info(f"Failed to apply spool ID '{spool_id}'. Check logs.")

    def rfid_detect(self):
        """Detect NTAG card presence"""
        self.gcode.respond_info("🔍 Starting NTAG tag detect..")
        # InListPassiveTarget: MaxTg=1, BrTy=0x00 (106kbps Type A ISO14443A)
        cmd = [PN532_COMMAND_INLISTPASSIVETARGET, 0x01, 0x00]
        
        timeout = 1.0

        logging.debug("PN532: =" * 60)
        logging.debug("PN532: 🔍 CARD DETECTION DEBUG START")
        logging.debug(f"PN532: Command: InListPassiveTarget [{' '.join(f'0x{b:02X}' for b in cmd)}]")
        logging.debug(f"PN532: Timeout: {timeout}s")
        
        # Send command and wait for ACK
        if not self.handler._send_command_check_ack(cmd, timeout):
            logging.debug("PN532: ❌ No ACK received from PN532")
            logging.debug("PN532: 🔍 CARD DETECTION DEBUG END (NO ACK)")
            logging.debug("PN532: =" * 60)
            self.handler._clear_current_card()
            return False, None
        logging.debug("PN532: 🔍 WAITING FOR IRQ")

        self.waiting_for_interrupt = True
            
    def rfid_read(self, from_interrupt=False):
        """Read NTAG card and parse JSON data with retry mechanism (inspired by Filaman project)"""
        try:
            # Detect card with retry mechanism and RF field refresh (like Filaman)
            max_attempts = 3
            success = False
            uid = None
            reuse_detection = False
            if from_interrupt:
                self.waiting_for_interrupt = False
                self.gcode.respond_info("🔍 NTAG interrupt received, starting read...")
            else:
                self.gcode.respond_info("🔍 Starting NTAG tag read...")

            # If we previously read a tag successfully, require removal before re-reading
            # if self.waiting_for_removal:
            #     res_success, res_uid = self.handler.read_passive_target_id(timeout=0.5)

            #     if res_success and res_uid:
            #         res_uid_list = list(res_uid)
            #         if self.last_uid and res_uid_list == self.last_uid:
            #             if not self.waiting_notice_sent:
            #                 self.gcode.respond_info("Tag already processed. Please remove it before re-reading.")
            #                 self.waiting_notice_sent = True
            #             return None
            #         else:
            #             logging.info("PN532: New tag detected while waiting for removal; resetting read state.")
            #             self.waiting_for_removal = False
            #             self.waiting_notice_sent = False
            #             self.last_uid = None
            #             success = True
            #             uid = res_uid_list
            #             reuse_detection = True
            #     else:
            #         if self.waiting_notice_sent:
            #             self.gcode.respond_info("Tag removed. Reader is ready.")
            #         self.waiting_for_removal = False
            #         self.waiting_notice_sent = False
            #         self.last_uid = None
            #         return None

            self.gcode.respond_info("🔍 Detecting NTAG tag...")
            if not reuse_detection:
                success, uid = self.handler.read_inlist_response()
                if not success or not uid:
                    for attempt in range(max_attempts):
                        logging.debug(f"PN532: Detection attempt {attempt + 1}/{max_attempts}")
                        success, uid = self.handler.read_passive_target_id(timeout=1.0)

                        if success and uid:
                            logging.info(f"PN532: Card detected on attempt {attempt + 1}")
                            break

                        if attempt < max_attempts - 1:
                            logging.info(f"PN532: Detection attempt {attempt + 1} failed, refreshing RF field...")
                            self.handler.sam_config()
                            time.sleep(0.01)  # Minimal delay between retries

            if not success or not uid:
                if not self.waiting_for_removal:
                    self.gcode.respond_info("No tag detected (3 attempts). Retrying later...")
                    logging.info("PN532: No card detected after 3 attempts")
                    logging.warning("PN532: I2C bus appears congested - consider reducing MMU I2C traffic")
                return None
            
            self.gcode.respond_info("Displaying UID...")
            # Display UID
            uid_list = list(uid)
            uid_str = ' '.join(f'{b:02X}' for b in uid_list)
            self.gcode.respond_info("=" * 50)
            self.gcode.respond_info("✓ NTAG Card Detected!")
            self.gcode.respond_info(f"Card UID: {uid_str}")
            logging.info(f"Card detected: UID={uid_str}")
            
            self.gcode.respond_info("reading user memory...")
            # Read user memory
            user_data = self.handler.ntag_read_user_memory(start_page=4, end_page=67)
            
            if not user_data or len(user_data) == 0:
                self.gcode.respond_info("No data on card")
                return None

            # Mark this UID as processed and wait for removal before next read
            self.last_uid = uid_list
            self.waiting_for_removal = True
            self.waiting_notice_sent = False
            
            # Show hex preview
            hex_preview = ' '.join(f'{b:02X}' for b in user_data[:32])
            self.gcode.respond_info(f"Data preview: {hex_preview}")
            
            # Decode as text
            data_str = user_data.decode('utf-8', errors='ignore').rstrip('\x00').strip()
            self.gcode.respond_info(f"Data length: {len(data_str)} chars")
            
            if not data_str:
                self.gcode.respond_info("Card is empty")
                return None
            
            # Remove NDEF header if present (look for JSON start)
            json_start = data_str.find('{')
            if json_start > 0:
                self.gcode.respond_info(f"Removing NDEF header ({json_start} chars)")
                data_str = data_str[json_start:]
            
            # Trim to JSON end
            json_end = data_str.rfind('}')
            if json_end > 0 and json_end < len(data_str) - 1:
                data_str = data_str[:json_end + 1]
            
            # Extract spool id from data
            spool_id = self._extract_spool_id(data_str)
            if spool_id:
                self._apply_spool_id(spool_id)
            else:
                logging.info("No spool ID found in tag data")
                self.gcode.respond_info("😢 No HappyHare spool ID found in tag data.")

            # Try to parse as JSON
            try:
                data_json = json.loads(data_str)
                json_formatted = json.dumps(data_json, indent=2, ensure_ascii=False)
                
                self.gcode.respond_info("NTAG data (JSON):")
                for line in json_formatted.split('\n'):
                    self.gcode.respond_info(f"  {line}")
                self.gcode.respond_info("=" * 50)
                
                logging.info(f"PN532: NTAG JSON: {json_formatted}")
                return json_formatted
            
            except json.JSONDecodeError as e:
                self.gcode.respond_info("Data is not JSON format")
                cleaned_parts = []
                for ch in data_str:
                    if (32 <= ord(ch) <= 126) or ch in ('\n', '\r'):
                        cleaned_parts.append(ch)
                    else:
                        cleaned_parts.append(f"<0x{ord(ch):02X}>")
                cleaned_text = ''.join(cleaned_parts)
                self.gcode.respond_info(f"Text data: {cleaned_text}")
                self.gcode.respond_info("=" * 50)
                logging.info(f"PN532: NTAG text data: {data_str}")
                return data_str

        except Exception as e:
            error_msg = f"Error reading NTAG: {e}"
            self.gcode.respond_info(error_msg)
            logging.error(f"PN532: {error_msg}")
            import traceback
            logging.error(f"PN532: {traceback.format_exc()}")
            return None
        finally:
            if from_interrupt: # schedule next detect
                self.handler.rfid_detect()
        


class PN532_:
    """Klipper plugin for PN532 NFC reader"""
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name().split()[1]
        
        # Setup I2C - use standard Klipper I2C configuration (same as BME280)
        # Expects config like:
        #   i2c_address: 36
        #   i2c_mcu: mmu
        #   i2c_bus: i2c2_PB10_PB11
        # Format: i2c<bus>_<SDA>_<SCL>
        from . import bus
        self.i2c = bus.MCU_I2C_from_config(
            config, default_addr=PN532_I2C_ADDRESS, default_speed=100000)
        
        self.irq_state = False
        
        # Delay initialization until Klipper is fully ready
        logging.info(f"PN532: Registering '{self.name}' (will initialize after system is ready)...")
        self.manager = None
        self.service = None
        # IRQ configuration
        self.irq_pin = config.get("irq_pin", None)
        if self.irq_pin:
            try:
                buttons = self.printer.load_object(config, "buttons")
                buttons.register_debounce_button(self.irq_pin, self._irq_callback, config)
            except Exception as e:
                logging.error(f"PN532: Failed to load buttons module for IRQ pin: {e}")
                self.irq_pin = None
        
        # Register connect handler to initialize AFTER all I2C devices are ready
        # This ensures BME280 and other devices initialize first
        self.printer.register_event_handler("klippy:connect", self._handle_connect)
        
        # Register commands
        self.gcode = self.printer.lookup_object("gcode")
        self.gcode.register_mux_command(
            cmd = "PN532",
            key = "NAME",
            value = self.name,
            func = self.cmd_PN532)

    
    def _handle_connect(self):
        """Initialize PN532 when Klipper is fully connected"""
        # Delay initialization to let other I2C devices initialize first
        reactor = self.printer.get_reactor()
        reactor.register_timer(self._delayed_init, reactor.monotonic() + 2.0)
    
    def _delayed_init(self, eventtime):
        """Delayed initialization after other I2C devices are ready"""
        try:
            logging.info(f"PN532: Starting '{self.name}' initialization (delayed)...")
            self.manager = PN532Manager(self.printer, self.i2c)
            logging.info(f"PN532: '{self.name}' ready!")
            if self.irq_pin:
                logging.info("PN532: IRQ pin configured, beginning read immediately")
                self.read_begin()
        except Exception as e:
            logging.error(f"PN532: '{self.name}' initialization failed: {e}")
            logging.error("PN532: PN532 will be disabled. Other I2C devices should continue to work.")
            import traceback
            logging.error(f"PN532: {traceback.format_exc()}")
            # Don't raise - allow Klipper to continue with other devices
            self.manager = None
        
        return self.printer.get_reactor().NEVER  # Don't repeat this timer

    def _irq_callback(self, eventtime, state):
        """Callback triggered when IRQ pin changes state.
        State=1 indicates pin is active (pressed), state=0 indicates released.
        For active-low pins, configure with invert=True in pin definition.
        """
        self.irq_state = state
        if not state:  # Only ,trigger when pin becomes active
            return
        if not self.manager:
            logging.info("PN532: Manager not initialized, cannot handle IRQ")
            return
        if not self.manager.waiting_for_interrupt:
            logging.info("PN532: Not waiting for interrupt, ignoring")
            return
        try:
            self.gcode.respond_info("PN532: IRQ triggered, scheduling RFID read")
            # Schedule the RFID detect on the reactor to avoid blocking the button handler
            self.manager.waiting_for_interrupt = False
            self.printer.get_reactor().register_callback(
                lambda t: self.manager.rfid_read())
        except Exception as e:
            logging.error(f"PN532: Error in IRQ callback: {e}")

    
    def _init_service(self):
        """Initialize service for periodic reading"""
        if not self.manager:
            logging.error("PN532: Manager not initialized, cannot start service")
            return
        self.service = PN532Service(self.printer.get_reactor())
    
    def read_begin(self):
        """Start periodic NTAG reading"""
        if not self.manager:
            self.gcode.respond_info("PN532 not initialized - check logs")
            return
        
        if not self.service:
            self._init_service()
        
        if self.irq_pin:
            self.service.period = 3
            #self.service.schedule(func=self.manager.rfid_detect)
            self.manager.rfid_detect()  # Single detect to prime IRQ
        else:
            self.service.schedule(func=self.manager.rfid_read)
        
        ret = self.service.start()
        msg = "PN532 read initiated in the backend." \
            if ret else "PN532 read is already running."
        self.gcode.respond_info(msg)
    
    def read_end(self):
        """Stop periodic NTAG reading"""
        if not self.service:
            logging.warning("PN532: No service found, return")
            return
        # Stop background service
        ret = self.service.stop()
        msg = "PN532 read terminated in the backend." \
            if ret else "PN532 read is not running."
        self.gcode.respond_info(msg)
    
    def cmd_PN532(self, gcmd):
        """G-Code command to control PN532"""
        # Get operation type: READ or SCAN
        read_flag = gcmd.get_int("READ", 0)
        scan_flag = gcmd.get_int("SCAN", 0)
        
        if read_flag == 1:
            # Start periodic reading
            self.read_begin()
        elif read_flag == 0:
            # Stop periodic reading (only if explicitly set to 0)
            self.read_end()
        elif scan_flag == 1:
            # SCAN operation
            self.gcode.respond_info("Scanning I2C bus for PN532...")
            self.gcode.respond_info(f"Current I2C address: 0x{PN532_I2C_ADDRESS:02X} (decimal {PN532_I2C_ADDRESS})")
            self.gcode.respond_info("Note: The I2C address is already configured via i2c_address parameter")
            self.gcode.respond_info("This scan just tests if the device responds at the configured address")
            
            try:
                # Try to read 1 byte from the configured I2C device
                # Empty list [] means no register address (direct read)
                self.gcode.respond_info("Attempting to read from PN532...")
                response = self.i2c.i2c_read([], 1)
                
                if response and 'response' in response:
                    data = response['response'][0]
                    self.gcode.respond_info("=" * 50)
                    self.gcode.respond_info(f"✓ PN532 found at configured address!")
                    self.gcode.respond_info(f"  Response: 0x{data:02X}")
                    if data == 0x01:
                        self.gcode.respond_info("  Status: READY (0x01) - Device is working!")
                    elif data == 0x00:
                        self.gcode.respond_info("  Status: BUSY (0x00) - Device is processing")
                    else:
                        self.gcode.respond_info(f"  Status: Unknown (0x{data:02X})")
                    self.gcode.respond_info("=" * 50)
                else:
                    self.gcode.respond_info("=" * 50)
                    self.gcode.respond_info("✗ No response from PN532")
                    self.gcode.respond_info("=" * 50)
                    
            except Exception as e:
                self.gcode.respond_info("=" * 50)
                self.gcode.respond_info(f"✗ Error reading from PN532: {e}")
                self.gcode.respond_info("")
                self.gcode.respond_info("Possible issues:")
                self.gcode.respond_info("  1. PN532 not in I2C mode (check SEL0=LOW, SEL1=HIGH)")
                self.gcode.respond_info("  2. Wrong I2C address in config")
                self.gcode.respond_info("  3. SDA/SCL pins swapped or disconnected")
                self.gcode.respond_info("  4. No power to PN532 (check VCC/GND)")
                self.gcode.respond_info("  5. I2C bus conflict with other devices")
                self.gcode.respond_info("=" * 50)
        
        else:
            # No operation specified, show help
            self.gcode.respond_info("PN532 command usage:")
            self.gcode.respond_info("  PN532 NAME=mmu_reader READ=1   - Start periodic NTAG reading")
            self.gcode.respond_info("  PN532 NAME=mmu_reader READ=0   - Stop periodic NTAG reading")
            self.gcode.respond_info("  PN532 NAME=mmu_reader SCAN=1   - Scan I2C bus")


def load_config_prefix(config):
    return PN532(config)

