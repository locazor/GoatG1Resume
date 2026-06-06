# Goatee Continue — Ecovacs GOAT G1 "resume / continue" for Home Assistant

A tiny, HACS-installable Home Assistant custom integration that adds the one
thing the built-in `lawn_mower` platform is missing for Ecovacs robots:
**Continue / resume the paused, unfinished mowing task** — exactly what the
Ecovacs app's **“Continue”** button does.

It exposes:

- a **service** `goatee_continue.resume`, and
- a **button** entity (`button.<name>_continue`, e.g. `button.goatee_continue`)

…both of which send the robot's native **resume** command (`act: r`) so the
mower picks up where it left off instead of re-mowing the whole map from the
dock.

---

## Why this exists

The built-in Home Assistant `ecovacs` integration only surfaces
`lawn_mower.start_mowing`, `lawn_mower.pause`, and `lawn_mower.dock`. There is
**no resume**.

Empirically on the **Ecovacs GOAT G1**: after the mower parks on the dock with a
task still preserved (the app shows *“Task paused / Continue”* and a mowing‑%),
calling `lawn_mower.start_mowing` **restarts the whole map** — progress resets to
~1%, it re-mows near the dock, and never reaches far zones. This is the known,
open core limitation tracked in
**[home-assistant/core#145338](https://github.com/home-assistant/core/issues/145338)**
(“`vacuum.start` initiates new clean instead of resuming paused state”;
`send_command: resume` has no effect).

### The key fact that makes a real fix possible

The resume command already exists at the Ecovacs protocol / library level — it
is simply not surfaced by the HA integration. The `Clean` command takes an
action `act` with values:

| `act` | meaning |
|-------|---------|
| `s`   | start   |
| `r`   | **resume** |
| `p`   | pause   |
| `h`   | stop    |

So **`act: r`** is the on-device command behind the app's “Continue”. The
underlying library `deebot-client` models this as `CleanAction.RESUME`.

---

## Architecture (Option A — reuse the official session, no second login)

There must be exactly **one** active Ecovacs cloud session per account, so this
integration does **not** log in again. Instead it:

1. Finds the official `ecovacs` integration's config entry and its
   `EcovacsController` (`entry.runtime_data`).
2. Locates the already-authenticated `deebot_client.device.Device` whose `did`
   matches the GOAT you selected.
3. Reads that device's **own** declared clean-action command class from its
   capabilities (`device.capabilities.clean.action.command`) — `CleanV2` for the
   GOAT G1, `Clean` for older models — and dispatches
   `command(CleanAction.RESUME)` via `device.execute_command(...)`.

> **Fragility caveat:** reaching into another integration's runtime data is
> **not** a stable public API and may break on Home Assistant core or
> `deebot-client` updates. All of that fragile access is isolated in a single,
> heavily-commented module — [`ecovacs_link.py`](custom_components/goatee_continue/ecovacs_link.py) —
> so there is exactly one place to fix. The integration verifies the required
> symbols at runtime and fails with a precise `HomeAssistantError` (logging the
> validated versions) if the structure changes.

There is **no** Option B (separate-account standalone login) in this build —
Option A works on the installed library, so a second login (which can log you
out of the app) is unnecessary. See the verification note below for proof.

---

## Verification note — how the resume API was confirmed

Verified against the **actually installed** `deebot-client` **6.0.2**:

**`CleanAction` (from `deebot_client/models.py`)** — `RESUME` exists:

```python
@unique
class CleanAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"   # <-- the app's "Continue" (act: r)
    STOP = "stop"
```

**Which command class the GOAT uses** — the GOAT G1's hardware capability file
is `deebot_client/hardware/deebot/5xu9h3.py` (header: *“DEEBOT GOAT G1
Capabilities”*), and it wires the clean action to **`CleanV2`**:

```python
from deebot_client.commands.json.clean import CleanV2, GetCleanInfoV2
...
action=CapabilityCleanAction(command=CleanV2),
```

> Note: the task brief guessed the GOAT's model code as `umwv6z`, but in
> `deebot-client` 6.0.2 that file is the **T10 PLUS** (uses `Clean`). The GOAT G1
> is model **`5xu9h3`** and uses **`CleanV2`**. This integration does **not**
> hardcode either — it reads `device.capabilities.clean.action.command` so the
> correct class is always used per device.

The resulting payload for the GOAT is exactly the “continue” command:

```python
CleanV2(CleanAction.RESUME)._args == {"act": "resume", "content": {}}
```

`deebot-client` additionally guards this: `Clean._execute` converts `RESUME`
into `START` only when the device's last reported state is **not** `PAUSED`, and
converts a `START` into `RESUME` when it **is** paused — i.e. resume is honored
precisely when there is a paused task to continue.

**Validated versions:** Home Assistant ~2026 stable · official `ecovacs`
integration (using `ConfigEntry.runtime_data` → `EcovacsController.devices`) ·
`deebot-client` **6.0.2**.

---

## Installation (HACS)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**, add this repo's URL
   with category **Integration**.
2. Install **“Goatee Continue (Ecovacs GOAT resume)”** and restart Home
   Assistant.
3. Go to **Settings → Devices & Services → Add Integration → Goatee Continue**.
4. Pick your GOAT from the list (populated from the official Ecovacs
   integration — **no credentials required**).

> The official **Ecovacs** integration must already be set up; the config flow
> aborts with a clear message if it isn't.

Manual install alternative: copy `custom_components/goatee_continue/` into your
HA `config/custom_components/` directory and restart.

---

## Usage

### Service

```yaml
# Resume every configured GOAT
service: goatee_continue.resume

# …or target a specific device / entity
service: goatee_continue.resume
target:
  entity_id: lawn_mower.goatee
```

### Button

A `button` entity is created and grouped under your existing Goatee device
(e.g. `button.goatee_continue`). Press it on a dashboard or call it from an
automation.

### Example automation

```yaml
automation:
  - alias: "Resume mowing after dock pause"
    triggers:
      - trigger: state
        entity_id: lawn_mower.goatee
        to: "paused"
        for: "00:02:00"
    actions:
      - action: goatee_continue.resume
```

---

## Behavior & safety

- **Real resume, no map restart.** With a paused, partially-complete task (app
  shows e.g. *“Task paused, 14% mowed”*), the resume service makes the mower
  **continue the same task** — the mowed-% keeps climbing and
  `sensor.goatee_area_cleaned` does **not** reset toward 0. (Contrast:
  `lawn_mower.start_mowing` resets it.)
- **Idempotent-safe.** If the device is not in a paused/resumable state (already
  `mowing`, or docked with no preserved task), it logs a clear warning and does
  nothing harmful.
- **Survives restarts.** The service and button re-register on startup and reuse
  the live ecovacs device once it loads (ordering handled gracefully).
- **Clear errors.** Raises `HomeAssistantError` if the official Ecovacs
  integration isn't loaded or the device can't be found.

### How to verify the behavioral fix on your GOAT

1. Start a mow, let it reach a few %, then `lawn_mower.pause` and
   `lawn_mower.dock` (or let it park) so the app shows *“Task paused / Continue”*.
2. Note `sensor.goatee_area_cleaned` / the app's mowed-%.
3. Call `goatee_continue.resume` (or press the button). The mower continues; the
   % climbs from where it was and the area-cleaned sensor does **not** reset.
4. For contrast, repeat but call `lawn_mower.start_mowing` instead — you'll see
   the % reset to ~1% and the area-cleaned sensor drop.

---

## Logging / troubleshooting

Enable debug logging to see the exact dispatched payload:

```yaml
logger:
  default: warning
  logs:
    custom_components.goatee_continue: debug
```

- *“The official Ecovacs integration is not configured”* → set up the built-in
  **Ecovacs** integration first.
- *“Could not find an Ecovacs device with id …”* → the device is offline or the
  ecovacs integration hasn't finished loading; check it's available, then retry.
- *“This version of deebot-client has no CleanAction.RESUME”* → the library
  changed; open an issue with your `deebot-client` version (printed in the
  message).
- *Password with `-` or `?`* — Ecovacs has a known auth-encoding bug for such
  passwords. This integration never logs in (Option A), so it's unaffected; the
  note is here only because it can bite the **official** integration's setup.

---

## Development / tests

```bash
pip install pytest pytest-asyncio deebot-client
python -m pytest
```

The unit tests mock the `deebot-client` Device and assert that the correct
resume command object (the device's own `Clean`/`CleanV2` class built with
`CleanAction.RESUME`, payload `act: r`) is dispatched, that resume is skipped
when not paused, and that a missing device raises `HomeAssistantError`.

---

## Files

```
custom_components/goatee_continue/
  __init__.py        # setup/unload + goatee_continue.resume service
  ecovacs_link.py    # the ONLY fragile module: reuse ecovacs session + build act:r
  config_flow.py     # UI: pick the GOAT (no credentials)
  button.py          # button.<name>_continue
  const.py
  manifest.json
  services.yaml
  strings.json
  translations/en.json
  translations/nb.json
hacs.json
tests/test_resume.py
```

## License

MIT
