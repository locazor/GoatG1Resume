# Migrating from `goatee_continue` 1.x to `ecovacs_resume` 2.0

Version 2.0 renames the integration's **domain** from `goatee_continue` to
`ecovacs_resume`. The old name was taken from one particular GOAT G1 named
"Goatee"; the integration was never G1-specific, and it now supports several
mowers at once.

**There is no automatic migration.** Home Assistant keys config entries, entity
ids, and the service name to the domain, and a custom integration cannot rename
its own domain in place — the old domain's entries belong to a component that no
longer exists. The upgrade is a one-time remove-and-re-add.

## What changes

| | 1.x | 2.0 |
| --- | --- | --- |
| Domain | `goatee_continue` | `ecovacs_resume` |
| Folder | `custom_components/goatee_continue/` | `custom_components/ecovacs_resume/` |
| Service | `goatee_continue.resume` | `ecovacs_resume.resume` |
| Button entity | `button.<…>_goatee_continue` | `button.<mower>_continue` |
| Config entries | one | one **per mower** |

Nothing about the resume behaviour changes: the same
`CleanV2(CleanAction.RESUME)` / `act: resume` command is dispatched, and it still
never falls back to starting a new task.

## Steps

1. **Note what references the old names.** Search your automations, scripts,
   scenes, dashboards, and templates for `goatee_continue`:

   *Developer tools → Template* is the quickest way to find entity references:

   ```jinja
   {{ states.button | selectattr('entity_id', 'search', 'goatee') | map(attribute='entity_id') | list }}
   ```

   Also grep your YAML if you keep any on disk:

   ```bash
   grep -rn "goatee_continue" config/
   ```

2. **Remove the old integration.** Settings → Devices & Services →
   **Goatee Continue** → ⋮ → **Delete**. This removes its config entry, its
   button entity, and (in 1.x) the duplicate device registry entry it created.

3. **Remove the old folder**, or HACS will keep offering it and Home Assistant
   will load both:

   ```bash
   rm -rf config/custom_components/goatee_continue
   ```

   If you installed via HACS, uninstall "Goatee Continue" from HACS instead of
   deleting by hand.

4. **Install `ecovacs_resume` 2.0** (HACS custom repository, or copy
   `custom_components/ecovacs_resume/` into `config/custom_components/`), then
   **restart Home Assistant**.

5. **Add the integration**: Settings → Devices & Services → Add Integration →
   **Ecovacs Resume** → pick your mower. Repeat once per mower.

6. **Update your automations** to the new service and entity ids:

   ```yaml
   # before
   action: goatee_continue.resume

   # after
   action: ecovacs_resume.resume
   target:
     entity_id: lawn_mower.a1600      # optional; no target = all configured mowers
   ```

## If you run both at once

2.0 detects a leftover `goatee_continue` config entry and logs a warning at
setup. Both integrations will try to put a Continue button on the same mower,
and two devices with the same name make Home Assistant generate awkward
area-prefixed entity ids (this is what produced `button.r38ute_goatee_continue`
in 1.x). Remove the old one.

## Why not ship an automatic migration?

Home Assistant offers `async_migrate_entry` for *version* bumps within a domain,
not for domain renames. Moving entries across domains would mean writing to
`.storage/core.config_entries` behind Home Assistant's back — unsupported, and
liable to corrupt the registry on a partial failure. A five-minute manual
re-add is the safe option, and it also clears out the stale duplicate device
entry that 1.x created.
