# Installation

- [Prerequisites](#prerequisites)
- [Install via HACS (recommended)](#install-via-hacs-recommended)
- [Manual install](#manual-install)
- [Configure (config flow)](#configure-config-flow)
- [Verify](#verify)

---

## Prerequisites

1. **The official Ecovacs integration is set up and working.** Goatee Continue
   reuses its authenticated session — it never logs in itself
   (`manifest.json` declares `"dependencies": ["ecovacs"]`). Configure it under
   **Settings → Devices & Services → Add Integration → Ecovacs** first.
2. **Your GOAT is live as a `lawn_mower` entity** (e.g. `lawn_mower.goatee`) and
   shows up under an Ecovacs device. If the mower is offline or the Ecovacs
   integration hasn’t finished loading, Goatee Continue won’t find it.
3. **Home Assistant `2024.12.0` or newer** (the minimum declared in `hacs.json`).

If the official integration is **not** configured, both the config flow and
setup abort/raise with a clear message (`ecovacs_not_loaded`).

---

## Install via HACS (recommended)

1. In **HACS → Integrations**, open the ⋮ menu → **Custom repositories**.
2. Add this repository’s URL, choose category **Integration**, and confirm.
3. Find **“Goatee Continue (Ecovacs GOAT resume)”** in the list, click
   **Download**, and **restart Home Assistant**.

> `hacs.json` sets `content_in_root: false`, so HACS installs the integration from
> `custom_components/goatee_continue/` — no extra configuration needed.

---

## Manual install

If you don’t use HACS:

```bash
# from the repo root, copy the component into your HA config dir
cp -r custom_components/goatee_continue \
      /path/to/homeassistant/config/custom_components/
```

Then **restart Home Assistant**. The end result is the same directory layout HACS
produces: `config/custom_components/goatee_continue/`.

---

## Configure (config flow)

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Goatee Continue** and select it.
3. You’ll see a single step titled **“Goatee Continue”** with one field,
   **“Ecovacs device”** — a dropdown populated from the official Ecovacs
   integration. **No credentials are requested.**
4. Pick your GOAT (shown as `Name (did)`, e.g. `Goatee (abc123…)`) and submit.

The integration stores only the device id (`did`) and a friendly name; it creates
the config entry and adds the button entity.

**Possible abort messages during the flow:**

| Reason | Meaning / fix |
| --- | --- |
| `ecovacs_not_loaded` | The official Ecovacs integration isn’t set up. Add it first. |
| `no_devices` | No Ecovacs device exposing a clean-action capability was found. Make sure Ecovacs is loaded and your GOAT is online. |
| `already_configured` | You already added this exact device. |

The dropdown only lists devices that expose
`capabilities.clean.action.command` (vacuums and mowers), so a sensor-only
device will never appear.

---

## Verify

1. **Entity created.** Under **Settings → Devices & Services →** your GOAT device,
   confirm a new button entity exists: **`button.<name>_continue`** (e.g.
   `button.goatee_continue`), named **“Continue”**, icon `mdi:play-pause`.
2. **Service registered.** In **Developer Tools → Actions**, search for
   **`goatee_continue.resume`** — it should be listed with `device_id` and
   `entity_id` fields.
3. **Behavioural test (must be confirmed on the live device).** Start a mow, let
   it reach a few %, then pause and dock so the app shows *“Task paused /
   Continue”*. Call `goatee_continue.resume` (or press the button) and confirm the
   mower **continues** the same task (mowed-% keeps climbing) rather than
   restarting. Full steps and the contrast test are in
   [docs/usage.md](usage.md#verifying-the-behavioural-fix-on-your-goat).

---

See also: [how it works](how-it-works.md) · [usage](usage.md) ·
[troubleshooting](troubleshooting.md)
