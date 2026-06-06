"""Bridge to the official Home Assistant ``ecovacs`` integration.

This is the *only* module that reaches into another integration's runtime
data and into the reverse-engineered ``deebot-client`` API. Everything that
is fragile and version dependent is isolated here on purpose, so that when
Home Assistant core or ``deebot-client`` change their internals, there is a
single, small, well-commented place to fix.

Architecture (Option A): we do **not** create a second Ecovacs cloud login.
We locate the already-authenticated ``deebot_client.device.Device`` object
that the official ``ecovacs`` integration created and stored on its config
entry's ``runtime_data`` (an ``EcovacsController``), and we dispatch the
native *resume* command (``act: r``) on it. One session per account is
preserved.

Validated against:
    * Home Assistant core ~2026 (``ecovacs`` integration using
      ``ConfigEntry.runtime_data`` -> ``EcovacsController.devices``).
    * ``deebot-client`` 6.0.2
        - ``CleanAction.RESUME`` exists (``models.CleanAction``, value ``"resume"``).
        - GOAT G1 (model ``5xu9h3``) declares
          ``capabilities.clean.action.command = CleanV2``.
        - ``Device.execute_command(command)`` dispatches.
        - ``Device.device_info`` is an ``ApiDeviceInfo`` mapping with a ``did``.
        - ``Device.events.get_last_event(StateEvent)`` exposes the live state.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .const import ECOVACS_DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# deebot-client State enum value for "paused"; imported lazily so that merely
# loading this module never hard-fails if the library layout changes.
_PAUSED_STATE_NAMES = {"PAUSED"}
# States from which a "continue" makes sense. The device reports PAUSED when a
# task is preserved (including after it has parked itself on the dock with the
# app showing "Task paused / Continue").
_RESUMABLE_STATE_NAMES = {"PAUSED"}


def deebot_client_version() -> str:
    """Return the installed ``deebot-client`` version (or ``"unknown"``)."""
    try:
        return version("deebot-client")
    except PackageNotFoundError:  # pragma: no cover - defensive
        return "unknown"


def _iter_ecovacs_devices(hass: HomeAssistant) -> list[Any]:
    """Return every authenticated ``deebot-client`` Device known to ecovacs.

    Defensive against the exact storage shape: the modern integration stores an
    ``EcovacsController`` on ``entry.runtime_data`` exposing a ``devices``
    attribute (list or callable). We also fall back to ``hass.data[ecovacs]``.
    """
    devices: list[Any] = []

    for entry in hass.config_entries.async_entries(ECOVACS_DOMAIN):
        controller = getattr(entry, "runtime_data", None)
        if controller is None:
            continue
        candidate = getattr(controller, "devices", None)
        # ``devices`` may be a plain list/property or, in some versions, a
        # callable that optionally filters by capability.
        if callable(candidate):
            try:
                candidate = candidate()
            except TypeError:  # pragma: no cover - signature mismatch
                candidate = None
        if candidate:
            devices.extend(_as_device_list(candidate))

    if not devices:
        # Legacy/alternative storage location.
        data = hass.data.get(ECOVACS_DOMAIN)
        if data:
            for value in (data.values() if isinstance(data, dict) else [data]):
                controller_devices = getattr(value, "devices", None)
                if callable(controller_devices):
                    try:
                        controller_devices = controller_devices()
                    except TypeError:  # pragma: no cover
                        controller_devices = None
                if controller_devices:
                    devices.extend(_as_device_list(controller_devices))

    return devices


def _as_device_list(candidate: Any) -> list[Any]:
    """Coerce a devices container into a list, keeping only real Devices."""
    try:
        items = list(candidate)
    except TypeError:  # pragma: no cover - not iterable
        return []
    # Keep only objects that look like a deebot Device (have device_info).
    return [item for item in items if hasattr(item, "device_info")]


def _device_did(device: Any) -> str | None:
    """Best-effort extraction of the deebot device id ("did") from a Device."""
    info = getattr(device, "device_info", None)
    if info is None:
        return None
    # ``device_info`` is an ``ApiDeviceInfo`` TypedDict (a plain dict at runtime).
    if isinstance(info, dict):
        return info.get("did")
    # Extremely defensive: object-style access.
    return getattr(info, "did", None)


def _device_name(device: Any) -> str | None:
    """Best-effort extraction of the friendly device name from a Device."""
    info = getattr(device, "device_info", None)
    if isinstance(info, dict):
        return info.get("nick") or info.get("name")
    return getattr(info, "name", None)


def async_list_goat_devices(hass: HomeAssistant) -> dict[str, str]:
    """Return ``{did: friendly_name}`` for ecovacs devices that can resume.

    Used by the config flow so the user can pick which device is their GOAT.
    We only include devices that expose a clean *action* capability (i.e. a
    start/pause/resume command), which is true for vacuums and mowers.
    """
    result: dict[str, str] = {}
    for device in _iter_ecovacs_devices(hass):
        if _resume_command_class(device) is None:
            continue
        did = _device_did(device)
        if not did:
            continue
        result[did] = _device_name(device) or did
    return result


def _find_device(hass: HomeAssistant, did: str) -> Any | None:
    """Return the live deebot Device whose did matches, or ``None``."""
    for device in _iter_ecovacs_devices(hass):
        if _device_did(device) == did:
            return device
    return None


def _resume_command_class(device: Any) -> type | None:
    """Return the clean-action command class for this device (Clean/CleanV2).

    We read it from the device's own declared capabilities instead of
    hardcoding, so the right command is used per model (the GOAT G1 uses
    ``CleanV2``; older devices use ``Clean``).
    """
    try:
        return device.capabilities.clean.action.command
    except AttributeError:
        return None


def _resume_action() -> Any:
    """Return ``CleanAction.RESUME``, verifying the symbol exists at runtime."""
    try:
        from deebot_client.models import CleanAction
    except ImportError as err:  # pragma: no cover - library missing
        raise HomeAssistantError(
            "deebot-client is not installed; the official Ecovacs integration "
            "must be set up for Goatee Continue to work."
        ) from err

    action = getattr(CleanAction, "RESUME", None)
    if action is None:  # pragma: no cover - API drift
        raise HomeAssistantError(
            "This version of deebot-client has no CleanAction.RESUME. The "
            "resume/continue command (act: r) could not be built. Please open "
            "an issue with your deebot-client version "
            f"({deebot_client_version()})."
        )
    return action


def _device_is_resumable(device: Any) -> bool | None:
    """Return True/False if the device is in a resumable (paused) state.

    Returns ``None`` if the state is unknown (no StateEvent yet), in which case
    callers should proceed and let the device/library decide.
    """
    try:
        from deebot_client.events import StateEvent
    except ImportError:  # pragma: no cover
        return None

    try:
        event = device.events.get_last_event(StateEvent)
    except Exception:  # noqa: BLE001 - defensive against API drift
        return None

    if event is None:
        return None

    state = getattr(event, "state", None)
    state_name = getattr(state, "name", None)
    if state_name is None:
        return None
    return state_name in _RESUMABLE_STATE_NAMES


async def async_send_resume(hass: HomeAssistant, did: str) -> None:
    """Resolve the deebot Device for ``did`` and dispatch the resume command.

    Mirrors the Ecovacs app's "Continue" button: sends the native
    ``Clean``/``CleanV2`` command with ``CleanAction.RESUME`` (``act: r``),
    which continues the *paused, unfinished* task instead of starting a new one.

    Raises ``HomeAssistantError`` for user-facing failures (ecovacs not loaded,
    device not found, command unsupported, dispatch failure).
    """
    device = _find_device(hass, did)
    if device is None:
        raise HomeAssistantError(
            f"Could not find an Ecovacs device with id '{did}'. Is the official "
            "Ecovacs integration loaded and the device online? "
            "(Goatee Continue reuses its authenticated session.)"
        )

    command_class = _resume_command_class(device)
    if command_class is None:
        raise HomeAssistantError(
            f"The Ecovacs device '{_device_name(device) or did}' does not expose "
            "a clean-action capability, so a resume command cannot be built."
        )

    action = _resume_action()

    # Idempotent-safe: if we positively know the device is NOT paused, skip.
    # The library additionally guards this (it converts RESUME->START when the
    # device is not paused), but skipping here avoids any accidental restart and
    # gives the user a clear log line.
    resumable = _device_is_resumable(device)
    name = _device_name(device) or did
    if resumable is False:
        _LOGGER.warning(
            "Skipping resume for '%s': device is not in a paused/resumable state "
            "(nothing to continue). Use lawn_mower.start_mowing to begin a new task.",
            name,
        )
        return

    command = command_class(action)
    _LOGGER.info("Sending resume/continue (act: r) to Ecovacs device '%s'", name)
    _LOGGER.debug(
        "Resume command: %s name=%s args=%s (deebot-client %s)",
        type(command).__name__,
        getattr(command, "name", "?"),
        getattr(command, "_args", "?"),
        deebot_client_version(),
    )

    try:
        await device.execute_command(command)
    except HomeAssistantError:
        raise
    except Exception as err:  # noqa: BLE001 - surface library errors to the user
        raise HomeAssistantError(
            f"Failed to send resume command to '{name}': {err}"
        ) from err

    # Best-effort: ask the device to refresh its state so HA reflects the change
    # promptly. Never fatal.
    try:
        from deebot_client.events import StateEvent

        device.events.request_refresh(StateEvent)
    except Exception:  # noqa: BLE001 - purely cosmetic
        _LOGGER.debug("Could not request a state refresh after resume", exc_info=True)
