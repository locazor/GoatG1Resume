# Development

- [Dev environment](#dev-environment)
- [Lint & test](#lint--test)
- [Test layout — what each test asserts](#test-layout--what-each-test-asserts)
- [Version-compatibility matrix](#version-compatibility-matrix)
- [Re-verifying after an upgrade](#re-verifying-after-an-upgrade)
- [How the resume API was verified](#how-the-resume-api-was-verified)
- [Contributing](#contributing)

---

## Dev environment

The unit tests deliberately do **not** require a full Home Assistant install —
`tests/test_resume.py` installs minimal `homeassistant` shims and loads
`ecovacs_link` directly. You only need Python plus the test requirements:

```bash
pip install -r requirements_test.txt
# pytest, pytest-asyncio, deebot-client>=6.0.2, ruff
```

`deebot-client` is required because the tests build real `Clean`/`CleanV2`
command objects and assert on their serialized payloads.

---

## Lint & test

```bash
ruff check .       # lint (config: Ruff defaults; repo is ruff-clean)
python -m pytest   # asyncio_mode=auto, testpaths=tests (see pytest.ini)
```

Expected: `ruff` reports *All checks passed!* and pytest reports **6 passed**.

---

## Test layout — what each test asserts

All in [`tests/test_resume.py`](../tests/test_resume.py):

| Test | Asserts |
| --- | --- |
| `test_resume_dispatches_cleanv2_resume_for_goat` | A paused GOAT (`CleanV2`) dispatches a `CleanV2` whose `name == "clean_V2"` and `_args == {"act": "resume", "content": {}}` (and `_args["act"] == "resume"`). |
| `test_resume_uses_devices_own_command_class` | A device declaring `Clean` dispatches a `Clean` with `_args == {"act": "resume"}` — i.e. the device’s **own** command class is used, not a hardcoded one. |
| `test_resume_skips_when_not_paused` | A `DOCKED` device → `execute_command` is **not** awaited (the idempotent-safe guard). |
| `test_resume_proceeds_when_state_unknown` | No `StateEvent` (state `None`) → `execute_command` **is** awaited (library decides). |
| `test_resume_raises_when_device_missing` | An unknown `did` raises `HomeAssistantError`. |
| `test_list_goat_devices_only_returns_resumable` | Devices without `clean.action.command` are excluded from the picker; result is `{"goat": "Goatee"}`. |

The tests mock the deebot `Device` (`device.capabilities.clean.action.command`,
`device.events.get_last_event(StateEvent)`, `device.execute_command`) and a `hass`
whose `ecovacs` entry exposes `runtime_data.devices`.

---

## Version-compatibility matrix

| Component | Validated | Notes |
| --- | --- | --- |
| `deebot-client` | **6.0.2** | `CleanAction.RESUME == "resume"`; GOAT G1 `5xu9h3` → `CleanV2`; `Clean._execute` guards `RESUME`↔`START`. |
| Official `ecovacs` integration | ~2026 | `ConfigEntry.runtime_data` is an `EcovacsController` exposing `.devices` (list or callable). |
| Home Assistant core | ~2026 stable | Minimum declared: `homeassistant 2024.12.0` (`hacs.json`). |
| This integration | `1.0.0` | `manifest.json` version. |

Everything outside `ecovacs_link.py` is ordinary HA integration code; the fragile,
version-sensitive assumptions are confined to that module (see
[architecture → fragility caveat](architecture.md#fragility-caveat)).

---

## Re-verifying after an upgrade

After bumping Home Assistant, `ecovacs`, or `deebot-client`, re-run this recon and
update the matrix above and the docstrings if anything moved:

```bash
# 1. CleanAction.RESUME still exists and serializes to "resume"
python -c "from deebot_client.models import CleanAction; \
print([(a.name, a.value) for a in CleanAction])"
# expect: [('START','start'), ('PAUSE','pause'), ('RESUME','resume'), ('STOP','stop')]

# 2. The GOAT G1 model file still wires CleanV2
python -c "import deebot_client, os; \
p=os.path.join(os.path.dirname(deebot_client.__file__),'hardware','deebot','5xu9h3.py'); \
print(open(p).read().splitlines()[0]); \
print([l.strip() for l in open(p) if 'CleanV2' in l or 'CapabilityCleanAction' in l])"
# expect header 'DEEBOT GOAT G1 Capabilities' and action=CapabilityCleanAction(command=CleanV2)

# 3. The serialized payloads are unchanged
python -c "from deebot_client.commands.json.clean import Clean, CleanV2; \
from deebot_client.models import CleanAction; \
print('CleanV2', CleanV2(CleanAction.RESUME)._args); \
print('Clean', Clean(CleanAction.RESUME)._args)"
# expect: CleanV2 {'act': 'resume', 'content': {}}   Clean {'act': 'resume'}
```

Then re-run `ruff check .` and `python -m pytest`. For the `ecovacs` side, confirm
`entry.runtime_data` still exposes `.devices` (the access in
`ecovacs_link._iter_ecovacs_devices`); if the storage shape changed, that one
function is where to fix it.

---

## How the resume API was verified

Verified against the **actually installed** `deebot-client` **6.0.2**.

**`CleanAction` (`deebot_client/models.py`)** — `RESUME` exists:

```python
@unique
class CleanAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"   # the app's "Continue"
    STOP = "stop"
```

**The command class the GOAT uses** — `deebot_client/hardware/deebot/5xu9h3.py`
(header *“DEEBOT GOAT G1 Capabilities”*):

```python
from deebot_client.commands.json.clean import CleanV2, GetCleanInfoV2
...
action=CapabilityCleanAction(command=CleanV2),
```

**Serialized resume payload (GOAT):**

```python
CleanV2(CleanAction.RESUME)._args == {"act": "resume", "content": {}}
```

> **Note: differs from earlier notes.** Earlier drafts described the payload as
> `act: r`; the verified value is the full word **`act: resume`**. The source
> docstrings/comments were corrected accordingly. The single-letter `s/r/p/h`
> table belongs to the legacy Ecovacs XML protocol, not `deebot-client` 6.0.2.

---

## Contributing

- Keep all fragile, version-dependent access inside `ecovacs_link.py`.
- Don’t hardcode the command class — read it from
  `device.capabilities.clean.action.command`.
- Add or update a unit test for any behavioural change, and keep `ruff` clean.
- Update [`CHANGELOG.md`](../CHANGELOG.md) and the version matrix above when you
  validate against new versions.
- Localisation: keep `strings.json` and `translations/en.json` in sync, and update
  `translations/nb.json` (Norwegian Bokmål) where possible.

---

See also: [architecture](architecture.md) · [API reference](api-reference.md) ·
[how it works](how-it-works.md)
