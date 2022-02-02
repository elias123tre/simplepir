"""
A module to generate a ip packet

Used for creating packets that controll LIFX lights with the corresponding LAN protocol.
Se https://lan.developer.lifx.com/ for documentation.

Usage:
    packet = Packet()
    packet.frame.append_param("protocol", [0x00, 0x34], 2)
    packet.payload.append_param("level", 0xFFFF, bit_to_size(16))
    packet.set_size()
    packet.pprint()
"""
from __future__ import annotations

import struct
from typing import List
from functools import reduce

# import pretty_errors


def hex_pad(number, fill=2):
    """Padds a number with zeros and returns hex"""
    try:
        number = int(number)
    except ValueError:
        return "0x00"
    return f"0x{hex(number)[2:].zfill(fill)}"


def tobytes(number: int):
    """Divide a number by 8"""
    return int(number / 8)


def to_bytearray(num: int, bitlength=8):
    """Turns an integer into byte array"""
    return list(num.to_bytes((num.bit_length() + bitlength - 1) // bitlength, "little"))


def packbytes(*pieces: tuple):
    """Pack bits into bytes"""
    def append(prev, new):
        val, length = new
        prev <<= length
        prev |= val
        return prev
    return reduce(append, pieces, pieces[0][0])


def deconstruct(packet: bytes, sizes: dict):
    """Deconstruct and unpack a packet inte `sizes` pieces"""
    index = 0
    for key, size in sizes:
        subsizes = None
        if isinstance(size, dict):
            subsizes = size
            size = sum(size.values())
        piece = packet[index:index + size // 8]
        piece = int.from_bytes(piece, "little")
        index += size // 8
        if subsizes:
            subindex = 0
            for k, subsize in subsizes.items():
                part = f"{piece:0{size}b}"[subindex:subindex + subsize]
                subindex += subsize
                yield k, int(part, 2)
        else:
            yield key, piece


MSGHEADER = [
    ("size", 16),
    ("protocol", {
        "origin": 2,
        "tagged": 1,
        "addressable": 1,
        "protocol": 12,
    }),
    ("source", 32),
    ("target", 64),
    ("reserved", 48),
    ("resp", {
        "reserved": 6,
        "ack_required": 1,
        "res_required": 1,
    }),
    ("sequence", 8),
    ("reserved", 64),
    ("type", 16),
    ("reserved", 16),
]


class Packet:
    """A class to store an ip packet"""
    class Part:
        """A class to store parts of an ip packet"""
        class Parameter(bytearray):
            """A class to store parameters of a part"""

            def __init__(self,
                         name: str = "",
                         values: int | list = 0,
                         length: int = 0,
                         reverse: bool = False):
                super().__init__(length)
                self.name = name
                if values:
                    if not isinstance(values, list):
                        # values = bytearray.fromhex(hex(values)[2:].zfill(2))
                        # values = [int(val, 16) for val in values]
                        val = to_bytearray(int(values))
                        values = val + [0] * (length - len(val))
                        # values = [val.pop() if val else 0 for _ in range(length)]
                        if reverse:
                            values.reverse()
                    for i, value in enumerate(values):
                        self[i] = value
                    self.zfill(length)

            def append(self, v: int, fmt='<B'):
                self.extend(struct.pack(fmt, v))

            def __str__(self) -> str:
                return ' '.join([str(i) for i in self])

            def __repr__(self) -> str:
                nameslug = self.name.replace(' ', '_')
                contents = ', '.join(str(num) for num in list(self))
                value = int.from_bytes(self, 'little')
                percentage = round(value * 100 / (256**len(self) - 1))
                return f"{type(self).__name__}:{nameslug}({contents}) == {value}, {percentage}%"

        def __init__(self, size: int = 0):
            self.parameters = []
            self.set_length(size)

        def __setitem__(self, index, value):
            self.parameters[index] = value

        def set_length(self, size: int):
            """Set the length with zero-filled Parameters"""
            for _ in range(size):
                self.parameters.append(self.Parameter())

        def __getitem__(self, item) -> Parameter:
            return self.parameters[item]

        def __getattr__(self, method):
            return getattr(self.parameters, method)

        def __len__(self) -> int:
            return sum([len(p) for p in self.parameters])

        def prepend_param(self, name: str, value: any, length: int):
            """Add a parameter to the beginning of the part
            Arguments are passed to Parameter constructor."""
            return self.parameters.insert(0, self.Parameter(name, value, length))

        def append_param(self, *args, **kwargs):
            """Add a parameter to the end of the part.
            Arguments are passed to Parameter constructor."""
            return self.parameters.append(self.Parameter(*args, **kwargs))

        def __repr__(self) -> str:
            return f"{type(self).__name__}({' '.join([repr(param) for param in self.parameters])})"

    def __init__(self) -> None:
        self.frame = self.Part()  # Size: 8 (first 2 size)
        self.frame_address = self.Part()  # Size: 16
        self.protocol_header = self.Part()  # Size: 12
        self.payload = self.Part()  # Variable size

    def get_parts(self) -> List[Part]:
        """List of child Parts"""
        return list(vars(self).values())

    def set_size(self, length=2):
        """Set the size of the whole ip packet as the first `length` bytes"""
        # self.frame[0].prepend(0x2a)
        # if self.frame[0].name == "size":
        # else:
        self.frame.prepend_param("size", 0, length)
        self.frame[0] = self.Part.Parameter(
            "size", len(self), 2, reverse=False)

    def __len__(self) -> int:
        return sum([len(l) for l in self.get_parts()])

    def __getitem__(self, item):
        return self.get_parts()[item]

    def get_bytes(self):
        """Returns a list with the bytes of the whole package"""
        result = []
        for part in self.get_parts():
            for param in part:
                for byte in param:
                    result.append(byte)
        return result

    def hex_string(self, separator: str = ' '):
        """A separated list of the hex bytes"""
        return separator.join([f"{hex_pad(byte)}" for byte in self.get_bytes()])

    def bytestring(self):
        """Bytestring notation of the hex bytes"""
        return self.hex_string().replace("0x", r"\x").replace(" ", "")

    def bytearray(self):
        """Flattened byte-like object"""
        bytelist = bytearray()
        for part in self.get_parts():
            for param in part:
                bytelist += param
                # for byte in param:
                #     bytelist += bytes(byte)
        return bytelist

    def pprint(self, width=4):
        """Prints the whole ip packet in YAML"""
        spacing = " " * width
        print("Packet:")
        for partname, part in vars(self).items():
            print(f"{spacing}Part: {partname}")
            for parameter in part:
                print(f"{spacing * 2}{repr(parameter)}")

    @property
    def msgtype(self):
        """Message type"""
        msgtype = next(filter(lambda par: par.name ==
                              "message type", self.protocol_header))
        return int.from_bytes(msgtype, 'little')

    def info(self):
        """Print a short representation of the packet"""
        print(f'Type: {self.msgtype}')

        size = len(self)
        print(f'Size: {size} == {hex_pad(size)}')

        print("\n".join(repr(part) for part in self.payload))

    def set_headers(self, msgtype, tagged=False, source=123,
                    res_required=True, ack_required=False, sequence=0):
        """
        Set common packet headers
        https://lan.developer.lifx.com/docs/packet-contents
        `msgtype`: 117=setpower, 102=setcolor, 101=getstate
        """
        # origin = 0, tagged = 1|0, addressable = 1, protocol = 1024
        protocol = packbytes((0b00, 2), (tagged, 1), (True, 1), (1024, 12))
        self.frame.append_param("protocol", protocol, tobytes(16))
        self.frame.append_param("source", source, tobytes(32))  # client id
        self.frame_address.append_param("target", 0, tobytes(64))
        self.frame_address.append_param("reserved", 0, tobytes(48))
        # reserved, ack_required, res_required
        resp = packbytes((0, 6), (ack_required, 1), (res_required, 1))
        self.frame_address.append_param("resp", resp, tobytes(8))
        self.frame_address.append_param("sequence", sequence, tobytes(8))
        self.protocol_header.append_param("reserved", 0, tobytes(64))
        self.protocol_header.append_param("message type", msgtype, tobytes(16))
        self.protocol_header.append_param("reserved", 0, tobytes(16))

    def __str__(self) -> str:
        return self.hex_string(', ')

    def __repr__(self) -> str:
        return f"{type(self).__name__}({', '.join([repr(a) for a in self.get_parts()])})"

    @classmethod
    def get_state(cls):
        """Generate packet for getting light state"""
        packet = cls()
        # https://lan.developer.lifx.com/docs/querying-the-device-for-data#getcolor---packet-101
        packet.set_headers(101, res_required=True)
        packet.set_size()
        return packet

    @classmethod
    def state(cls, hue: int, saturation: float, brightness: float,
              kelvin: int = 3500, duration: float = 0):
        """Generate packet changing state to HSL(kelvin), fading over `duration` seconds
        `hue`: 0-65535
        `saturation`: 0-65535
        `brightness`: 0-65535
        `kelvin`: 2500-9000
        `duration`: 0-4294967 seconds
        """
        packet = cls()
        # https://lan.developer.lifx.com/docs/changing-a-device#setcolor---packet-102
        packet.set_headers(102)
        packet.payload.append_param("reserved", 0, 1)
        # between 0xFFFF and 0x0000
        packet.payload.append_param("hue", int(hue), tobytes(16))
        packet.payload.append_param("saturation", int(saturation), tobytes(16))
        packet.payload.append_param("brightness", int(brightness), tobytes(16))
        packet.payload.append_param("kelvin", int(kelvin), tobytes(16))
        # In milliseconds
        packet.payload.append_param(
            "duration", int(duration * 1000), tobytes(32))
        packet.set_size()
        return packet

    @classmethod
    def power(cls, power: bool, duration: float = 0):
        """Generate packet with light `level` fading over `duration` seconds"""
        packet = cls()
        # https://lan.developer.lifx.com/docs/changing-a-device#setlightpower---packet-117
        packet.set_headers(117)
        packet.payload.append_param("level", int(0xFFFF * power), tobytes(16))
        # In milliseconds
        packet.payload.append_param(
            "duration", int(duration * 1000), tobytes(32))
        packet.set_size()
        return packet

    @classmethod
    def fastpwr(cls, power: bool):
        """Generate packet for power, no fading"""
        packet = cls()
        # https://lan.developer.lifx.com/docs/changing-a-device#setpower---packet-21
        packet.set_headers(21)
        # 0xFFFF or 0x0000
        packet.payload.append_param("level", int(0xFFFF * power), tobytes(16))
        packet.set_size()
        return packet


if __name__ == "__main__":
    # An example output
    powerpacket = Packet.power(True, 10)

    powerpacket.pprint()
    print(powerpacket)
    print(f"Packet length: {len(powerpacket)} == {hex_pad(len(powerpacket))}")
    print(powerpacket.bytestring())
