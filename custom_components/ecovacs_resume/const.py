"""Constants for the Ecovacs Resume integration."""

from __future__ import annotations

from typing import Final

# This integration's domain.
#
# Renamed in 2.0.0 from the G1-specific "goatee_continue". See
# docs/migration-2.0.md — there is no automatic migration, users remove the old
# integration and add this one.
DOMAIN: Final = "ecovacs_resume"

# The pre-2.0.0 domain. Only used to detect a leftover install and warn.
LEGACY_DOMAIN: Final = "goatee_continue"

# Domain of the official Home Assistant Ecovacs integration we piggy-back on.
ECOVACS_DOMAIN: Final = "ecovacs"

# Config entry data keys.
# The Ecovacs/deebot device id ("did") is the stable identifier we persist.
CONF_DID: Final = "did"
# A human friendly name (the mower's nickname, or its model name).
CONF_DEVICE_NAME: Final = "device_name"
# The Ecovacs model class code (e.g. "5xu9h3" for a GOAT G1, "e4gqia" for a
# GOAT A1600 LiDAR Pro). Diagnostic only: dispatch is decided at runtime from
# the device's declared capabilities, never from this value.
CONF_MODEL_CLASS: Final = "model_class"

# Service exposed by this integration: ``ecovacs_resume.resume``.
SERVICE_RESUME: Final = "resume"

# Optional service call fields used to target a specific device/entity.
ATTR_DEVICE_ID: Final = "device_id"
ATTR_ENTITY_ID: Final = "entity_id"

# Platforms this integration forwards config entries to.
PLATFORMS: Final = ["button"]
