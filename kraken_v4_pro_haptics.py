#!/usr/bin/env python3
"""
Razer Kraken V4 Pro haptics control (Linux).

Reverse-engineered from a USBPcap capture of Razer Synapse (Windows) talking
to the headset. Not affiliated with Razer or OpenRazer.

Target: VID 0x1532, PID 0x0568, USB interface 4 (the vendor-defined HID
interface). Commands are sent as HID SET_REPORT control transfers, Report
ID 2, exactly mirroring what Synapse sends -- so we replay known-good byte
sequences captured from the real UI rather than generating new ones (the
report's trailing checksum byte uses an unidentified algorithm, not the
classic OpenRazer XOR, so we can't safely synthesize arbitrary values yet).

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


def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        sys.exit(f"Device {VENDOR_ID:04x}:{PRODUCT_ID:04x} not found")

    detached = False
    if dev.is_kernel_driver_active(INTERFACE):
        dev.detach_kernel_driver(INTERFACE)
        detached = True

    return dev, detached


def send_report(dev, hexpayload):
    payload = bytes.fromhex(hexpayload)
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_intensity = sub.add_parser("intensity", help="Set haptic intensity (0=off, 1-5=on)")
    p_intensity.add_argument("level", type=int)

    p_a2h = sub.add_parser("audio-to-haptics", help="Enable/disable Audio-to-Haptics")
    p_a2h.add_argument("state", choices=["on", "off"])

    p_profile = sub.add_parser("profile", help="Select Audio-to-Haptics profile")
    p_profile.add_argument("name", choices=sorted(PROFILE))

    args = ap.parse_args()

    dev, detached = open_device()
    try:
        if args.cmd == "intensity":
            set_intensity(dev, args.level)
        elif args.cmd == "audio-to-haptics":
            set_audio_to_haptics(dev, args.state == "on")
        elif args.cmd == "profile":
            set_profile(dev, args.name)
        print("Sent OK")
    finally:
        if detached:
            try:
                dev.attach_kernel_driver(INTERFACE)
            except usb.core.USBError:
                pass


if __name__ == "__main__":
    main()
