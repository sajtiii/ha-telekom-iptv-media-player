"""The Telekom IPTV Box Media Player integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from telekom_iptv_remote import Device, Remote

from .const import (
    CONF_CID,
    CONF_KEY,
    CONF_SCAN_INTERVAL,
    CONF_VOLUME_MAX,
    CONF_VOLUME_MIN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VOLUME_MAX,
    DEFAULT_VOLUME_MIN,
    PLATFORMS,
    STATIC_REFRESH_INTERVAL,
)
from .coordinator import TelekomCoordinator

_LOGGER = logging.getLogger(__name__)

TelekomConfigEntry = ConfigEntry[TelekomCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TelekomConfigEntry) -> bool:
    """Set up Telekom IPTV Box Media Player from a config entry."""
    device = Device(
        ip=entry.data[CONF_HOST],
        cid=entry.data[CONF_CID],
        key=entry.data[CONF_KEY],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        volume_min=entry.options.get(CONF_VOLUME_MIN, DEFAULT_VOLUME_MIN),
        volume_max=entry.options.get(CONF_VOLUME_MAX, DEFAULT_VOLUME_MAX),
    )
    remote = Remote(device)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = TelekomCoordinator(hass, remote, scan_interval)

    await coordinator.async_load_channels()
    await coordinator.async_config_entry_first_refresh()
    try:
        await coordinator.async_epg_data()
    except Exception as err:  # noqa: BLE001 - EPG artwork is optional for local playback
        _LOGGER.warning("Initial EPG fetch failed; channel artwork is unavailable: %s", err)

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # periodically re-fetch the channel lineup + EPG (they change over time)
    entry.async_on_unload(
        async_track_time_interval(hass, coordinator.async_refresh_static, STATIC_REFRESH_INTERVAL)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TelekomConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: TelekomConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
