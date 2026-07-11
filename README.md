# 2N Intercom for Home Assistant

A Home Assistant custom integration for [2N](https://www.2n.com) IP intercoms
(IP Verso, IP Style, IP Solo, IP Base, IP Force, IP Safety, IP Uni, IP Vario, …)
using the local [2N HTTP API (HAPI)](https://wiki.2n.com/hip/hapi/latest/en).

The integration is fully local: it polls device state over HTTP(S) and receives
real-time events (doorbell presses, card swipes, motion, call state, door
sensors, …) through the HAPI logging subscription, so state changes arrive
instantly.

## Features

Entities are created based on what your device actually supports — the
integration probes the device's capabilities and event catalog at setup.

| Platform | Entities |
| --- | --- |
| `lock` | A door lock per configured switch (unlock activates the switch; `open` pulses it) |
| `switch` | Each 2N switch, plus each logic output relay |
| `button` | Trigger per switch, device restart |
| `camera` | Snapshots plus the device's native MJPEG stream |
| `binary_sensor` | Motion, noise, tamper, door state, unauthorized door open, door open too long, switches blocked, call in progress, ringing, logic inputs, SIP registration |
| `sensor` | Call state, last restart, last card, last user, last key |
| `event` | Doorbell (quick dial buttons), keypad, access (card/code/fingerprint/mobile key), call state |

### Services

| Service | Description |
| --- | --- |
| `two_n_intercom.dial` | Start an outgoing call to a number or SIP URI |
| `two_n_intercom.answer` | Answer an incoming call |
| `two_n_intercom.hangup` | Hang up a call (optionally with reason) |
| `two_n_intercom.switch_command` | Advanced switch control: `on`/`off`/`trigger`/`lock`/`unlock`/`hold`/`release` |
| `two_n_intercom.audio_test` | Run the built-in speaker/microphone loop test |
| `two_n_intercom.display_text` | Show a text message on the device display |
| `two_n_intercom.automation_trigger` | Fire an `HttpTrigger` block in the device's Automation |

### Events

Every device event is also fired on the Home Assistant event bus as
`two_n_intercom_event`, so you can build automations on any of the
[HAPI event types](https://wiki.2n.com/hip/hapi/latest/en):

```yaml
triggers:
  - trigger: event
    event_type: two_n_intercom_event
    event_data:
      event: CardEntered
actions:
  - action: notify.mobile_app
    data:
      message: "Card {{ trigger.event.data.params.uid }} presented"
```

## Device setup

On the intercom's web interface:

1. **Services → HTTP API**: enable the services you want the integration to
   use (System, Switch, I/O, Camera, Phone/Call, Logging, and optionally
   Audio, Display, Automation). Leave the connection type and authentication
   method at their defaults (HTTPS + Digest) or use Basic — both work.
2. **Services → HTTP API → Account**: create an API account with a password
   and grant it the privileges for the services above (monitoring and control
   as desired). Keypad and UID monitoring privileges are needed for keypad /
   card events.

> **Firmware note**: since firmware 2.35 the HTTP API requires no license.
> On older firmware most endpoints need the Enhanced Integration (Gold)
> license.

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS (category
   *Integration*).
2. Install **2N Intercom** and restart Home Assistant.

### Manual

Copy `custom_components/two_n_intercom` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

1. **Settings → Devices & Services → Add Integration → 2N Intercom**.
2. Enter the device's IP address or hostname and the HTTP API account
   credentials.
3. Leave *Verify SSL certificate* off unless you have installed a proper
   certificate on the device (2N devices ship with a self-signed one).

### Options

- **Polling interval** — how often full state is polled (default 30 s).
  Real-time events arrive instantly regardless of this setting.
- **Switches shown as door locks** — which 2N switches get a lock entity
  (all enabled switches by default).

## Live video

The camera entity proxies the device's MJPEG stream and serves snapshots. For
low-latency H.264 video (e.g. in a doorbell card, with two-way audio via
go2rtc/WebRTC), enable **Services → Streaming → RTSP** on the device and add a
[Generic Camera](https://www.home-assistant.io/integrations/generic/) or
go2rtc stream pointing at `rtsp://<device-ip>/h264_stream`.

## Development

```bash
scripts/setup    # install dependencies (uv)
scripts/develop  # run a local Home Assistant with the integration loaded
scripts/lint     # ruff format + check
scripts/tests    # pytest
```

## Disclaimer

This project is not affiliated with or endorsed by 2N Telekomunikace a.s.
