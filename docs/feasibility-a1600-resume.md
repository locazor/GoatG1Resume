# Feasibility: resume ("Continue") on the GOAT A1600 LiDAR Pro

**Verdict: YES.** The A1600 LiDAR Pro (`e4gqia`) supports resume through exactly the
same code path as the GOAT G1 (`5xu9h3`). No model-specific work is required.

| Item | Value |
| --- | --- |
| Model | GOAT A1600 LiDAR Pro |
| Ecovacs model class (`class`) | `e4gqia` |
| Internal model string | `GOAT_INT_A1600_LIDAR_PLUS_EU` |
| `UILogicId` | `goatl_ww_h_goat2plus` |
| Firmware seen | 1.13.10 |
| `capabilities.clean.action.command` | `CleanV2` |
| `CleanAction.RESUME` | present (`"resume"`) |
| Emitted payload | `clean_V2` / `{"act": "resume", "content": {}}` |

## Sources used

Both **static** (the installed library class file) and **live** (the running Home
Assistant) evidence were used:

* **Live** — the ecovacs config-entry diagnostics dump from the running HA instance
  reports the device as `"class": "e4gqia"`, `"deviceName": "GOAT A1600 LiDAR Pro"`,
  `"model": "GOAT_INT_A1600_LIDAR_PLUS_EU"`. That `class` value is the key
  `deebot-client` uses to select the hardware capability module, so it pins exactly
  which declaration below applies.
* **Static** — `deebot_client/hardware/e4gqia.py`, read from both **18.3.0** (the
  version in this repo's dev venv) and **18.5.1**.

The live deebot-client `Capabilities` object itself cannot be introspected remotely
(there is no HA service that evaluates arbitrary Python), so the capability
declarations below are read from the library source that the live `class` selects.

> ### Environment correction
>
> The task described the target as HA Core 2026.6.0 / deebot-client 18.3.0. The
> **live** system actually reports:
>
> * Home Assistant Core **2026.8.3**, HAOS **18.2**, Python **3.14.6**
> * `ecovacs` integration manifest requirement: **`deebot-client==18.5.1`**
>
> This matters: 18.5.1 declares one capability that 18.3.0 does not (see
> [Zone / map observation](#4-zone--map-observation)). Everything relevant to
> *resume* is identical in both, so the verdict is unaffected — but the docs and the
> supported-models table now record 18.5.1 as the validated version.

## 1. `e4gqia` capability declaration

`deebot_client/hardware/e4gqia.py` is **byte-identical to `5xu9h3.py` except for the
module docstring** — in 18.3.0 *and* in 18.5.1:

```console
$ diff -u deebot_client/hardware/5xu9h3.py deebot_client/hardware/e4gqia.py
--- 5xu9h3.py
+++ e4gqia.py
@@ -1,4 +1,4 @@
-"""DEEBOT GOAT G1 Capabilities."""
+"""GOAT A3000 LiDAR Pro."""
```

(Note the upstream docstring says *A3000*; the `class` code `e4gqia` is nevertheless
what the live A1600 reports. The docstring is cosmetic and has no runtime effect.)

Also note the file lives at `deebot_client/hardware/<class>.py` in these versions —
**not** `deebot_client/hardware/deebot/<class>.py` as in older releases.

The parts that matter, verbatim from `e4gqia.py`:

```python
def get_device_info() -> StaticDeviceInfo:
    """Get device info for this model."""
    return StaticDeviceInfo(
        DataType.JSON,
        Capabilities(
            device_type=DeviceType.MOWER,
            ...
            charge=CapabilityExecute(Charge),
            clean=CapabilityClean(
                action=CapabilityCleanAction(command=CleanV2),   # 18.3.0
            ),
            ...
            state=CapabilityEvent(StateEvent, [GetChargeState(), GetCleanInfoV2()]),
            stats=CapabilityStats(
                clean=CapabilityEvent(StatsEvent, [GetStats()]),
                report=CapabilityEvent(ReportStatsEvent, []),
                total=CapabilityEvent(TotalStatsEvent, [GetTotalStats()]),
            ),
        ),
    )
```

Resolved at runtime against 18.3.0:

```console
data_type            : j                       # DataType.JSON
device_type          : mower                   # DeviceType.MOWER
clean.action.command : <class 'deebot_client.commands.json.clean.CleanV2'>
clean.action.area    : None                    # 18.3.0 (see below — 18.5.1 differs)
capabilities.map     : None
station / water      : None None
```

Settings/state/stats capabilities are identical to the G1: `advanced_mode`,
`border_switch`, `cut_direction`, `child_lock`, `moveup_warning`,
`cross_map_border_warning`, `safe_protect`, `true_detect`, `volume`; life-span types
`BLADE` and `LENS_BRUSH`; state via `GetChargeState()` + `GetCleanInfoV2()`.

**There are no capability differences between `5xu9h3` and `e4gqia`.** Despite the
A1600 navigating by LiDAR rather than the G1's camera + beacons, the declared
capability surface — including `true_detect` and `lens_brush` — is the same.

## 2. `CleanAction.RESUME` in the installed library

`deebot_client/models.py`, **identical in 18.3.0 and 18.5.1**:

```python
@unique
class CleanAction(StrEnumWithXml):
    """Enum class for all possible clean actions."""

    START = "start", "s"
    PAUSE = "pause", "p"
    RESUME = "resume", "r"
    STOP = "stop", "h"
```

`StrEnumWithXml` stores the first element as the enum `.value` (used by the JSON
protocol) and the second as `.xml_value` (used only by the legacy XML protocol):

```python
class StrEnumWithXml(StrEnum):
    def __new__(cls, value: str, xml_value: str | None = None) -> Self:
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.xml_value = xml_value
        return obj
```

The A1600 is a **JSON** device (`DataType.JSON`), so the wire value is `"resume"`,
not `"r"`. `"r"` would only appear on an XML-protocol device.

`CleanV2` in `deebot_client/commands/json/clean.py`:

```python
class CleanV2(Clean):
    """Clean V2 command."""

    NAME = "clean_V2"

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        content: dict[str, str] = {}
        args = {"act": action.value, "content": content}
        match action:
            case CleanAction.START:
                content["type"] = CleanMode.AUTO.value
            case CleanAction.STOP | CleanAction.PAUSE:
                content["type"] = ""
        return args
```

`RESUME` matches no `case`, so `content` stays empty — which is correct: a resume
carries no new job parameters, it continues the job the mower already has.

## 3. Verdict and exact construction

Yes — `CleanV2(CleanAction.RESUME)` can be dispatched to this device. Verified by
constructing it against the installed library:

```python
from deebot_client.hardware.e4gqia import get_device_info
from deebot_client.models import CleanAction

caps = get_device_info().capabilities
command = caps.clean.action.command(CleanAction.RESUME)   # -> CleanV2
```

```console
NAME  : clean_V2
_args : {'act': 'resume', 'content': {}}
```

Dispatched via the already-authenticated device from the official integration:

```python
await device.execute_command(command)
```

The integration keeps reading the class from
`device.capabilities.clean.action.command` rather than hard-coding `CleanV2`, so a
model declaring plain `Clean` still gets `{"act": "resume"}` and a future model
declaring something else still works.

### The library silently rewrites RESUME to START

This is the single most important finding for correctness, and it is unchanged in
both 18.3.0 and 18.5.1. `CleanV2` inherits `_execute` from `Clean`:

```python
async def _execute(self, authenticator, device_info, event_bus):
    state = event_bus.get_last_event(StateEvent)
    if state and isinstance(self._args, dict):
        if (
            self._args["act"] == CleanAction.RESUME.value
            and state.state != State.PAUSED
        ):
            self._args = self._get_args(CleanAction.START)      # <-- restarts the map
        elif (
            self._args["act"] == CleanAction.START.value
            and state.state == State.PAUSED
        ):
            self._args = self._get_args(CleanAction.RESUME)
    return await super()._execute(authenticator, device_info, event_bus)
```

If the device's last `StateEvent` is anything other than `PAUSED`, the library turns
our resume into a **`START`**, which begins a new task and restarts the map — exactly
the behaviour this integration exists to avoid.

The integration's own pre-dispatch guard is what prevents this: we only dispatch when
the last `StateEvent` **is** `PAUSED`, so the library sees the same `PAUSED` state and
its rewrite branch is never taken. When no `StateEvent` exists at all, `if state`
is falsy and the raw `act: resume` goes out untouched, which is also safe.

**The guard is therefore load-bearing, not merely cosmetic.** Loosening it to "send
anyway and let the library decide" would reintroduce the map-restart bug.

## 4. Zone / map observation

`capabilities.map` is **`None`** for `e4gqia` in both 18.3.0 and 18.5.1 — the module
never passes a `map=` argument and `Capabilities.map` defaults to `None`. So there is
no map, no room/subset discovery, and no map-derived zone list, LiDAR
notwithstanding.

`clean.action.area`, however, **changed between the two versions**:

```console
# 18.3.0
clean=CapabilityClean(action=CapabilityCleanAction(command=CleanV2))
clean.action.area -> None

# 18.5.1
clean=CapabilityClean(action=CapabilityCleanAction(command=CleanV2, area=CleanAreaV2))
clean.action.area -> <class 'deebot_client.commands.json.clean.CleanAreaV2'>
```

Upstream added `area=CleanAreaV2` to `5xu9h3` **and** `e4gqia` alike, so this is not
an A1600-specific gain — the G1 got it too. 18.5.1 also adds a new
`CleanMode.FREE_CLEAN = "freeClean"` and teaches `CleanAreaV2` to prefix the pass
count for that mode.

**Flagged for possible future work (not implemented):** on deebot-client >= 18.5.1 a
custom-area mow looks constructible as

```python
caps.clean.action.area(CleanMode.CUSTOM_AREA, [x1, y1, x2, y2], 1)
# -> clean_V2 {"act": "start", "content": {"type": "customArea", "value": "x1,y1,x2,y2"}}
```

Caveats before anyone builds on this:

* With `capabilities.map is None` there is **no way to discover coordinates from HA** —
  the user would have to supply raw map coordinates by hand.
* It is `act: start`, so it **starts a new task**. It is not a resume and must not be
  wired into the resume path.
* Completely unverified on real hardware. Upstream declaring a capability is not
  proof the firmware honours it.

## 5. Must be confirmed on the live A1600

Everything above is verified from source and from the live device registry. The
following is **behavioural** and cannot be proven without running the mower:

1. **That resume continues rather than restarts.** The test: pause a partially
   completed mow, press *Continue*, then check that
   * the Ecovacs app's mowed-% **keeps climbing from where it was** rather than
     resetting to 0, and
   * `sensor.a1600_area_mowed` **does not reset** to `0.0`.

   A reset on either indicator means the firmware treated the resume as a new task,
   and this integration's core premise fails for this model.
2. **That the A1600 reports `State.PAUSED` when parked on the dock with a task still
   pending.** The G1 flapped between docked and paused in this situation. If the
   A1600 reports `DOCKED` while the app still offers "Continue", the guard will skip
   a legitimate resume — the skip is logged with the exact state name, so the log
   will say so plainly. Do not "fix" this by weakening the guard; see the
   RESUME-to-START warning above.
3. **That the resume survives a dock-and-recharge cycle** (mower returns to charge
   mid-task, then resumes) — untested on this model.

## Appendix: live device record

From the `ecovacs` config-entry diagnostics dump (credentials redacted by HA):

```json
{
  "class": "e4gqia",
  "company": "eco-ng",
  "deviceName": "GOAT A1600 LiDAR Pro",
  "model": "GOAT_INT_A1600_LIDAR_PLUS_EU",
  "UILogicId": "goatl_ww_h_goat2plus",
  "product_category": "GOATBOT",
  "materialNo": "116-2507-0001",
  "nick": null,
  "status": 1
}
```

Note `"nick": null` — the mower has no nickname set on the Ecovacs account, so
`device_info["name"]` falls back to the **account e-mail**. That is why the official
integration generated entity ids such as `sensor.pfosland_duck_com_wi_fi_rssi`. The
device picker in this integration therefore prefers `nick` -> `deviceName` -> `name`
so the dropdown reads "GOAT A1600 LiDAR Pro" instead of an e-mail address.
