# Game/Chat balance mixing -- investigation notes

Goal: replicate the Windows Synapse "Game/Chat balance" slider on Linux,
same way haptics were reverse-engineered.

## Solved: the HID balance command

Captured via the same Wireshark + USBPcap method used for haptics (see
`README.md` for the full protocol writeup). Summary:

- Command class `0x05`, sub-header `80 dc 00 01`, on the same `MI_04`
  vendor HID interface (Report ID 2, `SET_REPORT`, `wValue = 0x0202`)
- Byte 13 carries the value: `0x00` (full Game) to `0x14`/20 (full Chat),
  `0x0a`/10 = center -- 21 steps, 5% increments of the 0-100% slider
- **Checksum is fully solved:** byte 45 = `0x3a XOR value`. Verified against
  4 independently captured samples spanning the range (0, 10, 14, 20), all
  consistent with this exact formula.
- Implemented in `kraken_v4_pro_haptics.py` as `balance <percent>` /
  `balance-raw <0-20>` -- synthesizes any value, no lookup table needed.

Not yet tested against real hardware on Linux (only reverse-engineered from
Windows captures so far -- unlike the haptics commands, which are confirmed
working on a real device).

## What we know about the audio interfaces (from Linux-side inspection)

The headset exposes **two independent USB Audio Class playback
interfaces**, confirmed via `aplay -l` and `/proc/asound/card1/stream{0,1}`
on the same `1532:0568` device haptics uses:

- **Interface 2** ("USB Audio", ALSA device 0) -- this is **Game** audio.
  Confirmed by observing it go `Running` while music played through it.
- **Interface 6** ("USB Audio #1", ALSA device 1) -- this is **Chat**
  audio. Sits `Stop`/idle when nothing is routed to it.

Both are stereo, 48kHz, S16_LE/S24_3LE. The headset's firmware mixes these
two streams internally in hardware, with the mix ratio controlled by the
HID balance command above.

Oddly, the whole ALSA card identifies itself as
`"Razer Kraken V4 Pro - Chat Razer Kraken V4 Pro"` (see
`/proc/asound/card1/id` -> `Pro`, and the long card name) -- likely just a
firmware string quirk from how the two virtual sound devices are named
internally, not meaningful beyond confirming "Chat" is a real concept baked
into the device.

## What's still missing

**Exposing interface 6 as its own routable PipeWire sink on Linux.** Right
now PipeWire's ALSA card profile logic (`api.alsa.split-enable = "true"`)
only seems to expose the analog-stereo / iec958-stereo profile split
(Analog Output vs Digital S/PDIF in the GNOME sound picker), not this
second Game/Chat playback stream as an independently selectable sink. Need
to figure out whether a custom PipeWire ALSA rule (e.g. a `.conf` snippet
targeting `alsa.card = "1"`, device 1 specifically) can surface both
playback devices as separate sinks simultaneously, so a voice chat app can
be routed to interface 6 while games/music stay on interface 2.

This is independent of the HID balance command -- even with balance fully
controllable, we still need both ALSA playback devices routable
separately for the whole Game/Chat setup to be useful (games -> interface
2, Discord/voice chat -> interface 6, balance slider mixes them in
hardware).

## Next steps

1. Test the `balance`/`balance-raw` commands against real hardware.
2. Investigate PipeWire ALSA node configuration to expose interface 6 as an
   independent sink (custom `.conf` under
   `~/.config/pipewire/pipewire.conf.d/` or similar, targeting the second
   ALSA subdevice on card 1).
