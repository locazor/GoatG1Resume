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
native *resume* command (``act: resume``) on it. One session per account is
preserved.

CAVEAT: reaching into ``entry.runtime_data`` of another integration is not a
supported Home Assistant API. It is a deliberate trade-off — the alternative
is a second cloud login, and Ecovacs allows only one active session per
account. ``_iter_ecovacs_devices`` is written defensively and every deep
attribute access below is guarded; if core reshapes this, the breakage is
confined to this file.

Validated against:
    * Home Assistant core 2026.8.3 (``ecovacs`` integration using
      ``ConfigEntry.runtime_data`` -> ``EcovacsController.devices``).
    * ``deebot-client`` 18.3.0 and 18.5.1 (HA 2026 / Python 3.14). In both:
        - ``CleanAction.RESUME`` exists (``models.CleanAction``); ``.value`` is
          ``"resume"`` for JSON devices, ``.xml_value`` ``"r"`` for XML ones.
        - GOAT G1 (``5xu9h3``) and GOAT A1600 LiDAR Pro (``e4gqia``) both
          declare ``capabilities.clean.action.command = CleanV2``. The two
          hardware modules are byte-identical apart from their docstring.
        - ``Device.execute_command(command)`` dispatches.
        - ``Device.device_info`` is an ``ApiDeviceInfo`` mapping with a ``did``.
        - ``Device.events.get_last_event(StateEvent)`` exposes the live state.
      Note: neither version exposes an in-memory ``__version__`` attribute, so
      the version is read via ``importlib.metadata`` off the event loop.

WHY THE PAUSED GUARD MATTERS (do not weaken it):
    ``deebot_client.commands.json.clean.Clean._execute`` — inherited by
    ``CleanV2`` — rewrites a RESUME into a START whenever the device's last
    ``StateEvent`` is not ``PAUSED``::

        if (self._args["act"] == CleanAction.RESUME.value
                and state.state != State.PAUSED):
            self._args = self._get_args(CleanAction.START)

    A START begins a *new* task and restarts the map, which is exactly what
    this integration exists to avoid. By only dispatching when we have
    positively observed ``PAUSED``, the library sees the same ``PAUSED`` state
    and its rewrite branch is never taken. When no ``StateEvent`` exists at
    all the library's ``if state`` is falsy, so the raw ``act: resume`` goes
    out untouched — also safe. Sending "anyway and letting the library decide"
    would reintroduce the map-restart bug.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import version
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .const import ECOVACS_DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# States from which a "continue" makes sense, by ``deebot_client.models.State``
# member name. The device reports PAUSED when a task is preserved (including
# after it has parked itself on the dock with the app showing "Continue").
#
# Compared by *name* rather than by importing the enum so that a library
# reshuffle degrades to "unknown state" instead of raising at import time.
_RESUMABLE_STATE_NAMES = frozenset({"PAUSED"})

# When the last known state says "not resumable", it may simply be stale — the
# GOAT G1 was observed flapping between docked and paused while sitting on the
# dock with a task still pending. Before skipping, ask the device to re-report
# its state and look once more. This only ever *adds* a resume that would
# otherwise have been skipped; it never turns a resume into a start.
_STATE_RECHECK_DELAY_SECONDS = 1.5


# Cached ``deebot-client`` version string. Resolved exactly once, off the event
# loop (see ``async_get_deebot_client_version``). ``None`` means "not resolved
# yet"; once resolved it is a real version or the literal "unknown".
_deebot_client_version: str | None = None


def _read_deebot_client_version() -> str:
    """Blocking metadata read — MUST run in an executor, never on the loop.

    ``importlib.metadata.version`` performs filesystem I/O (``listdir``/``open``/
    ``read_text`` on the package ``dist-info/METADATA``), which Home Assistant
    forbids on the event loop. Any failure is non-fatal: the version is only
    used for logging/diagnostics, so we fall back to ``"unknown"``.
    """
    try:
        return version("deebot-client")
    except Exception:  # noqa: BLE001 - diagnostics only, never fatal
        return "unknown"


async def async_get_deebot_client_version(hass: HomeAssistant) -> str:
    """Return the installed ``deebot-client`` version without blocking the loop.

    The blocking metadata lookup is run once via the executor and cached for the
    lifetime of the process; subsequent calls are pure cache reads. Safe to call
    from setup, reload, or any service/button handler.
    """
    global _deebot_client_version
    if _deebot_client_version is None:
        _deebot_client_version = await hass.async_add_executor_job(
            _read_deebot_client_version
        )
    return _deebot_client_version


def deebot_client_version() -> str:
    """Return the cached ``deebot-client`` version (or ``"unknown"``).

    Pure, non-blocking cache read — safe to call on the event loop. The cache is
    populated off-loop by ``async_get_deebot_client_version`` (called during
    ``async_setup_entry``). If it has not been resolved yet, returns "unknown"
    rather than performing blocking I/O.
    """
    return _deebot_client_version if _deebot_client_version is not None else "unknown"


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
            for value in data.values() if isinstance(data, dict) else [data]:
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


def _device_info_get(device: Any, key: str) -> Any:
    """Read one key from a Device's ``device_info``, whatever its shape."""
    info = getattr(device, "device_info", None)
    if info is None:
        return None
    # ``device_info`` is an ``ApiDeviceInfo`` TypedDict (a plain dict at runtime).
    if isinstance(info, dict):
        return info.get(key)
    # Extremely defensive: object-style access.
    return getattr(info, key, None)


def _device_did(device: Any) -> str | None:
    """Best-effort extraction of the deebot device id ("did") from a Device."""
    did = _device_info_get(device, "did")
    return did if isinstance(did, str) and did else None


def _device_name(device: Any) -> str | None:
    """Best-effort friendly name for a Device.

    Preference order matters for the config-flow picker. When a mower has no
    nickname set on the Ecovacs account, ``name`` is the *account e-mail* — a
    useless and identical label across every device on the account. The model's
    ``deviceName`` ("GOAT A1600 LiDAR Pro") is far more helpful, so it wins.
    """
    for key in ("nick", "deviceName", "name"):
        value = _device_info_get(device, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _device_model_class(device: Any) -> str | None:
    """Return the Ecovacs model class code ("5xu9h3", "e4gqia", ...).

    Diagnostic only — the command class is always resolved from the device's
    declared capabilities, never from this code.
    """
    value = _device_info_get(device, "class")
    return value if isinstance(value, str) and value else None


def async_list_resumable_devices(hass: HomeAssistant) -> dict[str, dict[str, str]]:
    """Return ``{did: {"name": ..., "model_class": ...}}`` for resumable devices.

    Used by the config flow so the user can pick which mower to add. We only
    include devices that expose a clean *action* capability (i.e. a
    start/pause/resume command), which is true for vacuums and mowers.
    """
    result: dict[str, dict[str, str]] = {}
    for device in _iter_ecovacs_devices(hass):
        if _resume_command_class(device) is None:
            continue
        did = _device_did(device)
        if not did:
            continue
        result[did] = {
            "name": _device_name(device) or did,
            "model_class": _device_model_class(device) or "",
        }
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
    hardcoding, so the right command is used per model. Both the GOAT G1
    (``5xu9h3``) and the GOAT A1600 LiDAR Pro (``e4gqia``) declare ``CleanV2``;
    older vacuums declare plain ``Clean``.
    """
    try:
        # FRAGILE: deep attribute chain into deebot-client's capability model
        # (device.capabilities.clean.action.command). Guarded by AttributeError;
        # if the library reshapes this, this is the line to fix.
        command = device.capabilities.clean.action.command
    except AttributeError:
        return None
    return command if command is not None else None


def _resume_action() -> Any:
    """Return ``CleanAction.RESUME``, verifying the symbol exists at runtime."""
    try:
        from deebot_client.models import CleanAction
    except ImportError as err:  # pragma: no cover - library missing
        raise HomeAssistantError(
            "deebot-client is not installed; the official Ecovacs integration "
            "must be set up for Ecovacs Resume to work."
        ) from err

    action = getattr(CleanAction, "RESUME", None)
    if action is None:  # pragma: no cover - API drift
        raise HomeAssistantError(
            "This version of deebot-client has no CleanAction.RESUME. The "
            "resume/continue command (act: resume) could not be built. Please open "
            "an issue with your deebot-client version "
            f"({deebot_client_version()})."
        )
    return action


def _device_state_name(device: Any) -> str | None:
    """Return the device's last known deebot ``State`` member name.

    ``None`` means "unknown" — no ``StateEvent`` has arrived yet, or the
    library's shape changed. This reads the *deebot-client* state, deliberately
    not the Home Assistant ``lawn_mower`` state string, which is a lossy
    translation of it.
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

    return getattr(getattr(event, "state", None), "name", None)


def _request_state_refresh(device: Any) -> bool:
    """Ask the device to re-report its state. Returns True if the ask landed."""
    try:
        from deebot_client.events import StateEvent

        device.events.request_refresh(StateEvent)
    except Exception:
        _LOGGER.debug("Could not request a state refresh", exc_info=True)
        return False
    return True


async def _async_resolve_state_name(device: Any, name: str) -> str | None:
    """Return the device's state name, re-checking once if it looks stale.

    A state that is neither unknown nor resumable might simply be out of date:
    the GOAT G1 was observed flapping between ``DOCKED`` and ``PAUSED`` while
    sitting on the dock with an unfinished task. Rather than skip on a stale
    reading, request a refresh and look once more.
    """
    state_name = _device_state_name(device)
    if state_name is None or state_name in _RESUMABLE_STATE_NAMES:
        return state_name

    if not _request_state_refresh(device):
        return state_name

    await asyncio.sleep(_STATE_RECHECK_DELAY_SECONDS)
    rechecked = _device_state_name(device)
    if rechecked != state_name:
        _LOGGER.debug(
            "State for '%s' changed on re-check: %s -> %s", name, state_name, rechecked
        )
    return rechecked


async def async_send_resume(hass: HomeAssistant, did: str) -> None:
    """Resolve the deebot Device for ``did`` and dispatch the resume command.

    Mirrors the Ecovacs app's "Continue" button: sends the native
    ``Clean``/``CleanV2`` command with ``CleanAction.RESUME`` (serialized as
    ``act: resume``), which continues the *paused, unfinished* task instead of
    starting a new one.

    Never falls back to starting a new task — see the module docstring. If the
    device is not resumable this logs which state caused the skip and returns.

    Raises ``HomeAssistantError`` for user-facing failures (ecovacs not loaded,
    device not found, command unsupported, dispatch failure).
    """
    device = _find_device(hass, did)
    if device is None:
        raise HomeAssistantError(
            f"Could not find an Ecovacs device with id '{did}'. Is the official "
            "Ecovacs integration loaded and the device online? "
            "(Ecovacs Resume reuses its authenticated session.)"
        )

    name = _device_name(device) or did
    model_class = _device_model_class(device) or "unknown"

    command_class = _resume_command_class(device)
    if command_class is None:
        raise HomeAssistantError(
            f"The Ecovacs device '{name}' (model class '{model_class}') declares no "
            "clean-action capability (capabilities.clean.action.command), so a "
            "resume command cannot be built. This model is not supported by "
            "Ecovacs Resume."
        )

    action = _resume_action()

    # Only dispatch when we have positively observed a paused/resumable state.
    # This is load-bearing: deebot-client silently rewrites RESUME -> START when
    # the device is not paused, which would restart the map. See module docstring.
    state_name = await _async_resolve_state_name(device, name)
    if state_name is not None and state_name not in _RESUMABLE_STATE_NAMES:
        _LOGGER.warning(
            "Skipping resume for '%s' (model class %s): device state is %s, not one "
            "of %s, so there is no paused task to continue. Use "
            "lawn_mower.start_mowing to begin a new task.",
            name,
            model_class,
            state_name,
            ", ".join(sorted(_RESUMABLE_STATE_NAMES)),
        )
        return

    if state_name is None:
        _LOGGER.debug(
            "No state reported yet for '%s'; sending resume unconditionally "
            "(deebot-client leaves act: resume untouched when it has no state)",
            name,
        )

    command = command_class(action)
    # Resolve the version off-loop (cached after first call) for the debug line.
    dc_version = await async_get_deebot_client_version(hass)
    command_name = getattr(type(command), "NAME", "?")
    _LOGGER.info(
        "Sending resume/continue (act: resume) to Ecovacs device '%s' (state=%s)",
        name,
        state_name or "unknown",
    )
    _LOGGER.debug(
        "Resume command: %s name=%s args=%s model_class=%s (deebot-client %s)",
        type(command).__name__,
        command_name,
        getattr(command, "_args", "?"),
        model_class,
        dc_version,
    )

    try:
        await device.execute_command(command)
    except HomeAssistantError:
        raise
    except Exception as err:
        raise HomeAssistantError(
            f"Failed to send resume command to '{name}': {err}"
        ) from err

    # Best-effort: ask the device to refresh its state so HA reflects the change
    # promptly. Never fatal.
    _request_state_refresh(device)
