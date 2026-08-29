"""Unit tests for the Ecovacs Resume link helper.

These tests mock the ``deebot-client`` Device and assert that the correct
resume command object (the device's own clean-action command class, built with
``CleanAction.RESUME`` / ``act: resume``) is dispatched via ``execute_command``.

They require ``deebot-client`` to be importable (it is the dependency of the
official Ecovacs integration) but do NOT require Home Assistant core.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

from deebot_client.commands.json.clean import Clean, CleanV2
from deebot_client.events import StateEvent
from deebot_client.models import CleanAction, State
import pytest


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

PACKAGE = "ecovacs_resume"


def _load_ecovacs_link():
    """Load ``ecovacs_link`` without running the package ``__init__``.

    The package ``__init__`` pulls in full Home Assistant, which is not
    installed in this test environment.
    """
    import importlib.util
    import os

    base = os.path.join("custom_components", PACKAGE)
    pkg = types.ModuleType(PACKAGE)
    pkg.__path__ = [base]
    sys.modules[PACKAGE] = pkg

    for name in ("const", "ecovacs_link"):
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.{name}", os.path.join(base, f"{name}.py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{PACKAGE}.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{PACKAGE}.ecovacs_link"]


ecovacs_link = _load_ecovacs_link()


def _make_device(
    *,
    did: str,
    command_class: type | None,
    state: State | None,
    name: str | None = "Goatee",
    device_name: str | None = None,
    model_class: str | None = "5xu9h3",
    states: list[State] | None = None,
) -> MagicMock:
    """Build a mock deebot Device with the given capability and state.

    ``states`` optionally supplies a sequence of states returned on successive
    ``get_last_event(StateEvent)`` calls, to model a device whose reported state
    changes between the first read and the post-refresh re-check.
    """
    device = MagicMock()
    info: dict[str, object] = {"did": did}
    if name is not None:
        info["name"] = name
    if device_name is not None:
        info["deviceName"] = device_name
    if model_class is not None:
        info["class"] = model_class
    device.device_info = info

    # capabilities.clean.action.command -> command_class
    device.capabilities.clean.action.command = command_class

    remaining = list(states) if states is not None else None

    # events.get_last_event(StateEvent) -> StateEvent(state) or None
    def _get_last_event(event_type):
        if event_type is not StateEvent:
            return None
        if remaining is not None:
            current = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            return StateEvent(current) if current is not None else None
        return StateEvent(state) if state is not None else None

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

    # async_add_executor_job(func, *args) -> awaitable running func off-loop.
    async def _run_executor(func, *args):
        return func(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_run_executor)
    return hass


@pytest.fixture(autouse=True)
def _reset_version_cache():
    """Reset the module-global deebot-client version cache between tests."""
    ecovacs_link._deebot_client_version = None
    yield
    ecovacs_link._deebot_client_version = None


@pytest.fixture(autouse=True)
def _fast_state_recheck(monkeypatch):
    """Keep the stale-state re-check delay out of the test runtime."""
    monkeypatch.setattr(ecovacs_link, "_STATE_RECHECK_DELAY_SECONDS", 0)


# ---------------------------------------------------------------------------
# Per-model command class dispatch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resume_dispatches_cleanv2_resume_for_goat() -> None:
    """A paused GOAT (CleanV2) gets a CleanV2 resume command (act: resume)."""
    device = _make_device(did="abc123", command_class=CleanV2, state=State.PAUSED)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    device.execute_command.assert_awaited_once()
    sent = device.execute_command.await_args.args[0]
    assert isinstance(sent, CleanV2)
    assert type(sent).NAME == "clean_V2"
    # The serialized payload is the native resume action: act: resume.
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
async def test_each_device_gets_its_own_command_class() -> None:
    """With a mixed fleet, every mower is dispatched its declared command."""
    goat = _make_device(
        did="e4gqia-did",
        command_class=CleanV2,
        state=State.PAUSED,
        model_class="e4gqia",
    )
    legacy = _make_device(
        did="legacy-did",
        command_class=Clean,
        state=State.PAUSED,
        model_class="oldmodel",
    )
    hass = _hass_with_devices(goat, legacy)

    await ecovacs_link.async_send_resume(hass, "e4gqia-did")
    await ecovacs_link.async_send_resume(hass, "legacy-did")

    assert type(goat.execute_command.await_args.args[0]) is CleanV2
    assert type(legacy.execute_command.await_args.args[0]) is Clean
    # Neither device received the other's command.
    goat.execute_command.assert_awaited_once()
    legacy.execute_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_raises_when_no_clean_action_capability() -> None:
    """A device declaring no clean action fails with a precise message."""
    from homeassistant.exceptions import HomeAssistantError

    device = _make_device(
        did="nocap", command_class=None, state=State.PAUSED, model_class="zzzzzz"
    )
    hass = _hass_with_devices(device)

    with pytest.raises(HomeAssistantError) as excinfo:
        await ecovacs_link.async_send_resume(hass, "nocap")

    message = str(excinfo.value)
    assert "clean-action capability" in message
    assert "zzzzzz" in message
    device.execute_command.assert_not_awaited()


# ---------------------------------------------------------------------------
# Multi-device selection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resume_targets_only_the_requested_device() -> None:
    """Two configured mowers: resuming one must not touch the other."""
    a1600 = _make_device(
        did="did-a1600", command_class=CleanV2, state=State.PAUSED, model_class="e4gqia"
    )
    g1 = _make_device(
        did="did-g1", command_class=CleanV2, state=State.PAUSED, model_class="5xu9h3"
    )
    hass = _hass_with_devices(a1600, g1)

    await ecovacs_link.async_send_resume(hass, "did-a1600")

    a1600.execute_command.assert_awaited_once()
    g1.execute_command.assert_not_awaited()


def test_list_resumable_devices_returns_all_candidates() -> None:
    """Every device with a clean-action capability is offered to the picker."""
    a1600 = _make_device(
        did="did-a1600",
        command_class=CleanV2,
        state=None,
        name="pfosland@duck.com",
        device_name="GOAT A1600 LiDAR Pro",
        model_class="e4gqia",
    )
    g1 = _make_device(
        did="did-g1",
        command_class=CleanV2,
        state=None,
        name="Goatee",
        model_class="5xu9h3",
    )
    hass = _hass_with_devices(a1600, g1)

    devices = ecovacs_link.async_list_resumable_devices(hass)

    assert set(devices) == {"did-a1600", "did-g1"}
    assert devices["did-a1600"]["model_class"] == "e4gqia"
    assert devices["did-g1"]["model_class"] == "5xu9h3"


def test_list_resumable_devices_only_returns_resumable() -> None:
    """Devices without a clean-action capability are excluded from the picker."""
    goat = _make_device(did="goat", command_class=CleanV2, state=State.PAUSED)
    # A device with no clean.action.command capability.
    other = MagicMock()
    other.device_info = {"did": "other", "name": "Sensor"}
    other.capabilities.clean.action.command = None
    hass = _hass_with_devices(goat, other)

    devices = ecovacs_link.async_list_resumable_devices(hass)
    assert set(devices) == {"goat"}


def test_device_name_prefers_nickname_then_model_over_account_email() -> None:
    """A mower with no nickname must not be labelled with the account e-mail."""
    unnamed = _make_device(
        did="x",
        command_class=CleanV2,
        state=None,
        name="pfosland@duck.com",
        device_name="GOAT A1600 LiDAR Pro",
    )
    assert ecovacs_link._device_name(unnamed) == "GOAT A1600 LiDAR Pro"

    nicknamed = _make_device(
        did="y",
        command_class=CleanV2,
        state=None,
        name="pfosland@duck.com",
        device_name="GOAT A1600 LiDAR Pro",
    )
    nicknamed.device_info["nick"] = "Goatee"
    assert ecovacs_link._device_name(nicknamed) == "Goatee"


@pytest.mark.asyncio
async def test_resume_raises_when_device_missing() -> None:
    """Unknown did -> a clear HomeAssistantError is raised."""
    from homeassistant.exceptions import HomeAssistantError

    hass = _hass_with_devices()  # no devices

    with pytest.raises(HomeAssistantError):
        await ecovacs_link.async_send_resume(hass, "does-not-exist")


# ---------------------------------------------------------------------------
# Paused guard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resume_skips_when_not_paused() -> None:
    """When the device is docked/idle (no paused task) we do nothing harmful."""
    device = _make_device(did="abc123", command_class=CleanV2, state=State.DOCKED)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    device.execute_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_logs_the_state_that_caused_it(caplog) -> None:
    """The skip warning must name the state, so flapping is diagnosable."""
    device = _make_device(
        did="abc123", command_class=CleanV2, state=State.DOCKED, model_class="e4gqia"
    )
    hass = _hass_with_devices(device)

    with caplog.at_level("WARNING"):
        await ecovacs_link.async_send_resume(hass, "abc123")

    assert "DOCKED" in caplog.text
    assert "e4gqia" in caplog.text
    device.execute_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_non_paused_state_is_rechecked_after_refresh() -> None:
    """A stale DOCKED reading must not veto a mower that is really paused.

    Models the observed dock flapping: the first read says DOCKED, and after a
    refresh the device reports PAUSED. The resume must go out.
    """
    device = _make_device(
        did="abc123",
        command_class=CleanV2,
        state=None,
        states=[State.DOCKED, State.PAUSED],
    )
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    device.events.request_refresh.assert_called()
    device.execute_command.assert_awaited_once()
    sent = device.execute_command.await_args.args[0]
    assert sent._args["act"] == "resume"


@pytest.mark.asyncio
async def test_paused_state_does_not_trigger_a_recheck() -> None:
    """The happy path must not pay the re-check delay or an extra refresh."""
    device = _make_device(did="abc123", command_class=CleanV2, state=State.PAUSED)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    # Exactly one refresh: the post-dispatch one. No pre-dispatch re-check.
    assert device.events.request_refresh.call_count == 1
    device.execute_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_proceeds_when_state_unknown() -> None:
    """With no StateEvent yet, we still attempt resume.

    Safe because deebot-client only rewrites RESUME->START when it *has* a
    non-paused state; with no state the raw act: resume goes out untouched.
    """
    device = _make_device(did="abc123", command_class=CleanV2, state=None)
    hass = _hass_with_devices(device)

    await ecovacs_link.async_send_resume(hass, "abc123")

    device.execute_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_never_sends_start() -> None:
    """Belt and braces: no code path may emit act: start."""
    for state in (State.PAUSED, None):
        device = _make_device(did="abc123", command_class=CleanV2, state=state)
        hass = _hass_with_devices(device)

        await ecovacs_link.async_send_resume(hass, "abc123")

        sent = device.execute_command.await_args.args[0]
        assert sent._args["act"] == "resume"


# ---------------------------------------------------------------------------
# deebot-client version lookup (must never block the event loop)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_version_lookup_runs_off_loop_via_executor() -> None:
    """The blocking metadata read must go through async_add_executor_job.

    It must never execute on the event loop, and the result is cached after
    the first call.
    """
    hass = _hass_with_devices()

    version = await ecovacs_link.async_get_deebot_client_version(hass)

    # The (blocking) reader was dispatched to the executor exactly once...
    hass.async_add_executor_job.assert_awaited_once()
    assert (
        hass.async_add_executor_job.await_args.args[0]
        is ecovacs_link._read_deebot_client_version
    )
    assert isinstance(version, str) and version  # a real version or "unknown"

    # ...and a second call is served purely from cache (no further executor use).
    again = await ecovacs_link.async_get_deebot_client_version(hass)
    assert again == version
    hass.async_add_executor_job.assert_awaited_once()


def test_sync_version_is_nonblocking_cache_read() -> None:
    """The sync accessor never performs I/O.

    It returns 'unknown' until the async resolver has populated the cache,
    then the cached value.
    """
    assert ecovacs_link._deebot_client_version is None
    assert ecovacs_link.deebot_client_version() == "unknown"

    ecovacs_link._deebot_client_version = "18.5.1"
    assert ecovacs_link.deebot_client_version() == "18.5.1"


def test_reader_never_raises() -> None:
    """The executor-side reader is non-fatal: any failure yields 'unknown'."""
    link = sys.modules[f"{PACKAGE}.ecovacs_link"]

    original = link.version
    try:
        link.version = lambda _name: (_ for _ in ()).throw(RuntimeError("boom"))
        assert link._read_deebot_client_version() == "unknown"
    finally:
        link.version = original
