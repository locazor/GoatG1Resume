# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] — 2026-08-29

### ⚠️ Breaking

- **Domain renamed** `goatee_continue` → **`ecovacs_resume`**, and the folder
  `custom_components/goatee_continue/` → `custom_components/ecovacs_resume/`.
  The old name came from one particular GOAT G1 called "Goatee"; the integration
  was never G1-specific. Consequently:
  - the service is now **`ecovacs_resume.resume`**;
  - the button entity id is now `button.<mower>_continue`.

  **There is no automatic migration** — Home Assistant keys config entries,
  entity ids, and services to the domain, and a custom integration cannot rename
  its own domain in place. Remove the old integration and folder, install this
  one, and re-add it. Step-by-step: [docs/migration-2.0.md](docs/migration-2.0.md).
  2.0 logs a warning at setup if a leftover `goatee_continue` entry is detected.
- Service targets that resolve to Ecovacs devices which are **not** configured in
  this integration are now dropped (with a warning) instead of being resumed
  anyway. Previously `_resolve_target_dids` fell back to the unscoped set, so a
  target naming an unconfigured Ecovacs device would still have a command sent to
  it.

### Added

- **GOAT A1600 LiDAR Pro (`e4gqia`) support** — verified at the source level
  against `deebot-client` 18.3.0 and 18.5.1. The `e4gqia` capability module is
  byte-identical to the G1's `5xu9h3` apart from its docstring, so it needed no
  model-specific code. Full evidence and the exact payload:
  [docs/feasibility-a1600-resume.md](docs/feasibility-a1600-resume.md).
  ⏳ The *behavioural* check (that resume continues rather than restarts) still
  has to be run on the hardware.
- **Multiple mowers.** One config entry per device; run the config flow again to
  add another. Already-configured devices are hidden from the picker, which
  aborts with `all_configured` when nothing is left to add.
- The config entry records the Ecovacs `model_class` (`CONF_MODEL_CLASS`), and it
  appears in the device picker and the log lines. **Diagnostic only** — dispatch
  is still decided from the device's declared capabilities.
- Ruff configuration (`ruff.toml`) mirroring Home Assistant core's conventions;
  `ruff check`, `ruff format --check`, and `mypy` are clean.
- Tests for multi-device selection, per-model command-class dispatch across a
  mixed fleet, the missing-capability error, the state re-check, and the
  "never sends `act: start`" invariant.
- [docs/migration-2.0.md](docs/migration-2.0.md) and
  [docs/feasibility-a1600-resume.md](docs/feasibility-a1600-resume.md).

### Changed

- **Skip logging now names the state.** The "not resumable" warning includes the
  exact deebot `State` member (e.g. `DOCKED`) and the model class, so a flapping
  dock is visible in the log instead of guesswork.
- **Stale-state re-check.** When the last known state is non-resumable, the
  integration now calls `request_refresh(StateEvent)`, waits
  `_STATE_RECHECK_DELAY_SECONDS` (1.5 s), and reads the state once more before
  skipping. This addresses the G1's docked/paused flapping. The re-check can only
  *add* a resume that would otherwise have been skipped — it never turns a resume
  into a start. The guard itself is unchanged and deliberately still refuses to
  dispatch on a genuinely non-paused device.
- **Device picker labels.** The friendly name is resolved `nick` → `deviceName` →
  `name`. A mower with no nickname on the Ecovacs account reports the *account
  e-mail* as `name`, so every device on the account looked identical; it now
  shows e.g. `GOAT A1600 LiDAR Pro [e4gqia] (448c6077)`.
- The missing-capability error now names the device and its model class.
- Documentation: supported/validated model table, the "mowed" vs "cleaned" sensor
  naming difference between the A1600 and the G1, and the validated versions
  (HA 2026.8.3, `deebot-client` 18.5.1) throughout.

### Fixed

- **The button no longer creates a duplicate device.** `DeviceInfo` passed
  `name=` alongside `identifiers`, which made Home Assistant treat it as a device
  *definition* rather than a link; the result was a second registry entry with
  the same name as the Ecovacs device. Two same-named devices are why the entity
  id came out as the area-prefixed `button.r38ute_goatee_continue`. It now passes
  identifiers only, so the entity attaches to the existing Ecovacs device and the
  id is `button.<mower>_continue`. (The stale duplicate entry is cleared by the
  2.0 remove-and-re-add.)

### Verified

- `deebot-client` **18.3.0** and **18.5.1**: `CleanAction.RESUME` present in both
  (`RESUME = "resume", "r"` — `.value` `"resume"` for JSON devices, `"r"` is the
  XML alias only). `5xu9h3` and `e4gqia` both declare
  `clean.action.command = CleanV2`, payload `{"act": "resume", "content": {}}`,
  command name `clean_V2`.
- **`capabilities.map` is `None`** for both models in both versions — no map, no
  zone discovery, LiDAR notwithstanding. 18.5.1 *does* add
  `clean.action.area = CleanAreaV2` to both, so a coordinate-based custom-area mow
  may be constructible on that version; it is `act: start` (a new task, not a
  resume), needs hand-supplied coordinates, and is unverified on hardware. Not
  implemented — see the feasibility report.
- **Documented the library's `RESUME` → `START` rewrite.** `Clean._execute`
  (inherited by `CleanV2`) silently converts a resume into a map-restarting start
  when the last `StateEvent` is not `PAUSED`. The integration's paused guard is
  what prevents this, making it load-bearing rather than cosmetic. Called out in
  the module docstring, how-it-works, usage, and development docs.

## [1.0.1] — 2026

### Added
- Full documentation set under `docs/`: how-it-works, architecture (with
  component, sequence, and state-guard diagrams), installation, usage,
  API reference, troubleshooting, and development.
- Module/function docstrings completed across the integration; brief comments at
  the fragile `ecovacs_link.py` access points.
- Validated against `deebot-client` **18.3.0** (HAOS / Python 3.14) in addition
  to 6.0.2: `CleanAction.RESUME.value` is still `"resume"`, GOAT G1 `5xu9h3`
  still maps its clean action to `CleanV2`, and
  `device.capabilities.clean.action.command` is still the correct runtime path.
  Version matrix and re-verification notes added to `docs/development.md`.

### Fixed
- **Blocking I/O in the event loop.** The `deebot-client` version was read with
  `importlib.metadata.version()` synchronously during `async_setup_entry`, which
  performs blocking filesystem I/O (`listdir`/`open`/`read_text` on the package
  `dist-info/METADATA`) and was flagged by `homeassistant.util.loop`. The lookup
  now runs once via `hass.async_add_executor_job(...)` and is cached
  (`ecovacs_link.async_get_deebot_client_version`); the synchronous
  `deebot_client_version()` accessor is now a pure, non-blocking cache read.
  Failures are non-fatal (`"unknown"`) and never block setup. No resume/guard
  logic changed.
- Documentation accuracy: the resume payload is `act: resume` (the full
  `CleanAction.RESUME` value in `deebot-client` 6.0.2), not the single letter
  `act: r`. Corrected the docstrings, `services.yaml`, `strings.json`, the `en`/`nb`
  translations, and the test comments. No runtime logic changed.

## [1.0.0] — 2026

Initial release.

### Added
- Domain `goatee_continue`: a “resume / continue” capability for the Ecovacs
  **GOAT G1** robotic lawn mower, surfacing the resume command the built-in
  `lawn_mower` platform lacks (see home-assistant/core#145338).
- Service / action `goatee_continue.resume` (optional `device_id` / `entity_id`
  targets; no target resumes every configured GOAT).
- Button entity `button.<name>_continue` (named “Continue”, icon `mdi:play-pause`),
  grouped under the existing Ecovacs device.
- **Option A** architecture: reuses the official `ecovacs` integration’s
  already-authenticated `deebot-client` `Device` via `entry.runtime_data` →
  `EcovacsController.devices` — no second login. All fragile cross-integration
  access isolated in `ecovacs_link.py` with runtime symbol checks and clear
  `HomeAssistantError`s.
- Per-model correctness: reads `device.capabilities.clean.action.command` at
  runtime instead of hardcoding (GOAT G1 model `5xu9h3` → `CleanV2`; older models
  → `Clean`).
- Idempotent-safe guard: skips with a warning when the mower is not in a paused
  (resumable) state.
- Config flow (device picker, no credentials); English + Norwegian Bokmål
  translations; `services.yaml`; HACS metadata; MIT license; unit tests.

### Verified
- `deebot-client` **6.0.2**: `CleanAction.RESUME` exists and serializes to
  `act: resume`; the GOAT G1 (`5xu9h3`, *“DEEBOT GOAT G1 Capabilities”*) wires its
  clean action to `CleanV2`, so the resume payload is
  `{"act": "resume", "content": {}}`.

[2.0.0]: https://github.com/locazor/goatg1resume/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/locazor/goatg1resume/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/locazor/goatg1resume/releases/tag/v1.0.0
