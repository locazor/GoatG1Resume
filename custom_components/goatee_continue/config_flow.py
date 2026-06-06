"""Config flow for Goatee Continue."""

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

from .const import CONF_DEVICE_NAME, CONF_DID, DOMAIN, ECOVACS_DOMAIN
from .ecovacs_link import async_list_goat_devices


class GoateeContinueConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Goatee Continue."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick which Ecovacs device is the GOAT."""
        # The official ecovacs integration must be set up first; we reuse it.
        if not self.hass.config_entries.async_entries(ECOVACS_DOMAIN):
            return self.async_abort(reason="ecovacs_not_loaded")

        devices = async_list_goat_devices(self.hass)
        if not devices:
            return self.async_abort(reason="no_devices")

        if user_input is not None:
            did = user_input[CONF_DID]
            await self.async_set_unique_id(did)
            self._abort_if_unique_id_configured()
            name = devices.get(did, did)
            return self.async_create_entry(
                title=name,
                data={CONF_DID: did, CONF_DEVICE_NAME: name},
            )

        options = [
            SelectOptionDict(value=did, label=f"{name} ({did})")
            for did, name in devices.items()
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
