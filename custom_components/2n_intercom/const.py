"""Constants for the 2N Intercom integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "2n_intercom"
MANUFACTURER = "2N"

# Fired on the Home Assistant event bus for every device event.
EVENT_TWO_N_EVENT = f"{DOMAIN}_event"

# Options
CONF_VERIFY_SSL = "verify_ssl"
CONF_LOCK_SWITCHES = "lock_switches"
CONF_RTSP_STREAM = "rtsp_stream"
DEFAULT_VERIFY_SSL = False

# RTSP paths the device serves when Services -> Streaming -> RTSP is on.
# "none" leaves the camera on the HTTP MJPEG stream.
RTSP_STREAM_NONE = "none"
RTSP_STREAMS = ("h264_stream", "h265_stream", "mjpeg_stream")
RTSP_PORT = 554
# The plain RTSP paths above refuse the ONVIF audio backchannel (551 Option
# not supported), so two-way audio needs the matching ONVIF media profile
# instead, served at /onvif/media. The device has no H.265 ONVIF profile.
ONVIF_MEDIA_PATH = "/onvif/media"
ONVIF_PROFILES = {
    "h264_stream": "profile_h264_hq",
    "mjpeg_stream": "profile_mjpeg",
}

# Fixed polling interval (seconds). Real-time state arrives via the event loop,
# so this is not user-configurable.
DEFAULT_SCAN_INTERVAL = 30
# How often to ask 2N's update server for new firmware (seconds).
FIRMWARE_SCAN_INTERVAL = 86400

# Attributes used in bus events and entity attributes.
ATTR_EVENT = "event"
ATTR_PARAMS = "params"
ATTR_DEVICE_NAME = "device_name"
ATTR_EVENT_ID = "event_id"
ATTR_UTC_TIME = "utc_time"
