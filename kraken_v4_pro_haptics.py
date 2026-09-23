#!/usr/bin/env python3
"""
Razer Kraken V4 Pro haptics control (Linux).

Reverse-engineered from a USBPcap capture of Razer Synapse (Windows) talking
to the headset. Not affiliated with Razer or OpenRazer.

Target: VID 0x1532, PID 0x0568, USB interface 4 (the vendor-defined HID
interface). Commands are sent as HID SET_REPORT control transfers, Report
ID 2, exactly mirroring what Synapse sends. Most commands (intensity,
Audio-to-Haptics enable, profile select) replay known-good byte sequences
captured from the real UI, since their checksum algorithm is still unknown.
The Game/Chat balance command's checksum *is* solved (checksum = 0x3a XOR
value), so that one is synthesized for any value in range rather than
replayed from a fixed table.

Requires: pip install pyusb
Requires libusb1 installed (e.g. `sudo apt install libusb-1.0-0`).
Needs permission to open the USB device -- either run as root, or add a
udev rule, e.g. /etc/udev/rules.d/99-razer-kraken-v4-pro.rules:

    SUBSYSTEM=="usb", ATTR{idVendor}=="1532", ATTR{idProduct}=="0568", MODE="0666"

then `sudo udevadm control --reload-rules && sudo udevadm trigger`.
"""

import argparse
import sys

import usb.core
import usb.util

VENDOR_ID = 0x1532
PRODUCT_ID = 0x0568
INTERFACE = 4

# bmRequestType for a HID SET_REPORT class request, host-to-device, interface recipient
SET_REPORT_REQTYPE = 0x21
SET_REPORT_REQUEST = 0x09
REPORT_ID = 2
REPORT_TYPE_OUTPUT = 2
WVALUE = (REPORT_TYPE_OUTPUT << 8) | REPORT_ID  # 0x0202

# --- Known-good payloads captured verbatim from Synapse over USB ---
# Each is the full 64-byte wire payload (includes the leading Report ID byte).

INTENSITY = {
    # level -> payload (enabled + level bytes). All captured directly.
    0: "02006000000025165f808a0100000000000000000000000000000000000000000000000000000000000000000075000000000000000000000000000000000000",
    1: "02006000000025165f808a0101010000000000000000000000000000000000000000000000000000000000000073000000000000000000000000000000000000",
    2: "02006000000025165f808a0101020000000000000000000000000000000000000000000000000000000000000072000000000000000000000000000000000000",
    3: "02006000000025165f808a0101030000000000000000000000000000000000000000000000000000000000000071000000000000000000000000000000000000",
    4: "02006000000025165f808a0101040000000000000000000000000000000000000000000000000000000000000070000000000000000000000000000000000000",
    5: "02006000000025165f808a010105000000000000000000000000000000000000000000000000000000000000006f000000000000000000000000000000000000",
}

AUDIO_TO_HAPTICS_ENABLE = {
    False: "02006000000025165f808c090100d800000000000000000000000000000000000000000000000000000000000092000000000000000000000000000000000000",
    True: "02006000000025165f808c090100d80043000000000000000000000000000000000000000000000000000000004f000000000000000000000000000000000000",
}

PROFILE = {
    "controlled": "02006000000025165f808c240100000000000000000000000000000000000000000000000000000000000000004f000000000000000000000000000000000000",
    "balanced": "02006000000025165f808c240200000000000000000000000000000000000000000000000000000000000000004e000000000000000000000000000000000000",
    "dynamic": "02006000000025165f808c240300000000000000000000000000000000000000000000000000000000000000004d000000000000000000000000000000000000",
    "custom": "02006000000025165f808c240400000000000000000000000000000000000000000000000000000000000000004c000000000000000000000000000000000000",
}

# Game/Chat balance: unlike the commands above, this one's checksum is fully
# solved (checksum = 0x3a XOR value), so we can synthesize any value in the
# valid range instead of only replaying captured bytes. Value is 0-20:
# 0 = full Game, 10 = center, 20 = full Chat (5% steps on Synapse's slider).
BALANCE_HEADER = bytes.fromhex("02006000000005000080dc0001")
BALANCE_CHECKSUM_BASE = 0x3A
BALANCE_MIN, BALANCE_MAX = 0, 20


def make_balance_payload(value):
    if not (BALANCE_MIN <= value <= BALANCE_MAX):
        sys.exit(f"balance value must be between {BALANCE_MIN} and {BALANCE_MAX}")
    checksum = BALANCE_CHECKSUM_BASE ^ value
    payload = bytearray(64)
    payload[: len(BALANCE_HEADER)] = BALANCE_HEADER
    payload[len(BALANCE_HEADER)] = value
    payload[45] = checksum
    return bytes(payload)


def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        sys.exit(f"Device {VENDOR_ID:04x}:{PRODUCT_ID:04x} not found")

    detached = False
    if dev.is_kernel_driver_active(INTERFACE):
        dev.detach_kernel_driver(INTERFACE)
        detached = True

    return dev, detached


def send_report(dev, payload):
    if isinstance(payload, str):
        payload = bytes.fromhex(payload)
    dev.ctrl_transfer(
        SET_REPORT_REQTYPE,
        SET_REPORT_REQUEST,
        WVALUE,
        INTERFACE,
        payload,
    )


def set_intensity(dev, level):
    if level not in INTENSITY:
        sys.exit(f"level must be one of {sorted(INTENSITY)}")
    send_report(dev, INTENSITY[level])


def set_audio_to_haptics(dev, enabled):
    send_report(dev, AUDIO_TO_HAPTICS_ENABLE[enabled])


def set_profile(dev, name):
    name = name.lower()
    if name not in PROFILE:
        sys.exit(f"profile must be one of {sorted(PROFILE)}")
    send_report(dev, PROFILE[name])


def set_balance(dev, value):
    send_report(dev, make_balance_payload(value))


def set_balance_percent(dev, percent):
    if not (0 <= percent <= 100):
        sys.exit("percent must be between 0 (full Game) and 100 (full Chat)")
    # Native device scale is inverted: raw 0 = full Chat, raw 20 = full Game
    # (confirmed against real hardware -- see GAME_CHAT_MIXING.md).
    value = BALANCE_MAX - round(percent / 5)
    send_report(dev, make_balance_payload(value))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_intensity = sub.add_parser("intensity", help="Set haptic intensity (0=off, 1-5=on)")
    p_intensity.add_argument("level", type=int)

    p_a2h = sub.add_parser("audio-to-haptics", help="Enable/disable Audio-to-Haptics")
    p_a2h.add_argument("state", choices=["on", "off"])

    p_profile = sub.add_parser("profile", help="Select Audio-to-Haptics profile")
    p_profile.add_argument("name", choices=sorted(PROFILE))

    p_balance = sub.add_parser(
        "balance", help="Set Game/Chat balance as a percent (0=full Game, 100=full Chat)"
    )
    p_balance.add_argument("percent", type=int)

    p_balance_raw = sub.add_parser(
        "balance-raw",
        help=(
            f"Set Game/Chat balance using the device's native {BALANCE_MIN}-{BALANCE_MAX} "
            "scale (0=full Chat, 20=full Game -- inverted from the 'balance' percent command)"
        ),
    )
    p_balance_raw.add_argument("value", type=int)

    args = ap.parse_args()

    dev, detached = open_device()
    try:
        if args.cmd == "intensity":
            set_intensity(dev, args.level)
        elif args.cmd == "audio-to-haptics":
            set_audio_to_haptics(dev, args.state == "on")
        elif args.cmd == "profile":
            set_profile(dev, args.name)
        elif args.cmd == "balance":
            set_balance_percent(dev, args.percent)
        elif args.cmd == "balance-raw":
            set_balance(dev, args.value)
        print("Sent OK")
    finally:
        if detached:
            try:
                dev.attach_kernel_driver(INTERFACE)
            except usb.core.USBError:
                pass


if __name__ == "__main__":
    main()
