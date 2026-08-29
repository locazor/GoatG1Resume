"""Button platform for Ecovacs Resume.

Exposes ``button.<mower>_continue`` which performs the same resume/continue
action as the ``ecovacs_resume.resume`` service, so it can be dropped on a
dashboard or used in automations. One button per config entry, i.e. per mower.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DID, ECOVACS_DOMAIN
from .ecovacs_link import async_send_resume

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the continue button from a config entry."""
    async_add_entities([EcovacsResumeButton(entry)])


class EcovacsResumeButton(ButtonEntity):
    """A button that resumes the paused mowing task."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:play-pause"
    # Translatable name; see translations/*.json ("continue").
    _attr_translation_key = "continue"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialise the button for the configured device."""
        self._did: str = entry.data[CONF_DID]
        self._attr_unique_id = f"{self._did}_continue"
        # Attach to the *existing* ecovacs device rather than describing a new
        # one: identifiers only, no name/manufacturer/model. Passing descriptive
        # fields here makes Home Assistant treat this as a device *definition*,
        # which under the pre-2.0 domain produced a second registry entry with
        # the same name as the ecovacs device — and a duplicate device name is
        # what forced the ugly area-prefixed `button.<area>_<mower>_continue`
        # entity id. Identifiers-only links the entity onto the ecovacs device.
        self._attr_device_info = DeviceInfo(
            identifiers={(ECOVACS_DOMAIN, self._did)},
        )

    async def async_press(self) -> None:
        """Handle the button press: resume the paused task."""
        _LOGGER.debug("Continue button pressed for did=%s", self._did)
        await async_send_resume(self.hass, self._did)
