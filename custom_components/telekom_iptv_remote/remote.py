"""Remote entity exposing the box's full key set."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import RemoteEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TelekomConfigEntry
from .const import DOMAIN
from .coordinator import TelekomCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TelekomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the remote entity from a config entry."""
    async_add_entities([TelekomRemote(entry.runtime_data, entry)])


class TelekomRemote(CoordinatorEntity[TelekomCoordinator], RemoteEntity):
    """Send arbitrary key presses to the box.

    `remote.send_command` accepts wire key names, e.g. "volumeup", "guide", "menu".
    """

    _attr_has_entity_name = True
    _attr_name = "Remote"

    def __init__(self, coordinator: TelekomCoordinator, entry: TelekomConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_remote"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.unique_id)})

    @property
    def is_on(self) -> bool | None:
        act = self.coordinator.data.activity if self.coordinator.data else None
        return act.awake if act else None

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        """Send one or more key presses (wire names from telekom_iptv_remote.Key)."""
        remote = self.coordinator.remote
        for key in command:
            await self.hass.async_add_executor_job(remote.send_key, key)
        await self.coordinator.async_request_refresh()
