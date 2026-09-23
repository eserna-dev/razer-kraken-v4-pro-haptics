# Game/Chat balance mixing -- investigation notes

Goal: replicate the Windows Synapse "Game/Chat balance" slider on Linux,
same way haptics were reverse-engineered. **Both pieces (HID balance
command + separate routable sinks) are now confirmed working together on
real hardware.**

## Solved: the HID balance command

Captured via the same Wireshark + USBPcap method used for haptics (see
`README.md` for the full protocol writeup). Summary:

- Command class `0x05`, sub-header `80 dc 00 01`, on the same `MI_04`
  vendor HID interface (Report ID 2, `SET_REPORT`, `wValue = 0x0202`)
- Byte 13 carries the value: `0x00`-`0x14` (0-20), `0x0a`/10 = center -- 21
  steps, almost certainly 5% increments of the 0-100% slider
- **Checksum is fully solved:** byte 45 = `0x3a XOR value`. Verified against
  4 independently captured samples spanning the range (0, 10, 14, 20), all
  consistent with this exact formula.
- Implemented in `kraken_v4_pro_haptics.py` as `balance <percent>` /
  `balance-raw <0-20>` -- synthesizes any value, no lookup table needed.

**Value direction, confirmed against real hardware:** `0x00` = full **Chat**,
`0x14`/20 = full **Game** -- the reverse of our first guess from the Windows
capture alone. Confirmed by ear: playing a YouTube video (as a game-audio
stand-in) on the Game sink and a Discord voice channel on the Chat sink,
then sweeping the balance value -- moving toward the value we now call
"Game" (20) quiets the Discord/Chat side and leaves YouTube/Game alone, and
vice versa. `kraken_v4_pro_haptics.py`'s `balance <percent>` command (0=Game,
100=Chat, matching Synapse's own slider convention) already accounts for
this inversion internally; `balance-raw` still takes the device's native
0-20 scale directly (0=Chat, 20=Game).

## What we know about the audio interfaces (from Linux-side inspection)

The headset exposes **two independent USB Audio Class playback
interfaces**, confirmed via `aplay -l` and `/proc/asound/card1/stream{0,1}`
on the same `1532:0568` device haptics uses:

- **Interface 2** ("USB Audio", ALSA device 0, `hw:X,0`) -- **Game** audio.
  Confirmed by observing it go `Running` while music played through it.
- **Interface 6** ("USB Audio #1", ALSA device 1, `hw:X,1`) -- **Chat**
  audio. Sits `Stop`/idle when nothing is routed to it.

Both are stereo, 48kHz, S16_LE/S24_3LE. The headset's firmware mixes these
two streams internally in hardware, with the mix ratio controlled by the
HID balance command above. This Game/Chat identity (which *interface* is
which) is unrelated to, and unaffected by, the HID balance value inversion
described above -- interface 2 is Game and interface 6 is Chat, full stop.

Oddly, the whole ALSA card identifies itself as
`"Razer Kraken V4 Pro - Chat Razer Kraken V4 Pro"` (see
`/proc/asound/card1/id` -> `Pro`, and the long card name) -- likely just a
firmware string quirk from how the two virtual sound devices are named
internally, not meaningful beyond confirming "Chat" is a real concept baked
into the device.

## Solved: exposing both interfaces as separate PipeWire sinks

**First attempt (rejected):** switching the card's PipeWire profile to
"Pro Audio" (`wpctl set-profile <device-id> <pro-audio-index>`) does expose
both interfaces simultaneously, but as a whole-card change to raw
multichannel routing -- individual mono ports instead of normal one-click
stereo sinks, needs a patchbay app (`qpwgraph`/`helvum`/`pw-link`) to route,
and it broke mic capture negotiation. Reverted.

**Working solution:** disable ACP (Automatic Card Profile) just for this
device via a WirePlumber rule matched on USB vendor/product ID, so the
plain (non-ACP) ALSA monitor creates one plain node per PCM subdevice
instead of ACP's mutually-exclusive profile-switching nodes. This gives
two permanent, normally-named stereo sinks with no other side effects (mic
capture still works normally).

The config is checked into this repo at
[`wireplumber/51-razer-kraken-v4-pro-game-chat.conf`](wireplumber/51-razer-kraken-v4-pro-game-chat.conf).
Install it with:

```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cp wireplumber/51-razer-kraken-v4-pro-game-chat.conf ~/.config/wireplumber/wireplumber.conf.d/
systemctl --user restart wireplumber pipewire pipewire-pulse
```

Result (`wpctl status`):
- `Razer Kraken V4 Pro` (`hw:X,0`) = **Game** sink
- `Razer Kraken V4 Pro (USB Audio #1)` (`hw:X,1`) = **Chat** sink

Both show up as normal selectable outputs in the GNOME Sound Output picker
and in per-app output pickers (e.g. Discord's Settings -> Voice & Video ->
Speaker dropdown), exactly like any other output device -- no patchbay
needed.

### Renaming the sinks

The default names (`Razer Kraken V4 Pro` / `Razer Kraken V4 Pro (USB Audio
#1)`) weren't very clear, so the same conf file also matches on `node.name`
(which ends in `.playback.0.0` for Game / `.playback.1.0` for Chat) and sets
`node.description`/`node.nick` to `Razer Kraken V4 Pro (Game)` and
`Razer Kraken V4 Pro (Chat)`. Confirmed showing up with those names in both
the GNOME Sound Output picker and per-app output pickers (e.g. Discord's
Settings -> Voice & Video -> Speaker dropdown).

## Confirmed end-to-end on real hardware

- YouTube (Game sink) + Discord voice (Chat sink) both play simultaneously,
  routed to the correct hardware interface.
- `balance`/`balance-raw` audibly mixes the two in hardware, in the
  direction described above.

## Remaining polish

- Consider whether the WirePlumber config install step should also be
  documented as an optional setup step in the main `README.md`'s Usage
  section, since it's required for the Game/Chat sink split to work
  (separate from the HID commands, which don't need it).
