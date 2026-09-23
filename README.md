# Razer Kraken V4 Pro Haptics (Linux)

Reverse-engineered USB HID protocol for controlling the Razer Kraken V4 Pro's
Sensa HD haptics from Linux, without Synapse and without waiting on
OpenRazer to add support (the V4 Pro isn't recognized by OpenRazer yet, and
even supported headsets rarely get haptics implemented).

Not affiliated with Razer or OpenRazer. Use at your own risk.

## Background

Haptics on the V4 Pro are driven over a proprietary Razer HID protocol,
separate from the standard USB audio path. This repo documents that
protocol as reverse-engineered from a USB capture (Wireshark + USBPcap) of
Razer Synapse on Windows, and provides a small Python script to replay the
captured commands on Linux via raw USB control transfers.

## Device

- VID `0x1532`, PID `0x0568`
- Target interface: `MI_04`, the vendor-defined HID interface
  (`USB\VID_1532&PID_0568&MI_04`), reported by Windows as having two
  vendor-defined HID collections plus one standard one
- Commands are sent as HID `SET_REPORT` control transfers, **Report ID 2**,
  Report Type **Output** (`wValue = 0x0202`)

## Protocol

Every command is a 64-byte payload (byte 0 is the Report ID prefix,
`0x02`), with a shared 10-byte header:

```
02 00 60 00 00 00 25 16 5f 80 ...
```

followed by a sub-opcode and its arguments, then zero padding, with a
checksum byte at offset 45.

**Solved:** for this command class (`0x25`, covering intensity/profile/
Audio-to-Haptics-enable below), the checksum is a plain two's-complement
byte-sum over the sub-opcode+payload region:

```
checksum = (256 - sum(payload[10:45])) & 0xFF
```

Verified exactly against all 12 known-good captured payloads (6 intensity
levels, 4 profiles, 2 Audio-to-Haptics states) -- not just consistent with
each individually, but every single one matches this one formula. It is
*not* the classic OpenRazer XOR checksum (verified against known-good
lighting-command checksums, which do use that formula), and it is a
different algorithm from the Game/Chat balance command's checksum below
(command class `0x05`) -- brute-forced every possible byte range and no
sum-based formula reproduces that command's checksums, so the two command
classes use genuinely different checksum schemes, not one general formula.

The script currently still replays exact captured byte sequences for
intensity/profile/Audio-to-Haptics rather than synthesizing with this
formula, since the lookup tables already cover every reachable state; the
formula is documented here in case a new sub-command needs a fresh,
non-captured payload in the future.

### Command: set haptic intensity (sub-opcode `0x8a`)

| Byte offset | Meaning | Values |
|---|---|---|
| 12 | enabled | `0x00` = off, `0x01` = on |
| 13 | intensity level | `0x00`-`0x05` |

### Command: select Audio-to-Haptics profile (sub-opcode `0x8c`, byte 11 = `0x24`)

| Byte 12 | Profile |
|---|---|
| `0x01` | Controlled |
| `0x02` | Balanced |
| `0x03` | Dynamic |
| `0x04` | Custom |

Selecting "Custom" also triggers two additional sub-commands (`0x23`,
`0x0c`) that push custom-profile parameters (e.g. sensitivity/bass
sliders) -- not yet mapped in detail.

### Command: enable/disable Audio-to-Haptics (sub-opcode `0x8c`, byte 11 = `0x09`)

Byte 16: `0x43` = on, `0x00` = off. (Least certain of the mapped fields --
this sub-command appears to be sent as part of a broader status-sync
packet, so byte 16's meaning could be narrower than "just" the on/off
flag.)

### Command: set Game/Chat balance (command class `0x05`, sub-header `80 dc 00 01`)

Different header from the commands above:

```
02 00 60 00 00 00 05 00 00 80 dc 00 01 <value> ...
```

| Byte offset | Meaning | Values |
|---|---|---|
| 13 | balance | `0x00`-`0x14` (0-20) |

`0x00` = full Chat, `0x0a` (10) = center, `0x14` (20) = full Game -- 21 steps,
almost certainly 5% increments of Synapse's 0-100% slider. (Confirmed
against real hardware; this is inverted from our initial guess when we only
had the Windows capture to go on -- see `GAME_CHAT_MIXING.md`.)

**This command's checksum is fully solved:** `checksum = 0x3a XOR value`
(byte 45). Verified against four independently captured samples spanning
the full range. Unlike the other commands, this one is *synthesized*, not
replayed from a lookup table -- any value 0-20 works without a new capture.

## Usage

```bash
pip install pyusb
```

Requires `libusb-1.0` (e.g. `sudo apt install libusb-1.0-0`) and permission
to open the device -- either run as root, or add a udev rule:

`/etc/udev/rules.d/99-razer-kraken-v4-pro.rules`:
```
SUBSYSTEM=="usb", ATTR{idVendor}=="1532", ATTR{idProduct}=="0568", MODE="0666"
```
then `sudo udevadm control --reload-rules && sudo udevadm trigger`.

```bash
python3 kraken_v4_pro_haptics.py intensity 5
python3 kraken_v4_pro_haptics.py intensity 0
python3 kraken_v4_pro_haptics.py audio-to-haptics on
python3 kraken_v4_pro_haptics.py profile dynamic
python3 kraken_v4_pro_haptics.py balance 75      # 75% toward Chat
python3 kraken_v4_pro_haptics.py balance-raw 5   # native 0-20 scale, 0=Chat 20=Game
```

To actually route separate audio (e.g. game audio vs. Discord voice chat)
to the two sides of the balance mix, install the PipeWire config that
exposes the headset's two USB audio interfaces as separate "(Game)"/"(Chat)"
sinks -- see `GAME_CHAT_MIXING.md` for details:

```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cp wireplumber/51-razer-kraken-v4-pro-game-chat.conf ~/.config/wireplumber/wireplumber.conf.d/
systemctl --user restart wireplumber pipewire pipewire-pulse
```

The script detaches the kernel's generic HID driver from interface 4
before sending, and reattaches it afterward.

## Known limitations / next steps

- Both checksum algorithms are now solved -- see the Protocol section
  above for the `0x25`-class two's-complement sum formula and the
  Game/Chat balance section for its XOR formula.
- The Custom Audio-to-Haptics profile's parameter sub-commands (`0x23`,
  `0x0c`) aren't mapped.
- Confirmed working against a real Kraken V4 Pro on Linux: intensity
  levels, Audio-to-Haptics enable/disable, profile switching, and
  Game/Chat balance all work with no Synapse installed. Separate Game/Chat
  audio routing (two distinct sinks, mixed in hardware by the balance
  command) is also confirmed working end-to-end -- see
  `GAME_CHAT_MIXING.md`.

## Captures

Raw `.pcapng` captures used to derive this protocol are not included in
this repo (see `.gitignore`). If you want to keep them for future protocol
work, drop them in `captures/` -- they're git-ignored by default since
they're large binary artifacts.
