"""Polling coordinator for a Telekom set-top box."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from telekom_iptv_remote import (
    Activity,
    BoxChannel,
    Channel,
    ChannelGroup,
    Epg,
    NowPlaying,
    Remote,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class BoxState:
    """Snapshot returned by each poll."""

    activity: Activity | None
    now_playing: NowPlaying | None


class TelekomCoordinator(DataUpdateCoordinator[BoxState]):
    """Fetch live state from the box on an interval.

    telekom_iptv_remote is synchronous (urllib), so every call runs in the executor.
    """

    def __init__(self, hass: HomeAssistant, remote: Remote, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.remote = remote
        self.epg = Epg()
        self.channels_by_lcn: dict[int, BoxChannel] = {}
        self.epg_to_lcn: dict[str, int] = {}
        self._epg_channels: list[Channel] | None = None
        self._epg_groups: list[ChannelGroup] | None = None

    async def async_load_channels(self) -> None:
        """Fetch the box channel list once (LCN <-> name / EPG id)."""
        channels = await self.hass.async_add_executor_job(self.remote.channels)
        self.channels_by_lcn = {c.lcn: c for c in channels if c.lcn is not None}
        self.epg_to_lcn = {c.epg_id: c.lcn for c in channels if c.lcn is not None and c.epg_id}

    async def async_epg_data(self) -> tuple[list[Channel], list[ChannelGroup]]:
        """Fetch EPG channels + groups once (cloud guide, cached for the media browser)."""
        if self._epg_channels is None or self._epg_groups is None:
            self._epg_channels = await self.hass.async_add_executor_job(self.epg.channels)
            self._epg_groups = await self.hass.async_add_executor_job(self.epg.groups)
        return self._epg_channels, self._epg_groups

    async def async_refresh_static(self, _now=None) -> None:
        """Re-fetch the box channel list and EPG (scheduled every few hours).

        The channel lineup and cloud guide change over time, so this is called on an
        interval; failures are logged and the previous data is kept.
        """
        try:
            await self.async_load_channels()
            self._epg_channels = None
            self._epg_groups = None
            await self.async_epg_data()
        except Exception as err:  # noqa: BLE001 - keep the timer alive on any error
            _LOGGER.warning("Periodic channel/EPG refresh failed: %s", err)

    async def _async_update_data(self) -> BoxState:
        def _fetch() -> BoxState:
            return BoxState(
                activity=self.remote.activity(),
                now_playing=self.remote.info(),
            )

        try:
            return await self.hass.async_add_executor_job(_fetch)
        except Exception as err:  # noqa: BLE001 - surface any transport error uniformly
            raise UpdateFailed(f"Error polling box: {err}") from err
