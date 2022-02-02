"""Control lifx lights with LAN Sockets"""
from __future__ import annotations

import logging
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict

from gpiozero import MotionSensor

from packet_builder import MSGHEADER, Packet, deconstruct

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

CONSOLE_FORMAT = logging.Formatter('[%(levelname)s]: %(message)s', "%H:%M:%S")
logconsole = logging.StreamHandler()
logconsole.setFormatter(CONSOLE_FORMAT)
logconsole.setLevel(logging.DEBUG)
log.addHandler(logconsole)

FILE_FORMAT = logging.Formatter('[%(asctime)s] [%(levelname)s]: %(message)s', "%H:%M:%S")
logfile = logging.FileHandler(f"log/lifx {datetime.now().strftime('%Y-%m-%d')}.log", "a")
logfile.setFormatter(FILE_FORMAT)
logfile.setLevel(logging.INFO)
log.addHandler(logfile)


def uncaught_handler(exception_type, value, traceback):
    """Log uncaught exceptions. To file and console."""
    log.exception(
        "Uncaught exception: %s: %s",
        value.__class__.__name__,
        value,
        exc_info=(
            exception_type,
            value,
            traceback))


# Log uncaught exceptions to file & stdout
sys.excepthook = uncaught_handler


class Device(Enum):
    """Devices enumerator"""
    # Name = (IP, PORT)
    Taklampa = ("192.168.1.99", 56700)
    LIFXZ = ("192.168.1.45", 56700)


def send_packet(device: Device, bytestring: Packet, silent: bool = False):
    """Send a packet to a device"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    sock.connect(device.value)
    if not silent:
        log.debug("Sending packet %d to %s...", bytestring.msgtype, device.name)
    size = sock.send(bytestring.bytearray())
    sock.close()
    return size


def send_recieve_packet(device: Device, bytestring: Packet, silent: bool = False):
    """Send a packet and return recieved response"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    sock.connect(device.value)
    if not silent:
        log.debug("Sending packet %d to %s...", bytestring.msgtype, device.name)
    sock.send(bytestring.bytearray())

    if not silent:
        log.debug("Recieveing response from device %s...", device.name)
    resp = sock.recv(0xff)
    sock.close()
    return resp


def get_state(device: Device, silent: bool = False) -> Dict[str, int]:
    """Get the light state of a device"""
    response = send_recieve_packet(device, Packet.get_state(), silent=silent)
    if not silent:
        log.debug("Receiving state...")
    decodemap = MSGHEADER + [
        ("hue", 16),
        ("saturation", 16),
        ("brightness", 16),
        ("kelvin", 16),
        ("reserved", 16),
        ("power", 16),
        ("label", 32),
        ("reserved", 64),
    ]
    result = deconstruct(response, decodemap)
    return dict(result)


class MotionHandler:
    """Handles triggers from a PIR"""
    dark = 0.01

    def __init__(self, pir: MotionSensor, delay: timedelta,
                 fadetime: timedelta):
        self.pir = pir
        self.delay = delay
        self.fadetime = fadetime
        self.last_state = {}
        self.is_active = True
        self.fading_timer = threading.Timer(self.fadetime.total_seconds(), self.fading_false)
        self.is_fading = False

        self.pir.when_activated = self.motion
        self.pir.when_deactivated = self.no_motion
        self.timer = threading.Timer(self.waittime, self.timeout)

    @property
    def waittime(self):
        """Returns seconds to wait for delay"""
        return self.delay.total_seconds()

    def fading_false(self):
        """Set `self.is_fading` to False"""
        self.is_fading = False

    def timeout(self):
        """Funciton triggered `delay` time after no motion"""
        try:
            self.is_active = False
            self.brightness(self.dark, self.fadetime.total_seconds())
            if self.fading_timer.is_alive():
                self.fading_timer.cancel()
            self.fading_timer = threading.Timer(self.fadetime.total_seconds(), self.fading_false)
            self.fading_timer.start()
            self.is_fading = True
            log.info("Timer executed!")
        except BaseException as err:
            log.exception("Uncaught exception in thread")
            raise err

    def motion(self):
        """Triggered when PIR senses motion"""
        if self.fading_timer.is_alive():
            self.fading_timer.cancel()
        if self.timer.is_alive():
            self.timer.cancel()
        if not self.is_active:
            last_brightness = self.last_state.get("brightness")
            self.brightness(last_brightness / 0xFFFF if last_brightness is not None else 1)
        log.info("Timer cancelled")
        self.is_active = True

    def no_motion(self):
        """Triggered when PIR senses no motion"""
        # self.brightness(0.5)
        log.info("Timer reset and started")
        if self.timer.is_alive():
            self.timer.cancel()
        self.timer = threading.Timer(self.waittime, self.timeout)
        self.timer.start()

    def brightness(self, level: float, duration: float = 0.1):
        """Set the light to given brightnes over duration in seconds"""
        state = self.last_state or get_state(Device.Taklampa)
        log.debug("Changing brightness to %.2f over %.2f seconds...", level, duration)
        send_packet(
            Device.Taklampa,
            Packet.state(
                state.get("hue", 0),
                state.get("saturation", 0),
                level * 0xFFFF,
                state.get("kelvin", 3500),
                duration
            ))


if __name__ == "__main__":
    args = dict(enumerate(sys.argv))
    # BCM Pin 17, Physical 11
    handler = MotionHandler(
        MotionSensor(17),
        timedelta(minutes=float(args.get(1, 5))),
        fadetime=timedelta(minutes=float(args.get(2, 5)))
    )

    while True:
        try:
            if handler.is_active or (not handler.is_active and not handler.is_fading):
                new_state = get_state(Device.Taklampa, silent=True)
                if new_state.get("brightness", 0) > (handler.dark * 10) * 0xFFFF \
                        and new_state.get("power") >= 0xFF00:
                    if new_state.get("brightness") != handler.last_state.get("brightness"):
                        log.debug(
                            "Setting last state to %s, %s",
                            new_state.get("brightness"),
                            new_state.get("power"))
                        handler.last_state = new_state
        except socket.timeout:
            log.error(
                "Socket timed out during ping to %s, retrying in 5 seconds",
                Device.Taklampa.value,
                exc_info=False)
        finally:
            time.sleep(5)
