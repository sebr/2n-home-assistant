"""Constants for the 2N Intercom integration."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "two_n_intercom"
MANUFACTURER = "2N"

# Fired on the Home Assistant event bus for every device event.
EVENT_TWO_N_EVENT = f"{DOMAIN}_event"

# Options
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_LOCK_SWITCHES = "lock_switches"
DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL = 30

# Attributes used in bus events and entity attributes.
ATTR_EVENT = "event"
ATTR_PARAMS = "params"
ATTR_DEVICE_NAME = "device_name"
