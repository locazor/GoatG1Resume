# Troubleshooting

Every symptom below maps to a real error path in the code. Turn on debug logging
first — it prints the exact dispatched payload and the validated versions.

## Reading the logs

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.ecovacs_resume: debug
```

The logger names are `custom_components.ecovacs_resume` (service registration,
button presses) and `custom_components.ecovacs_resume.ecovacs_link` (device
resolution, the resume dispatch). At `debug` you’ll see, for each resume:

```
Sending resume/continue (act: resume) to Ecovacs device '<name>'
Resume command: CleanV2 name=clean_V2 args={'act': 'resume', 'content': {}} model_class=e4gqia (deebot-client 18.5.1)
```

---

## Symptom → cause → fix

### “The official Ecovacs integration is not configured”

- **Raised by:** `async_setup_entry` (`__init__.py`), and the config flow aborts
  with `ecovacs_not_loaded`.
- **Cause:** Ecovacs Resume reuses the official `ecovacs` session, and no
  `ecovacs` config entry exists.
- **Fix:** Set up **Settings → Devices & Services → Add Integration → Ecovacs**
  first, then add/reload Ecovacs Resume.

### “No compatible Ecovacs devices were found” (config flow abort `no_devices`)

- **Raised by:** `async_step_user` when `async_list_resumable_devices` is empty.
- **Cause:** the Ecovacs integration is loaded but no device exposes a clean-action
  capability (`capabilities.clean.action.command`) — usually because the mower is
  offline or Ecovacs hasn’t finished loading its devices yet.
- **Fix:** Confirm the mower is online (visible as a `lawn_mower` entity), wait for
  Ecovacs to finish loading, then retry the flow.

### “Could not find an Ecovacs device with id '…'”

- **Raised by:** `async_send_resume` → `_find_device` returns `None`.
- **Cause:** the configured `did` isn’t among the live deebot devices right now —
  the device is offline, or the Ecovacs integration hasn’t loaded it yet (e.g. a
  resume fired at startup before Ecovacs was ready).
- **Fix:** Ensure the device is online and Ecovacs is loaded, then retry. For
  automations that can fire early, add a `for:` delay or condition on the mower
  entity being available.

### Resume was skipped

- **Symptom (log):**
  `Skipping resume for '<name>': device is not in a paused/resumable state …`
- **Cause:** the guard keys only on `PAUSED` (`_RESUMABLE_STATE_NAMES = {"PAUSED"}`).
  The last reported state was something else.
- **Two common situations:**
  1. **Nothing to continue** — the mower is genuinely idle/docked with no preserved
     task. This is correct behaviour; use `lawn_mower.start_mowing` to begin a new
     task.
  2. **Docked/paused flapping (known limitation)** — on the GOAT G1, a preserved task
     can report `docked` and `paused` alternately while on the dock. A call that
     lands on a `docked` sample is skipped even though “Continue” is available in
     the app. **Fix/workaround:** retry, or trigger the automation on the `paused`
     state. See [usage → timing caveat](usage.md#known-timing-caveat-dockedpaused-flapping).
     The exact flapping window **must be confirmed on the live device**.

### “This version of deebot-client has no CleanAction.RESUME” / “deebot-client is not installed”

- **Raised by:** `_resume_action()`.
- **Cause:** library version drift — the `CleanAction` enum changed or moved, or
  `deebot-client` isn’t importable (it normally comes with the Ecovacs
  integration). The message includes the detected `deebot-client` version.
- **Fix:** Note the version printed in the message and open an issue. Re-run the
  recon in [development → re-verifying after an upgrade](development.md#re-verifying-after-an-upgrade)
  to confirm `CleanAction.RESUME` still exists.

### “Failed to send resume command to '…': &lt;error&gt;”

- **Raised by:** `async_send_resume` wrapping an exception from
  `device.execute_command`.
- **Cause:** a transport/cloud error from `deebot-client` (device unreachable,
  cloud hiccup, auth expired on the official integration’s session).
- **Fix:** Check the official Ecovacs integration’s health and the mower’s
  connectivity; retry. The original error is included in the message.

### Resume “works” but the mower restarts the map

- **Cause:** This integration sends `act: resume`. If the device was **not** paused
  at dispatch time, `deebot-client`’s `Clean._execute` converts `RESUME → START`
  (a new task) by design. So a restart means the device didn’t consider itself
  paused.
- **Fix:** Ensure the task is actually paused (app shows *“Task paused /
  Continue”*) before resuming; mind the docked/paused flapping caveat above.

### Breakage right after a Home Assistant update (Option A fragility)

- **Cause:** Ecovacs Resume reaches into the `ecovacs` integration’s
  `runtime_data` / `EcovacsController.devices` and the `deebot-client` `Device`
  shape — none of which are stable public APIs. A core/`ecovacs`/`deebot-client`
  upgrade can change them.
- **Fix:** The fragile access is all in
  [`ecovacs_link.py`](../custom_components/ecovacs_resume/ecovacs_link.py). Enable
  debug logging, find which assumption broke (device lookup vs. capability vs.
  `CleanAction`), and patch that one module. See
  [architecture → fragility caveat](architecture.md#fragility-caveat) and the
  re-verification recon in [development](development.md#re-verifying-after-an-upgrade).

### A note on Ecovacs passwords with `-` or `?`

Ecovacs has a known auth-encoding bug for passwords containing certain characters.
Ecovacs Resume **never logs in** (Option A), so it is unaffected — this note is
here only because that bug can break the **official** integration’s setup, which
Ecovacs Resume depends on.

---

See also: [usage](usage.md) · [architecture](architecture.md) ·
[development](development.md)
