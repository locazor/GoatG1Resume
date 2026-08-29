# Ecovacs Resume — “continue mowing” for Home Assistant

[![HACS: custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
![Home Assistant 2024.12+](https://img.shields.io/badge/Home%20Assistant-2024.12%2B-41BDF5.svg)
![deebot-client 18.5.1](https://img.shields.io/badge/deebot--client-18.3.0%20%7C%2018.5.1-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

A tiny, HACS-installable Home Assistant custom integration (domain
**`ecovacs_resume`**) that adds the one thing the built-in `lawn_mower`
platform is missing for Ecovacs robots: **Continue / resume the paused,
unfinished mowing task** — exactly what the Ecovacs app’s **“Continue”** button
does.

It exposes:

- a **service / action** `ecovacs_resume.resume`, and
- a **button** entity (`button.<mower>_continue`)

…both of which dispatch the robot’s native resume command so the mower picks up
where it left off instead of re-mowing the whole map from the dock.

> **Renamed in 2.0.0.** This integration used to be `goatee_continue` (“Goatee
> Continue”), named after one particular GOAT G1. It is not G1-specific and never
> was, so the domain is now `ecovacs_resume`. Upgrading from 1.x requires a
> one-time remove-and-re-add: see **[docs/migration-2.0.md](docs/migration-2.0.md)**.

---

## Why this exists (the #145338 limitation)

The built-in Home Assistant `ecovacs` integration only surfaces
`lawn_mower.start_mowing`, `lawn_mower.pause`, and `lawn_mower.dock` — there is
**no resume**. Calling `lawn_mower.start_mowing` on a paused task
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
  climbing instead of resetting. Never falls back to `start_mowing`.
- ✅ **Service & button** — `ecovacs_resume.resume` and `button.<mower>_continue`.
- ✅ **Multiple mowers** — one config entry per device; add the integration again
  for each mower. The service takes a normal HA target.
- ✅ **No second login** — reuses the official `ecovacs` session (Option A).
- ✅ **Per-model correctness** — reads `device.capabilities.clean.action.command`
  at runtime (`CleanV2` for GOAT models; `Clean` for older ones); nothing
  hardcoded, and a clear error if a device declares no clean action at all.
- ✅ **Idempotent-safe** — skips with a warning naming the exact state if the
  mower has no paused task, with a re-check to survive dock-state flapping.
- ✅ **Config flow** — pick your mower from a dropdown; **no credentials**.
- ✅ **Localised** — English + Norwegian Bokmål.
- ✅ `ruff`-clean, `mypy`-clean, unit-tested.

---

## Supported / validated models

| Model | Model class | `clean.action.command` | Resume | Status |
| --- | --- | --- | --- | --- |
| GOAT G1 | `5xu9h3` | `CleanV2` | `{"act": "resume", "content": {}}` | ✅ Validated on hardware (1.x) |
| GOAT A1600 LiDAR Pro | `e4gqia` | `CleanV2` | `{"act": "resume", "content": {}}` | ✅ Capability-verified; ⏳ behavioural test pending |
| Other Ecovacs vacuums/mowers | any | `Clean` / `CleanV2` / other | resolved at runtime | ⚪ Should work, untested |

`e4gqia` (A1600) and `5xu9h3` (G1) are **byte-identical** in `deebot-client`
apart from their module docstring, so the A1600 needs no model-specific code.
Full evidence: **[docs/feasibility-a1600-resume.md](docs/feasibility-a1600-resume.md)**.

Nothing in the integration keys off the model class — it is recorded for
diagnostics only. Dispatch always comes from the device's own declared
capabilities, so an unlisted model works as long as it declares a clean action.

### “mowed” vs “cleaned” sensor naming

The official integration's companion sensor **entity ids differ between these two
models**, because HA generated the G1's ids back when the entities were named
after vacuum “cleaning”:

| What it measures | GOAT G1 | GOAT A1600 LiDAR Pro |
| --- | --- | --- |
| Area this session | `sensor.<mower>_area_cleaned` | `sensor.<mower>_area_mowed` |
| Duration this session | `sensor.<mower>_cleaning_duration` | `sensor.<mower>_mowing_duration` |
| Total area | `sensor.<mower>_total_area_cleaned` | `sensor.<mower>_total_area_mowed` |
| Total duration | `sensor.<mower>_total_cleaning_duration` | `sensor.<mower>_total_mowing_duration` |
| Job count | `sensor.<mower>_total_cleanings` | `sensor.<mower>_total_mowings` |

The **friendly names are identical** on both (“Area mowed”, “Mowing duration”, …)
— only the entity ids differ. If you have automations or templates that reference
the `_cleaned` ids, they will not match a newly added A1600. This integration
itself reads none of these sensors; the note is here because automations built
around resume usually do.

---

## Quick start (HACS)

1. **Prerequisite:** the official **Ecovacs** integration is set up and your mower
   appears as a `lawn_mower` entity.
2. In HACS → **Integrations** → ⋮ → **Custom repositories**, add this repo’s URL
   with category **Integration**, install **“Ecovacs Resume (continue mowing)”**,
   and restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Ecovacs Resume**, then
   pick your mower from the dropdown (no credentials required).
4. Repeat step 3 for each additional mower.

See [docs/installation.md](docs/installation.md) for the full walk-through.

---

## Usage at a glance

```yaml
# Resume every configured mower
action: ecovacs_resume.resume

# …or target a specific lawn mower
action: ecovacs_resume.resume
target:
  entity_id: lawn_mower.a1600
```

A `button.<mower>_continue` entity is also created and grouped under your existing
Ecovacs device. Full reference and automation examples: [docs/usage.md](docs/usage.md).

---

## Documentation

| Doc | What’s inside |
| --- | --- |
| [docs/how-it-works.md](docs/how-it-works.md) | The #145338 limitation, the `CleanAction` codes, `act: resume`, the runtime capability lookup, end-to-end flow. |
| [docs/architecture.md](docs/architecture.md) | Option A in depth, component & sequence diagrams, the fragility caveat, and why Option B is not used. |
| [docs/installation.md](docs/installation.md) | Prerequisites, HACS install, config-flow walk-through, verification. |
| [docs/usage.md](docs/usage.md) | Service & button reference, real automations, the idempotent-safe guard, the docked-flap timing caveat. |
| [docs/api-reference.md](docs/api-reference.md) | Authoritative reference: service schema, button entity, config options, `const.py`, and the `ecovacs_link.py` / `__init__.py` helper signatures. |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Symptom → cause → fix for every real error path, plus how to read the logs. |
| [docs/development.md](docs/development.md) | Dev env, `ruff`/`pytest`, the test layout, the version-compatibility matrix, and how to re-verify after upgrades. |
| [docs/feasibility-a1600-resume.md](docs/feasibility-a1600-resume.md) | Source-level proof that the A1600 LiDAR Pro supports resume, plus the zone/map observation. |
| [docs/migration-2.0.md](docs/migration-2.0.md) | Upgrading from `goatee_continue` 1.x to `ecovacs_resume` 2.0. |
| [CHANGELOG.md](CHANGELOG.md) | Release history (Keep a Changelog). |

---

## Validated versions

| Component | Validated against |
| --- | --- |
| Home Assistant core | **2026.8.3** on HAOS 18.2 / **Python 3.14.6** (`ecovacs` using `ConfigEntry.runtime_data` → `EcovacsController.devices`); manifest minimum `homeassistant 2024.12.0` |
| Official `ecovacs` integration | runtime data is an `EcovacsController` exposing `.devices` |
| `deebot-client` | **18.3.0** and **18.5.1** (18.5.1 is what HA 2026.8.3 ships). `CleanAction.RESUME.value` = `"resume"`; `5xu9h3` and `e4gqia` → `CleanV2`. See [docs/development.md](docs/development.md#version-compatibility-matrix). |

> **Fragility caveat:** reaching into another integration’s `runtime_data` is **not**
> a stable public API and may break on Home Assistant core, `ecovacs`, or
> `deebot-client` upgrades. All of that access is isolated in one heavily-commented
> module, [`ecovacs_link.py`](custom_components/ecovacs_resume/ecovacs_link.py),
> which verifies the required symbols at runtime and fails with a precise
> `HomeAssistantError`. See [docs/architecture.md](docs/architecture.md#fragility-caveat).

---

## License

[MIT](LICENSE) © 2026 locazor.
