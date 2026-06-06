"""Constants for the Goatee Continue integration."""

from __future__ import annotations

from typing import Final

# This integration's domain.
DOMAIN: Final = "goatee_continue"

# Domain of the official Home Assistant Ecovacs integration we piggy-back on.
ECOVACS_DOMAIN: Final = "ecovacs"

# Config entry data keys.
# The Ecovacs/deebot device id ("did") is the stable identifier we persist.
CONF_DID: Final = "did"
# A human friendly name (defaults to the deebot device name, e.g. "Goatee").
CONF_DEVICE_NAME: Final = "device_name"

# Service exposed by this integration: ``goatee_continue.resume``.
SERVICE_RESUME: Final = "resume"

# Optional service call fields used to target a specific device/entity.
ATTR_DEVICE_ID: Final = "device_id"
ATTR_ENTITY_ID: Final = "entity_id"

# Platforms this integration forwards config entries to.
PLATFORMS: Final = ["button"]
