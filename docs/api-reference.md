# API reference

Authoritative reference generated from the code in
`custom_components/ecovacs_resume/`. Signatures and schemas match the source
exactly.

- [Service: `ecovacs_resume.resume`](#service-ecovacs_resumeresume)
- [Button entity](#button-entity)
- [Config flow](#config-flow)
- [Constants (`const.py`)](#constants-constpy)
- [Helpers (`ecovacs_link.py`)](#helpers-ecovacs_linkpy)
- [Helpers (`__init__.py`)](#helpers-__init__py)
- [Manifest & HACS metadata](#manifest--hacs-metadata)

---

## Service: `ecovacs_resume.resume`

Defined in [`services.yaml`](../custom_components/ecovacs_resume/services.yaml);
the runtime schema is `_RESUME_SCHEMA` in
[`__init__.py`](../custom_components/ecovacs_resume/__init__.py).

```yaml
resume:
  fields:
    device_id:   # optional; selector: device (integration: ecovacs)
    entity_id:   # optional; selector: entity (domain: lawn_mower, integration: ecovacs)
```

Runtime validation:

```python
_RESUME_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_ENTITY_ID): vol.All(cv.ensure_list, [cv.string]),
    }
)
```

| Field | Required | Type (after coercion) | Default behaviour |
| --- | --- | --- | --- |
| `device_id` | no | `list[str]` | — |
| `entity_id` | no | `list[str]` | — |
| *(no target)* | — | — | Resume **all** configured mowers |

**Raises** (`HomeAssistantError`):

- *“No Ecovacs Resume device matched this service call…”* — targets resolved to
  zero configured devices.
- Per-device failures from `async_send_resume` are collected and re-raised joined
  by `"; "`.

---

## Button entity

Class `EcovacsResumeButton(ButtonEntity)` in
[`button.py`](../custom_components/ecovacs_resume/button.py).

| Attribute | Value |
| --- | --- |
| `entity_id` pattern | `button.<mower>_continue` (e.g. `button.a1600_continue`) |
| `_attr_has_entity_name` | `True` |
| `_attr_translation_key` | `"continue"` → friendly name **“Continue”** (`nb`: *“Fortsett”*) |
| `_attr_icon` | `"mdi:play-pause"` |
| `_attr_unique_id` | `f"{did}_continue"` |
| `_attr_device_info` | `DeviceInfo(identifiers={("ecovacs", did)})` — **identifiers only**, so the entity attaches to the existing Ecovacs device instead of defining a second one |

```python
async def async_press(self) -> None:
    """Handle the button press: resume the paused task."""
    await async_send_resume(self.hass, self._did)
```

`async_setup_entry(hass, entry, async_add_entities)` adds exactly one button per
config entry, i.e. one per mower.

---

## Config flow

Class `EcovacsResumeConfigFlow(ConfigFlow, domain="ecovacs_resume")` in
[`config_flow.py`](../custom_components/ecovacs_resume/config_flow.py).
`VERSION = 1`. Single user step:

```python
async def async_step_user(
    self, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult: ...
```

| Behaviour | Detail |
| --- | --- |
| Abort `ecovacs_not_loaded` | no `ecovacs` config entries exist |
| Abort `no_devices` | `async_list_resumable_devices` returned empty |
| Abort `all_configured` | every resumable device already has a config entry |
| Abort `already_configured` | `did` unique id already set up |
| Created entry `title` | the friendly device name |
| Created entry `data` | `{ "did": <did>, "device_name": <name>, "model_class": <class> }` |

The single form field `did` is a `SelectSelector` (dropdown) whose options are
`f"{name} [{model_class}] ({did[:8]})"` for each resumable Ecovacs device that is
**not already configured**. Run the flow again to add another mower.

`name` is resolved as `nick` → `deviceName` → `name`: a mower with no nickname on
the Ecovacs account reports the *account e-mail* as `name`, which would make every
device on the account look identical in the dropdown.

---

## Constants (`const.py`)

| Constant | Value |
| --- | --- |
| `DOMAIN` | `"ecovacs_resume"` |
| `ECOVACS_DOMAIN` | `"ecovacs"` |
| `CONF_DID` | `"did"` |
| `LEGACY_DOMAIN` | `"goatee_continue"` (pre-2.0 domain; detected to warn about a leftover install) |
| `CONF_DEVICE_NAME` | `"device_name"` |
| `CONF_MODEL_CLASS` | `"model_class"` |
| `SERVICE_RESUME` | `"resume"` |
| `ATTR_DEVICE_ID` | `"device_id"` |
| `ATTR_ENTITY_ID` | `"entity_id"` |
| `PLATFORMS` | `["button"]` |

---

## Helpers (`ecovacs_link.py`)

The integration’s only fragile module. Public helpers:

```python
async def async_get_deebot_client_version(hass: HomeAssistant) -> str
```
Returns the installed `deebot-client` version (or `"unknown"`). The blocking
`importlib.metadata` lookup is run **off the event loop** via
`hass.async_add_executor_job(...)` and cached for the process lifetime, so it is
read at most once and never blocks the loop. Diagnostic-only — any failure
yields `"unknown"` and never blocks setup.

```python
def deebot_client_version() -> str
```
Pure, non-blocking read of the cached version (or `"unknown"` if not yet
resolved). Safe to call on the event loop; the cache is warmed by
`async_get_deebot_client_version` during `async_setup_entry`.

```python
def async_list_resumable_devices(hass: HomeAssistant) -> dict[str, dict[str, str]]
```
Returns `{did: {"name": ..., "model_class": ...}}` for every Ecovacs device that
exposes a clean-action capability (i.e. can resume). Used by the config flow.
Devices without `capabilities.clean.action.command` or without a `did` are
excluded.

```python
async def async_send_resume(hass: HomeAssistant, did: str) -> None
```
Resolves the live deebot `Device` for `did` and dispatches the resume command
(`device.execute_command(CleanV2(CleanAction.RESUME))`, payload
`{"act": "resume", "content": {}}` for the GOATs). Idempotent-safe: if the device
is positively **not** paused — after one refresh-and-re-check — it logs a warning
naming the offending state and the model class, then returns without dispatching.
After a successful dispatch it requests a best-effort state refresh.

It **never** falls back to `start_mowing`. Note that this guard is load-bearing:
`deebot-client` rewrites `RESUME` → `START` when the device is not paused, which
would restart the map.

**Raises** `HomeAssistantError` when: the device id can’t be found; the device has
no clean-action capability; `deebot-client`/`CleanAction.RESUME` is missing; or
`execute_command` fails.

Internal (private) helpers, for reference:

| Function | Returns | Purpose |
| --- | --- | --- |
| `_iter_ecovacs_devices(hass)` | `list[Any]` | enumerate authenticated deebot `Device`s via `runtime_data` (+ `hass.data` fallback) |
| `_as_device_list(candidate)` | `list[Any]` | coerce a devices container to a list of real `Device`s |
| `_device_did(device)` | `str \| None` | extract `did` from `device.device_info` |
| `_device_info_get(device, key)` | `Any` | read one key from `device_info`, dict or object shaped |
| `_device_name(device)` | `str \| None` | friendly name: `nick` → `deviceName` → `name` |
| `_find_device(hass, did)` | `Any \| None` | first device whose did matches |
| `_resume_command_class(device)` | `type \| None` | `device.capabilities.clean.action.command` (`Clean`/`CleanV2`) |
| `_resume_action()` | `Any` | `CleanAction.RESUME`, verifying the symbol exists |
| `_device_state_name(device)` | `str \| None` | last deebot `State` member name (e.g. `"PAUSED"`), `None` if unknown |
| `_device_model_class(device)` | `str \| None` | Ecovacs model class code (`"5xu9h3"`, `"e4gqia"`); diagnostic only |
| `_request_state_refresh(device)` | `bool` | ask the device to re-report state; `True` if the ask landed |
| `_async_resolve_state_name(device, name)` | `str \| None` | state name, re-checked once after a refresh if it looks stale |

Module constants:

| Constant | Value | Purpose |
| --- | --- | --- |
| `_RESUMABLE_STATE_NAMES` | `frozenset({"PAUSED"})` | deebot `State` member names that allow a dispatch |
| `_STATE_RECHECK_DELAY_SECONDS` | `1.5` | how long to wait after `request_refresh` before re-reading a non-resumable state |

---

## Helpers (`__init__.py`)

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool
```
Raises `HomeAssistantError` if no `ecovacs` config entry exists, forwards the
`button` platform, and registers the `resume` service.

```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool
```
Unloads platforms and removes the domain service once the last entry is gone.

| Function | Returns | Purpose |
| --- | --- | --- |
| `_async_register_service(hass)` | `None` | register `ecovacs_resume.resume` once |
| `_configured_dids(hass)` | `set[str]` | dids configured via this integration |
| `_resolve_target_dids(hass, call)` | `set[str]` | map a call’s `device_id`/`entity_id` targets to dids (no target → all configured). Targets that resolve to Ecovacs devices which are **not** configured here are dropped, with a warning. |

---

## Manifest & HACS metadata

| Key | `manifest.json` |
| --- | --- |
| `domain` | `ecovacs_resume` |
| `name` | `Ecovacs Resume (continue mowing)` |
| `codeowners` | `["@locazor"]` |
| `config_flow` | `true` |
| `dependencies` | `["ecovacs"]` |
| `iot_class` | `cloud_push` |
| `requirements` | `[]` (deebot-client comes from the ecovacs integration) |
| `version` | `2.0.0` |

| Key | `hacs.json` |
| --- | --- |
| `name` | `Ecovacs Resume (continue mowing)` |
| `content_in_root` | `false` |
| `render_readme` | `true` |
| `homeassistant` | `2024.12.0` |
| `zip_release` | `false` |

---

See also: [usage](usage.md) · [architecture](architecture.md) ·
[development](development.md)
