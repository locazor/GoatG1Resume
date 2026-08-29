"""The Ecovacs Resume integration.

Adds the "continue / resume mowing" capability that the built-in Home
Assistant ``lawn_mower`` platform lacks for Ecovacs robots (see core issue
home-assistant/core#145338). It reuses the authenticated ``deebot-client``
session owned by the official ``ecovacs`` integration (no second login) and
dispatches the native resume command (``act: resume``).

One config entry per mower. Add the integration once per device you want a
Continue button for; the ``ecovacs_resume.resume`` service accepts a normal
Home Assistant target and resolves it to the right device.
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)

from .const import (
    ATTR_DEVICE_ID,
    ATTR_ENTITY_ID,
    CONF_DID,
    CONF_MODEL_CLASS,
    DOMAIN,
    ECOVACS_DOMAIN,
    LEGACY_DOMAIN,
    PLATFORMS,
    SERVICE_RESUME,
)
from .ecovacs_link import async_get_deebot_client_version, async_send_resume

_LOGGER = logging.getLogger(__name__)

# Service schema: with no target we resume every configured mower; otherwise the
# caller may scope the call to specific HA device_id(s) or entity_id(s).
_RESUME_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ENTITY_ID): vol.All(cv.ensure_list, [cv.string]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ecovacs Resume from a config entry."""
    # Defensive ordering check: the official ecovacs integration must be loaded
    # because we reuse its authenticated session.
    if not hass.config_entries.async_entries(ECOVACS_DOMAIN):
        raise HomeAssistantError(
            "The official Ecovacs integration is not configured. Ecovacs Resume "
            "reuses its authenticated session and cannot work without it."
        )

    if hass.config_entries.async_entries(LEGACY_DOMAIN):
        _LOGGER.warning(
            "The old '%s' integration is still installed alongside '%s'. Both will "
            "try to create a Continue button for the same mower. Remove the old one "
            "(Settings > Devices & services) and delete "
            "custom_components/%s. See docs/migration-2.0.md",
            LEGACY_DOMAIN,
            DOMAIN,
            LEGACY_DOMAIN,
        )

    # Resolve the deebot-client version off the event loop (cached thereafter).
    # ``importlib.metadata.version`` does blocking filesystem I/O, which HA
    # forbids on the loop; the version is diagnostic only so failures are
    # non-fatal and fall back to "unknown".
    _LOGGER.debug(
        "Setting up Ecovacs Resume for did=%s model_class=%s (deebot-client %s)",
        entry.data.get(CONF_DID),
        entry.data.get(CONF_MODEL_CLASS) or "unknown",
        await async_get_deebot_client_version(hass),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_service(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove the domain service once the last entry is gone.
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    if not remaining and hass.services.has_service(DOMAIN, SERVICE_RESUME):
        hass.services.async_remove(DOMAIN, SERVICE_RESUME)

    return unload_ok


def _async_register_service(hass: HomeAssistant) -> None:
    """Register the ``ecovacs_resume.resume`` service (once)."""
    if hass.services.has_service(DOMAIN, SERVICE_RESUME):
        return

    async def _handle_resume(call: ServiceCall) -> None:
        dids = _resolve_target_dids(hass, call)
        if not dids:
            raise HomeAssistantError(
                "No Ecovacs Resume device matched this service call. Configure "
                "the integration or target a configured Ecovacs device."
            )
        errors: list[str] = []
        for did in sorted(dids):
            try:
                await async_send_resume(hass, did)
            except HomeAssistantError as err:
                errors.append(str(err))
        if errors:
            raise HomeAssistantError("; ".join(errors))

    hass.services.async_register(
        DOMAIN, SERVICE_RESUME, _handle_resume, schema=_RESUME_SCHEMA
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_RESUME)


def _configured_dids(hass: HomeAssistant) -> set[str]:
    """Return the set of deebot dids configured via this integration."""
    return {
        entry.data[CONF_DID]
        for entry in hass.config_entries.async_entries(DOMAIN)
        if CONF_DID in entry.data
    }


def _resolve_target_dids(hass: HomeAssistant, call: ServiceCall) -> set[str]:
    """Map a service call's targets to deebot device ids ("did").

    * No target -> every configured mower (the common case / the button).
    * ``device_id`` / ``entity_id`` -> resolve to the ecovacs device's did via
      the device & entity registries, then intersect with what's configured
      so we never act on an unrelated ecovacs device by accident.
    """
    device_ids: list[str] = call.data.get(ATTR_DEVICE_ID, []) or []
    entity_ids: list[str] = call.data.get(ATTR_ENTITY_ID, []) or []

    configured = _configured_dids(hass)

    if not device_ids and not entity_ids:
        return set(configured)

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    # Translate entity_ids into their backing HA device_ids. This is what makes
    # targeting `lawn_mower.a1600` (or our own button entity) work.
    resolved_device_ids: set[str] = set(device_ids)
    for entity_id in entity_ids:
        entity = ent_reg.async_get(entity_id)
        if entity and entity.device_id:
            resolved_device_ids.add(entity.device_id)

    dids: set[str] = set()
    for ha_device_id in resolved_device_ids:
        device = dev_reg.async_get(ha_device_id)
        if not device:
            continue
        # The ecovacs integration identifies devices as ("ecovacs", did).
        for domain, identifier in device.identifiers:
            if domain == ECOVACS_DOMAIN:
                dids.add(identifier)

    # Only act on devices this integration is actually configured for.
    scoped = {did for did in dids if did in configured}
    if dids and not scoped:
        _LOGGER.warning(
            "Service call targeted Ecovacs device(s) %s, which are not configured "
            "in Ecovacs Resume. Add a config entry for them first.",
            ", ".join(sorted(dids)),
        )
    return scoped
