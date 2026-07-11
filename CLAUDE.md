# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow

- **Never commit to `main`.** All work goes on a feature branch and lands via a pull request.
- Create a branch, push it, and open a PR (`gh pr create`) for every change.

## Commands

Dependencies and tooling are managed with `uv`. Wrapper scripts live in `scripts/`.

```bash
scripts/setup    # apt deps (ffmpeg, libturbojpeg, libpcap) + uv sync
scripts/develop  # run a local Home Assistant with this integration loaded (config/)
scripts/lint     # uv run ruff format . && uv run ruff check . --fix
scripts/tests    # uv run pytest tests/ -v --tb=short
```

Run a single test:

```bash
uv run pytest tests/test_config_flow.py -v
uv run pytest tests/test_api.py::test_name -v
```

CI (`.github/workflows/`) runs ruff (format `--check` + lint, no autofix), pytest, and
Hassfest + HACS validation. Match these locally before opening a PR. Ruff is configured
in `.ruff.toml` with `select = ["ALL"]` — the linter is strict; keep it green rather than
adding blanket ignores.

## Architecture

A Home Assistant custom integration (`domain: two_n_intercom`) for 2N IP intercoms,
talking to the device's local [HTTP API (HAPI)](https://wiki.2n.com/hip/hapi/latest/en).
`iot_class` is `local_push`: state is polled, but real-time events arrive via a log
subscription. All integration code lives under `custom_components/two_n_intercom/`.

### Two layers

- **`hapi/`** — a self-contained, Home-Assistant-agnostic async client. `api.py`
  (`TwoNApiClient`) wraps every HAPI endpoint over `httpx`, auto-negotiating Basic vs
  Digest auth. `models.py` holds `from_dict` dataclasses for the device's JSON. `exceptions.py`
  maps the device's numeric error envelope to a typed hierarchy (`TwoNAuthError`,
  `TwoNPrivilegeError`, `TwoNNotSupportedError`, …). This layer knows nothing about `hass`.
- **The integration** — everything else, built on Home Assistant's config-entry +
  `DataUpdateCoordinator` pattern.

### Coordinator is the hub

`coordinator.py` (`TwoNUpdateCoordinator`) owns the API client and is the single source of
truth. Understanding it explains most of the codebase:

1. **Capability discovery** (`_async_setup`, runs once): probes each subsystem via
   `_probe()`, which swallows `TwoNNotSupportedError`/`TwoNPrivilegeError` and returns
   `None`. The resulting `has_switches`, `has_camera`, `supported_events`, `switch_caps`,
   etc. flags drive which entities each platform creates — **entities are conditional on what
   the specific device actually supports.**
2. **Polling** (`_async_update_data`): fetches per-subsystem status into a single
   `TwoNData` dataclass (`data.py`), keyed dicts of switches/ports/sessions/accounts.
3. **Real-time events**: on first successful poll it starts the API's background
   subscribe/pull loop (`hapi/api.py` `_event_loop`, long-polling `/api/log/pull`). Each
   event lands in `_handle_event`, which (a) records last-event-per-type in `event_states`,
   (b) folds state-bearing events into `TwoNData` via `_apply_event_to_data` (so entities
   update instantly without waiting for the next poll), (c) fires the `two_n_intercom_event`
   bus event for user automations, and (d) dispatches an internal signal
   (`signal_event(entry_id)`) that event-driven entities subscribe to.

### Platforms and entities

Each `Platform.*` in `__init__.py::PLATFORMS` has a module (`switch.py`, `lock.py`,
`sensor.py`, `binary_sensor.py`, `event.py`, `button.py`, `camera.py`). Their
`async_setup_entry` reads the coordinator's capability flags to decide what to create.
All entities subclass `TwoNEntity` (`entity.py`), which sets `has_entity_name`, a
`unique_id` of `{entry_id}_{key}`, and shared `DeviceInfo` — every entity attaches to one
device registered up front in `__init__.py::async_setup_entry` (so bus events can reference
its `device_id` before any entity exists).

`services.py` registers domain-level services (`dial`, `answer`, `hangup`,
`switch_command`, `audio_test`, `display_text`, `automation_trigger`) once in
`async_setup`, independent of config entries; schemas are in `services.yaml`. The config
entry's `runtime_data` holds the coordinator (`TwoNConfigEntry = ConfigEntry[TwoNUpdateCoordinator]`).

### Auth and re-auth

Auth failures on the background event loop can't raise into a coordinator update, so the
API exposes an auth-error callback; the coordinator's `_trigger_reauth` starts HA's re-auth
flow. Note the distinction the coordinator draws: `TwoNPrivilegeError` (privileges narrowed
after setup — credentials still valid) surfaces as `UpdateFailed`, while `TwoNAuthError`
raises `ConfigEntryAuthFailed`.

## Conventions

- Python ≥ 3.14; `from __future__ import annotations` everywhere, HA-imports guarded under
  `TYPE_CHECKING`.
- The device probes are deliberately fault-tolerant — a missing/disabled endpoint should
  degrade to "feature absent", never crash setup. Preserve this when adding endpoints.
- `config/` is a local Home Assistant runtime dir for `scripts/develop`; it's gitignored
  (only `configuration.yaml` is tracked) — don't commit its contents.

## Testing

`pytest-homeassistant-custom-component` provides HA fixtures; `respx` mocks httpx.
`tests/conftest.py` provides a fully-stubbed `mock_api` (a `MagicMock(spec=TwoNApiClient)`)
and `patch_api` to inject it into the coordinator — use these to test integration behaviour
without a real device.
