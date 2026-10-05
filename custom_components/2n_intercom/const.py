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

# Fixed polling interval (seconds). Real-time state arrives via the event loop,
# so this is not user-configurable.
DEFAULT_SCAN_INTERVAL = 30

# Attributes used in bus events and entity attributes.
ATTR_EVENT = "event"
ATTR_PARAMS = "params"
ATTR_DEVICE_NAME = "device_name"
