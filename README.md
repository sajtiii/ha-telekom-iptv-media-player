# Telekom IPTV Box Media Player

A HomeAssistant custom integration for Magyar Telekom (Microsoft Mediaroom) set-top
boxes. It wraps the [`telekom-iptv-remote`](https://pypi.org/project/telekom-iptv-remote/)
library and exposes the box as a **media player** plus a **remote**.

- Local polling over the LAN (no cloud).
- Pair once with the on-screen code; credentials are stored in the config entry.

## Entities

**`media_player`**
- state: playing / idle (screensaver) / off (standby)
- volume level + set (absolute, via the library's self-correcting stepper), volume up/down, mute
- channel: `media_channel` name, `next/previous track` = channel up/down, `source` list = all channels
- now playing: `media_title`, position/duration from the current program
- **media browser**: browse the cloud EPG as channel groups → channels (with logos);
  picking a channel tunes the box to it (EPG id resolved to the box's LCN)

**`remote`**
- `remote.send_command` with wire key names (`volumeup`, `guide`, `menu`, `power`, …);
  see `telekom_iptv_remote.Key` for the full set.

## Requirements

The integration depends on the [`telekom-iptv-remote`](https://pypi.org/project/telekom-iptv-remote/)
package (declared in `manifest.json`). Home Assistant installs it automatically from PyPI.

## Install

1. Copy `custom_components/telekom_iptv_remote/` into your HA `config/custom_components/`
   (or add this repo to HACS as a custom repository).
2. Restart Home Assistant.
3. **Settings → Devices & services → Add integration → Telekom IPTV Box Media Player.**
4. Enter the box IP and the 8-character pairing code shown on the TV. Optionally set
   the client name (default **HomeAssistant**).

## Options

Settings → the integration → **Configure**:
- **volume min / max** — the box's volume scale (defaults 0–25) used for the slider.
- **polling interval** — how often live state is read (default 5 s).

## Notes

- There is no absolute-volume command on the box; `set_volume` reads the current level
  and sends the right number of up/down presses, correcting for dropped presses.
- Poll interval is a trade-off: 5 s feels responsive without hammering the box.
- The media browser uses the public cloud EPG (`smartapp.telekom.hu`). The channel
  lineup, channel groups and LCN map are cached and re-fetched every 6 hours
  (`STATIC_REFRESH_INTERVAL`); a failed refresh keeps the previous data. The box is
  only used to tune when you pick a channel.
- The box exposes every paired companion's key over `op=devices`; treat it as a
  trusted-LAN device only.