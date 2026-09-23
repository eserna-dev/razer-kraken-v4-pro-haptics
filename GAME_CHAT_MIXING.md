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

**Confirmed working against real hardware on Linux:** `balance-raw 0`,
`balance-raw 20`, and `balance 50` all sent successfully with no USB
errors.

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

## Exposing both interfaces as separate PipeWire sinks

Switching the card's ALSA/PipeWire profile to **"Pro Audio"** (`wpctl
set-profile <device-id> <pro-audio-index>`, index found via `pw-dump`'s
`EnumProfile` for the device) does expose both interfaces simultaneously:

- `alsa_output...pro-output-0` (`hw:X,0`) = **Game** (interface 2)
- `alsa_output...pro-output-1` (`hw:X,1`) = **Chat** (interface 6)

Confirmed by checking each node's `api.alsa.path` via `wpctl inspect`.

**Trade-off:** Pro Audio mode is a whole-card change, not a per-stream
toggle. It switches the card to raw multichannel routing -- each sink
exposes individual mono FL/FR ports instead of a normal one-click stereo
device in the GNOME sound picker, apps need manual patchbay routing (e.g.
`qpwgraph`, `helvum`, or `pw-link`), and it also disrupted the mic input
(a WEBRTC capture stream got stuck "negotiating" instead of connecting)
until switched back to the normal profile. Not a clean solution as-is --
reverted to the default `analog-stereo` profile afterward.

## What's still missing

**A clean, always-on way to get two normal named stereo sinks** ("Game"
and "Chat") without the whole-card Pro Audio side effects. Likely
approaches to try:

1. A custom WirePlumber rule (`~/.config/wireplumber/wireplumber.conf.d/`
   or a `.lua`/`.conf` script under the older config style) that manually
   creates two `adapter`/`api.alsa.pcm.sink` nodes bound to `hw:X,0` and
   `hw:X,1` directly, bypassing ACP's profile exclusivity, while leaving
   the rest of the card (mic, normal profile) alone.
2. Alternatively, run a second, independent PipeWire/ALSA sink manually
   via `pw-cli create-node` or a static `.conf` snippet targeting just the
   `hw:X,1` subdevice, without touching the card's active profile at all.
3. Once a clean "Chat" sink exists, route a voice app (Discord, Mumble,
   etc.) to it via PipeWire's normal per-app output selection, and route
   games/music to the normal "Game" analog sink -- then use
   `balance`/`balance-raw` to mix them in hardware on the headset.

## Next steps

1. ~~Test the `balance`/`balance-raw` commands against real hardware.~~ Done.
2. Write a WirePlumber node-config snippet that exposes `hw:X,1` as a
   permanent, cleanly-named "Chat" stereo sink without switching the whole
   card to Pro Audio profile.
3. Verify a voice app can be routed to that Chat sink independently while
   games/music stay on the normal Game sink, and that the hardware balance
   command actually mixes the two audibly.
