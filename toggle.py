"""Test the lifx module"""
from lifx import Device, get_state, send_packet
from packet_builder import Packet


def brightness(state, level, duration=0):
    """Set lifx to select brightness level"""
    send_packet(
        Device.Taklampa,
        Packet.state(
            state.get("hue", 0),
            state.get("saturation", 0),
            level * 0xFFFF,
            state.get("kelvin", 3500),
            duration
        ))


def toggle():
    """Toggle the lifx light"""
    state = get_state(Device.Taklampa)
    if state["brightness"] > 0:
        brightness(state, 0)
    else:
        brightness(state, 1)
    print(state)


if __name__ == "__main__":
    toggle()
