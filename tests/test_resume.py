"""Unit tests for the Goatee Continue resume helper.

These tests mock the ``deebot-client`` Device and assert that the correct
resume command object (the device's own clean-action command class, built with
``CleanAction.RESUME`` / ``act: r``) is dispatched via ``execute_command``.

They require ``deebot-client`` to be importable (it is the dependency of the
official Ecovacs integration) but do NOT require Home Assistant core.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from deebot_client.commands.json.clean import Clean, CleanV2
from deebot_client.events import StateEvent
from deebot_client.models import CleanAction, State


# ---------------------------------------------------------------------------
# Minimal Home Assistant shims so ecovacs_link imports without HA installed.
# ---------------------------------------------------------------------------
def _install_ha_stubs() -> None:
    if "homeassistant" in sys.modules:
        return
    ha = types.ModuleType("homeassistant")
    exceptions = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Stub mirroring homeassistant.exceptions.HomeAssistantError."""

    exceptions.HomeAssistantError = HomeAssistantError
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    ha.exceptions = exceptions
    ha.core = core
    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.exceptions"] = exceptions
    sys.modules["homeassistant.core"] = core


_install_ha_stubs()


def _load_ecovacs_link():
    """Load ``ecovacs_link`` (and its ``const`` sibling) without running the
    package ``__init__`` (which pulls in full Home Assistant)."""
    import importlib.util
    import os

    base = os.path.join("custom_components", "goatee_continue")
    pkg = types.ModuleType("goatee_continue")
    pkg.__path__ = [base]
    sys.modules["goatee_continue"] = pkg

    for name in ("const", "ecovacs_link"):
        spec = importlib.util.spec_from_file_location(
            f"goatee_continue.{name}", os.path.join(base, f"{name}.py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"goatee_continue.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules["goatee_continue.ecovacs_link"]


ecovacs_link = _load_ecovacs_link()  # noqa: N816


def _make_device(
    *, did: str, command_class: type, state: State | None
) -> MagicMock:
    """Build a mock deebot Device with the given capability and state."""
    device = MagicMock()
    device.device_info = {"did": did, "name": "Goatee"}

    # capabilities.clean.action.command -> command_class
    device.capabilities.clean.action.command = command_class

    # events.get_last_event(StateEvent) -> StateEvent(state) or None
    def _get_last_event(event_type):
        if event_type is StateEvent and state is not None:
            return StateEvent(state)
        return None

    device.events.get_last_event.side_effect = _get_last_event
    device.execute_command = AsyncMock()
    return device


def _hass_with_devices(*devices: MagicMock) -> MagicMock:
    """Build a mock hass whose ecovacs entry exposes the given devices."""
    hass = MagicMock()
    controller = MagicMock()
    controller.devices = list(devices)
    entry = MagicMock()
    entry.runtime_data = controller
    hass.config_entries.async_entries.return_value = [entry]
    hass.data = {}
    return hass


@pytest.mark.asyncio
async def test_resume_dispatches_cleanv2_resume_for_goat() -> None:
    """A paused GOAT (CleanV2) gets a CleanV2 resume command (act: r)."""
    device = _make_device(did="abc123", command_class=CleanV2, state=State.PAUSED)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    device.execute_command.assert_awaited_once()
    sent = device.execute_command.await_args.args[0]
    assert isinstance(sent, CleanV2)
    assert sent.name == "clean_V2"
    # The serialized payload is the native resume action: act: r.
    assert sent._args == {"act": CleanAction.RESUME.value, "content": {}}
    assert sent._args["act"] == "resume"


@pytest.mark.asyncio
async def test_resume_uses_devices_own_command_class() -> None:
    """Older devices declaring Clean get a Clean resume command, not CleanV2."""
    device = _make_device(did="legacy1", command_class=Clean, state=State.PAUSED)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "legacy1")

    sent = device.execute_command.await_args.args[0]
    assert type(sent) is Clean
    assert sent._args == {"act": "resume"}


@pytest.mark.asyncio
async def test_resume_skips_when_not_paused() -> None:
    """When the device is docked/idle (no paused task) we do nothing harmful."""
    device = _make_device(did="abc123", command_class=CleanV2, state=State.DOCKED)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    device.execute_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_proceeds_when_state_unknown() -> None:
    """With no StateEvent yet, we still attempt resume (library decides)."""
    device = _make_device(did="abc123", command_class=CleanV2, state=None)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    device.execute_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_raises_when_device_missing() -> None:
    """Unknown did -> a clear HomeAssistantError is raised."""
    from homeassistant.exceptions import HomeAssistantError

    hass = _hass_with_devices()  # no devices

    with pytest.raises(HomeAssistantError):
        await ecovacs_link.async_send_resume(hass, "does-not-exist")


def test_list_goat_devices_only_returns_resumable() -> None:
    """Devices without a clean-action capability are excluded from the picker."""
    goat = _make_device(did="goat", command_class=CleanV2, state=State.PAUSED)
    # A device with no clean.action.command capability.
    other = MagicMock()
    other.device_info = {"did": "other", "name": "Sensor"}
    other.capabilities.clean.action.command = None
    hass = _hass_with_devices(goat, other)

    devices = ecovacs_link.async_list_goat_devices(hass)
    assert devices == {"goat": "Goatee"}
