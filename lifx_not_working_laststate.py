"""Control lifx lights with LAN Sockets"""
from __future__ import annotations
from functools import reduce

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

FORMAT = logging.Formatter('[%(asctime)s] [%(levelname)s]: %(message)s', "%H:%M:%S")
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

logconsole = logging.StreamHandler()
logconsole.setFormatter(FORMAT)
logconsole.setLevel(logging.DEBUG)
log.addHandler(logconsole)

logfile = logging.FileHandler(f"log/lifx {datetime.now().strftime('%Y-%m-%d')}.log", "a")
logfile.setFormatter(FORMAT)
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


sys.excepthook = uncaught_handler


class Device(Enum):
    """Devices enumerator"""
    # Name = (IP, PORT)
    Taklampa = ("192.168.1.99", 56700)
    LIFXZ = ("192.168.1.45", 56700)


def send_packet(device: Device, bytestring: Packet, silent: bool = False):
    """Send a packet to a device"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(device.value)
    if not silent:
        log.debug("Sending packet %d to %s...", bytestring.msgtype, device.name)
    size = sock.send(bytestring.bytearray())
    sock.close()
    return size


def send_recieve_packet(device: Device, bytestring: Packet, silent: bool = False):
    """Send a packet and return recieved response"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(device.value)
    if not silent:
        log.debug("Sending packet %d to %s...", bytestring.msgtype, device.name)
    sock.send(bytestring.bytearray())

    sock.setblocking(0)
    sock.settimeout(5.0)
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


# All on
# bytestring = b'\x2a\x00\x00\x34\xb4\x3c\xf0\x84\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x0d\x00\x00\x00\x00\x00\x00\x00\x00\x75\x00\x00\x00\xff\xff\xe8\x03\x00\x00'
# All off
# bytestring =
# b'\x2a\x00\x00\x34\xb4\x3c\xf0\x84\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x0b\x00\x00\x00\x00\x00\x00\x00\x00\x75\x00\x00\x00\x00\x00\xe8\x03\x00\x00'


class MotionHandler:
    """Handles triggers from a PIR"""
    dark = 0.01

    def __init__(self, pir: MotionSensor, delay: timedelta,
                 fadetime: timedelta):
        self.pir = pir
        self.delay = delay
        self.fadetime = fadetime
        self.last_state = {}

        self.pir.when_activated = self.motion
        self.pir.when_deactivated = self.no_motion
        self.timer = threading.Timer(self.waittime, self.timeout)

    @property
    def waittime(self):
        """Returns seconds to wait for delay"""
        return self.delay.total_seconds()

    def timeout(self):
        """Funciton triggered `delay` time after no motion"""
        self.brightness(self.dark, self.fadetime.total_seconds())
        log.info("Timer executed!")

    def motion(self):
        """Triggered when PIR senses motion"""
        if self.timer.is_alive():
            self.timer.cancel()
            last_brightness = self.last_state.get("brightness")
            self.brightness(last_brightness / 0xFFFF if last_brightness is not None else 1)
            log.info("Timer cancelled")

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
        state = get_state(Device.Taklampa)
        log.debug("Changing brightness to %.2f over %.2f seconds...", level, duration)
        send_packet(
            Device.Taklampa,
            Packet.state(
                state["hue"],
                state["saturation"],
                level * 0xFFFF,
                state["kelvin"],
                duration
            ))


if __name__ == "__main__":
    # BCM Pin 17, Physical 11
    handler = MotionHandler(MotionSensor(17), timedelta(minutes=1), fadetime=timedelta(seconds=5))
    state_queue = []

    try:
        while True:
            if len(state_queue) >= 3:
                state_queue.pop(0)
            state_queue.append(get_state(Device.Taklampa, silent=True))
            log.debug("State queue: %s",
                      [{"brightness": e.get("brightness"),
                        "power": e.get("power")} for e in state_queue])
            changing = False
            for prev, curr in zip(state_queue, state_queue[1:]):
                # log.debug("Prev: %d Curr: %d", prev.get("brightness"), curr.get("brightness"))
                # log.debug("Different: %s", prev.get("brightness") != curr.get("brightness"))
                if prev.get("brightness") != curr.get("brightness"):
                    changing = True
                    break
            log.debug("Changing: %s", changing)
            # log.warning("Alive: %s", handler.timer.is_alive())
            # log.warning("Bright != 0: %s", state_queue[-1].get("brightness") != 0)
            # log.warning("Bright != dark: %s",
            #             state_queue[-1].get("brightness") != int(handler.dark * 0xFFFF))
            # log.warning("Not changing: %s", not changing)
            # log.warning("Total: %s", handler.timer.is_alive() or (
            # state_queue[-1].get("brightness", 0) > int(handler.dark * 0xFFFF) and
            # not changing))
            if (state_queue[-1].get("brightness", 0) > int(handler.dark *
                                                           0xFFFF and state_queue[-1].get("power") == 0xFFFF)) and not changing:
                handler.last_state = state_queue[-1]
                log.debug("Setting last state to %s", state_queue[-1])
            time.sleep(5)
    except KeyboardInterrupt:
        log.error("PIR timer shut down using CTRL+C")
