"""Media player entity for a Telekom set-top box."""

from __future__ import annotations

import asyncio
import time

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from telekom_iptv_remote import Key

from . import TelekomConfigEntry
from .const import DOMAIN
from .coordinator import TelekomCoordinator

SUPPORT = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.PLAY_MEDIA
)

# media_content_type for a tunable channel in the media browser
CHANNEL = "channel"

# the box drops rapid key presses and reports volume with a lag, so volume is changed in
# short paced bursts, each verified against a fresh read before the next one
VOLUME_PRESS_INTERVAL = 0.15  # seconds between presses in a burst
VOLUME_SETTLE_DELAY = 0.6  # seconds to let the box apply a burst before re-reading
VOLUME_MAX_ROUNDS = 6


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TelekomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the media player from a config entry."""
    async_add_entities([TelekomMediaPlayer(entry.runtime_data, entry)])


class TelekomMediaPlayer(CoordinatorEntity[TelekomCoordinator], MediaPlayerEntity):
    """Represents the box as a media player."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_supported_features = SUPPORT

    def __init__(self, coordinator: TelekomCoordinator, entry: TelekomConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._volume_lock = asyncio.Lock()
        self._volume_target: int | None = None
        self._attr_unique_id = entry.unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="Magyar Telekom",
            model="Mediaroom STB",
        )

    # --- helpers ----------------------------------------------------------------
    # read the channel map live so the periodic refresh propagates to source_list etc.
    @property
    def _name_by_lcn(self) -> dict[int, str]:
        return {
            lcn: (ch.long_name or ch.short_name)
            for lcn, ch in self.coordinator.channels_by_lcn.items()
        }

    @property
    def _lcn_by_name(self) -> dict[str, int]:
        return {name: lcn for lcn, name in self._name_by_lcn.items()}

    @property
    def _remote(self):
        return self.coordinator.remote

    @property
    def _activity(self):
        return self.coordinator.data.activity if self.coordinator.data else None

    @property
    def _now(self):
        return self.coordinator.data.now_playing if self.coordinator.data else None

    # --- state ------------------------------------------------------------------
    @property
    def state(self) -> MediaPlayerState | None:
        act = self._activity
        if act is None:
            return None
        if not act.awake:
            return MediaPlayerState.OFF
        if act.screensaver:
            return MediaPlayerState.IDLE
        return MediaPlayerState.PLAYING

    @property
    def volume_level(self) -> float | None:
        act = self._activity
        if act is None or act.volume is None:
            return None
        lo = self._remote.device.volume_min
        span = max(1, self._remote.device.volume_max - lo)
        return min(1.0, max(0.0, (act.volume - lo) / span))

    @property
    def is_volume_muted(self) -> bool | None:
        act = self._activity
        return act.muted if act else None

    @property
    def media_title(self) -> str | None:
        now = self._now
        return now.title if now else None

    @property
    def media_channel(self) -> str | None:
        act = self._activity
        if act is None or act.channel is None:
            return None
        return self._name_by_lcn.get(act.channel, str(act.channel))

    @property
    def media_image_url(self) -> str | None:
        act = self._activity
        if act is None or act.channel is None:
            return None
        channel = self.coordinator.channels_by_lcn.get(act.channel)
        if channel is None or channel.epg_id is None:
            return None
        return self.coordinator.channel_images_by_epg_id.get(channel.epg_id)

    @property
    def media_duration(self) -> int | None:
        now = self._now
        if now is None or now.duration is None:
            return None
        return int(now.duration.total_seconds())

    @property
    def media_position(self) -> int | None:
        now = self._now
        if now is None or now.start_time is None:
            return None
        elapsed = (dt_util.utcnow() - now.start_time).total_seconds()
        return max(0, int(elapsed))

    @property
    def media_position_updated_at(self):
        return dt_util.utcnow()

    @property
    def source(self) -> str | None:
        return self.media_channel

    @property
    def source_list(self) -> list[str]:
        return sorted(self._lcn_by_name)

    # --- commands (telekom_iptv_remote is sync -> run in executor) ---------------
    async def _send(self, func, *args) -> None:
        await self.hass.async_add_executor_job(func, *args)
        await self.coordinator.async_request_refresh()

    def _apply_volume(self) -> None:
        """Drive the box volume to self._volume_target (runs in the executor).

        The target is re-read every round so a newer request (e.g. a dragged slider)
        supersedes the one in progress instead of fighting it.
        """
        remote = self._remote
        for _ in range(VOLUME_MAX_ROUNDS):
            act = remote.activity()
            target = self._volume_target
            if act is None or act.volume is None or target is None:
                return
            delta = target - act.volume
            if delta == 0:
                return
            key = Key.VOLUME_UP if delta > 0 else Key.VOLUME_DOWN
            for _ in range(abs(delta)):
                remote.send_key(key)
                time.sleep(VOLUME_PRESS_INTERVAL)
            time.sleep(VOLUME_SETTLE_DELAY)

    async def async_set_volume_level(self, volume: float) -> None:
        dev = self._remote.device
        self._volume_target = dev.volume_min + round(volume * (dev.volume_max - dev.volume_min))
        # a call arriving mid-change only updates the target; the running one picks it up
        async with self._volume_lock:
            await self.hass.async_add_executor_job(self._apply_volume)
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        async with self._volume_lock:
            await self._send(self._remote.send_key, Key.VOLUME_UP)

    async def async_volume_down(self) -> None:
        async with self._volume_lock:
            await self._send(self._remote.send_key, Key.VOLUME_DOWN)

    async def async_mute_volume(self, mute: bool) -> None:
        # the box only has a mute toggle; send it when the desired state differs
        act = self._activity
        if act is None or act.muted != mute:
            await self._send(self._remote.send_key, Key.MUTE)

    # the box only has a power toggle, so read the live state first and press only
    # when it differs from what was asked for
    async def _async_set_power(self, on: bool) -> None:
        act = await self.hass.async_add_executor_job(self._remote.activity)
        if act is not None and act.awake == on:
            await self.coordinator.async_request_refresh()
            return
        await self._send(self._remote.send_key, Key.POWER)

    async def async_turn_on(self) -> None:
        await self._async_set_power(True)

    async def async_turn_off(self) -> None:
        await self._async_set_power(False)

    async def async_media_next_track(self) -> None:
        await self._send(self._remote.send_key, Key.CHANNEL_UP)

    async def async_media_previous_track(self) -> None:
        await self._send(self._remote.send_key, Key.CHANNEL_DOWN)

    async def async_select_source(self, source: str) -> None:
        lcn = self._lcn_by_name.get(source)
        if lcn is not None:
            await self._send(self._remote.tune, str(lcn))

    # --- EPG media browser ------------------------------------------------------
    async def async_play_media(self, media_type: str, media_id: str, **kwargs) -> None:
        """Tune to the channel selected in the media browser (media_id = EPG id)."""
        lcn = self.coordinator.epg_to_lcn.get(media_id)
        if lcn is not None:
            await self._send(self._remote.tune, str(lcn))

    async def async_browse_media(
        self, media_content_type: str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia:
        """Browse the EPG: groups -> channels (each tunes on play)."""
        channels, groups = await self.coordinator.async_epg_data()

        # a specific group -> its channels
        if media_content_id and media_content_id.startswith("group/"):
            group_id = media_content_id.split("/", 1)[1]
            members = [c for c in channels if group_id in c.group_ids]
            return self._directory(media_content_id, _group_name(groups, group_id), members)

        # "all channels"
        if media_content_id == "all":
            return self._directory("all", "All channels", channels)

        # root: one node per group + an "all channels" node
        root_children = [
            BrowseMedia(
                title="All channels",
                media_class=MediaClass.DIRECTORY,
                media_content_type="directory",
                media_content_id="all",
                can_play=False,
                can_expand=True,
            )
        ]
        root_children += [
            BrowseMedia(
                title=g.name,
                media_class=MediaClass.DIRECTORY,
                media_content_type="directory",
                media_content_id=f"group/{g.id}",
                can_play=False,
                can_expand=True,
            )
            for g in groups
        ]
        return BrowseMedia(
            title="TV channels",
            media_class=MediaClass.DIRECTORY,
            media_content_type="directory",
            media_content_id="root",
            can_play=False,
            can_expand=True,
            children=root_children,
            children_media_class=MediaClass.DIRECTORY,
        )

    def _directory(self, content_id: str, title: str, channels) -> BrowseMedia:
        return BrowseMedia(
            title=title,
            media_class=MediaClass.DIRECTORY,
            media_content_type="directory",
            media_content_id=content_id,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.CHANNEL,
            children=[self._channel_item(c) for c in channels],
        )

    def _channel_item(self, channel) -> BrowseMedia:
        return BrowseMedia(
            title=channel.name,
            media_class=MediaClass.CHANNEL,
            media_content_type=MediaType.CHANNEL,
            media_content_id=channel.id,  # EPG id -> resolved to LCN on play
            can_play=channel.id in self.coordinator.epg_to_lcn,
            can_expand=False,
            thumbnail=channel.img,
        )


def _group_name(groups, group_id: str) -> str:
    return next((g.name for g in groups if g.id == group_id), "Channels")
