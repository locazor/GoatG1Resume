# How it works

This page explains the technical background, sourced from the code in this repo
and from the installed `deebot-client` (**18.3.0** and **18.5.1**; HA 2026.8.3
ships 18.5.1). Where this differs from earlier notes, the code wins and the
difference is called out.

- [The Home Assistant limitation (#145338)](#the-home-assistant-limitation-145338)
- [The Ecovacs clean-action codes and `act: resume`](#the-ecovacs-clean-action-codes-and-act-resume)
- [Model classes, `CleanV2`, and the runtime capability lookup](#model-classes-cleanv2-and-the-runtime-capability-lookup)
- [End-to-end: from service/button to the mower](#end-to-end-from-servicebutton-to-the-mower)

---

## The Home Assistant limitation (#145338)

The built-in `ecovacs` integration maps the mower onto Home Assistant’s
`lawn_mower` platform, which only offers `start_mowing`, `pause`, and `dock`.
There is **no “resume”**. Once a task is paused (the app shows
*“Task paused / Continue”* with a mowing-%), calling `lawn_mower.start_mowing`
**starts a brand-new task** — progress resets to ~1% and the previously-planned
coverage is lost.

This is the open core limitation tracked in
**[home-assistant/core#145338](https://github.com/home-assistant/core/issues/145338)**
(*“`vacuum.start` initiates new clean instead of resuming paused state”*;
`send_command: resume` has no effect through the built-in surface).

The resume capability exists in the protocol/library — it is simply not exposed
by the built-in integration. Ecovacs Resume surfaces it.

---

## The Ecovacs clean-action codes and `act: resume`

The mower’s “clean” command carries an **action** named `act`. In
`deebot-client` 18.x the actions are modelled by the `CleanAction` string enum
(`deebot_client/models.py`):

```python
@unique
class CleanAction(StrEnumWithXml):
    START = "start", "s"
    PAUSE = "pause", "p"
    RESUME = "resume", "r"   # <-- the app's "Continue"
    STOP = "stop", "h"
```

The first element is the enum `.value` (the JSON wire value); the second is
`.xml_value`, used only by legacy XML-protocol devices.

So the on-the-wire value for resume is the **full word** `act: resume` — verified
at runtime:

```python
>>> from deebot_client.models import CleanAction
>>> [(a.name, a.value) for a in CleanAction]
[('START', 'start'), ('PAUSE', 'pause'), ('RESUME', 'resume'), ('STOP', 'stop')]
```

> **Note: differs from earlier notes.** Some older notes (and earlier drafts of
> the docstrings) described the action as the single letter **`act: r`**, from the
> legacy `s` / `r` / `p` / `h` table for the *historical* Ecovacs XML protocol.
> Those letters are real, but they are the `.xml_value`s — they do **not** apply to
> JSON devices like the GOATs, whose `CleanAction` `.value`s are full words. The authoritative value this integration
> sends is **`act: resume`**, proven by `tests/test_resume.py`
> (`assert sent._args["act"] == "resume"`). The docstrings in this repo were
> corrected to say `act: resume`.

The library also makes resume safe to send: `Clean._execute` looks at the last
reported state and converts the action if needed —

```python
# deebot_client/commands/json/clean.py (Clean._execute, abridged)
if self._args["act"] == CleanAction.RESUME.value and state.state != State.PAUSED:
    self._args = self._get_args(CleanAction.START)
elif self._args["act"] == CleanAction.START.value and state.state == State.PAUSED:
    self._args = self._get_args(CleanAction.RESUME)
```

`CleanV2` inherits this `_execute`. Read the first branch carefully: if the last
reported state is **not** `PAUSED`, the library **silently rewrites our resume into
a `START`** — which begins a new task and restarts the map. That is precisely the
behaviour this integration exists to prevent, so it must never be relied on as a
safety net; it *is* the hazard.

Ecovacs Resume therefore applies its **own guard first** (see
[the state-guard flowchart](usage.md#the-idempotent-safe-guard)) and only
dispatches once it has positively observed `PAUSED`. The library then sees the
same `PAUSED` state and its rewrite branch is never taken. When no state has been
reported at all, the library's `if state` is falsy and the raw `act: resume` goes
out untouched — also safe. **Do not weaken this guard** on the theory that the
library will do the right thing.

---

## Model classes, `CleanV2`, and the runtime capability lookup

Each Ecovacs model ships a hardware capability file, selected by the model
`class` code the cloud reports for the device. In `deebot-client` 18.x these live
at `deebot_client/hardware/<class>.py` (older releases used
`deebot_client/hardware/deebot/<class>.py`).

Both GOAT mowers validated here wire their clean action to **`CleanV2`**
(not `Clean`):

```python
# deebot_client/hardware/5xu9h3.py  — "DEEBOT GOAT G1 Capabilities."
# deebot_client/hardware/e4gqia.py  — "GOAT A3000 LiDAR Pro."  (the A1600 class)
from deebot_client.commands.json.clean import CleanV2, GetCleanInfoV2
...
action=CapabilityCleanAction(command=CleanV2),
```

The two files are **byte-identical apart from that docstring**, in both 18.3.0
and 18.5.1 — which is why the GOAT A1600 LiDAR Pro needed no new code. (The
upstream docstring says *A3000*; `e4gqia` is nevertheless the class a live A1600
reports. It is cosmetic.)

The two command classes serialize differently:

| Command class | `CleanAction.RESUME` payload (`._args`) | `NAME` |
| --- | --- | --- |
| `Clean` (older models, e.g. T10 PLUS `umwv6z`) | `{"act": "resume"}` | `clean` |
| `CleanV2` (GOAT G1 `5xu9h3`, GOAT A1600 `e4gqia`) | `{"act": "resume", "content": {}}` | `clean_V2` |

`CleanAction.RESUME` is a `StrEnumWithXml` member — `RESUME = "resume", "r"`. The
`.value` (`"resume"`) is what JSON-protocol devices receive; the `"r"` is only the
alias for legacy XML-protocol devices. Both GOATs are JSON devices, so the wire
value is `resume`.

Rather than hardcode `CleanV2`, the integration reads the command class straight
from the device's declared capabilities, so the correct class is used per model:

```python
# custom_components/ecovacs_resume/ecovacs_link.py
def _resume_command_class(device: Any) -> type | None:
    """Return the clean-action command class for this device (Clean/CleanV2)."""
    try:
        command = device.capabilities.clean.action.command
    except AttributeError:
        return None
    return command if command is not None else None
```

If a device declares no clean action at all, `async_send_resume` raises a
`HomeAssistantError` naming the device and its model class rather than guessing.

This is also the filter the config flow uses: a device is only offered in the
picker if it exposes `capabilities.clean.action.command` (true for vacuums and
mowers, false for sensor-only devices).

---

## End-to-end: from service/button to the mower

1. A user, automation, or dashboard calls **`ecovacs_resume.resume`** (or presses
   **`button.<name>_continue`**).
2. `__init__.py` resolves the call’s target(s) to one or more deebot device ids
   (“did”) via `_resolve_target_dids`, then calls
   `ecovacs_link.async_send_resume(hass, did)` for each.
3. `ecovacs_link` reaches into the official `ecovacs` integration’s
   `entry.runtime_data` (an `EcovacsController`), enumerates its authenticated
   `deebot_client` `Device` objects, and finds the one whose `did` matches.
4. It reads that device’s clean-action command class
   (`device.capabilities.clean.action.command` → `CleanV2` for the GOAT), checks
   the device is in a resumable (paused) state, then dispatches
   `await device.execute_command(CleanV2(CleanAction.RESUME))`.
5. `deebot-client` sends `act: resume` to the Ecovacs cloud, which tells the mower
   to continue the paused task. A best-effort state refresh is requested so HA
   reflects the change promptly.

The full sequence (with the guard and error branches) is in
[docs/architecture.md](architecture.md#sequence-of-a-resume-call).

---

See also: [architecture](architecture.md) · [usage](usage.md) ·
[API reference](api-reference.md) · [troubleshooting](troubleshooting.md)
