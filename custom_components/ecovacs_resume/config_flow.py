"""Config flow for Ecovacs Resume.

One config entry per mower. The picker lists every Ecovacs device that declares
a clean-action capability and is not already configured, so a second (third, …)
mower can be added by simply running the flow again.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_DEVICE_NAME, CONF_DID, CONF_MODEL_CLASS, DOMAIN, ECOVACS_DOMAIN
from .ecovacs_link import async_list_resumable_devices


class EcovacsResumeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ecovacs Resume."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which Ecovacs mower to add a Continue button for."""
        # The official ecovacs integration must be set up first; we reuse it.
        if not self.hass.config_entries.async_entries(ECOVACS_DOMAIN):
            return self.async_abort(reason="ecovacs_not_loaded")

        devices = async_list_resumable_devices(self.hass)
        if not devices:
            return self.async_abort(reason="no_devices")

        # Hide devices that already have an entry so the dropdown only offers
        # something that can actually be added.
        configured = {
            entry.data.get(CONF_DID)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        }
        available = {
            did: info for did, info in devices.items() if did not in configured
        }
        if not available:
            return self.async_abort(reason="all_configured")

        if user_input is not None:
            did = user_input[CONF_DID]
            await self.async_set_unique_id(did)
            self._abort_if_unique_id_configured()
            info = available.get(did) or devices.get(did) or {}
            name = info.get("name") or did
            return self.async_create_entry(
                title=name,
                data={
                    CONF_DID: did,
                    CONF_DEVICE_NAME: name,
                    CONF_MODEL_CLASS: info.get("model_class", ""),
                },
            )

        options = [
            SelectOptionDict(value=did, label=_label(did, info))
            for did, info in sorted(
                available.items(), key=lambda item: item[1].get("name", "")
            )
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_DID): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)


def _label(did: str, info: dict[str, str]) -> str:
    """Build a dropdown label: name, model class, and a short id."""
    name = info.get("name") or did
    model_class = info.get("model_class")
    # A full did is a UUID — too long for a dropdown, but a prefix is enough to
    # tell two identical models apart.
    short_did = did[:8]
    if model_class:
        return f"{name} [{model_class}] ({short_did})"
    return f"{name} ({short_did})"
