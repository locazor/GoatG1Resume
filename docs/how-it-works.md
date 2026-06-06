# How it works

This page explains the technical background, sourced from the code in this repo
and from the installed `deebot-client` **6.0.2**. Where this differs from earlier
notes, the code wins and the difference is called out.

- [The Home Assistant limitation (#145338)](#the-home-assistant-limitation-145338)
- [The Ecovacs clean-action codes and `act: resume`](#the-ecovacs-clean-action-codes-and-act-resume)
- [Model `5xu9h3`, `CleanV2`, and the runtime capability lookup](#model-5xu9h3-cleanv2-and-the-runtime-capability-lookup)
- [End-to-end: from service/button to the mower](#end-to-end-from-servicebutton-to-the-mower)

---

## The Home Assistant limitation (#145338)

The built-in `ecovacs` integration maps the GOAT onto Home Assistant’s
`lawn_mower` platform, which only offers `start_mowing`, `pause`, and `dock`.
There is **no “resume”**. On the GOAT G1, once a task is paused (the app shows
*“Task paused / Continue”* with a mowing-%), calling `lawn_mower.start_mowing`
**starts a brand-new task** — progress resets to ~1% and the previously-planned
coverage is lost.

This is the open core limitation tracked in
**[home-assistant/core#145338](https://github.com/home-assistant/core/issues/145338)**
(*“`vacuum.start` initiates new clean instead of resuming paused state”*;
`send_command: resume` has no effect through the built-in surface).

The resume capability exists in the protocol/library — it is simply not exposed
by the built-in integration. Goatee Continue surfaces it.

---

## The Ecovacs clean-action codes and `act: resume`

The mower’s “clean” command carries an **action** named `act`. In
`deebot-client` 6.0.2 the actions are modelled by the `CleanAction` string enum
(`deebot_client/models.py`):

```python
@unique
class CleanAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"   # <-- the app's "Continue"
    STOP = "stop"
```

So the on-the-wire value for resume is the **full word** `act: resume` — verified
at runtime:

```python
>>> from deebot_client.models import CleanAction
>>> [(a.name, a.value) for a in CleanAction]
[('START', 'start'), ('PAUSE', 'pause'), ('RESUME', 'resume'), ('STOP', 'stop')]
```

> **Note: differs from earlier notes.** Some older notes (and earlier drafts of
> the docstrings) described the action as the single letter **`act: r`**, and a
> legacy `s` / `r` / `p` / `h` table circulated for the *historical* Ecovacs XML
> protocol. That does **not** match `deebot-client` 6.0.2’s JSON commands, whose
> `CleanAction` values are full words. The authoritative value this integration
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

— i.e. a `RESUME` is honoured precisely when there is a paused task to continue,
and degrades to `START` otherwise. `CleanV2` inherits this `_execute` guard.
Goatee Continue adds its **own** earlier guard on top (see
[the state-guard flowchart](usage.md#the-idempotent-safe-guard)) so it can skip
with a clear log line instead of relying solely on the library.

---

## Model `5xu9h3`, `CleanV2`, and the runtime capability lookup

Each Ecovacs model ships a hardware capability file. The **GOAT G1** is model
**`5xu9h3`** — `deebot_client/hardware/deebot/5xu9h3.py`, header
*“DEEBOT GOAT G1 Capabilities”* — and it wires its clean action to **`CleanV2`**
(not `Clean`):

```python
# deebot_client/hardware/deebot/5xu9h3.py (abridged)
"""DEEBOT GOAT G1 Capabilities."""
from deebot_client.commands.json.clean import CleanV2, GetCleanInfoV2
...
action=CapabilityCleanAction(command=CleanV2),
```

The two command classes serialize differently:

| Command class | `CleanAction.RESUME` payload (`._args`) | `name` |
| --- | --- | --- |
| `Clean` (older models, e.g. T10 PLUS `umwv6z`) | `{"act": "resume"}` | `clean` |
| `CleanV2` (GOAT G1 `5xu9h3`) | `{"act": "resume", "content": {}}` | `clean_V2` |

> **Note: differs from earlier notes.** An earlier brief guessed the GOAT’s model
> code as `umwv6z`. In `deebot-client` 6.0.2 that file is actually the **T10 PLUS**
> (which uses `Clean`). The GOAT G1 is model **`5xu9h3`** and uses **`CleanV2`**.

Rather than hardcode `CleanV2`, the integration reads the command class straight
from the device’s declared capabilities, so the correct class is used per model:

```python
# custom_components/goatee_continue/ecovacs_link.py
def _resume_command_class(device: Any) -> type | None:
    """Return the clean-action command class for this device (Clean/CleanV2)."""
    try:
        return device.capabilities.clean.action.command
    except AttributeError:
        return None
```

This is also the filter the config flow uses: a device is only offered as a
“GOAT” if it exposes `capabilities.clean.action.command` (true for vacuums and
mowers, false for sensor-only devices).

---

## End-to-end: from service/button to the mower

1. A user, automation, or dashboard calls **`goatee_continue.resume`** (or presses
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
