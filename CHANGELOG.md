# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/locazor/goatg1resume/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/locazor/goatg1resume/releases/tag/v1.0.0
