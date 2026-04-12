# Manual PN532 I2C console for Klipper.
#
# This module is intentionally small and does not auto-initialize the reader.
# It lets each PN532 init transaction be run from the Fluidd console so the
# exact I2C operation that fails can be identified in klippy.log.
#
# Example printer.cfg:
#
# [pn532_console mmu_reader]
# i2c_mcu: lane4
# i2c_bus: i2c3_PB3_PB4
# i2c_address: 36
#
# Software I2C example:
#
# [pn532_console mmu_reader]
# i2c_mcu: lane4
# i2c_software_scl_pin: PB3
# i2c_software_sda_pin: PB4
# i2c_address: 36
#
# Start in Fluidd with:
#
# PN_CONSOLE NAME=mmu_reader HELP=1

import logging
import time

from . import bus


PN532_PREAMBLE = 0x00
PN532_STARTCODE1 = 0x00
PN532_STARTCODE2 = 0xFF
PN532_POSTAMBLE = 0x00

PN532_HOSTTOPN532 = 0xD4
PN532_PN532TOHOST = 0xD5

PN532_COMMAND_GETFIRMWAREVERSION = 0x02
PN532_COMMAND_SAMCONFIGURATION = 0x14
PN532_COMMAND_INLISTPASSIVETARGET = 0x4A

PN532_I2C_ADDRESS = 0x24
PN532_I2C_READY = 0x01
PN532_I2C_BUSY = 0x00

PN532_ACK = [0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00]


def _hex(data):
    return " ".join("%02X" % (b & 0xFF) for b in data)


def _parse_hex_bytes(value):
    value = value.replace(",", " ").replace(":", " ").replace("-", " ")
    parts = []
    for token in value.split():
        token = token.strip()
        if not token:
            continue
        if token.lower().startswith("0x"):
            token = token[2:]
        parts.append(int(token, 16) & 0xFF)
    return parts


class PN532Console:
    def __init__(self, config):
        self.printer = config.get_printer()
        parts = config.get_name().split()
        self.name = parts[-1] if len(parts) > 1 else "default"
        self.gcode = self.printer.lookup_object("gcode")
        self.i2c = bus.MCU_I2C_from_config(
            config, default_addr=PN532_I2C_ADDRESS, default_speed=100000)

        self.gcode.register_mux_command(
            cmd="PN_CONSOLE",
            key="NAME",
            value=self.name,
            func=self.cmd_PN_CONSOLE,
            desc="Manually step PN532 I2C init/read transactions")

        logging.info("PN_CONSOLE: registered '%s' with manual-only I2C",
                     self.name)

    def _respond(self, gcmd, message):
        gcmd.respond_info("PN_CONSOLE[%s]: %s" % (self.name, message))

    def _next(self, gcmd, command):
        self._respond(gcmd, "NEXT: %s" % command)

    def _build_command_frame(self, cmd_and_params):
        if not isinstance(cmd_and_params, list):
            cmd_and_params = [cmd_and_params]

        data = [PN532_HOSTTOPN532] + list(cmd_and_params)
        length = len(data)
        frame = [
            PN532_PREAMBLE,
            PN532_STARTCODE1,
            PN532_STARTCODE2,
            length,
            ((~length + 1) & 0xFF),
        ] + data
        checksum = ((~sum(data) + 1) & 0xFF)
        frame += [checksum, PN532_POSTAMBLE]
        return frame

    def _write(self, gcmd, data, label):
        self._respond(gcmd, "%s WRITE before: %s" % (label, _hex(data)))
        logging.info("PN_CONSOLE[%s]: %s WRITE before: %s",
                     self.name, label, _hex(data))
        self.i2c.i2c_write(data)
        logging.info("PN_CONSOLE[%s]: %s WRITE after", self.name, label)
        self._respond(gcmd, "%s WRITE after: OK" % label)

    def _read(self, gcmd, length, label):
        self._respond(gcmd, "%s READ before: %d byte(s)" % (label, length))
        logging.info("PN_CONSOLE[%s]: %s READ before: %d byte(s)",
                     self.name, label, length)
        response = self.i2c.i2c_read([], length)
        data = list(response.get("response", []))
        logging.info("PN_CONSOLE[%s]: %s READ after: %s",
                     self.name, label, _hex(data))
        self._respond(gcmd, "%s READ after: %s" % (label, _hex(data)))
        return data

    def _ready_step(self, gcmd):
        data = self._read(gcmd, 1, "READY")
        if not data:
            self._respond(gcmd, "READY result: no bytes returned")
            return
        status = data[0]
        if status == PN532_I2C_READY:
            self._respond(gcmd, "READY result: ready (0x01)")
        elif status == PN532_I2C_BUSY:
            self._respond(gcmd, "READY result: busy (0x00)")
        else:
            self._respond(gcmd, "READY result: unknown status 0x%02X" % status)

    def _ack_read_step(self, gcmd):
        ready = self._read(gcmd, 1, "ACK_READY")
        if not ready:
            self._respond(gcmd, "ACK_READY result: no bytes returned")
            return
        if ready[0] != PN532_I2C_READY:
            self._respond(gcmd, "ACK_READY result: busy/unknown 0x%02X; not reading ACK yet" %
                          ready[0])
            self._next(gcmd, "PN_CONSOLE NAME=%s STEP=%s" %
                       (self.name, gcmd.get("STEP", "FIRMWARE_ACK").upper()))
            return

        length = gcmd.get_int("LEN", 7, minval=1, maxval=7)
        data = self._read(gcmd, length, "ACK")
        if not data:
            self._respond(gcmd, "ACK result: no bytes returned")
            return
        if length < 7:
            self._respond(gcmd, "ACK probe only: read %d byte(s), raw=%s" %
                          (length, _hex(data)))
            self._respond(gcmd, "Try the same ACK step with LEN=%d next" %
                          min(length + 1, 7))
            return
        status = data[0]
        ack = data[1:]
        self._respond(gcmd, "ACK status byte: 0x%02X" % status)
        self._respond(gcmd, "ACK frame: %s" % _hex(ack))
        if ack == PN532_ACK:
            self._respond(gcmd, "ACK result: valid PN532 ACK")
        else:
            self._respond(gcmd, "ACK result: invalid, expected %s" %
                          _hex(PN532_ACK))

    def _firmware_response_step(self, gcmd):
        data = self._read(gcmd, 14, "FIRMWARE_RESPONSE")
        if len(data) < 12:
            self._respond(gcmd, "Firmware response too short")
            return
        status = data[0]
        frame = data[1:]
        self._respond(gcmd, "Firmware status byte: 0x%02X" % status)
        if (len(frame) >= 11 and frame[0] == 0x00 and frame[1] == 0x00 and
                frame[2] == 0xFF and frame[5] == PN532_PN532TOHOST and
                frame[6] == 0x03):
            ic = frame[7]
            ver = frame[8]
            rev = frame[9]
            support = frame[10]
            self._respond(
                gcmd,
                "Firmware parsed: v%d.%d IC=0x%02X support=0x%02X" %
                (ver, rev, ic, support))
        else:
            self._respond(gcmd, "Firmware response did not match expected PN532 frame")

    def _firmware_ack_direct_step(self, gcmd):
        frame = self._build_command_frame([PN532_COMMAND_GETFIRMWAREVERSION])
        delay = gcmd.get_float("DELAY", 0.050, minval=0.0, maxval=2.0)
        self._write(gcmd, frame, "FIRMWARE_DIRECT")
        self._respond(gcmd, "FIRMWARE_DIRECT waiting %.3f seconds before ACK read" %
                      delay)
        time.sleep(delay)
        data = self._read(gcmd, 7, "FIRMWARE_DIRECT_ACK")
        if not data:
            self._respond(gcmd, "FIRMWARE_DIRECT_ACK result: no bytes returned")
            return
        status = data[0]
        ack = data[1:]
        self._respond(gcmd, "FIRMWARE_DIRECT_ACK status byte: 0x%02X" % status)
        self._respond(gcmd, "FIRMWARE_DIRECT_ACK frame: %s" % _hex(ack))
        if ack == PN532_ACK:
            self._respond(gcmd, "FIRMWARE_DIRECT_ACK result: valid PN532 ACK")
            self._next(gcmd, "PN_CONSOLE NAME=%s STEP=FIRMWARE_READY" %
                       self.name)
        else:
            self._respond(gcmd, "FIRMWARE_DIRECT_ACK result: invalid, expected %s" %
                          _hex(PN532_ACK))

    def _sam_response_step(self, gcmd):
        data = self._read(gcmd, 9, "SAM_RESPONSE")
        if len(data) < 8:
            self._respond(gcmd, "SAM response too short")
            return
        status = data[0]
        frame = data[1:]
        self._respond(gcmd, "SAM status byte: 0x%02X" % status)
        if (len(frame) >= 8 and frame[0] == 0x00 and frame[1] == 0x00 and
                frame[2] == 0xFF and frame[5] == PN532_PN532TOHOST and
                frame[6] == 0x15):
            self._respond(gcmd, "SAM response parsed: OK")
        else:
            self._respond(gcmd, "SAM response did not match expected PN532 frame")

    def _passive_response_step(self, gcmd):
        length = gcmd.get_int("LEN", 30, minval=1, maxval=64)
        data = self._read(gcmd, length, "PASSIVE_RESPONSE")
        if not data:
            self._respond(gcmd, "Passive response: no bytes returned")
            return
        self._respond(gcmd, "Passive response raw includes leading I2C status byte")

    def _help(self, gcmd):
        lines = [
            "Manual PN532 init sequence. Run one command at a time.",
            "1. PN_CONSOLE NAME=%s STEP=WAKEUP" % self.name,
            "2. PN_CONSOLE NAME=%s STEP=READY" % self.name,
            "3. PN_CONSOLE NAME=%s STEP=FIRMWARE_WRITE" % self.name,
            "4. PN_CONSOLE NAME=%s STEP=FIRMWARE_ACK" % self.name,
            "5. PN_CONSOLE NAME=%s STEP=FIRMWARE_READY" % self.name,
            "6. PN_CONSOLE NAME=%s STEP=FIRMWARE_RESPONSE" % self.name,
            "Direct ACK probe:",
            "PN_CONSOLE NAME=%s STEP=FIRMWARE_ACK_DIRECT DELAY=0.050" % self.name,
            "7. PN_CONSOLE NAME=%s STEP=SAM_WRITE" % self.name,
            "8. PN_CONSOLE NAME=%s STEP=SAM_ACK" % self.name,
            "9. PN_CONSOLE NAME=%s STEP=SAM_READY" % self.name,
            "10. PN_CONSOLE NAME=%s STEP=SAM_RESPONSE" % self.name,
            "Optional tag detect:",
            "11. PN_CONSOLE NAME=%s STEP=PASSIVE_WRITE" % self.name,
            "12. PN_CONSOLE NAME=%s STEP=PASSIVE_ACK" % self.name,
            "13. PN_CONSOLE NAME=%s STEP=PASSIVE_READY" % self.name,
            "14. PN_CONSOLE NAME=%s STEP=PASSIVE_RESPONSE LEN=30" % self.name,
            "Raw tools:",
            "PN_CONSOLE NAME=%s RAW_READ=1 LEN=1" % self.name,
            "PN_CONSOLE NAME=%s RAW_WRITE=00" % self.name,
        ]
        gcmd.respond_info("\n".join(lines))

    def cmd_PN_CONSOLE(self, gcmd):
        if gcmd.get_int("HELP", 0):
            self._help(gcmd)
            return

        raw_write = gcmd.get("RAW_WRITE", None)
        if raw_write is not None:
            data = _parse_hex_bytes(raw_write)
            self._write(gcmd, data, "RAW")
            self._next(gcmd, "PN_CONSOLE NAME=%s RAW_READ=1 LEN=1" %
                       self.name)
            return

        if gcmd.get_int("RAW_READ", 0):
            length = gcmd.get_int("LEN", 1, minval=1, maxval=64)
            self._read(gcmd, length, "RAW")
            return

        step = gcmd.get("STEP", "HELP").upper()
        try:
            if step == "HELP":
                self._help(gcmd)
            elif step == "WAKEUP":
                self._write(gcmd, [0x00], "WAKEUP")
                time.sleep(0.05)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=READY" %
                           self.name)
            elif step == "READY":
                self._ready_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=FIRMWARE_WRITE" %
                           self.name)
            elif step == "FIRMWARE_WRITE":
                frame = self._build_command_frame(
                    [PN532_COMMAND_GETFIRMWAREVERSION])
                self._write(gcmd, frame, "FIRMWARE")
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=FIRMWARE_ACK" %
                           self.name)
            elif step == "FIRMWARE_ACK":
                self._ack_read_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=FIRMWARE_READY" %
                           self.name)
            elif step == "FIRMWARE_READY":
                self._ready_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=FIRMWARE_RESPONSE" %
                           self.name)
            elif step == "FIRMWARE_RESPONSE":
                self._firmware_response_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=SAM_WRITE" %
                           self.name)
            elif step == "FIRMWARE_ACK_DIRECT":
                self._firmware_ack_direct_step(gcmd)
            elif step == "SAM_WRITE":
                frame = self._build_command_frame(
                    [PN532_COMMAND_SAMCONFIGURATION, 0x01, 0x14, 0x01])
                self._write(gcmd, frame, "SAM")
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=SAM_ACK" %
                           self.name)
            elif step == "SAM_ACK":
                self._ack_read_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=SAM_READY" %
                           self.name)
            elif step == "SAM_READY":
                self._ready_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=SAM_RESPONSE" %
                           self.name)
            elif step == "SAM_RESPONSE":
                self._sam_response_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=PASSIVE_WRITE" %
                           self.name)
            elif step == "PASSIVE_WRITE":
                frame = self._build_command_frame(
                    [PN532_COMMAND_INLISTPASSIVETARGET, 0x01, 0x00])
                self._write(gcmd, frame, "PASSIVE")
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=PASSIVE_ACK" %
                           self.name)
            elif step == "PASSIVE_ACK":
                self._ack_read_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=PASSIVE_READY" %
                           self.name)
            elif step == "PASSIVE_READY":
                self._ready_step(gcmd)
                self._next(gcmd, "PN_CONSOLE NAME=%s STEP=PASSIVE_RESPONSE LEN=30" %
                           self.name)
            elif step == "PASSIVE_RESPONSE":
                self._passive_response_step(gcmd)
            else:
                self._respond(gcmd, "Unknown STEP=%s" % step)
                self._help(gcmd)
        except Exception as e:
            logging.exception("PN_CONSOLE[%s]: step %s failed",
                              self.name, step)
            self._respond(gcmd, "STEP %s failed: %s" % (step, e))
            self._respond(gcmd, "If Klipper shut down, the failed line above is the transaction to inspect.")


def load_config_prefix(config):
    return PN532Console(config)
