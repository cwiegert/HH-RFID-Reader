import logging

class NFCReader:
    """Klipper plugin for NFC reader"""
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name().split()[1]

        reader = self.printer.load_object(config, "nfc_reader", self.name)

        from . import bus
        self.i2c = bus.MCU_I2C_from_config(
        config, default_addr=PN532_I2C_ADDRESS, default_speed=100000)
        
        reader_type = config.get("reader_type", None)
        if reader_type is not None: reader_type = reader_type.lower()

        match reader_type:
            case "pn532":
                self.reader = PN532(self, config)
            case None:
                raise config.error("Missing 'reader_type' (e.g., PN532)")

PN532_I2C_ADDRESS = 0x24  # 0x48 >> 1
PN532_I2C_READY = 0x01
PN532_I2C_BUSY = 0x00

class PN532:
     def __init__(self, reader, config):
        self.i2c = reader.i2c
        #self.irq_state = False

        if self.i2c is None:
            raise config.error("PN532 requires I2C bus configuration")
        data_ready_pin = config.get("data_ready_pin", None)
        
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
        
def load_config_prefix(config):
    return NFCReader(config)