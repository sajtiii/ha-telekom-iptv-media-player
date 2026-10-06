"""Constants for the Telekom IPTV Box Media Player integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "telekom_iptv_remote"

# how often to re-fetch the box channel list, EPG channels/groups and LCN map
STATIC_REFRESH_INTERVAL = timedelta(hours=6)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.REMOTE]

# config entry keys
CONF_CID = "cid"
CONF_KEY = "key"
CONF_VOLUME_MIN = "volume_min"
CONF_VOLUME_MAX = "volume_max"
CONF_SCAN_INTERVAL = "scan_interval"

# pairing step keys
CONF_CODE = "code"

DEFAULT_PORT = 53208
DEFAULT_SCAN_INTERVAL = 5  # seconds
DEFAULT_VOLUME_MIN = 0
DEFAULT_VOLUME_MAX = 25
DEFAULT_CLIENT_NAME = "HomeAssistant"  # name registered with the box on pairing
