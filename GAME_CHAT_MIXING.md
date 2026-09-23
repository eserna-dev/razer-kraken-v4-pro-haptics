# Game/Chat balance mixing -- investigation notes

Goal: replicate the Windows Synapse "Game/Chat balance" slider on Linux,
same way haptics were reverse-engineered.

## What we know so far (from Linux-side inspection)

The headset exposes **two independent USB Audio Class playback
interfaces**, confirmed via `aplay -l` and `/proc/asound/card1/stream{0,1}`
on the same `1532:0568` device haptics uses:

- **Interface 2** ("USB Audio", ALSA device 0) -- this is **Game** audio.
  Confirmed by observing it go `Running` while music played through it.
- **Interface 6** ("USB Audio #1", ALSA device 1) -- this is **Chat**
  audio. Sits `Stop`/idle when nothing is routed to it.

Both are stereo, 48kHz, S16_LE/S24_3LE. The headset's firmware must mix
these two streams internally in hardware, with the mix ratio controlled by
the Game/Chat balance slider in Synapse -- almost certainly via another HID
command on the same vendor interface (`MI_04`, interface 4) that haptics
commands already use (report ID 2, `SET_REPORT`, `wValue = 0x0202`).

Oddly, the whole ALSA card identifies itself as
`"Razer Kraken V4 Pro - Chat Razer Kraken V4 Pro"` (see
`/proc/asound/card1/id` -> `Pro`, and the long card name) -- likely just a
firmware string quirk from how the two virtual sound devices are named
internally, not meaningful beyond confirming "Chat" is a real concept baked
into the device.

## What's still missing

1. **The HID command for the Game/Chat balance value.** Not yet captured.
   Likely another sub-opcode alongside the known ones (`0x8a` intensity,
   `0x8c` profile/audio-to-haptics enable) in the same 64-byte payload
   format documented in `README.md`. Probably a single byte 0-100 (or
   0-255) somewhere in the payload for the balance percentage.

2. **Exposing interface 6 as its own routable PipeWire sink on Linux.**
   Right now PipeWire's ALSA card profile logic (`api.alsa.split-enable =
   "true"`) only seems to expose the analog-stereo / iec958-stereo profile
   split (Analog Output vs Digital S/PDIF in the GNOME sound picker), not
   this second Game/Chat playback stream as an independently selectable
   sink. Need to figure out whether a custom PipeWire ALSA rule (e.g. a
   `.conf` snippet targeting `alsa.card = "1"`, device 1 specifically) can
   surface both playback devices as separate sinks simultaneously, so a
   voice chat app can be routed to interface 6 while games/music stay on
   interface 2.

## Next step: capture the balance command on Windows

Using the same Wireshark + USBPcap setup used for the haptics capture:

1. Open Synapse, go to the Kraken V4 Pro's Game/Chat balance control.
2. Start a USBPcap capture on the device's root hub.
3. Move the balance slider through several distinct positions (e.g. full
   Game, full Chat, and a few points in between -- the more samples the
   easier it is to spot which byte(s) change and how).
4. Stop the capture, filter to `SET_REPORT` control transfers on interface
   4 (`bRequest == 0x09`, `wValue == 0x0202`), same filter used originally
   for the haptics/profile commands.
5. Diff the captured payloads against each other and against the known
   payloads in `kraken_v4_pro_haptics.py` to find the new sub-opcode and
   which byte offset carries the balance value.

Once we have a handful of captured payloads at different balance settings,
we can add a `balance` sub-command to `kraken_v4_pro_haptics.py` the same
way `intensity`/`profile`/`audio-to-haptics` were added -- replaying exact
captured bytes if the checksum stays unsolved, or synthesizing if we crack
it by then.
