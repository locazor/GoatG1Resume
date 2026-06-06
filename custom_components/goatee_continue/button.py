"""Button platform for Goatee Continue.

Exposes ``button.<name>_continue`` which performs the same resume/continue
action as the ``goatee_continue.resume`` service, so it can be dropped on a
dashboard or used in automations.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEVICE_NAME, CONF_DID, ECOVACS_DOMAIN
from .ecovacs_link import async_send_resume

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the continue button from a config entry."""
    async_add_entities([GoateeContinueButton(entry)])


class GoateeContinueButton(ButtonEntity):
    """A button that resumes the paused mowing task."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:play-pause"
    # Translatable name; see translations/*.json ("continue").
    _attr_translation_key = "continue"

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialise the button for the configured device."""
        self._did: str = entry.data[CONF_DID]
        name: str = entry.data.get(CONF_DEVICE_NAME, self._did)
        self._attr_unique_id = f"{self._did}_continue"
        # Link to the existing ecovacs device so the button groups under it.
        self._attr_device_info = DeviceInfo(
            identifiers={(ECOVACS_DOMAIN, self._did)},
            name=name,
        )

    async def async_press(self) -> None:
        """Handle the button press: resume the paused task."""
        _LOGGER.info("Continue button pressed for %s", self._did)
        await async_send_resume(self.hass, self._did)
