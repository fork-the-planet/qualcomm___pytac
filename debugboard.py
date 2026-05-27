# Copyright (c)i 2025-2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

import json
import logging
import os
import re
import sys
from time import sleep
from types import MethodType

import hid
import pyudev
import serial
import usb
from pexpect import fdpexpect
from pyftdi.gpio import GpioAsyncController

logger = logging.getLogger()

# wait time for other GPIOs to be truly set before touching the reset GPIO
PRE_RESET_DELAY = 0.1

BITMODE_CBUS = 0x20

# USB ctrl transfer request for FT230X CBUS
SIO_SET_BITMODE_REQUEST = 0x0B


class TACException(Exception):
    status_code = 420
    detail = "Unable to perform requested operation"


class Board(dict):
    ID_VENDOR_FTDI = 0x0403
    ID_PRODUCT_FTDI = 0x6011
    ID_VENDOR_QCOM = 0x05C6
    ID_PRODUCT_QCOM = 0x9302
    ID_PRODUCT_BUGHOPPER_V1 = 0x6015
    ID_VENDOR_BUGHOPPER_V2 = 0x2341
    ID_PRODUCT_BUGHOPPER_V2 = 0xB001

    @classmethod
    def create_from_config(cls, config_file_path):
        return DummyBoard(config_file_path)

    @classmethod
    def create_board(cls, serial, tac_config_path):
        device = usb.core.find(serial_number=serial)
        if device:
            if (
                device.idVendor == Board.ID_VENDOR_FTDI
                and device.idProduct == Board.ID_PRODUCT_BUGHOPPER_V1
            ):
                logger.debug("Found Bughopper V1")
                return BughopperV1Board(device)
            if (
                device.idProduct == Board.ID_PRODUCT_FTDI
                and device.idVendor == Board.ID_VENDOR_FTDI
            ):
                logger.debug("Found FTDI Board")
                return FtdiBoard(device, tac_config_path)
            if (
                device.idProduct == Board.ID_PRODUCT_QCOM
                and device.idVendor == Board.ID_VENDOR_QCOM
            ):
                logger.debug("Found Psoc Board")
                return PsocBoard(device, tac_config_path)
            if (
                device.idVendor == Board.ID_VENDOR_BUGHOPPER_V2
                and device.idProduct == Board.ID_PRODUCT_BUGHOPPER_V2
            ):
                logger.debug("Found Bughopper V2")
                return BughopperV2Board(device)

    def __init__(self):
        self.ports = {}
        self.pins = {}
        self.commands = {}
        self.quick_methods = {}
        self.usb_device = None
        dict.__init__(
            self, ports=self.ports, pins=self.pins, quick_methods=self.quick_methods
        )

    def logComment(self, comment):
        print(comment)

    def delay(self, length):
        d = float(length / 1000)
        self.logComment(f"Sleeping for {d} seconds")
        sleep(d)

    def create_pins(self):
        raise NotImplementedError()

    def create_ports(self):
        raise NotImplementedError()

    def parse_script(self):
        if self.full_config:
            initial_script = self.full_config["script"]
            new_script = initial_script
            # replace variables with actual values
            variables = self.full_config.get("variables", [])
            for variable in variables:
                # create global variables
                var_name = variable.get("name")
                if var_name:
                    var_re = re.compile(rf"\${var_name}")
                    new_script = var_re.sub(variable["default_value"], new_script)

            # remove commented lines
            fix_comments = re.compile(r"\/\/.*")
            new_script = fix_comments.sub("\r", new_script)
            fix_comments = re.compile(r"\/\/.*\r")
            new_script = fix_comments.sub("\r", new_script)

            # fix function definitions
            fix_functions = re.compile(r"\(\)[\s]?", re.MULTILINE)
            new_script = fix_functions.sub("(self):\n", new_script)
            fix_functions2 = re.compile(r"\(\)[\s]?\r", re.MULTILINE)
            new_script = fix_functions2.sub("(self):\r", new_script)

            # add brackets to function calls
            fix_no_parenthesis = re.compile(
                r"([A-Za-z0-9_]+)\s([0-9]+)\s?", re.MULTILINE
            )
            new_script = fix_no_parenthesis.sub(r"self.\1(\2)\n", new_script)

            # fixes syntax of internal function calls
            fix_no_parenthesis_func = re.compile(r"\t([A-Za-z0-9_]+)$", re.MULTILINE)
            new_script = fix_no_parenthesis_func.sub(r"\tself.\1()", new_script)

            fix_no_parenthesis_empty = re.compile(
                r"self.([A-Za-z0-9_]+)\s?$", re.MULTILINE
            )
            new_script = fix_no_parenthesis_empty.sub(r"self.\1()", new_script)

            fix_log_comment = re.compile(
                r"logComment\s([a-zA-Z0-9=_\ ]+)\s?$", re.MULTILINE
            )
            new_script = fix_log_comment.sub(r'self.logComment("\1")', new_script)

            d = {}
            # nosemgrep: python.lang.security.audit.exec-detected.exec-detected
            exec(new_script, d)  # pylint: disable=exec-used

            # create ports
            self.create_ports()

            # create pins
            self.create_pins()

            for name, value in d:
                if not name.startswith("__"):
                    logger.debug(f"Adding {name}")
                    self.quick_methods.update({name: QuickMethod(self, name)})
                    method = MethodType(value, self)
                    setattr(self, name, method)


class DummyBoard(Board):
    def __init__(self, config_path):
        Board.__init__(self)
        self.config_path = config_path
        self.usb_device = lambda: None
        self.usb_device.serial_number = "123456"
        with open(self.config_path) as cf:
            self.full_config = json.loads(cf.read())
        self.parse_script()

    def create_ports(self):
        logger.debug("creating ports")
        if "FTDI" in self.config_path:
            for p in self.full_config.get("bus"):
                bus_name = p.get("bus")
                if p.get("bus_function") == 2:
                    self.ports.update({bus_name: DummyPort(bus_name, "123456")})

        if "PSOC" in self.config_path:
            self.ports.update({0: DummyPort("123456", None)})

    def create_pins(self):
        logger.debug("creating pins")
        for config in self.full_config.get("pins"):
            pin = DummyPin(self, config)
            pin.setPort(self.ports.get(0))
            logger.debug(f"Adding {pin.command}")
            self.pins.update({f"{pin.pin_number}": pin})
            self.commands.update({f"{pin.command}": f"{pin.command}"})
            setattr(self, pin.command, pin.set)


class BughopperV1Board(Board):
    def __init__(self, usb_device):
        Board.__init__(self)
        self.usb_device = usb_device
        self.quick_methods.update({"powerOn": QuickMethod(self, "powerOn")})
        self.quick_methods.update({"bootToEDL": QuickMethod(self, "bootToEDL")})
        self.quick_methods.update({"powerOff": QuickMethod(self, "powerOff")})
        self.quick_methods.update({"reset": QuickMethod(self, "reset")})
        self.quick_methods.update(
            {"forceUsbcHostMode": QuickMethod(self, "forceUsbcHostMode")}
        )

        self.EDL_BIT = 0b00000001
        self.POWER_DISABLE_BIT = 0b00000100
        self.VOL_DOWN_BIT = 0b00001000

        self.EDL_MASK = self.EDL_BIT << 4
        self.POWER_DISABLE_MASK = self.POWER_DISABLE_BIT << 4
        self.VOL_DOWN_MASK = self.VOL_DOWN_BIT << 4

    def _ftdi_set_bitmode(self, bitmask):
        bmRequestType = usb.util.build_request_type(
            usb.util.CTRL_OUT, usb.util.CTRL_TYPE_VENDOR, usb.util.CTRL_RECIPIENT_DEVICE
        )

        wValue = bitmask | (BITMODE_CBUS << 8)
        self.usb_device.ctrl_transfer(bmRequestType, SIO_SET_BITMODE_REQUEST, wValue)

    def powerOn(self):
        logger.debug("Power cycle to normal boot mode")
        self._ftdi_set_bitmode(self.POWER_DISABLE_MASK | self.POWER_DISABLE_BIT)
        sleep(PRE_RESET_DELAY)
        self._ftdi_set_bitmode(
            self.POWER_DISABLE_MASK | self.EDL_MASK | self.VOL_DOWN_MASK
        )

    def bootToEDL(self):
        logger.debug("Power cycle to USB boot mode")
        self._ftdi_set_bitmode(self.POWER_DISABLE_MASK | self.POWER_DISABLE_BIT)
        sleep(PRE_RESET_DELAY)
        self._ftdi_set_bitmode(self.POWER_DISABLE_MASK | self.EDL_MASK | self.EDL_BIT)

    def reset(self):
        logger.debug("MPU reset pulse")
        self._ftdi_set_bitmode(self.POWER_DISABLE_MASK | self.POWER_DISABLE_BIT)
        sleep(PRE_RESET_DELAY)
        self._ftdi_set_bitmode(
            self.POWER_DISABLE_MASK | self.EDL_MASK | self.VOL_DOWN_MASK
        )

    def powerOff(self):
        logger.debug("MPU poweroff")
        self._ftdi_set_bitmode(self.POWER_DISABLE_MASK | self.POWER_DISABLE_BIT)

    def forceUsbcHostMode(self):
        logger.debug("Forcing host mode")
        self._ftdi_set_bitmode(
            self.POWER_DISABLE_MASK
            | self.VOL_DOWN_MASK
            | self.POWER_DISABLE_BIT
            | self.VOL_DOWN_BIT
        )
        sleep(PRE_RESET_DELAY)
        self._ftdi_set_bitmode(
            self.POWER_DISABLE_MASK
            | self.EDL_MASK
            | self.VOL_DOWN_MASK
            | self.VOL_DOWN_BIT
        )


class BughopperV2Board(Board):
    def __init__(self, usb_device):
        Board.__init__(self)
        self.usb_device = hid.Device(usb_device.idVendor, usb_device.idProduct)
        self.usb_device.serial_number = self.usb_device.serial
        self.quick_methods.update({"powerOn": QuickMethod(self, "powerOn")})
        self.quick_methods.update({"bootToEDL": QuickMethod(self, "bootToEDL")})
        self.quick_methods.update({"powerOff": QuickMethod(self, "powerOff")})
        self.quick_methods.update({"reset": QuickMethod(self, "reset")})
        self.quick_methods.update(
            {"forceUsbcHostMode": QuickMethod(self, "forceUsbcHostMode")}
        )

        self.CMD_GPIO = 0x1

        self.EDL_BIT = 0x1
        self.POWER_DISABLE_BIT = 0x4
        self.VOL_DOWN_BIT = 0x8

    def _hid_set_bitmode(self, command, gpio_value, mask=0xF):
        self.usb_device.write(bytes([command, gpio_value, mask]))

    def powerOn(self):
        logger.debug("Power cycle to normal boot mode")
        self._hid_set_bitmode(
            self.CMD_GPIO, self.POWER_DISABLE_BIT, self.POWER_DISABLE_BIT
        )
        sleep(PRE_RESET_DELAY)
        self._hid_set_bitmode(
            self.CMD_GPIO,
            0x0,
            self.POWER_DISABLE_BIT | self.EDL_BIT | self.VOL_DOWN_BIT,
        )

    def bootToEDL(self):
        logger.debug("Power cycle to USB boot mode")
        self._hid_set_bitmode(
            self.CMD_GPIO, self.POWER_DISABLE_BIT, self.POWER_DISABLE_BIT
        )
        sleep(PRE_RESET_DELAY)
        self._hid_set_bitmode(
            self.CMD_GPIO, self.EDL_BIT, self.EDL_BIT | self.POWER_DISABLE_BIT
        )

    def reset(self):
        logger.debug("MPU reset pulse")
        self._hid_set_bitmode(
            self.CMD_GPIO, self.POWER_DISABLE_BIT, self.POWER_DISABLE_BIT
        )
        sleep(PRE_RESET_DELAY)
        self._hid_set_bitmode(
            self.CMD_GPIO,
            0x0,
            self.POWER_DISABLE_BIT | self.EDL_BIT | self.VOL_DOWN_BIT,
        )

    def powerOff(self):
        logger.debug("MPU poweroff")
        self._hid_set_bitmode(
            self.CMD_GPIO, self.POWER_DISABLE_BIT, self.POWER_DISABLE_BIT
        )

    def forceUsbcHostMode(self):
        logger.debug("Forcing host mode")
        self._hid_set_bitmode(
            self.CMD_GPIO,
            self.POWER_DISABLE_BIT | self.VOL_DOWN_BIT,
            self.POWER_DISABLE_BIT | self.VOL_DOWN_BIT,
        )
        sleep(PRE_RESET_DELAY)
        self._hid_set_bitmode(
            self.CMD_GPIO,
            self.VOL_DOWN_BIT,
            self.POWER_DISABLE_BIT | self.VOL_DOWN_BIT | self.EDL_BIT,
        )


class FtdiBoard(Board):
    def __init__(self, usb_device, tac_config_path):
        Board.__init__(self)
        self.usb_device = usb_device
        conf = os.path.join(
            tac_config_path, "TAC_FTDI_13.tcnf"
        )  # default config for FTDI Alpaca-lite
        f = open(os.path.join(tac_config_path, "devicelist.json"), "r")
        device_list = json.loads(f.read())
        f.close()
        catalog = device_list.get("catalog")
        conf_dict = next(
            (x for x in catalog if x.get("usb_descriptor") == self.usb_device.product),
            None,
        )
        if conf_dict:
            conf = os.path.join(
                tac_config_path, os.path.basename(conf_dict.get("configPath"))
            )

        if conf is None:
            logger.error("No matching FTDI config found")
            sys.exit(1)

        f = open(conf, "rb")
        self.full_config = json.loads(f.read())
        f.close()
        self.parse_script()

    def create_ports(self):
        for p in self.full_config.get("bus"):
            bus_name = p.get("bus")
            if p.get("bus_function") == 2:
                self.ports.update(
                    {bus_name: FtdiPort(bus_name, self.usb_device.serial_number)}
                )

    def create_pins(self):
        for p in self.full_config.get("pins"):
            if not p.get("enabled", True):
                continue
            pin = FtdiPin(self, p)
            pin.setPort(self.ports.get(pin.bus))
            logger.debug(f"Adding {pin.command}")
            self.pins.update({f"{pin.bus}{pin.pin_number}": pin})
            self.commands.update({f"{pin.command}": f"{pin.command}"})
            setattr(self, pin.command, pin.set)


class PsocBoard(Board):
    def __init__(self, usb_device, tac_config_path):
        Board.__init__(self)
        self.usb_device = usb_device
        conf = None
        f = open(os.path.join(tac_config_path, "devicelist.json"), "r")
        device_list = json.loads(f.read())
        f.close()
        catalog = device_list.get("catalog")
        self.board_id = self.__get_board_id()
        conf_dict = next(
            (x for x in catalog if x.get("platform_id") == self.board_id), None
        )
        if conf_dict:
            conf = os.path.join(
                tac_config_path, os.path.basename(conf_dict.get("configPath"))
            )

        if conf is None:
            logger.error("No matching PSOC config found")
            sys.exit(1)

        f = open(conf, "rb")
        self.full_config = json.loads(f.read())
        f.close()
        self.parse_script()
        self.quick_methods.update({"devicePowerOn": QuickMethod(self, "devicePowerOn")})
        self.quick_methods.update(
            {"devicePowerOff": QuickMethod(self, "devicePowerOff")}
        )
        self.quick_methods.update(
            {"usbDevicePowerOn": QuickMethod(self, "usbDevicePowerOn")}
        )
        self.quick_methods.update(
            {"usbDevicePowerOff": QuickMethod(self, "usbDevicePowerOff")}
        )

    def devicePower(self, value):
        logger.debug(f"Calling devicePower {value}")
        if value:
            self.ports[0].call_method("devicePower", "on")
        else:
            self.ports[0].call_method("devicePower", "off")

    def usbDevicePower(self, value):
        logger.debug(f"Calling usbDevicePower {value}")
        if value:
            self.ports[0].call_method("usbDevicePower", "on")
        else:
            self.ports[0].call_method("usbDevicePower", "off")

    def devicePowerOn(self):
        self.devicePower(True)

    def devicePowerOff(self):
        self.devicePower(False)

    def usbDevicePowerOn(self):
        self.usbDevicePower(True)

    def usbDevicePowerOff(self):
        self.usbDevicePower(False)

    def __get_board_id(self):
        # connect to serial and call "getboardid"
        serial_port = None
        context = pyudev.Context()
        for d in context.list_devices(ID_SERIAL_SHORT=self.usb_device.serial_number):
            for l in d.device_links:
                serial_port = l
                break

        logger.info(f"Opening {serial_port}")
        expect_connection = None

        connection = serial.Serial()
        connection.baudrate = 115200
        connection.port = serial_port
        try:
            connection.open()
        except serial.SerialException as e:
            logger.error("Serial Exception")
            logger.error(e)
            sys.exit(1)
        expect_connection = fdpexpect.fdspawn(connection)
        if not expect_connection.isalive():
            logger.error("Expect connection not created")
            sys.exit(1)

        expect_connection.send("\r")
        expect_connection.expect("CMD")
        expect_connection.send("getboardid\r")
        expect_connection.expect("ok")
        ret_value = expect_connection.before
        expect_connection.close()
        # find returned value
        r = re.search(r"\d+", ret_value.decode())
        if r:
            return int(r.group(0))
        return None

    def create_ports(self):
        self.ports.update({0: PsocPort(self.usb_device.serial_number)})

    def create_pins(self):
        for config in self.full_config.get("pins"):
            if not config.get("enabled", True):
                continue
            pin = PsocPin(self, config)
            pin.setPort(self.ports.get(0))
            logger.debug(f"Adding {pin.command}")
            self.pins.update({f"{pin.pin_number}": pin})
            self.commands.update({f"{pin.command}": f"{pin.command}"})
            setattr(self, pin.command, pin.set)


class QuickMethod(dict):
    def __init__(self, board, name):
        self.name = name
        self.board = board
        dict.__init__(self, name=self.name, board=self.board.usb_device.serial_number)

    def call(self):
        try:
            getattr(self.board, self.name)()
        except Exception as e:
            logger.error(e)
            raise TACException
        return {}


class Pin(dict):
    def __init__(self, board, config):
        self.board = board
        self.bus = config.get("bus")
        self.command = config.get("command")
        self.initial_value = config.get("initial_value")
        self.value = self.initial_value
        self.input = config.get("input")
        self.inverted = config.get("inverted")
        self.pin_number = int(config.get("pin_number"))
        self.help_hint = config.get("help_hint")
        self.port = None
        dict.__init__(
            self,
            bus=self.bus,
            command=self.command,
            initial_value=self.initial_value,
            value=self.value,
            input=self.input,
            inverted=self.inverted,
            pin_number=self.pin_number,
            help_hint=self.help_hint,
            port=self.port,
        )

    def set(self, value):
        self.value = value
        super().__setitem__("value", self.value)

    def initialize(self):
        raise NotImplementedError()

    def setPort(self, port):
        self.port = port
        super().__setitem__("port", self.port)


class DummyPin(Pin):
    def initialize(self):
        logger.info(f"Initializing pin: {self.bus} {self.pin_number}")


class FtdiPin(Pin):
    def __init__(self, board, config):
        Pin.__init__(self, board, config)
        self.pin_number_mask = 1 << self.pin_number

    def set(self, value):
        super().set(value)
        if not self.port:
            logger.warning(f"No port set for pin {self.bus}{self.pin_number}")
            return
        logger.debug(f"Port {self.bus} status: 0x{self.port.status:02X}")
        logger.debug(f"Setting {self.bus}{self.pin_number} to {value}")
        logger.debug(f"Mask: 0x{self.pin_number_mask:02X}")
        if self.value:
            self.port.write(self.port.status | self.pin_number_mask)
        else:
            self.port.write(self.port.status & ~self.pin_number_mask)

    def initialize(self):
        self.set(int(self.initial_value))

    def setPort(self, port):
        super().setPort(port)
        self.initialize()


class PsocPin(Pin):
    def __init__(self, board, config):
        Pin.__init__(self, board, config)

    def set(self, value):
        lcl_value = None
        try:
            lcl_value = int(value)
        except ValueError:
            logger.error("Value has to be int")
            logger.error(f"Received {value}")
            return
        super().set(lcl_value)
        if not self.port:
            logger.warning(f"No port set for pin {self.pin_number}")
            return
        logger.debug(f"Setting {self.pin_number} to {lcl_value}")
        self.port.write(lcl_value, self.pin_number)

    def initialize(self):
        self.set(int(self.initial_value))

    def setPort(self, port):
        super().setPort(port)
        self.initialize()


class Port(dict):
    def __init__(self, bus, serial):
        self.serial = serial
        self.bus = bus
        dict.__init__(self, serial=self.serial, bus=self.bus)

    def write(self, value, pin=None):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()


class DummyPort(Port):
    def write(self, value, pin=None):
        logger.info(f"Writing to port {self.bus} {self.serial}")

    def close(self):
        logger.info(f"Closing port {self.bus}")


class PsocPort(Port):
    def __init__(self, serialid):
        Port.__init__(self, None, serialid)
        self.serial_port = None
        context = pyudev.Context()
        for d in context.list_devices(ID_SERIAL_SHORT=serialid):
            for l in d.device_links:
                self.serial_port = l
                break

        self.expect_connection = None

        self.connection = serial.Serial()
        self.connection.baudrate = 115200
        self.connection.port = self.serial_port
        try:
            self.connection.open()
        except serial.SerialException as e:
            logger.error("Serial Exception")
            logger.error(e)
            sys.exit(1)
        self.expect_connection = fdpexpect.fdspawn(self.connection)
        if not self.expect_connection.isalive():
            logger.error("Expect connection not created")
            sys.exit(1)

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()

    def call_method(self, method, value):
        logger.debug(f"Calling {method} {value}")
        if self.expect_connection and self.expect_connection.isalive():
            self.expect_connection.send("\r")
            self.expect_connection.expect("CMD")
            message = f"{method} {value}\r"

            self.expect_connection.send(message)
            self.expect_connection.expect("ok")
        else:
            logger.error("No expect connection")
            sys.exit(1)

    def write(self, value, pin=None):
        if not pin:
            logger.warning("No pin selected")
            return
        if self.expect_connection and self.expect_connection.isalive():
            self.expect_connection.send("\r")
            self.expect_connection.expect("CMD")
            message = f"pin {value} {pin}\r"

            self.expect_connection.send(message)
            self.expect_connection.expect("ok")
        else:
            logger.error("No expect connection")
            sys.exit(1)


class FtdiPort(Port):
    def __init__(self, bus, serial, direction=0xFF):
        Port.__init__(self, bus, serial)
        self.direction = direction
        self.port = ord(self.bus) - ord("A") + 1
        self.url = f"ftdi://::{self.serial}/{self.port}"
        self.pins = {}
        self.status = 0x0
        self.gpio = GpioAsyncController()
        self.gpio.configure(self.url, direction=self.direction)

    def write(self, value, pin=None):
        self.status = value
        logger.debug(f"Port {self.bus} value: 0x{self.status:02X}")
        self.gpio.write(self.status)

    def close(self):
        logger.debug(f"Closing port {self.bus}")
        self.gpio.close()
