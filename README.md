# Goatee Continue — Ecovacs GOAT G1 “resume / continue” for Home Assistant

[![HACS: custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
![Home Assistant 2024.12+](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-41BDF5.svg)
![deebot-client 6.0.2](https://img.shields.io/badge/deebot--client-6.0.2-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

A tiny, HACS-installable Home Assistant custom integration (domain
**`goatee_continue`**) that adds the one thing the built-in `lawn_mower`
platform is missing for Ecovacs robots: **Continue / resume the paused,
unfinished mowing task** — exactly what the Ecovacs app’s **“Continue”** button
does.

It exposes:

- a **service / action** `goatee_continue.resume`, and
- a **button** entity (`button.<name>_continue`, e.g. `button.goatee_continue`)

…both of which dispatch the robot’s native resume command so the mower picks up
where it left off instead of re-mowing the whole map from the dock.

---

## Why this exists (the #145338 limitation)

The built-in Home Assistant `ecovacs` integration only surfaces
`lawn_mower.start_mowing`, `lawn_mower.pause`, and `lawn_mower.dock` — there is
**no resume**. On the GOAT G1, calling `lawn_mower.start_mowing` on a paused task
**restarts the whole map** (progress resets to ~1%), which is the open core
limitation tracked in
**[home-assistant/core#145338](https://github.com/home-assistant/core/issues/145338)**.
The resume command, however, already exists at the library level: `deebot-client`
models it as **`CleanAction.RESUME`**, which serializes to **`act: resume`** — the
exact on-device command behind the app’s “Continue”. This integration simply
surfaces it, reusing the official `ecovacs` integration’s already-authenticated
session (no second login).

---

## Features

- ✅ **Real resume, not restart** — continues the paused task; the mowed-% keeps
  climbing instead of resetting.
- ✅ **Service & button** — `goatee_continue.resume` and `button.<name>_continue`,
  both dispatching `CleanV2(CleanAction.RESUME)`.
- ✅ **No second login** — reuses the official `ecovacs` session (Option A).
- ✅ **Per-model correctness** — reads `device.capabilities.clean.action.command`
  at runtime (GOAT G1 → `CleanV2`; older models → `Clean`); nothing hardcoded.
- ✅ **Idempotent-safe** — skips with a warning if the mower is not paused.
- ✅ **Config flow** — pick your GOAT from a dropdown; **no credentials**.
- ✅ **Localised** — English + Norwegian Bokmål.
- ✅ **Tested** — unit tests against `deebot-client` 6.0.2; `ruff`-clean.

---

## Quick start (HACS)

1. **Prerequisite:** the official **Ecovacs** integration is set up and your GOAT
   appears as a `lawn_mower` entity.
2. In HACS → **Integrations** → ⋮ → **Custom repositories**, add this repo’s URL
   with category **Integration**, install **“Goatee Continue (Ecovacs GOAT
   resume)”**, and restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Goatee Continue**, then
   pick your GOAT from the dropdown (no credentials required).

See [docs/installation.md](docs/installation.md) for the full walk-through.

---

## Usage at a glance

```yaml
# Resume every configured GOAT
action: goatee_continue.resume

# …or target a specific lawn mower
action: goatee_continue.resume
target:
  entity_id: lawn_mower.goatee
```

A `button.<name>_continue` entity is also created and grouped under your existing
GOAT device. Full reference and automation examples: [docs/usage.md](docs/usage.md).

---

## Documentation

| Doc | What’s inside |
| --- | --- |
| [docs/how-it-works.md](docs/how-it-works.md) | The #145338 limitation, the `CleanAction` codes, `act: resume`, model `5xu9h3`/`CleanV2`, the runtime capability lookup, end-to-end flow. |
| [docs/architecture.md](docs/architecture.md) | Option A in depth, component & sequence diagrams, the fragility caveat, and why Option B is not used. |
| [docs/installation.md](docs/installation.md) | Prerequisites, HACS install, config-flow walk-through, verification. |
| [docs/usage.md](docs/usage.md) | Service & button reference, real automations, the idempotent-safe guard, the docked-flap timing caveat. |
| [docs/api-reference.md](docs/api-reference.md) | Authoritative reference: service schema, button entity, config options, `const.py`, and the `ecovacs_link.py` / `__init__.py` helper signatures. |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Symptom → cause → fix for every real error path, plus how to read the logs. |
| [docs/development.md](docs/development.md) | Dev env, `ruff`/`pytest`, the test layout, the version-compatibility matrix, and how to re-verify after upgrades. |
| [CHANGELOG.md](CHANGELOG.md) | Release history (Keep a Changelog). |

---

## Validated versions

| Component | Validated against |
| --- | --- |
| Home Assistant core | ~2026 stable (`ecovacs` using `ConfigEntry.runtime_data` → `EcovacsController.devices`); manifest minimum `homeassistant 2024.12.0` |
| Official `ecovacs` integration | runtime data is an `EcovacsController` exposing `.devices` |
| `deebot-client` | **6.0.2** (`CleanAction.RESUME` = `"resume"`; GOAT G1 model `5xu9h3` → `CleanV2`) |

> **Fragility caveat:** reaching into another integration’s `runtime_data` is **not**
> a stable public API and may break on Home Assistant core, `ecovacs`, or
> `deebot-client` upgrades. All of that access is isolated in one heavily-commented
> module, [`ecovacs_link.py`](custom_components/goatee_continue/ecovacs_link.py),
> which verifies the required symbols at runtime and fails with a precise
> `HomeAssistantError`. See [docs/architecture.md](docs/architecture.md#fragility-caveat).

---

## License

[MIT](LICENSE) © 2026 locazor.
